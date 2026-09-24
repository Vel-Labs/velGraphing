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
import time
from typing import Callable, Sequence

sys.dont_write_bytecode = True


_source_root = next(
    (
        _parent
        for _parent in Path(__file__).resolve().parents
        if (_parent / "packages" / "core").is_dir()
    ),
    None,
)
if _source_root is not None:
    sys.path.insert(0, str(_source_root))
else:
    _runtime_root = next(
        (
            _parent / "runtime"
            for _parent in Path(__file__).resolve().parents
            if (_parent / "runtime" / "core").is_dir()
        ),
        None,
    )
    if _runtime_root is not None:
        sys.path.insert(0, str(_runtime_root))

try:  # noqa: E402
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
        graph_find,
        plan_ranked_context,
        ranked_candidates_from_retrieval,
        retrieve,
        select_ranked_context,
    )
    from packages.core import jev
    from packages.core.retrieval import _STOPWORDS, _words
except ModuleNotFoundError:  # packaged plugin runtime
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
) -> tuple[bytes | None, str | None, tuple[int, int] | None]:
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
            return None, "non_regular", None
        inode = (metadata.st_dev, metadata.st_ino)
        if metadata.st_size > maximum:
            return None, "max_file_bytes", inode
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
    finally:
        os.close(descriptor)
    if len(data) > maximum:
        return None, "max_file_bytes", inode
    try:
        data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        return None, "invalid_utf8", inode
    return data, None, inode


class SnapshotReader:
    """Read-only reader over the exact bytes captured for one snapshot."""

    def __init__(self, root: Path, sources: dict[str, bytes], *,
                 read_observer: Callable[[str, bytes], None] | None = None) -> None:
        self.root = root
        self.sources = sources
        self.read_observer = read_observer
        self.operation_stage = "retrieval"

    def read_bytes(self, project_relative_path: str) -> bytes:
        raw = self.sources[project_relative_path]
        if self.read_observer is not None:
            self.read_observer(self.operation_stage, raw)
        return raw

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
    *,
    derive_edges: bool = True,
    source_observer: Callable[[str, bytes], None] | None = None,
    diagnostics: dict[str, object] | None = None,
) -> tuple[Graph, SourceSnapshotV4, SnapshotReader, dict[str, object]]:
    _repository_root(root)
    paths = _git(root, "ls-files", "-z", "--cached").split(b"\x00")
    sources: dict[str, bytes] = {}
    inodes: set[tuple[int, int]] = set()
    total = 0
    skipped: list[dict[str, str]] = []
    sensitive_paths_excluded = 0
    scan_started = time.perf_counter_ns()
    for encoded in sorted(item for item in paths if item):
        try:
            relative = _safe_relative(encoded.decode("utf-8", "strict"))
        except UnicodeDecodeError as error:
            raise InputError("Git path is not UTF-8") from error
        if _is_sensitive_path(relative):
            sensitive_paths_excluded += 1
            continue
        data, skip_reason, inode = _read_regular(root, relative, max_file_bytes)
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
        if diagnostics is not None:
            diagnostics.setdefault("source_operations", []).append({
                "access": "file_read", "stage": "scan",
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "byte_count": len(data),
            })
        total += len(data)
        sources[relative.as_posix()] = data
    if diagnostics is not None:
        diagnostics.setdefault("stage_ns", {})["scan"] = time.perf_counter_ns() - scan_started
    if not sources:
        raise InputError("repository has no usable Git-tracked UTF-8 files")
    def observe_read(stage: str, raw: bytes) -> None:
        if diagnostics is not None:
            diagnostics.setdefault("source_operations", []).append({
                "access": "memory_read", "stage": stage,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "byte_count": len(raw),
            })

    reader = SnapshotReader(
        root, sources, read_observer=observe_read if diagnostics is not None else None,
    )
    graph_started = time.perf_counter_ns()
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
    reader.operation_stage = "graph_build"
    relations = derive_source_relations(source_graph, snapshot, reader) if derive_edges else None
    reader.operation_stage = "retrieval"
    edges = relations.edges if relations is not None else ()
    final_graph = Graph(records, edges)
    if diagnostics is not None:
        diagnostics.setdefault("stage_ns", {})["graph_build"] = time.perf_counter_ns() - graph_started
    reason_counts: dict[str, int] = {}
    for item in skipped:
        reason = item["reason"]
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    if sensitive_paths_excluded:
        reason_counts["sensitive_paths_excluded"] = sensitive_paths_excluded
    scan_complete = not any(
        item["reason"] in {"max_file_bytes", "max_total_bytes"} for item in skipped
    ) and not sensitive_paths_excluded
    metadata = {
        "files_scanned": len(sources),
        "files_skipped": skipped,
        "skip_counts": dict(sorted(reason_counts.items())),
        "sensitive_paths_excluded": sensitive_paths_excluded,
        "scan_complete": scan_complete,
        "source_bytes": total,
        "max_file_bytes": max_file_bytes,
        "max_total_bytes": max_total_bytes,
        "edges_derived": len(edges),
        "relation_coverage": (
            [item.to_dict() for item in relations.coverage]
            if relations is not None
            else []
        ),
    }
    return final_graph, snapshot, reader, metadata


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
    context_byte_budget: int | None,
    jev_response: str | None,
    allow_network: bool,
    approved_request_sha256: str | None,
    diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    retrieval_started = time.perf_counter_ns()
    reader.operation_stage = "retrieval"
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
    if diagnostics is not None:
        diagnostics.setdefault("stage_ns", {})["retrieval"] = time.perf_counter_ns() - retrieval_started
    selection_started = time.perf_counter_ns()
    reader.operation_stage = "selection"
    try:
        public_task_facets = tuple(sorted({facet.value for facet in facets.facets}))
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
        selection_task = (
            replace(task, byte_budget=context_byte_budget)
            if context_byte_budget is not None else task
        )
        plan = plan_ranked_context(
            graph,
            selection_task,
            snapshot,
            reader,
            query=prompt,
            direct_candidates=direct_candidates,
            graph_candidates=graph_candidates,
            jev_enabled=mode != "plan",
            task_facets=public_task_facets,
        )
    except (TypeError, ValueError, jev.JevError) as error:
        return _ranked_fallback(mode, str(error))
    if diagnostics is not None:
        diagnostics.setdefault("stage_ns", {})["selection"] = time.perf_counter_ns() - selection_started

    result: dict[str, object] = {
        "jev_observation": None,
        "jev_preview": None,
        "mode": mode,
        "network_called": False,
        "plan": plan.to_dict(),
        "realized_route": plan.realized_route(direct_candidates, plan.baseline),
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
        selection_task,
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
        "realized_route": plan.realized_route(direct_candidates, selected),
        "reason": selected.reason,
        "selection": _ranked_selection(selected),
        "status": "fallback" if selected.projection.fail_closed else "selected",
    })
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="absolute canonical Git repository root")
    parser.add_argument("--prompt", required=True, help="non-empty repository navigation prompt")
    parser.add_argument("--semantic-candidate", action="append", default=[], help="optional known vocabulary candidate")
    parser.add_argument("--max-file-bytes", type=lambda value: _positive_bounded(value, "--max-file-bytes", HARD_MAX_FILE_BYTES), default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-bytes", type=lambda value: _positive_bounded(value, "--max-total-bytes", HARD_MAX_TOTAL_BYTES), default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--maximum-results", type=lambda value: _positive_bounded(value, "--maximum-results", 200), default=6)
    parser.add_argument("--byte-budget", type=lambda value: _positive_bounded(value, "--byte-budget", HARD_MAX_TOTAL_BYTES), default=32768)
    parser.add_argument("--context-byte-budget", type=lambda value: _positive_bounded(value, "--context-byte-budget", HARD_MAX_TOTAL_BYTES))
    parser.add_argument("--ranked-context", choices=("plan", "preview", "replay", "evaluate"))
    parser.add_argument("--jev-mode", choices=("shadow", "rerank"), default="rerank")
    parser.add_argument("--jev-model", default=jev.DEFAULT_MODEL)
    parser.add_argument("--jev-timeout", type=float, default=10.0)
    parser.add_argument("--jev-response")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--approve-request-sha256")
    parser.add_argument("--diagnostics", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if not arguments.prompt.strip():
        parser.error("--prompt must be non-empty")
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
        diagnostics: dict[str, object] = {"source_operations": [], "stage_ns": {}}
        graph, snapshot, reader, scan_metadata = _scan(
            root, arguments.max_file_bytes, arguments.max_total_bytes,
            diagnostics=diagnostics if arguments.diagnostics else None,
        )
        terms = tuple(sorted(set(token.casefold() for token in _TOKEN.findall(arguments.prompt))))
        task = TaskSpec(
            task_id="graph-find",
            query_terms=terms,
            node_budget=arguments.maximum_results,
            byte_budget=arguments.byte_budget,
            allowed_sensitivities=(Sensitivity.INTERNAL,),
        )
        graph_started = time.perf_counter_ns()
        reader.operation_stage = "retrieval"
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
        if arguments.diagnostics:
            diagnostics["stage_ns"]["graph_find"] = time.perf_counter_ns() - graph_started
        if scan_metadata["sensitive_paths_excluded"]:
            result = replace(result, route="defer", reason="sensitive_paths_excluded")
        elif not scan_metadata["scan_complete"]:
            result = replace(result, route="defer", reason="repository_scan_incomplete")
        payload = result.to_dict()
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
                    context_byte_budget=arguments.context_byte_budget,
                    jev_response=arguments.jev_response,
                    allow_network=arguments.allow_network,
                    approved_request_sha256=arguments.approve_request_sha256,
                    diagnostics=diagnostics if arguments.diagnostics else None,
                )
        if arguments.diagnostics:
            snapshot_sha256 = snapshot.snapshot_sha256
            plugin_root = next((parent for parent in Path(__file__).resolve().parents
                                if (parent / ".codex-plugin" / "release-manifest.json").is_file()), None)
            release = None
            adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            if plugin_root is not None:
                release = json.loads(
                    (plugin_root / ".codex-plugin" / "release-manifest.json").read_text(encoding="utf-8")
                )
            diagnostics["source_snapshot_sha256"] = snapshot_sha256
            diagnostics["runtime_identity"] = {
                "candidate_sha256": release.get("candidate_sha256") if release else None,
                "adapter_sha256": adapter_sha256,
            }
            payload["diagnostics"] = diagnostics
        json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    except (InputError, OSError, TypeError, ValueError, UnicodeError) as error:
        print(f"graph-find: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
