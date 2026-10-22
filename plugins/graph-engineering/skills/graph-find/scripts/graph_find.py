#!/usr/bin/env python3
"""Portable, read-only Git-tracked repository adapter for ``/graph-find``."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Callable, Sequence

sys.dont_write_bytecode = True


_plugin_root = Path(__file__).resolve().parents[3]
_candidate_source = _plugin_root.parent.parent
_source_root = (
    _candidate_source
    if _plugin_root == _candidate_source / "plugins/graph-engineering"
    and (_candidate_source / "packages/core").is_dir()
    else None
)
_runtime_root = _plugin_root / "runtime" if (_plugin_root / "runtime/core").is_dir() else None
if _source_root is not None:
    sys.path.insert(0, str(_source_root))
elif _runtime_root is not None:
    sys.path.insert(0, str(_runtime_root))

if _source_root is not None:  # noqa: E402
    from packages.core import (
        Admission,
        Freshness,
        Graph,
        GraphRecord,
        Provenance,
        Sensitivity,
        SourceIdentityV4,
        SourceSnapshotV4,
        TaskSpec,
        TrustClass,
        build_repository_tag_index,
        compile_prompt,
        compile_proof_obligations,
        derive_source_relations,
        assist,
        graph_find,
        plan_ranked_context,
        ranked_candidates_from_retrieval,
        retrieve,
        select_ranked_context,
    )
    from packages.core import jev
    from packages.core.retrieval import _STOPWORDS, _words
else:  # packaged plugin runtime must not import an editable source namespace
    if _runtime_root is None:
        raise ModuleNotFoundError("colocated graph core runtime is unavailable")
    from core import (  # type: ignore[no-redef]
        Admission,
        Freshness,
        Graph,
        GraphRecord,
        Provenance,
        Sensitivity,
        SourceIdentityV4,
        SourceSnapshotV4,
        TaskSpec,
        TrustClass,
        build_repository_tag_index,
        compile_prompt,
        compile_proof_obligations,
        derive_source_relations,
        assist,
        graph_find,
        plan_ranked_context,
        ranked_candidates_from_retrieval,
        retrieve,
        select_ranked_context,
    )
    from core import jev  # type: ignore[no-redef]
    from core.retrieval import _STOPWORDS, _words  # type: ignore[no-redef]


DEFAULT_MAX_FILE_BYTES = 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 16 * 1024 * 1024
HARD_MAX_FILE_BYTES = 16 * 1024 * 1024
HARD_MAX_TOTAL_BYTES = 128 * 1024 * 1024
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,63}")
_SENSITIVE_COMPONENTS = frozenset({"private", "secrets", "credentials"})
_SENSITIVE_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pfx"})
_PRIVATE_KEY_BASENAMES = frozenset(
    {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", "private-key", "private_key", "privatekey"}
)


class InputError(ValueError):
    """Raised for unsafe or unreadable adapter input."""


def _canonical_root(value: str) -> Path:
    if not os.path.isabs(value):
        raise InputError("--root must be an absolute path")
    if value != os.path.normpath(value):
        raise InputError("--root must not contain path aliases")
    root = Path(value)
    if not root.is_dir():
        raise InputError("--root must be a directory")
    if root.is_symlink():
        raise InputError("--root must not be a symlink alias")
    return root


def _safe_relative(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise InputError("Git path is not a normalized relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise InputError("Git path is not a normalized relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise InputError("Git path contains an alias or escape")
    return path


def _is_sensitive_path(relative: PurePosixPath) -> bool:
    parts = tuple(part.casefold() for part in relative.parts)
    basename = parts[-1]
    return (
        basename == ".env"
        or bool(set(parts) & _SENSITIVE_COMPONENTS)
        or any(basename.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)
        or basename in _PRIVATE_KEY_BASENAMES
    )


def _reject_symlink_components(root: Path, path: Path) -> None:
    relative = path.relative_to(root)
    if root.is_symlink():
        raise InputError("repository root must not be a symlink alias")
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise InputError(f"tracked path is a symlink: {relative.as_posix()}")


def _git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise InputError(f"cannot run git: {error}") from error
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise InputError(f"git {' '.join(arguments)} failed: {detail or result.returncode}")
    return result.stdout


def _repository_root(root: Path) -> None:
    reported = _git(root, "rev-parse", "--show-toplevel").decode("utf-8", "strict").strip()
    if Path(reported) != root.resolve(strict=True):
        raise InputError("--root must be the canonical Git repository root")


def _read_regular(
    root: Path, relative: PurePosixPath, maximum: int
) -> tuple[bytes | None, str | None, tuple[int, int] | None, int]:
    path = root.joinpath(*relative.parts)
    _reject_symlink_components(root, path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise InputError(f"cannot read tracked path {relative}: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, "non_regular", None, 0
        inode = (metadata.st_dev, metadata.st_ino)
        if metadata.st_size > maximum:
            return None, "max_file_bytes", inode, 0
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
    finally:
        os.close(descriptor)
    if len(data) > maximum:
        return None, "max_file_bytes", inode, len(data)
    try:
        data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        return None, "invalid_utf8", inode, len(data)
    return data, None, inode, len(data)


class SnapshotReader:
    """Read-only reader over the exact bytes captured for one snapshot."""

    def __init__(self, root: Path, sources: dict[str, bytes]) -> None:
        self.root = root
        self.sources = sources

    def read_bytes(self, project_relative_path: str) -> bytes:
        return self.sources[project_relative_path]

    def is_symlink(self, project_relative_path: str) -> bool:
        path = self.root.joinpath(*_safe_relative(project_relative_path).parts)
        current = self.root
        for part in path.relative_to(self.root).parts:
            current /= part
            if current.is_symlink():
                return True
        return False


def _scan(
    root: Path,
    max_file_bytes: int,
    max_total_bytes: int,
    excluded_path_prefixes: tuple[str, ...] = (),
    *,
    derive_edges: bool = True,
    source_observer: Callable[[str, bytes], None] | None = None,
) -> tuple[Graph, SourceSnapshotV4, SnapshotReader, dict[str, object]]:
    _repository_root(root)
    exclusions = tuple(
        sorted({_safe_relative(value) for value in excluded_path_prefixes})
    )
    paths = _git(root, "ls-files", "-z", "--cached").split(b"\x00")
    sources: dict[str, bytes] = {}
    inodes: set[tuple[int, int]] = set()
    total = 0
    total_read = 0
    path_scope_excluded = 0
    skipped: list[dict[str, str]] = []
    sensitive_paths_excluded = 0
    for encoded in sorted(item for item in paths if item):
        try:
            relative = _safe_relative(encoded.decode("utf-8", "strict"))
        except UnicodeDecodeError as error:
            raise InputError("Git path is not UTF-8") from error
        if _is_sensitive_path(relative):
            sensitive_paths_excluded += 1
            continue
        if any(relative == prefix or prefix in relative.parents for prefix in exclusions):
            path_scope_excluded += 1
            continue
        data, skip_reason, inode, bytes_read = _read_regular(root, relative, max_file_bytes)
        total_read += bytes_read
        if inode is not None and inode in inodes:
            raise InputError(f"tracked path aliases another file: {relative}")
        if inode is not None:
            inodes.add(inode)
        if skip_reason is not None:
            skipped.append({"path": relative.as_posix(), "reason": skip_reason})
            continue
        assert data is not None
        if total + len(data) > max_total_bytes:
            skipped.append({"path": relative.as_posix(), "reason": "max_total_bytes"})
            continue
        if source_observer is not None:
            source_observer(relative.as_posix(), data)
        total += len(data)
        sources[relative.as_posix()] = data
    if not sources:
        raise InputError("repository has no usable Git-tracked UTF-8 files")
    reader = SnapshotReader(root, sources)
    snapshot = SourceSnapshotV4(
        tuple(
            SourceIdentityV4(path, len(data), hashlib.sha256(data).hexdigest())
            for path, data in sorted(sources.items())
        )
    )
    records = tuple(
        GraphRecord(
            record_id=f"repo:{path}",
            kind="source",
            title=path,
            content=data.decode("utf-8"),
            provenance=Provenance(path, hashlib.sha256(data).hexdigest(), "git-tracked-bytes", True),
            trust=TrustClass.VERIFIED_SOURCE,
            sensitivity=Sensitivity.INTERNAL,
            freshness=Freshness.CURRENT,
            admission=Admission.VERIFIER,
            eligible=True,
        )
        for path, data in sorted(sources.items())
    )
    source_graph = Graph(records)
    relations = derive_source_relations(source_graph, snapshot, reader) if derive_edges else None
    edges = relations.edges if relations is not None else ()
    reason_counts: dict[str, int] = {}
    for item in skipped:
        reason = item["reason"]
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    if sensitive_paths_excluded:
        reason_counts["sensitive_paths_excluded"] = sensitive_paths_excluded
    scan_complete = not any(
        item["reason"] in {"max_file_bytes", "max_total_bytes"} for item in skipped
    ) and not sensitive_paths_excluded and not path_scope_excluded
    metadata = {
        "excluded_path_prefixes": [path.as_posix() for path in exclusions],
        "files_scanned": len(sources),
        "files_skipped": skipped,
        "path_scope_excluded": path_scope_excluded,
        "skip_counts": dict(sorted(reason_counts.items())),
        "sensitive_paths_excluded": sensitive_paths_excluded,
        "scan_complete": scan_complete,
        "source_bytes": total,
        "source_bytes_read": total_read,
        "max_file_bytes": max_file_bytes,
        "max_total_bytes": max_total_bytes,
        "edges_derived": len(edges),
        "relation_coverage": (
            [item.to_dict() for item in relations.coverage]
            if relations is not None
            else []
        ),
    }
    return Graph(records, edges), snapshot, reader, metadata


def _positive_bounded(value: str, label: str, ceiling: int) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{label} must be an integer") from error
    if not 1 <= number <= ceiling:
        raise argparse.ArgumentTypeError(f"{label} must be between 1 and {ceiling}")
    return number


def _load_jev_replay(path: str) -> object:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > jev.MAX_RESPONSE_BYTES:
                raise InputError("Jev replay must be a bounded regular file")
            raw = stream.read(jev.MAX_RESPONSE_BYTES + 1)
    except OSError as error:
        raise InputError("Jev replay is unavailable") from error
    if len(raw) > jev.MAX_RESPONSE_BYTES:
        raise InputError("Jev replay exceeds the response byte limit")
    try:
        return jev.decode(raw)
    except jev.JevError as error:
        raise InputError(f"Jev replay is invalid: {error}") from error


def _ranked_packet(query: str, candidates: tuple[object, ...]) -> dict[str, object]:
    return jev.validate_packet({
        "schema_version": jev.PACKET_VERSION,
        "query": query,
        "candidates": [
            {
                "id": candidate.candidate_id,
                "path": candidate.source_path,
                "source_sha256": candidate.source_sha256,
                "byte_start": candidate.byte_start,
                "byte_end": candidate.byte_end,
                "required": candidate.required,
            }
            for candidate in candidates
        ],
    })


def _ranked_selection(result: object) -> dict[str, object]:
    projection = result.projection
    return {
        "approved_request_sha256": result.approved_request_sha256,
        "candidate_set_sha256": result.candidate_set_sha256,
        "context": json.loads(projection.content) if projection.content else None,
        "excerpt_byte_count": projection.excerpt_byte_count,
        "fail_closed": projection.fail_closed,
        "jev_decision": result.jev_decision.to_dict(),
        "jev_source_revalidated": result.jev_source_revalidated,
        "order_source": result.order_source,
        "reason": result.reason,
        "route": result.route,
        "schema_version": "graph-find-ranked-context-selection-v1",
        "serialized_byte_count": projection.serialized_byte_count,
        "source_revalidated": result.source_revalidated,
    }


def _ranked_fallback(mode: str, reason: str) -> dict[str, object]:
    return {
        "jev_observation": None,
        "jev_preview": None,
        "mode": mode,
        "network_called": False,
        "plan": None,
        "reason": reason,
        "route": "defer",
        "schema_version": "graph-find-ranked-context-v1",
        "selection": None,
        "status": "fallback",
        "fail_closed": True,
    }


def _ranked_context(
    root: Path,
    graph: Graph,
    task: TaskSpec,
    prompt: str,
    snapshot: SourceSnapshotV4,
    reader: SnapshotReader,
    *,
    semantic_candidates: tuple[str, ...],
    maximum_results: int,
    mode: str,
    jev_mode: str,
    jev_model: str,
    jev_timeout: float,
    jev_response: str | None,
    allow_network: bool,
    approved_request_sha256: str | None,
) -> dict[str, object]:
    index = build_repository_tag_index(graph, snapshot, reader)
    facets = compile_prompt(prompt, index, semantic_candidates=semantic_candidates)

    def run(expand_one_hop: bool):
        return retrieve(
            graph,
            task,
            index,
            facets,
            snapshot,
            reader,
            expand_one_hop=expand_one_hop,
            source_bound_expansion=True,
            maximum_results=maximum_results,
        )

    direct = run(False)
    short_prompt = len([word for word in _words(prompt) if word not in _STOPWORDS]) < 3
    if direct.reason == "prompt_facets_insufficient" or short_prompt:
        obligations = compile_proof_obligations(prompt, graph, index, snapshot, reader)
        facets = compile_prompt(
            prompt,
            index,
            semantic_candidates=semantic_candidates,
            proof_obligations=obligations,
        )
        direct = run(False)
    graph_result = run(True)
    try:
        direct_candidates = ranked_candidates_from_retrieval(
            graph,
            task,
            snapshot,
            reader,
            direct,
            maximum_candidates=jev.MAX_CANDIDATES,
            maximum_candidate_bytes=jev.MAX_EXCERPTS_BYTES,
            maximum_unit_bytes=jev.MAX_EXCERPT_BYTES,
        )
        graph_candidates = ranked_candidates_from_retrieval(
            graph,
            task,
            snapshot,
            reader,
            graph_result,
            maximum_candidates=jev.MAX_CANDIDATES,
            maximum_candidate_bytes=jev.MAX_EXCERPTS_BYTES,
            maximum_unit_bytes=jev.MAX_EXCERPT_BYTES,
        )
        plan = plan_ranked_context(
            graph,
            task,
            snapshot,
            reader,
            query=prompt,
            direct_candidates=direct_candidates,
            graph_candidates=graph_candidates,
            jev_enabled=mode != "plan",
        )
    except (TypeError, ValueError, jev.JevError) as error:
        return _ranked_fallback(mode, str(error))

    result: dict[str, object] = {
        "jev_observation": None,
        "jev_preview": None,
        "mode": mode,
        "network_called": False,
        "plan": plan.to_dict(),
        "reason": plan.reason,
        "schema_version": "graph-find-ranked-context-v1",
        "selection": _ranked_selection(plan.baseline),
        "status": "fallback" if plan.baseline.projection.fail_closed else "selected",
    }
    if mode == "plan" or not plan.baseline.jev_decision.jev_call_could_affect_selection:
        return result

    packet = _ranked_packet(prompt, plan.candidates)
    if mode == "preview":
        try:
            result["jev_preview"] = jev.prepare(packet, root, jev_model)
        except jev.JevError as error:
            return _ranked_fallback(mode, str(error))
        return result

    observation = jev.evaluate(
        packet,
        root,
        mode=jev_mode,
        allow_network=allow_network,
        approved_request_sha256=approved_request_sha256,
        model=jev_model,
        timeout_s=jev_timeout,
        replay=_load_jev_replay(jev_response) if mode == "replay" and jev_response else None,
    )
    request_sha256 = observation.get("request_sha256")
    qualified = (
        observation.get("status") == "reranked"
        and observation.get("mode") == "rerank"
        and observation.get("source_revalidated") is True
        and observation.get("execution") in {"live", "replay"}
    )
    selected = select_ranked_context(
        graph,
        task,
        snapshot,
        reader,
        query=prompt,
        candidates=plan.candidates,
        approved_request_sha256=(
            request_sha256 if isinstance(request_sha256, str) else None
        ),
        jev_observation=observation,
        jev_enabled=True,
        jev_observation_qualified=qualified,
    )
    result.update({
        "jev_observation": observation,
        "network_called": observation.get("execution") == "live",
        "reason": selected.reason,
        "selection": _ranked_selection(selected),
        "status": "fallback" if selected.projection.fail_closed else "selected",
    })
    return result
_SOURCE_MENTION = re.compile(
    r"(?<![\w./\\:-])(?:\.?[\w-]+(?:\.[\w-]+)*/)*"
    r"(?:\.[\w-]+(?:\.[\w-]+)*|[\w-]+(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9_]{0,15})"
    r"(?![\w/\\-]|\.(?=\S))"
)
_SOURCE_URI = re.compile(
    r"(?<!\S)\S*://\S+|(?<![\w+./\\-])[A-Za-z][A-Za-z0-9+.-]*:\S+"
)


def _named_source_recovery(payload, prompt, sources, maximum_results):
    """Report explicit filename custody gaps; never infer semantic sufficiency.

    Resolve only inside the admitted snapshot. A hint neither admits a node
    nor authorizes a read. Complete follow-up content must match exact bytes.
    """
    # URI query/fragment text is not a local source reference. Keep the
    # original prompt for ranking and build intent; mask only name discovery.
    mentions = sorted(set(_SOURCE_MENTION.findall(_SOURCE_URI.sub(" ", prompt))))
    documents = (payload.get("follow_up", {}).get("payload") or {}).get("documents", [])
    targets, hints = [], []
    for mention in mentions[:16]:
        paths = sorted(path for path in sources if
                       (path == mention if "/" in mention else PurePosixPath(path).name == mention))
        target = {"mention": mention, "candidate_count": len(paths),
                  "candidate_paths": paths[:maximum_results]}
        if len(paths) != 1:
            target["status"] = "ambiguous" if paths else "not_admitted_or_not_found"
        else:
            path = paths[0]
            raw = sources[path]
            source_hash = hashlib.sha256(raw).hexdigest()
            complete = any(
                isinstance(doc, dict) and doc.get("source_path") == path and
                doc.get("source_sha256") == source_hash and
                type(doc.get("byte_count")) is int and doc["byte_count"] == len(raw) and
                isinstance(doc.get("content"), str) and doc["content"].encode("utf-8") == raw
                for doc in documents
            )
            target.update(source_sha256=source_hash,
                          status="complete_source_delivered" if complete else "complete_source_read_needed")
            if not complete:
                hints.append(path)
                target["next_build"] = {"op": "build", "intent": prompt, "scope": path, "limit": 1}
                target["next_read"] = "Select only the complete file node returned by successful build."
        targets.append(target)
    needed = len(mentions) > 16 or any(t["status"] != "complete_source_delivered" for t in targets)
    payload["named_source_recovery"] = {
        "needs_recovery": needed, "targets": targets,
        "omitted_mentions": max(0, len(mentions) - 16),
        "assessment": "explicit_file_mentions_only; semantic_completeness_not_assessed",
        "handoff": "new_request_local_JSONL_session; build_then_read_returned_file_with_identity_and_budget_checks",
    }
    if needed:
        # A recovery handoff carries the remaining content allowance forward.
        # Keep ranking pointers, but reserve source delivery for complete reads.
        payload["ranked_context_bytes_withheld"] = len(payload.get("context", "").encode("utf-8"))
        payload["context"] = ""
        payload["context_bytes"] = payload["delivered_context_bytes"] = 0
        budget = payload["delivery_budget"]
        delivered = budget["follow_up_source_bytes"]
        remaining = max(0, budget["limit_bytes"] - delivered)
        budget.update(graph_context_bytes=0, delivered_content_bytes=delivered,
                      remaining_bytes=remaining)
        payload.update(delivered_total_bytes=delivered, remaining_byte_budget=remaining)
        payload.setdefault("retrieval_route", payload["route"])
        payload.setdefault("retrieval_reason", payload["reason"])
        if payload["route"] == "graph":
            payload.update(route="defer", reason="named_source_recovery_required")
        payload["recommended_fallback_paths"] = sorted(set(payload.get("recommended_fallback_paths", [])) | set(hints))



def _follow_up_delivery(graph, task, snapshot, reader, paths, byte_budget):
    """Select complete sources from the same snapshot within one allowance."""
    follow_up_payload = None
    source_bytes = envelope_bytes = 0
    route, reason = "defer", "shared_delivery_budget_exhausted"
    if byte_budget:
        try:
            follow_up = assist(
                graph, replace(task, byte_budget=byte_budget), snapshot, reader,
                required_source_paths=paths, fallback_source_paths=paths,
                required_escalation=True,
            )
        except ValueError as error:
            if "context failure envelope exceeds byte budget" not in str(error):
                raise
        else:
            follow_up_payload = json.loads(follow_up.projection.content)
            source_bytes = sum(
                document.get("byte_count", 0)
                for document in follow_up_payload.get("documents", [])
                if isinstance(document, dict)
                and isinstance(document.get("byte_count", 0), int)
            )
            envelope_bytes = follow_up.projection.byte_count
            route, reason = follow_up.route, follow_up.reason
    return {
        "route": route, "reason": reason, "source_bytes": source_bytes,
        "envelope_bytes": envelope_bytes,
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "payload": follow_up_payload,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="absolute canonical Git repository root")
    parser.add_argument("--prompt", required=True, help="non-empty repository navigation prompt")
    parser.add_argument("--semantic-candidate", action="append", default=[], help="optional known vocabulary candidate")
    parser.add_argument("--max-file-bytes", type=lambda value: _positive_bounded(value, "--max-file-bytes", HARD_MAX_FILE_BYTES), default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-bytes", type=lambda value: _positive_bounded(value, "--max-total-bytes", HARD_MAX_TOTAL_BYTES), default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--maximum-results", type=lambda value: _positive_bounded(value, "--maximum-results", 200), default=6)
    parser.add_argument("--byte-budget", type=lambda value: _positive_bounded(value, "--byte-budget", HARD_MAX_TOTAL_BYTES), default=32768)
    parser.add_argument("--ranked-context", choices=("plan", "preview", "replay", "evaluate"))
    parser.add_argument("--jev-mode", choices=("shadow", "rerank"), default="rerank")
    parser.add_argument("--jev-model", default=jev.DEFAULT_MODEL)
    parser.add_argument("--jev-timeout", type=float, default=10.0)
    parser.add_argument("--jev-response")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--approve-request-sha256")
    parser.add_argument("--deliver", action="store_true", help="include source text selected by retrieval")
    parser.add_argument("--follow-up-path", action="append", default=[], help="read one explicit Git-tracked source path from the admitted snapshot")
    parser.add_argument("--exclude-path-prefix", action="append", default=[], help="exclude a Git path or directory subtree before source reads; repeat for multiple paths")
    arguments = parser.parse_args(argv)
    if not arguments.prompt.strip():
        parser.error("--prompt must be non-empty")
    if arguments.ranked_context is not None and (arguments.deliver or arguments.follow_up_path):
        parser.error("--ranked-context and source delivery are separate budgeted modes")
    if arguments.ranked_context == "replay" and not arguments.jev_response:
        parser.error("--ranked-context replay requires --jev-response")
    if arguments.ranked_context != "replay" and arguments.jev_response:
        parser.error("--jev-response requires --ranked-context replay")
    if arguments.ranked_context != "evaluate" and (
        arguments.allow_network or arguments.approve_request_sha256
    ):
        parser.error("network approval controls require --ranked-context evaluate")
    try:
        root = _canonical_root(arguments.root)
        graph, snapshot, reader, scan_metadata = _scan(
            root,
            arguments.max_file_bytes,
            arguments.max_total_bytes,
            tuple(arguments.exclude_path_prefix),
        )
        terms = tuple(sorted(set(token.casefold() for token in _TOKEN.findall(arguments.prompt))))
        task = TaskSpec(
            task_id="graph-find",
            query_terms=terms,
            node_budget=arguments.maximum_results,
            byte_budget=arguments.byte_budget,
            allowed_sensitivities=(Sensitivity.INTERNAL,),
        )
        result = graph_find(
            graph,
            task,
            arguments.prompt,
            snapshot,
            reader,
            semantic_candidates=tuple(arguments.semantic_candidate),
            expand_one_hop=True,
            source_bound_expansion=True,
            maximum_results=arguments.maximum_results,
        )
        retrieval_route = result.route
        retrieval_reason = result.reason
        scan_caveats: list[str] = []
        if scan_metadata["sensitive_paths_excluded"]:
            scan_caveats.append("sensitive_paths_excluded")
            result = replace(result, route="defer", reason="sensitive_paths_excluded")
        elif any(
            item["reason"] in {"max_file_bytes", "max_total_bytes"}
            for item in scan_metadata["files_skipped"]
        ):
            scan_caveats.append("repository_scan_incomplete")
            result = replace(result, route="defer", reason="repository_scan_incomplete")
        elif scan_metadata["path_scope_excluded"]:
            scan_caveats.append("source_scope_excluded")
            result = replace(result, route="defer", reason="source_scope_excluded")
        deliver = arguments.deliver or bool(arguments.follow_up_path)
        payload = result.to_delivery_dict() if deliver else result.to_dict()
        if scan_caveats:
            payload["retrieval_route"] = retrieval_route
            payload["retrieval_reason"] = retrieval_reason
            payload["scan_caveats"] = scan_caveats
        if deliver:
            payload["acquisition"] = {
                "source_bytes_read": scan_metadata["source_bytes_read"],
                "source_bytes_in_snapshot": scan_metadata["source_bytes"],
                "files_scanned": scan_metadata["files_scanned"],
                "meaning": "bytes read from non-sensitive tracked regular files; includes invalid UTF-8 and cap probes",
            }
            graph_context_bytes = len(result._context.encode("utf-8"))
            follow_up_source_bytes = 0
            follow_up_envelope_bytes = 0
            follow_up_charge_bytes = 0
            delivery_limit = arguments.byte_budget
        if arguments.follow_up_path:
            if len(arguments.follow_up_path) > arguments.maximum_results:
                parser.error("--follow-up-path count must not exceed --maximum-results")
            paths = tuple(sorted(set(arguments.follow_up_path)))
            remaining_delivery_budget = max(0, delivery_limit - graph_context_bytes)
            payload["follow_up"] = _follow_up_delivery(
                graph, task, snapshot, reader, paths, remaining_delivery_budget,
            )
            follow_up_source_bytes = payload["follow_up"]["source_bytes"]
            follow_up_envelope_bytes = payload["follow_up"]["envelope_bytes"]
            follow_up_charge_bytes = follow_up_source_bytes
        if deliver:
            delivered_total_bytes = graph_context_bytes + follow_up_charge_bytes
            remaining_delivery_budget = max(0, delivery_limit - delivered_total_bytes)
            payload["delivered_total_bytes"] = delivered_total_bytes
            payload["remaining_byte_budget"] = remaining_delivery_budget
            payload["delivery_budget"] = {
                "limit_bytes": delivery_limit,
                "graph_context_bytes": graph_context_bytes,
                "follow_up_source_bytes": follow_up_charge_bytes,
                "delivered_content_bytes": delivered_total_bytes,
                "remaining_bytes": remaining_delivery_budget,
                "meaning": (
                    "one shared UTF-8 content budget for graph context plus follow-up source text; "
                    "follow-up envelope bytes are separately measured and constrained to the remaining budget"
                ),
            }
            if follow_up_source_bytes:
                payload["follow_up"]["envelope_bytes"] = follow_up_envelope_bytes
        payload["scan"] = scan_metadata
        if arguments.ranked_context is not None:
            if not scan_metadata["scan_complete"]:
                payload["ranked_context"] = _ranked_fallback(
                    arguments.ranked_context,
                    "sensitive_paths_excluded"
                    if scan_metadata["sensitive_paths_excluded"]
                    else "repository_scan_incomplete",
                )
            else:
                payload["ranked_context"] = _ranked_context(
                    root,
                    graph,
                    task,
                    arguments.prompt,
                    snapshot,
                    reader,
                    semantic_candidates=tuple(arguments.semantic_candidate),
                    maximum_results=arguments.maximum_results,
                    mode=arguments.ranked_context,
                    jev_mode=arguments.jev_mode,
                    jev_model=arguments.jev_model,
                    jev_timeout=arguments.jev_timeout,
                    jev_response=arguments.jev_response,
                    allow_network=arguments.allow_network,
                    approved_request_sha256=arguments.approve_request_sha256,
                )
        if deliver:
            withheld_context_bytes = 0
            if arguments.follow_up_path and graph_context_bytes and not follow_up_source_bytes:
                # Probe only the public recovery decision. Nothing has been
                # emitted; clone the budget before the helper mutates it.
                probe = {**payload, "delivery_budget": dict(payload["delivery_budget"])}
                _named_source_recovery(probe, arguments.prompt, reader.sources, arguments.maximum_results)
                initial = payload["follow_up"]
                initial_payload_reason = (initial["payload"] or {}).get("reason")
                budget_refusal = (
                    initial["reason"] == "shared_delivery_budget_exhausted"
                    or initial_payload_reason in {
                        "fallback_context_exceeds_byte_budget", "required_context_exceeds_byte_budget",
                    }
                )
                if (probe["named_source_recovery"]["needs_recovery"] and budget_refusal
                        and all(path in reader.sources for path in paths)):
                    # One snapshot-only retry reallocates snippets already
                    # destined to be withheld. Successful no-gap context and
                    # unavailable/identity refusals keep their first result.
                    withheld_context_bytes = graph_context_bytes
                    payload["follow_up"] = _follow_up_delivery(
                        graph, task, snapshot, reader, paths, delivery_limit,
                    )
                    payload["follow_up"]["allocation"] = {
                        "attempts": 2,
                        "initial_budget_bytes": delivery_limit - graph_context_bytes,
                        "initial_reason": initial["reason"],
                        "initial_payload_reason": initial_payload_reason,
                        "withheld_graph_context_bytes": graph_context_bytes,
                        "final_budget_bytes": delivery_limit,
                    }
                    delivered = payload["follow_up"]["source_bytes"]
                    remaining = delivery_limit - delivered
                    payload.update(context="", context_bytes=0, delivered_context_bytes=0,
                                   delivered_total_bytes=delivered, remaining_byte_budget=remaining)
                    payload["delivery_budget"].update(
                        graph_context_bytes=0, follow_up_source_bytes=delivered,
                        delivered_content_bytes=delivered, remaining_bytes=remaining,
                    )
            _named_source_recovery(payload, arguments.prompt, reader.sources, arguments.maximum_results)
            if withheld_context_bytes:
                payload["ranked_context_bytes_withheld"] = withheld_context_bytes
        json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    except (InputError, OSError, TypeError, ValueError, UnicodeError) as error:
        print(f"graph-find: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
