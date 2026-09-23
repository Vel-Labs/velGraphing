"""Deterministic, source-bound candidate packets for time-to-correct v3."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    from .time_to_correct import MeasurementError, Trial, canonical, digest
    from .time_to_correct_jev import load_jev
except ImportError:
    from time_to_correct import MeasurementError, Trial, canonical, digest
    from time_to_correct_jev import load_jev


MAX_CANDIDATES = 6
MAX_SPAN_BYTES = 4096
EVIDENCE_BUDGET_BYTES = 16384
_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,63}")
_STOPWORDS = frozenset({
    "about", "after", "also", "and", "are", "before", "can", "could",
    "describe", "does", "each", "explain", "for", "from", "have", "how",
    "identify", "into", "its", "may", "must", "of", "on", "or", "our",
    "should", "that", "the", "their", "then", "these", "this", "through",
    "to", "what", "when", "where", "which", "with", "would", "you",
})
REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _jev() -> Any:
    return load_jev(REPO_ROOT)


def _path(value: Any, scope: set[str]) -> str:
    if type(value) is not str or value not in scope:
        raise MeasurementError("candidate_path_outside_scope")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise MeasurementError("candidate_path_invalid")
    return value


def _supported_path(path: str) -> bool:
    try:
        _jev()._path(path)
        return True
    except ValueError as error:
        if str(error) == "unsupported_source_type":
            return False
        raise MeasurementError("candidate_path_invalid") from None


def _read(trial: Trial, root: Path, path: str, operation: str) -> bytes:
    try:
        raw = _jev()._read_source(root, path)
    except (OSError, ValueError):
        raise MeasurementError("candidate_source_unavailable") from None
    trial.source(digest(raw), 0, len(raw), access="file_read",
                 operation_id=f"packet-{trial.current['attempt_id']}-{operation}")
    return raw


def _direct_span(raw: bytes, terms: Sequence[bytes]) -> tuple[int, int, int]:
    lines = raw.splitlines(keepends=True) or [raw]
    offsets = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    scores = [sum(line.lower().count(term) for term in terms) for line in lines]
    best = max(range(len(lines)), key=lambda index: (scores[index], -index))
    if len(lines[best]) > MAX_SPAN_BYTES:
        lowered = lines[best].lower()
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        match = min(positions) if positions else 0
        start = offsets[best] + max(0, match - MAX_SPAN_BYTES // 2)
        end = min(offsets[best] + len(lines[best]), start + MAX_SPAN_BYTES)
        while start < end:
            try:
                raw[start:end].decode("utf-8")
                break
            except UnicodeDecodeError as error:
                if error.start == 0:
                    start += 1
                else:
                    end -= 1
        return start, end, scores[best]
    left = right = best
    used = len(lines[best])
    while True:
        changed = False
        if left and used + len(lines[left - 1]) <= MAX_SPAN_BYTES:
            left -= 1
            used += len(lines[left])
            changed = True
        if right + 1 < len(lines) and used + len(lines[right + 1]) <= MAX_SPAN_BYTES:
            right += 1
            used += len(lines[right])
            changed = True
        if not changed:
            break
    start = offsets[left]
    end = offsets[right] + len(lines[right])
    return start, end, scores[best]


def _direct_pointers(trial: Trial, root: Path, question: str,
                     source_scope: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    terms = tuple(sorted({term.casefold().encode("ascii") for term in _TERM.findall(question)
                          if term.casefold() not in _STOPWORDS}))
    if not terms:
        raise MeasurementError("candidate_query_empty")
    scope = set(source_scope)
    documents: dict[str, bytes] = {}
    ranked = []
    with trial.phase("candidate_discovery"):
        for index, candidate_path in enumerate(sorted(scope)):
            path = _path(candidate_path, scope)
            if not _supported_path(path):
                continue
            raw = _read(trial, root, path, f"direct-scan-{index}")
            try:
                raw.decode("utf-8")
            except UnicodeError:
                continue
            documents[path] = raw
            start, end, content_score = _direct_span(raw, terms)
            path_score = sum(path.casefold().count(term.decode("ascii")) for term in terms)
            ranked.append((content_score + path_score, path, start, end))
        with trial.phase("retrieval"):
            ranked.sort(key=lambda row: (-row[0], row[1], row[2], row[3]))
            selected = [row for row in ranked if row[0] > 0][:MAX_CANDIDATES]
    if not selected:
        raise MeasurementError("candidate_selection_empty")
    return ([{"path": path, "source_sha256": digest(documents[path]),
              "byte_start": start, "byte_end": end, "required": False}
             for _, path, start, end in selected], documents)


def _graph_pointers(navigation: Mapping[str, Any], source_scope: Sequence[str]) -> list[dict[str, Any]]:
    scope = set(source_scope)
    if navigation.get("fail_closed") is True or navigation.get("route") != "graph":
        raise MeasurementError("graph_navigation_deferred")
    hits = navigation.get("hits")
    evidence = navigation.get("evidence")
    if type(hits) is not list or type(evidence) is not list:
        raise MeasurementError("graph_candidate_output_invalid")
    by_path: dict[str, list[Mapping[str, Any]]] = {}
    for item in evidence:
        if type(item) is dict and type(item.get("source_path")) is str:
            by_path.setdefault(item["source_path"], []).append(item)
    pointers = []
    for hit in hits:
        path = _path(hit.get("source_path") if type(hit) is dict else None, scope)
        if not _supported_path(path):
            continue
        choices = by_path.get(path, [])
        if not choices:
            continue
        item = choices[0]
        start, end = item.get("byte_start"), item.get("byte_end")
        if (type(start) is not int or type(end) is not int or start < 0
                or end <= start or end - start > MAX_SPAN_BYTES):
            raise MeasurementError("graph_candidate_span_invalid")
        pointers.append({
            "path": path, "source_sha256": item.get("source_sha256"),
            "excerpt_sha256": item.get("excerpt_sha256"),
            "byte_start": start, "byte_end": end, "required": False,
            "expand": True,
        })
        if len(pointers) == MAX_CANDIDATES:
            break
    if not pointers:
        raise MeasurementError("candidate_selection_empty")
    return pointers


def _expanded_span(raw: bytes, start: int, end: int) -> tuple[int, int]:
    if len(raw) <= MAX_SPAN_BYTES:
        return 0, len(raw)
    remaining = MAX_SPAN_BYTES - (end - start)
    left = max(0, start - remaining // 2)
    right = min(len(raw), end + (remaining - (start - left)))
    left = max(0, right - MAX_SPAN_BYTES)
    while left < right:
        try:
            raw[left:right].decode("utf-8")
            return left, right
        except UnicodeDecodeError as error:
            if error.start == 0:
                left += 1
            else:
                right -= 1
    raise MeasurementError("candidate_span_not_utf8")


def _capture(trial: Trial, root: Path, scope: set[str], pointers: Sequence[Mapping[str, Any]],
             cached: Mapping[str, bytes]) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    candidates = []
    documents = dict(cached)
    total = 0
    with trial.phase("source_capture"):
        for index, pointer in enumerate(pointers):
            path = _path(pointer.get("path"), scope)
            raw = documents.get(path)
            if raw is None:
                raw = _read(trial, root, path, f"capture-{index}")
                documents[path] = raw
            if pointer.get("source_sha256") != digest(raw):
                raise MeasurementError("candidate_source_digest_mismatch")
            start, end = pointer.get("byte_start"), pointer.get("byte_end")
            if (type(start) is not int or type(end) is not int or start < 0
                    or end <= start or end > len(raw) or end - start > MAX_SPAN_BYTES):
                raise MeasurementError("candidate_span_invalid")
            matched_excerpt = raw[start:end]
            if pointer.get("excerpt_sha256") not in {None, digest(matched_excerpt)}:
                raise MeasurementError("candidate_excerpt_digest_mismatch")
            if pointer.get("expand") is True:
                start, end = _expanded_span(raw, start, end)
            excerpt = raw[start:end]
            try:
                excerpt.decode("utf-8")
            except UnicodeError:
                raise MeasurementError("candidate_span_not_utf8") from None
            required = pointer.get("required") is True
            if total + len(excerpt) > EVIDENCE_BUDGET_BYTES:
                if required:
                    raise MeasurementError("required_evidence_budget_exceeded")
                continue
            candidates.append({
                "id": f"c{len(candidates)}", "path": path,
                "source_sha256": digest(raw), "byte_start": start,
                "byte_end": end, "required": required,
            })
            total += len(excerpt)
    if not candidates:
        raise MeasurementError("candidate_selection_empty")
    return candidates, documents


def build_candidate_packet(trial: Trial, root: Path, question: str,
                           source_scope: Sequence[str], *, route: str,
                           graph_navigation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build one exact packet. The same inputs produce the same A/B or C/D packet."""
    if type(question) is not str or not question.strip() or not source_scope:
        raise MeasurementError("candidate_input_invalid")
    if len(set(source_scope)) != len(source_scope):
        raise MeasurementError("candidate_scope_invalid")
    scope = set(source_scope)
    if route == "direct":
        pointers, documents = _direct_pointers(trial, root, question, source_scope)
        label = "direct_flat"
    elif route == "graph" and graph_navigation is not None:
        pointers, documents = _graph_pointers(graph_navigation, source_scope), {}
        label = "graph_find_tag_index"
    else:
        raise MeasurementError("candidate_route_invalid")
    candidates, _ = _capture(trial, root, scope, pointers, documents)
    packet = {"schema_version": "velgraphing-jev-candidates-v1",
              "query": question, "candidates": candidates}
    candidate_set_sha256 = _jev().sha256(_jev().canonical(candidates))
    baseline_order = [candidate["id"] for candidate in candidates]
    trial.bind(candidate_set_sha256=candidate_set_sha256)
    graph = trial.current.get("graph_observation", {})
    trial.current["candidate_observation"] = {
        "route": label,
        "candidate_packet_sha256": digest(canonical(packet)),
        "candidate_set_sha256": candidate_set_sha256,
        "baseline_order_sha256": digest(canonical(baseline_order)),
        "candidate_count": len(candidates),
        "evidence_bytes": sum(candidate["byte_end"] - candidate["byte_start"]
                              for candidate in candidates),
        "record_count": graph.get("record_count") if route == "graph" else None,
        "edge_count": graph.get("edge_count") if route == "graph" else None,
        "edge_expansion_status": "not_available" if route == "graph" else "not_applicable",
    }
    return packet


def compose_answer_payload(trial: Trial, root: Path, packet: Mapping[str, Any],
                           order: Sequence[str]) -> dict[str, Any]:
    candidates = packet.get("candidates")
    if type(candidates) is not list or type(order) not in {list, tuple}:
        raise MeasurementError("answer_evidence_invalid")
    by_id = {candidate.get("id"): candidate for candidate in candidates
             if type(candidate) is dict}
    if (len(by_id) != len(candidates) or not order
            or any(type(candidate_id) is not str for candidate_id in order)
            or len(set(order)) != len(order)
            or any(candidate_id not in by_id for candidate_id in order)):
        raise MeasurementError("answer_evidence_order_invalid")
    evidence = []
    total = 0
    with trial.phase("context_composition"):
        for index, candidate_id in enumerate(order):
            candidate = by_id[candidate_id]
            raw = _read(trial, root, candidate["path"], f"compose-{index}")
            if digest(raw) != candidate["source_sha256"]:
                raise MeasurementError("candidate_source_digest_mismatch")
            start, end = candidate["byte_start"], candidate["byte_end"]
            excerpt = raw[start:end]
            if len(excerpt) > MAX_SPAN_BYTES or total + len(excerpt) > EVIDENCE_BUDGET_BYTES:
                raise MeasurementError("answer_evidence_budget_exceeded")
            try:
                text = excerpt.decode("utf-8")
            except UnicodeError:
                raise MeasurementError("candidate_span_not_utf8") from None
            evidence.append({
                "id": candidate_id, "excerpt": text, "path": candidate["path"],
                "source_sha256": candidate["source_sha256"],
                "byte_start": start, "byte_end": end,
            })
            total += len(excerpt)
    return {
        "schema_version": "velgraphing-answer-evidence-v3",
        "question": packet["query"],
        "citation_instruction": "Cite supporting evidence IDs as [cN].",
        "evidence": evidence,
    }
