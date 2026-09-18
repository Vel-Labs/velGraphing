"""Observe the shipped graph-find path without changing production functions.

Benchmark-only isolated module copies retain the real scan, index, retrieval,
source checks and CLI serialization. No warm cache or graph edge is invented.
This observes graph discovery, NOT answer generation or a native agent session.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
from typing import Any, Sequence
import uuid

try:
    from .time_to_correct import MeasurementError, Trial, canonical, digest
except ImportError:
    from time_to_correct import MeasurementError, Trial, canonical, digest


def observe_graph_find(trial: Trial, repo: Path, argv: Sequence[str]) -> dict[str, Any]:
    """Run the exact graph-find CLI in-process and return its normal payload.

    Call trial.context on the actual serialized payload delivered to the model,
    not automatically here: a host may filter or never expose this return value.
    All source paths remain governed by the original CLI. Trace stores hashes.
    """
    modules = []
    def load(path: Path, name: str) -> Any:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise MeasurementError('graph_module_unavailable')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        modules.append(name)
        spec.loader.exec_module(module)
        return module
    old_path = sys.path[:]
    try:
        driver = load(repo/'plugins/graph-engineering/skills/graph-find/scripts/graph_find.py',
                      '_benchmark_graph_driver_' + uuid.uuid4().hex)
        # Real relative imports and shared Graph/source classes; isolated globals
        # let us wrap only this evaluation's functions, not production callers.
        core = load(repo/'packages/core/retrieval.py', 'packages.core._benchmark_retrieval_' + uuid.uuid4().hex)
        old_scan, old_read = driver._scan, driver._read_regular
        old_index, old_retrieve, old_compile = core.build_repository_tag_index, core.retrieve, core.compile_prompt
        count = 0
        def record(raw: bytes, access: str) -> None:
            nonlocal count
            count += 1
            trial.source(digest(raw), 0, len(raw), access=access,
                         operation_id=f'graph-{trial.current["attempt_id"]}-{count}')
        def read(*args: Any, **kwargs: Any) -> Any:
            result = old_read(*args, **kwargs)
            if result[0] is not None:
                record(result[0], 'file_read')
            return result
        def scan(*args: Any, **kwargs: Any) -> Any:
            with trial.phase('cold_graph_build'):
                graph, snapshot, reader, metadata = old_scan(*args, **kwargs)
            actual_snapshot = snapshot.snapshot_sha256
            if actual_snapshot != trial.identity['source_snapshot_sha256']:
                raise MeasurementError('graph_source_snapshot_mismatch')
            memory_read = reader.read_bytes
            def observed_memory(path: str) -> bytes:
                raw = memory_read(path)
                record(raw, 'memory_read')
                return raw
            reader.read_bytes = observed_memory
            trial.bind(graph_artifact_sha256=digest(canonical({
                'records': [r.to_dict() for r in graph.records],
                'edges': [e.to_dict() for e in graph.edges]})))
            trial.current['graph_observation'] = {
                'record_count': len(graph.records), 'edge_count': len(graph.edges),
                'files_scanned': metadata['files_scanned'], 'accepted_source_bytes': metadata['source_bytes'],
                'scan_complete': metadata['scan_complete'], 'graph_snapshot_sha256': snapshot.snapshot_sha256,
                'skipped_file_read_bytes': None if metadata['files_skipped'] else 0,
            }
            return graph, snapshot, reader, metadata
        def index(*args: Any, **kwargs: Any) -> Any:
            with trial.phase('cold_graph_build'):
                return old_index(*args, **kwargs)
        def retrieve(*args: Any, **kwargs: Any) -> Any:
            with trial.phase('retrieval'):
                return old_retrieve(*args, **kwargs)
        def compile_prompt(*args: Any, **kwargs: Any) -> Any:
            with trial.phase('candidate_discovery'):
                return old_compile(*args, **kwargs)
        driver._scan, driver._read_regular = scan, read
        core.build_repository_tag_index, core.retrieve, core.compile_prompt = index, retrieve, compile_prompt
        driver.graph_find = core.graph_find
        trial.not_applicable('warm_graph_load')
        output = io.StringIO()
        with redirect_stdout(output):
            returncode = driver.main(list(argv))
        if returncode != 0:
            raise MeasurementError('graph_cli_failed')
        payload = json.loads(output.getvalue())
        # Keep the complete delivered tool representation private; expose only
        # byte count/hash if and when the caller actually delivers it to a model.
        return payload
    finally:
        sys.path[:] = old_path
        for name in modules:
            sys.modules.pop(name, None)
