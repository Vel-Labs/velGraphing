#!/usr/bin/env python3
"""Generate oracle-blind v4 ranked candidates from frozen source lanes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
GRAPH_FIND_PATH = (
    ROOT / "plugins/graph-engineering/skills/graph-find/scripts/graph_find.py"
)
EVALUATOR_PATH = ROOT / "scripts/benchmarks/time_to_correct_retrieval_eval_v4.py"
SPEC = importlib.util.spec_from_file_location("ranked_candidates_graph_find", GRAPH_FIND_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load graph-find adapter")
graph_adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(graph_adapter)
EVALUATOR_SPEC = importlib.util.spec_from_file_location(
    "ranked_candidates_evaluator", EVALUATOR_PATH
)
if EVALUATOR_SPEC is None or EVALUATOR_SPEC.loader is None:
    raise RuntimeError("cannot load candidate evaluator")
candidate_evaluator = importlib.util.module_from_spec(EVALUATOR_SPEC)
EVALUATOR_SPEC.loader.exec_module(candidate_evaluator)

from packages.core import Graph, Sensitivity, TaskSpec, graph_find  # noqa: E402
from packages.core.retrieval import _GENERIC, _STOPWORDS, _line_window  # noqa: E402


SCHEMA_VERSION = "velgraphing-ranked-candidates-v4"
PRODUCTION_STUDY = "velgraphing-v4-six-task-production"
ROUTES = (
    "direct",
    "tag_index",
    "typed_graph",
    "typed_graph_no_edges",
    "typed_graph_no_expansion",
)
CORPUS_MANIFESTS = {
    "cpython": "cpython.json",
    "engineering-handbook": "engineering-handbook.json",
    "openchain-reference-material": "openchain.json",
    "thealgorithms-python": "thealgorithms-python.json",
}
SEED_LIMIT = 12
SHORTLIST_BYTE_BUDGET = 24_576
DIRECT_WINDOW_BYTES = 800
DIRECT_STOPWORDS = _STOPWORDS | _GENERIC
OUTPUT_ROOT = ROOT / "benchmarks/velgraphing-time-to-correct-v4/.inputs"


class GenerationError(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _snapshot_digest(sources: Sequence[Mapping[str, object]]) -> str:
    raw = json.dumps(
        {"sources": sources}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _digest(raw)


def _exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise GenerationError(f"invalid_{label}")
    return value


def _safe_path(value: object) -> str:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise GenerationError("invalid_source_path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise GenerationError("invalid_source_path")
    return value


def _git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments], check=False, capture_output=True
    )
    if result.returncode:
        raise GenerationError("git_command_failed")
    return result.stdout


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GenerationError("invalid_json_input") from error
    if type(value) is not dict:
        raise GenerationError("invalid_json_input")
    return value


def _manifest(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    _exact_keys(
        value,
        {
            "schema_version", "repository", "commit", "includes", "excludes",
            "sources", "source_count", "source_bytes", "snapshot_sha256", "skipped",
        },
        "manifest",
    )
    if (
        value["schema_version"] != "velgraphing-corpus-source-manifest-v1"
        or value["repository"] != "git-object-source"
        or type(value["commit"]) is not str
        or len(value["commit"]) != 40
        or type(value["sources"]) is not list or not value["sources"]
        or type(value["source_count"]) is not int
        or type(value["source_bytes"]) is not int
        or type(value["snapshot_sha256"]) is not str
        or type(value["skipped"]) is not dict
    ):
        raise GenerationError("invalid_manifest")
    seen: set[str] = set()
    total = 0
    for source in value["sources"]:
        _exact_keys(source, {"path", "byte_length", "sha256"}, "manifest_source")
        source_path = _safe_path(source["path"])
        if source_path in seen:
            raise GenerationError("duplicate_manifest_source")
        seen.add(source_path)
        if type(source["byte_length"]) is not int or source["byte_length"] < 0:
            raise GenerationError("invalid_manifest_source")
        if (
            type(source["sha256"]) is not str
            or len(source["sha256"]) != 64
            or set(source["sha256"]) - set("0123456789abcdef")
        ):
            raise GenerationError("invalid_manifest_source")
        total += source["byte_length"]
    if value["source_count"] != len(seen) or value["source_bytes"] != total:
        raise GenerationError("manifest_totals_mismatch")
    if _snapshot_digest(value["sources"]) != value["snapshot_sha256"]:
        raise GenerationError("manifest_snapshot_mismatch")
    return value


def _indexed_modes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in _git(root, "ls-files", "-s", "-z", "--cached").split(b"\x00"):
        if not entry:
            continue
        metadata, encoded_path = entry.split(b"\t", 1)
        mode = metadata.split()[0].decode("ascii")
        path = encoded_path.decode("utf-8", "strict")
        if mode not in {"100644", "100755"} or path in result:
            raise GenerationError("lane_contains_nonregular_or_duplicate_entry")
        result[_safe_path(path)] = mode
    return result


def scan_lane(
    lane: Path,
    manifest: Mapping[str, Any],
    *,
    derive_edges: bool,
) -> tuple[Any, Any, Any, dict[str, object]]:
    if not lane.is_absolute() or lane.resolve(strict=True) != lane or lane.is_symlink():
        raise GenerationError("lane_root_invalid")
    head = _git(lane, "rev-parse", "HEAD").decode("ascii").strip()
    if head != manifest["commit"]:
        raise GenerationError("lane_commit_mismatch")
    expected = {source["path"]: source for source in manifest["sources"]}
    if set(_indexed_modes(lane)) != set(expected):
        raise GenerationError("lane_path_set_mismatch")
    graph, snapshot, reader, metadata = graph_adapter._scan(
        lane,
        max(1, max(source["byte_length"] for source in manifest["sources"])),
        max(1, manifest["source_bytes"]),
        derive_edges=derive_edges,
    )
    if (
        not metadata["scan_complete"]
        or metadata["files_skipped"]
        or metadata["files_scanned"] != manifest["source_count"]
        or metadata["source_bytes"] != manifest["source_bytes"]
        or snapshot.snapshot_sha256 != manifest["snapshot_sha256"]
    ):
        raise GenerationError("lane_scan_mismatch")
    actual = {
        source.path: (source.byte_length, source.sha256) for source in snapshot.sources
    }
    expected_identity = {
        path: (source["byte_length"], source["sha256"])
        for path, source in expected.items()
    }
    if actual != expected_identity:
        raise GenerationError("lane_source_identity_mismatch")
    return graph, snapshot, reader, metadata


class CountingReader:
    def __init__(self, reader: Any) -> None:
        self.reader = reader
        self.operations = 0

    def read_bytes(self, project_relative_path: str) -> bytes:
        self.operations += 1
        return self.reader.read_bytes(project_relative_path)

    def is_symlink(self, project_relative_path: str) -> bool:
        return self.reader.is_symlink(project_relative_path)


def _candidate(
    path: str,
    source_sha256: str,
    byte_start: int,
    byte_end: int,
    sources: Mapping[str, bytes],
    *,
    required: bool = False,
) -> dict[str, object]:
    if path not in sources or _digest(sources[path]) != source_sha256:
        raise GenerationError("candidate_source_mismatch")
    raw = sources[path]
    if (
        type(byte_start) is not int
        or type(byte_end) is not int
        or not 0 <= byte_start < byte_end <= len(raw)
    ):
        raise GenerationError("candidate_range_invalid")
    try:
        excerpt = raw[byte_start:byte_end].decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise GenerationError("candidate_utf8_invalid") from error
    if excerpt.encode("utf-8") != raw[byte_start:byte_end]:
        raise GenerationError("candidate_utf8_invalid")
    identity = {
        "path": path,
        "source_sha256": source_sha256,
        "byte_start": byte_start,
        "byte_end": byte_end,
    }
    return {
        "id": f"candidate:{_digest(_canonical(identity))}",
        **identity,
        "required": required,
    }


def _retain(
    rows: Sequence[tuple[dict[str, object], str]],
) -> tuple[list[dict[str, object]], set[str]]:
    retained: list[dict[str, object]] = []
    record_ids: set[str] = set()
    seen: set[str] = set()
    used = 0
    for row, record_id in rows:
        if row["id"] in seen:
            continue
        size = int(row["byte_end"]) - int(row["byte_start"])
        if len(retained) == SEED_LIMIT:
            break
        if used + size > SHORTLIST_BYTE_BUDGET:
            continue
        retained.append(row)
        record_ids.add(record_id)
        seen.add(str(row["id"]))
        used += size
    return retained, record_ids


def _retain_with_supports(
    primary: Sequence[tuple[dict[str, object], str]],
    supports: Mapping[str, dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    retained: list[dict[str, object]] = []
    seen: set[str] = set()
    supported_seeds: set[str] = set()
    used = 0

    def append(row: dict[str, object]) -> bool:
        nonlocal used
        identity = str(row["id"])
        if identity in seen:
            return False
        size = int(row["byte_end"]) - int(row["byte_start"])
        if used + size > SHORTLIST_BYTE_BUDGET:
            return False
        retained.append(row)
        seen.add(identity)
        used += size
        return True

    support_count = 0
    for row, record_id in primary:
        if len(retained) == SEED_LIMIT:
            break
        primary_retained = append(row)
        if (
            primary_retained
            and record_id not in supported_seeds
            and record_id in supports
            and len(retained) < SEED_LIMIT
        ):
            supported_seeds.add(record_id)
            if append(supports[record_id]):
                support_count += 1
    return retained, support_count


def _metrics(source_operations: int, retrieval_ns: int) -> dict[str, int | None]:
    return {
        "source_operations": source_operations,
        "cold_ns": None,
        "warm_ns": None,
        "retrieval_ns": retrieval_ns,
        "expansion_ns": None,
        "fallback_ns": None,
        "source_failures": 0,
        "authority_failures": 0,
    }


def _controls(
    seed_record_ids: Sequence[str],
    derived_edge_count: int,
    active_edge_count: int,
    source_bound_expansion: bool,
    expand_one_hop: bool,
) -> dict[str, object]:
    return {
        "seed_record_ids": list(seed_record_ids),
        "seed_limit": SEED_LIMIT,
        "shortlist_byte_budget": SHORTLIST_BYTE_BUDGET,
        "derived_edge_count": derived_edge_count,
        "active_edge_count": active_edge_count,
        "source_bound_expansion": source_bound_expansion,
        "expand_one_hop": expand_one_hop,
    }


def _source_rows(snapshot: Any) -> list[dict[str, object]]:
    return [
        {
            "path": source.path,
            "source_sha256": source.sha256,
            "byte_length": source.byte_length,
        }
        for source in snapshot.sources
    ]


def _direct_run(
    task_id: str,
    prompt: str,
    graph: Graph,
    snapshot: Any,
    reader: Any,
) -> tuple[dict[str, object], int]:
    counting = CountingReader(reader)
    started = time.monotonic_ns()
    terms = tuple(
        dict.fromkeys(
            token.casefold()
            for token in graph_adapter._TOKEN.findall(prompt)
            if token.casefold() not in DIRECT_STOPWORDS
        )
    )
    scored: list[tuple[int, str, list[tuple[int, int]]]] = []
    for source in snapshot.sources:
        raw = counting.read_bytes(source.path)
        lowered = raw.lower()
        anchors: list[tuple[int, int]] = []
        score = 0
        for term in terms:
            encoded = term.encode("ascii")
            cursor = 0
            occurrences = 0
            while occurrences < 4:
                position = lowered.find(encoded, cursor)
                if position < 0:
                    break
                anchors.append((position, position + len(encoded)))
                score += 1
                occurrences += 1
                cursor = position + len(encoded)
            if term in source.path.casefold():
                score += 5
        if score:
            scored.append((score, source.path, sorted(set(anchors))))
    scored.sort(key=lambda item: (-item[0], item[1]))
    rows: list[tuple[dict[str, object], str]] = []
    seed_ids: list[str] = []
    sources = reader.sources
    source_hashes = {source.path: source.sha256 for source in snapshot.sources}
    for _, path, anchors in scored[:SEED_LIMIT]:
        record_id = f"repo:{path}"
        seed_ids.append(record_id)
        raw = sources[path]
        if not anchors and raw:
            anchors = [(0, min(len(raw), DIRECT_WINDOW_BYTES))]
        for start, end in anchors[:4]:
            window_start, window_end = _line_window(raw, start, end, DIRECT_WINDOW_BYTES)
            if window_end <= window_start:
                continue
            rows.append(
                (
                    _candidate(
                        path, source_hashes[path], window_start, window_end, sources
                    ),
                    record_id,
                )
            )
    candidates, _ = _retain(rows)
    elapsed = time.monotonic_ns() - started
    return (
        {
            "task_id": task_id,
            "route": "direct",
            "source_snapshot_sha256": snapshot.snapshot_sha256,
            "sources": _source_rows(snapshot),
            "candidates": candidates,
            "controls": _controls(seed_ids, 0, 0, False, False),
            "metrics": _metrics(counting.operations, elapsed),
        },
        0,
    )


def _graph_run(
    task_id: str,
    prompt: str,
    route: str,
    graph: Graph,
    snapshot: Any,
    reader: Any,
    *,
    derived_edge_count: int,
    active_edge_count: int,
    source_bound_expansion: bool,
    expand_one_hop: bool,
) -> tuple[dict[str, object], int]:
    counting = CountingReader(reader)
    task = TaskSpec(
        task_id=task_id,
        query_terms=tuple(
            dict.fromkeys(token.casefold() for token in graph_adapter._TOKEN.findall(prompt))
        ),
        node_budget=SEED_LIMIT,
        byte_budget=SHORTLIST_BYTE_BUDGET,
        allowed_sensitivities=(Sensitivity.INTERNAL,),
    )
    started = time.monotonic_ns()
    result = graph_find(
        graph,
        task,
        prompt,
        snapshot,
        counting,
        channels=("exact", "sparse", "wiki"),
        maximum_results=SEED_LIMIT,
        source_bound_expansion=source_bound_expansion,
        expand_one_hop=expand_one_hop,
    )
    elapsed = time.monotonic_ns() - started
    if result.fail_closed:
        raise GenerationError("retrieval_failed_closed")
    sources = reader.sources
    primary: list[tuple[dict[str, object], str]] = []
    for item in result.evidence:
        primary.append(
            (
                _candidate(
                    item.source_path,
                    item.source_sha256,
                    item.byte_start,
                    item.byte_end,
                    sources,
                ),
                item.record_id,
            )
        )
    support_rows: dict[str, dict[str, object]] = {}
    if route == "typed_graph":
        for support in result.relationship_supports:
            coordinate = support.target_coordinate
            support_rows[support.seed_record_id] = _candidate(
                coordinate.source_path,
                coordinate.source_sha256,
                coordinate.byte_start,
                coordinate.byte_end,
                sources,
            )
        candidates, support_count = _retain_with_supports(primary, support_rows)
    else:
        candidates, _ = _retain(primary)
        support_count = 0
    return (
        {
            "task_id": task_id,
            "route": route,
            "source_snapshot_sha256": snapshot.snapshot_sha256,
            "sources": _source_rows(snapshot),
            "candidates": candidates,
            "controls": _controls(
                [hit.record_id for hit in result.hits],
                derived_edge_count,
                active_edge_count,
                source_bound_expansion,
                expand_one_hop,
            ),
            "metrics": _metrics(counting.operations, elapsed),
        },
        support_count,
    )


def _questions(path: Path) -> tuple[list[dict[str, str]], str]:
    value = _load_json(path)
    _exact_keys(value, {"schema_version", "questions"}, "questions")
    if value["schema_version"] != "velgraphing-corpus-pilot-questions-v1":
        raise GenerationError("invalid_questions")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in value["questions"]:
        _exact_keys(row, {"id", "corpus", "prompt"}, "question")
        if any(type(row[key]) is not str or not row[key] for key in row):
            raise GenerationError("invalid_question")
        if row["corpus"] not in CORPUS_MANIFESTS:
            raise GenerationError("unknown_question_corpus")
        if row["id"] in seen:
            raise GenerationError("duplicate_question")
        seen.add(row["id"])
        rows.append(dict(row))
    return rows, _digest(_canonical(value))


def generate(
    questions_path: Path,
    manifests_root: Path,
    lanes_root: Path,
    selector_commit: str,
    *,
    study_id: str = PRODUCTION_STUDY,
) -> tuple[dict[str, object], dict[str, dict[str, int]]]:
    questions, question_registry_sha256 = _questions(questions_path)
    prepared: dict[str, tuple[Any, Any, Any, Any, int]] = {}
    for corpus in dict.fromkeys(row["corpus"] for row in questions):
        manifest = _manifest(manifests_root / CORPUS_MANIFESTS[corpus])
        lane = lanes_root / corpus
        plain_graph, plain_snapshot, plain_reader, _ = scan_lane(
            lane, manifest, derive_edges=False
        )
        typed_graph, typed_snapshot, typed_reader, _ = scan_lane(
            lane, manifest, derive_edges=True
        )
        if plain_snapshot != typed_snapshot or plain_graph.records != typed_graph.records:
            raise GenerationError("paired_scan_mismatch")
        prepared[corpus] = (
            plain_graph,
            plain_snapshot,
            plain_reader,
            typed_graph,
            len(typed_graph.edges),
        )

    runs: list[dict[str, object]] = []
    summary = {
        route: {"candidates": 0, "supports": 0, "derived_edges": 0,
                "active_edges": 0, "retrieval_ns": 0}
        for route in ROUTES
    }
    for question in questions:
        plain_graph, snapshot, reader, typed_graph, edge_count = prepared[question["corpus"]]
        no_edges = Graph(typed_graph.records)
        route_rows = [
            _direct_run(question["id"], question["prompt"], plain_graph, snapshot, reader),
            _graph_run(
                question["id"], question["prompt"], "tag_index", plain_graph,
                snapshot, reader, derived_edge_count=0,
                active_edge_count=0,
                source_bound_expansion=False, expand_one_hop=False,
            ),
            _graph_run(
                question["id"], question["prompt"], "typed_graph", typed_graph,
                snapshot, reader, derived_edge_count=edge_count,
                active_edge_count=edge_count,
                source_bound_expansion=True, expand_one_hop=True,
            ),
            _graph_run(
                question["id"], question["prompt"], "typed_graph_no_edges", no_edges,
                snapshot, reader, derived_edge_count=edge_count,
                active_edge_count=0,
                source_bound_expansion=True, expand_one_hop=True,
            ),
            _graph_run(
                question["id"], question["prompt"], "typed_graph_no_expansion", typed_graph,
                snapshot, reader, derived_edge_count=edge_count,
                active_edge_count=edge_count,
                source_bound_expansion=True, expand_one_hop=False,
            ),
        ]
        for run, support_count in route_rows:
            run["corpus"] = question["corpus"]
            run["prompt_sha256"] = _digest(question["prompt"].encode("utf-8"))
            runs.append(run)
            route_summary = summary[str(run["route"])]
            route_summary["candidates"] += len(run["candidates"])
            route_summary["supports"] += support_count
            route_summary["derived_edges"] += int(run["controls"]["derived_edge_count"])
            route_summary["active_edges"] += int(run["controls"]["active_edge_count"])
            route_summary["retrieval_ns"] += int(run["metrics"]["retrieval_ns"])
    artifact = {
            "schema_version": SCHEMA_VERSION,
            "study_id": study_id,
            "selector_commit": selector_commit,
            "question_registry_sha256": question_registry_sha256,
            "runs": runs,
        }
    candidate_evaluator.validate_candidates(artifact)
    return artifact, summary


def _clean_commit() -> str:
    if _git(ROOT, "status", "--porcelain=v1", "--untracked-files=all"):
        raise GenerationError("selector_checkout_not_clean")
    commit = _git(ROOT, "rev-parse", "HEAD").decode("ascii").strip()
    if len(commit) != 40:
        raise GenerationError("selector_commit_invalid")
    return commit


def _output_path(path: Path) -> Path:
    if any(part in {".", ".."} for part in path.parts):
        raise GenerationError("invalid_output_path")
    root = OUTPUT_ROOT.resolve(strict=True)
    if OUTPUT_ROOT.is_symlink() or not root.is_dir() or root != OUTPUT_ROOT:
        raise GenerationError("invalid_output_root")
    candidate = path if path.is_absolute() else Path.cwd() / path
    if candidate.parent != root or candidate.name in {"", ".", ".."}:
        raise GenerationError("invalid_output_path")
    if candidate.exists() or candidate.is_symlink():
        raise GenerationError("output_exists")
    ignored = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "--quiet", "--", str(candidate)],
        check=False,
    )
    if ignored.returncode:
        raise GenerationError("output_not_ignored")
    return candidate


def write_artifact(path: Path, artifact: Mapping[str, object]) -> tuple[str, int]:
    raw = _canonical(artifact)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise GenerationError("invalid_output_file")
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _digest(raw), len(raw)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--manifests-root", type=Path, required=True)
    parser.add_argument("--lanes-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        output = _output_path(arguments.output)
        commit = _clean_commit()
        artifact, summary = generate(
            arguments.questions,
            arguments.manifests_root,
            arguments.lanes_root,
            commit,
        )
        output_sha256, _ = write_artifact(output, artifact)
        if _git(ROOT, "status", "--porcelain=v1", "--untracked-files=all"):
            raise GenerationError("selector_checkout_changed")
        print(
            json.dumps(
                {
                    "output_sha256": output_sha256,
                    "runs": len(artifact["runs"]),
                    "selector_commit": commit,
                    "routes": summary,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except (GenerationError, OSError, UnicodeError, ValueError) as error:
        print(f"ranked-candidates-v4: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
