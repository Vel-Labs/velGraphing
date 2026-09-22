#!/usr/bin/env python3
"""Offline freeze and preflight validator for the successor four-arm study."""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from time_to_correct import (Budget, MeasurementError, Trial, canonical, digest,
                             load_completed_trials, save_completed_trial)
from time_to_correct_calibration import (LiveJevBudget, _v3_trial_measurement,
                                         bind_controller, controller_identity,
                                         finish_workers, handoff_argv,
                                         jev_answer_payload, replay_envelope,
                                         require_resumable, revalidate_lane,
                                         start_fixture_worker, verify_lane)
from time_to_correct_handoff import (HandoffError, atomic_write, read_canonical,
                                     run_root as validate_run_root)
from time_to_correct_host import (ANSWER_RESPONSE_CONTRACT, GRADER_RESPONSE_CONTRACT,
                                  SUCCESSOR_GRADER_RESPONSE_CONTRACT,
                                  run_process_trial)
from time_to_correct_jev import evaluate_live, evaluate_offline
from time_to_correct_packet import compose_answer_payload
from packages.core import (
    Graph, RankedContextCandidate,
    Sensitivity,
    TaskSpec,
    build_repository_tag_index,
    compile_prompt,
    compile_proof_obligations,
    ranked_candidates_from_retrieval,
    retrieve,
    select_ranked_context,
)
from packages.core import jev


DEFAULT_ROOT = ROOT / "benchmarks/velgraphing-four-arm-study-v1"
SUCCESSOR_RUBRICS = "successor-rubrics.json"
SUCCESSOR_TTC_CONTRACT = "successor-ttc-contract.json"
SUCCESSOR_FREEZE = "successor-freeze.json"
SUCCESSOR_PREFLIGHT = "successor-preflight.json"
SUCCESSOR_FREEZE_SCHEMA = "velgraphing-four-arm-successor-freeze-v1"
SUCCESSOR_PREFLIGHT_SCHEMA = "velgraphing-four-arm-successor-preflight-v1"
SUCCESSOR_WITNESS_CUSTODY = (
    ".velgraphing-local/velgraphing-four-arm-study-v1/"
    "successor-ttc-witness-custody.json"
)
COLLABORATION_TASK_NAME_RE = re.compile(r"[a-z0-9_]+\Z")
THREAD_ID_SEMANTICS = "canonical_collaboration_task_name_not_opaque_host_id"
LOCAL_POOL_ARTIFACT = ".velgraphing-local/velgraphing-four-arm-study-v1/phase-2-pools.json"
PROVIDER_BUDGET_AUTHORITY = {
    "currency": "USD",
    "total_authorized_usd": "1.0000",
    "operator_reported_spend_to_date_usd": "0.0969",
    "operator_reported_calls_to_date": 108,
    "operator_reported_tokens_to_date": 2_371_440,
    "remaining_authorized_usd": "0.9031",
    "max_additional_spend_usd": "0.9031",
    "source": "operator_provided_typesafe_account_truth",
    "provider_verified": False,
    "historical_reservation_reconciliation": {
        "amount_usd": "0.359789241",
        "basis": "historical_request_byte_based_total_reservation",
        "status": "retired_historical_only",
        "counts_as_spend": False,
        "charged": False,
        "subtract_again_from_remaining_budget": False,
        "attributable_to_operator_reported_account_level_spend": False,
    },
}
MAX_ADDITIONAL_PROVIDER_SPEND_USD = Decimal(
    PROVIDER_BUDGET_AUTHORITY["max_additional_spend_usd"]
)
HISTORICAL_CONTROLLER_SHA256 = "79f42fbeee18c45731ec963102e31480bd4669f9f89cb1cedaccbbbcb2e8a21a"
HISTORICAL_HOST_SHA256 = "4e89e9283870ca164a9a82fb93d65b60c9027b76d85ef5e99670d278e1fa1393"
HISTORICAL_HANDOFF_SHA256 = "b993fb11ff2c405ee5154fab85c578818e179df5afcae83ccb0490a636359085"
SUCCESSOR_ARM_LABELS = {
    "A": "edge-disabled frozen-shortlist baseline; Jev off",
    "B": "edge-disabled frozen-shortlist baseline; Jev on",
    "C": "relationship-enabled frozen-shortlist arm; Jev off",
    "D": "relationship-enabled frozen-shortlist arm; Jev on",
}
GRAPH_FIND_PATH = ROOT / "plugins/graph-engineering/skills/graph-find/scripts/graph_find.py"
GRAPH_FIND_SPEC = importlib.util.spec_from_file_location("four_arm_graph_find", GRAPH_FIND_PATH)
if GRAPH_FIND_SPEC is None or GRAPH_FIND_SPEC.loader is None:
    raise RuntimeError("cannot load graph-find adapter")
graph_find_adapter = importlib.util.module_from_spec(GRAPH_FIND_SPEC)
GRAPH_FIND_SPEC.loader.exec_module(graph_find_adapter)
TASKS = ("S-01", "D-01", "L-01", "M-02")
TASK_CORPORA = {
    "S-01": "thealgorithms-python",
    "D-01": "thealgorithms-python",
    "L-01": "engineering-handbook",
    "M-02": "openchain-reference-material",
}
ARMS = {
    "A": {"jev": "off", "route": "direct"},
    "B": {"jev": "on", "route": "direct"},
    "C": {"jev": "off", "route": "graph"},
    "D": {"jev": "on", "route": "graph"},
}
DISPATCH = (
    "A-S-01", "B-S-01", "C-S-01", "D-S-01",
    "B-D-01", "C-D-01", "D-D-01", "A-D-01",
    "C-L-01", "D-L-01", "A-L-01", "B-L-01",
    "D-M-02", "A-M-02", "B-M-02", "C-M-02",
)
TIME_METRICS = {
    "user_visible_wall", "user_visible_wall_excluding_operator_approval",
    "discovery", "graph_build", "graph_load", "source_capture", "provider",
    "selection_and_context_composition", "answer", "grading",
    "fallback_and_repair", "operator_approval",
}
USAGE_METRICS = {
    "answer_input_tokens", "answer_output_tokens", "answer_cached_input_tokens",
    "grader_input_tokens", "grader_output_tokens", "grader_cached_input_tokens",
    "provider_input_tokens", "provider_output_tokens", "provider_cached_input_tokens",
    "provider_cost_usd", "request_bytes", "context_bytes",
}
SHA256 = set("0123456789abcdef")
RETRIEVAL_NODE_LIMIT = 12
CANDIDATE_LIMIT = 64
CANDIDATE_AGGREGATE_BYTE_BUDGET = 32_768
CANDIDATE_UNIT_BYTE_BUDGET = 4096
FINAL_CONTEXT_BYTE_BUDGET = 16_384
LOCAL_ARTIFACT_SCHEMA = "velgraphing-four-arm-pools-local-v1"
PREFLIGHT_SCHEMA = "velgraphing-four-arm-preflight-v2"
PREPARE_ARGV_TEMPLATE = [
    "/usr/bin/env", "python3", "-B", "scripts/benchmarks/four_arm_study_v1.py",
    "prepare", "--root", "benchmarks/velgraphing-four-arm-study-v1",
    "--lanes-root", "<ABSOLUTE_FROZEN_LANES_ROOT>",
    "--local-output", "<ABSOLUTE_IGNORED_POOL_ARTIFACT>",
    "--preflight-output", "benchmarks/velgraphing-four-arm-study-v1/preflight.json",
]
EXECUTION_ARGV_TEMPLATE = [
    "<ABSOLUTE_PYTHON_EXECUTABLE>", "-B", "scripts/benchmarks/four_arm_study_v1.py",
    "run", "--root", "benchmarks/velgraphing-four-arm-study-v1",
    "--pool-artifact", "<ABSOLUTE_IGNORED_POOL_ARTIFACT>",
    "--lane-root", "<ABSOLUTE_FROZEN_LANES_ROOT>", "--run-root", "<ABSOLUTE_RUN_ROOT>",
    "--lane-manifest", "<ABSOLUTE_RUN_ROOT>/lane-manifest.json",
    "--approved-lane-manifest-sha256", "<APPROVED_LANE_MANIFEST_SHA256>",
    "--approved-python-executable", "<ABSOLUTE_PYTHON_EXECUTABLE>",
]
FREEZE_KEYS = {
    "arms", "artifacts", "candidate_pool_contract", "controller", "corpora",
    "dispatch_order", "execution_gates", "implementation_bindings", "jev",
    "lane_boundary", "lane_identity_contract", "product", "prompt_bindings",
    "public_source_only", "schema_version", "status", "study_id", "tasks",
    "telemetry_schema", "terms_boundary",
}
IMPLEMENTATION_PATHS = {
    "corpus_materializer": "scripts/benchmarks/velgraphing_corpus_pilot_v1.py",
    "handoff": "scripts/benchmarks/time_to_correct_handoff.py",
    "host": "scripts/benchmarks/time_to_correct_host.py",
    "jev": "packages/core/jev.py",
    "retrieval": "packages/core/retrieval.py",
    "selection": "packages/core/selection.py",
    "graph_find_adapter": "plugins/graph-engineering/skills/graph-find/scripts/graph_find.py",
}
CORPUS_MANIFESTS = {
    "engineering-handbook": "benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/engineering-handbook.json",
    "openchain-reference-material": "benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/openchain.json",
    "thealgorithms-python": "benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/thealgorithms-python.json",
}
LOCAL_POOL_SHA256 = "3721b7378848d024e073cfa67bce44249b62551835ce236c22837119fee16d7b"
REQUEST_BYTE_SET_SHA256 = "80b3411f0d30600bc302a59debe36fe66734e4aceca0da6afdae303dc096af94"
JEV_RATE = Decimal("0.042")
INCREMENTAL_RESERVATION = Decimal("0.03184146")
HISTORICAL_RESERVATION = Decimal("0.327947781")
TOTAL_RESERVATION = Decimal("0.359789241")
REMAINING_BUDGET = Decimal("0.640210759")


class StudyError(ValueError):
    pass


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _is_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and not (set(value) - SHA256)


def _read_json(path: Path, reason: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise StudyError(reason) from None
    if type(value) is not dict:
        raise StudyError(reason)
    return raw, value


def _is_ancestor(repo_root: Path, commit: object) -> bool:
    if type(commit) is not str or len(commit) != 40 or set(commit) - SHA256:
        return False
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=repo_root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return completed.returncode == 0


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments], check=False, capture_output=True,
    )
    if completed.returncode:
        raise StudyError("lane_git_invalid")
    return completed.stdout


def _bound_blob_sha256(
    repo_root: Path, commit: str, path: str, reason: str,
) -> str:
    try:
        return digest(_git(repo_root, "show", f"{commit}:{path}"))
    except StudyError:
        raise StudyError(reason) from None


def _safe_path(value: object) -> str:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise StudyError("source_manifest_invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute() or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise StudyError("source_manifest_invalid")
    return value


def _is_collaboration_task_name(value: object) -> bool:
    """Validate the handoff's legacy thread_id field as a canonical task_name."""
    return (
        type(value) is str
        and COLLABORATION_TASK_NAME_RE.fullmatch(value) is not None
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    _, value = _read_json(path, "source_manifest_invalid")
    if set(value) != {
        "schema_version", "repository", "commit", "includes", "excludes",
        "sources", "source_count", "source_bytes", "snapshot_sha256", "skipped",
    } or value.get("schema_version") != "velgraphing-corpus-source-manifest-v1":
        raise StudyError("source_manifest_invalid")
    sources = value.get("sources")
    if type(sources) is not list or not sources:
        raise StudyError("source_manifest_invalid")
    paths: list[str] = []
    total = 0
    for source in sources:
        if type(source) is not dict or set(source) != {"path", "byte_length", "sha256"}:
            raise StudyError("source_manifest_invalid")
        paths.append(_safe_path(source["path"]))
        if type(source["byte_length"]) is not int or source["byte_length"] < 0:
            raise StudyError("source_manifest_invalid")
        if not _is_sha256(source["sha256"]):
            raise StudyError("source_manifest_invalid")
        total += source["byte_length"]
    if (
        paths != sorted(paths) or len(paths) != len(set(paths))
        or value.get("source_count") != len(paths)
        or value.get("source_bytes") != total
        or value.get("snapshot_sha256") != _sha256({"sources": sources})
    ):
        raise StudyError("source_manifest_invalid")
    return value


def _indexed_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for entry in _git(root, "ls-files", "-s", "-z", "--cached").split(b"\x00"):
        if not entry:
            continue
        metadata, encoded_path = entry.split(b"\t", 1)
        mode = metadata.split()[0].decode("ascii")
        path = _safe_path(encoded_path.decode("utf-8", "strict"))
        if mode not in {"100644", "100755"} or path in paths:
            raise StudyError("lane_index_invalid")
        paths.add(path)
    return paths


def _scan_lane(
    lane: Path, manifest: Mapping[str, Any], *, derive_edges: bool,
    source_observer: Any = None,
) -> tuple[Any, Any, Any, dict[str, object]]:
    if (
        not lane.is_absolute() or not lane.is_dir() or lane.is_symlink()
        or lane.resolve(strict=True) != lane
        or _git(lane, "rev-parse", "HEAD").decode("ascii").strip()
        != manifest["commit"]
    ):
        raise StudyError("lane_identity_invalid")
    expected_paths = {source["path"] for source in manifest["sources"]}
    if _indexed_paths(lane) != expected_paths:
        raise StudyError("lane_index_invalid")
    graph, snapshot, reader, metadata = graph_find_adapter._scan(
        lane,
        max(1, max(source["byte_length"] for source in manifest["sources"])),
        max(1, manifest["source_bytes"]),
        derive_edges=derive_edges,
        source_observer=source_observer,
    )
    actual = {
        source.path: (source.byte_length, source.sha256) for source in snapshot.sources
    }
    expected = {
        source["path"]: (source["byte_length"], source["sha256"])
        for source in manifest["sources"]
    }
    if (
        metadata.get("scan_complete") is not True
        or metadata.get("files_skipped")
        or metadata.get("files_scanned") != manifest["source_count"]
        or metadata.get("source_bytes") != manifest["source_bytes"]
        or snapshot.snapshot_sha256 != manifest["snapshot_sha256"]
        or actual != expected
    ):
        raise StudyError("lane_scan_invalid")
    return graph, snapshot, reader, metadata


def _candidate_row(candidate: Any) -> dict[str, object]:
    sensitivity = candidate.relationship_sensitivity
    return {
        "candidate_id": candidate.candidate_id,
        "source_path": candidate.source_path,
        "source_sha256": candidate.source_sha256,
        "byte_start": candidate.byte_start,
        "byte_end": candidate.byte_end,
        "required": candidate.required,
        "record_id": candidate.record_id,
        "relationship_parent_candidate_id": candidate.relationship_parent_candidate_id,
        "relationship_edge_id": candidate.relationship_edge_id,
        "relationship_direction": candidate.relationship_direction,
        "relationship_relation": candidate.relationship_relation,
        "relationship_sensitivity": (
            sensitivity.value if sensitivity is not None else None
        ),
    }


def _packet(prompt: str, candidates: Sequence[Any]) -> dict[str, Any]:
    return jev.validate_packet({
        "schema_version": jev.PACKET_VERSION,
        "query": prompt,
        "candidates": [candidate._packet_value() for candidate in candidates],
    })


def _install_graph_find(run_root: Path) -> tuple[Path, str, str]:
    """Materialize the manifest-bound plugin once, outside the measured trial."""
    plugin_root = ROOT / "plugins/graph-engineering"
    manifest_path = plugin_root / ".codex-plugin/release-manifest.json"
    _, release = _read_json(manifest_path, "installed_adapter_invalid")
    candidate_sha256 = release.get("candidate_sha256")
    rows = release.get("files")
    if not _is_sha256(candidate_sha256) or type(rows) is not list:
        raise StudyError("installed_adapter_invalid")
    expected_paths = {".codex-plugin/release-manifest.json"}
    for row in rows:
        if type(row) is not dict or set(row) != {"path", "sha256", "size"}:
            raise StudyError("installed_adapter_invalid")
        relative = _safe_path(row["path"])
        if relative in expected_paths:
            raise StudyError("installed_adapter_invalid")
        expected_paths.add(relative)
    installed_root = run_root / "installed-plugin/graph-engineering"
    if installed_root.exists() and (installed_root.is_symlink() or not installed_root.is_dir()):
        raise StudyError("installed_adapter_invalid")
    if not installed_root.exists():
        installed_root.mkdir(parents=True, mode=0o700)
        for row in rows:
            relative = _safe_path(row["path"])
            source = plugin_root.joinpath(*PurePosixPath(relative).parts)
            if source.is_symlink() or not source.is_file():
                raise StudyError("installed_adapter_invalid")
            raw = source.read_bytes()
            if len(raw) != row["size"] or digest(raw) != row["sha256"]:
                raise StudyError("installed_adapter_invalid")
            target = installed_root.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (installed_root / ".codex-plugin").mkdir(parents=True, exist_ok=True)
        (installed_root / ".codex-plugin/release-manifest.json").write_bytes(
            manifest_path.read_bytes()
        )
    installed_manifest = installed_root / ".codex-plugin/release-manifest.json"
    if not installed_manifest.is_file() or installed_manifest.read_bytes() != manifest_path.read_bytes():
        raise StudyError("installed_adapter_invalid")
    for path in installed_root.rglob("*"):
        if path.is_symlink() or (
            path.is_file()
            and path.relative_to(installed_root).as_posix() not in expected_paths
        ):
            raise StudyError("installed_adapter_invalid")
    for row in rows:
        target = installed_root.joinpath(*PurePosixPath(row["path"]).parts)
        if target.is_symlink() or not target.is_file():
            raise StudyError("installed_adapter_invalid")
        raw = target.read_bytes()
        if len(raw) != row["size"] or digest(raw) != row["sha256"]:
            raise StudyError("installed_adapter_invalid")
    adapter = installed_root / "skills/graph-find/scripts/graph_find.py"
    adapter_sha256 = digest(adapter.read_bytes())
    return adapter, candidate_sha256, adapter_sha256


def _record_graph_find_process(
    trial: Trial, argv: Sequence[str], stdout: bytes, stderr: bytes,
    exit_code: int | None, status: str,
) -> None:
    trial.current.setdefault("host_processes", []).append({
        "kind": "graph_find",
        "argv_sha256": digest(canonical(list(argv))),
        "input_sha256": digest(b""),
        "stdout_sha256": digest(stdout),
        "stderr_sha256": digest(stderr),
        "exit_code": exit_code,
        "timeout_limit_ns": 120_000_000_000,
        "status": status,
    })


def _installed_graph_payload(
    trial: Trial, *, task_id: str, prompt: str, lane: Path,
    source_manifest: Mapping[str, Any], installed: tuple[Path, str, str],
    run_root: Path | None = None,
    replay_envelope: Mapping[str, Any] | None = None,
    approved_request_sha256: str | None = None,
    live_request_sha256: str | None = None,
    live_request_bytes: int | None = None,
) -> dict[str, Any]:
    adapter, candidate_sha256, adapter_sha256 = installed
    replay_dir = None
    replay_bytes = None
    replay_path = None
    live = live_request_sha256 is not None
    if live and replay_envelope is not None:
        raise MeasurementError("installed_graph_find_jev_mode_invalid")
    ranked_mode = "plan"
    argv = [
        sys.executable, str(adapter), "--root", str(lane), "--prompt", prompt,
        "--maximum-results", str(RETRIEVAL_NODE_LIMIT), "--byte-budget",
        str(CANDIDATE_AGGREGATE_BYTE_BUDGET),
    ]
    if replay_envelope is not None:
        if (
            not _is_sha256(approved_request_sha256)
            or type(replay_envelope) is not dict
            or set(replay_envelope) != {"schema_version", "request_sha256", "response"}
            or replay_envelope.get("schema_version") != "velgraphing-jev-replay-v1"
            or replay_envelope.get("request_sha256") != approved_request_sha256
        ):
            raise MeasurementError("fixture_request_mismatch")
        replay_bytes = canonical(replay_envelope)
        if len(replay_bytes) > jev.MAX_RESPONSE_BYTES:
            raise MeasurementError("installed_graph_find_jev_replay_invalid")
        if run_root is None or not run_root.is_dir():
            raise MeasurementError("installed_graph_find_jev_run_root_invalid")
        replay_dir = tempfile.TemporaryDirectory(prefix="graph-find-replay-", dir=run_root)
        replay_path = Path(replay_dir.name) / "response.json"
        ranked_mode = "replay"
    elif live:
        if (
            not _is_sha256(live_request_sha256)
            or type(live_request_bytes) is not int or live_request_bytes <= 0
            or run_root is None or not run_root.is_dir()
        ):
            raise MeasurementError("installed_graph_find_jev_live_invalid")
        ranked_mode = "evaluate"
    else:
        ranked_mode = "plan"
    try:
        if replay_path is not None:
            replay_path.write_bytes(replay_bytes)
            argv.extend(["--ranked-context", "replay", "--jev-mode", "rerank",
                         "--jev-response", str(replay_path), "--diagnostics"])
        elif live:
            argv.extend([
                "--ranked-context", "evaluate", "--jev-mode", "rerank",
                "--allow-network", "--approve-request-sha256", live_request_sha256,
                "--diagnostics",
            ])
        else:
            argv.extend(["--ranked-context", "plan", "--diagnostics"])
        child_env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if live:
            api_key = os.environ.get("TYPESAFE_API_KEY")
            if type(api_key) is not str or not api_key:
                raise MeasurementError("installed_graph_find_jev_live_unavailable")
            child_env["TYPESAFE_API_KEY"] = api_key
        with trial.phase("candidate_discovery"):
            try:
                completed = subprocess.run(
                    argv, cwd=str(ROOT),
                    env=child_env,
                    capture_output=True, check=False, timeout=120,
                )
            except subprocess.TimeoutExpired as exc:
                _record_graph_find_process(
                    trial, argv, exc.stdout or b"", exc.stderr or b"", None, "timeout",
                )
                raise TimeoutError from None
    finally:
        if replay_dir is not None:
            replay_dir.cleanup()
    _record_graph_find_process(
        trial, argv, completed.stdout, completed.stderr, completed.returncode,
        "completed" if completed.returncode == 0 else "failed",
    )
    if completed.returncode != 0:
        raise MeasurementError("installed_graph_find_failed")
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise MeasurementError("installed_graph_find_invalid") from None
    ranked = payload.get("ranked_context")
    diagnostics = payload.get("diagnostics")
    if type(ranked) is not dict or type(diagnostics) is not dict:
        raise MeasurementError("installed_graph_find_invalid")
    selection = ranked.get("selection")
    context = selection.get("context") if type(selection) is dict else None
    plan = ranked.get("plan")
    identity = diagnostics.get("runtime_identity")
    expected_snapshot = source_manifest.get("snapshot_sha256")
    if (
        ranked.get("mode") != ranked_mode or ranked.get("status") != "selected"
        or type(selection) is not dict or selection.get("fail_closed") is not False
        or selection.get("route") != "ranked"
        or selection.get("source_revalidated") is not True
        or type(context) is not dict or context.get("fail_closed") is not False
        or type(plan) is not dict
        or plan.get("candidate_set_sha256") != selection.get("candidate_set_sha256")
        or context.get("candidate_set_sha256") != selection.get("candidate_set_sha256")
        or context.get("source_snapshot_sha256") != expected_snapshot
        or diagnostics.get("source_snapshot_sha256") != expected_snapshot
        or type(identity) is not dict
        or identity.get("candidate_sha256") != candidate_sha256
        or identity.get("adapter_sha256") != adapter_sha256
    ):
        raise MeasurementError("installed_graph_find_binding_mismatch")
    source_rows = source_manifest.get("sources")
    sources = {row["path"]: row for row in source_rows if type(row) is dict}
    selected_ids = context.get("selected_candidate_ids")
    required_ids = context.get("required_candidate_ids")
    spans = context.get("spans")
    if (
        type(selected_ids) is not list
        or any(type(item) is not str or not item for item in selected_ids)
        or len(selected_ids) != len(set(selected_ids))
        or type(required_ids) is not list
        or any(type(item) is not str or not item for item in required_ids)
        or len(required_ids) != len(set(required_ids))
        or not set(required_ids).issubset(selected_ids)
        or type(spans) is not list
        or any(type(row) is not dict for row in spans)
        or {row.get("candidate_id") for row in spans if type(row) is dict} != set(selected_ids)
    ):
        raise MeasurementError("installed_graph_find_evidence_invalid")
    live_observation = None
    if replay_envelope is not None:
        observation = ranked.get("jev_observation")
        replayed_usage = observation.get("replayed_usage") if type(observation) is dict else None
        jev_order = observation.get("order") if type(observation) is dict else None
        jev_required = observation.get("required_ids") if type(observation) is dict else None
        jev_decision = selection.get("jev_decision")
        elapsed_ms = observation.get("elapsed_ms") if type(observation) is dict else None
        if (
            type(observation) is not dict
            or observation.get("mode") != "rerank"
            or observation.get("status") != "reranked"
            or observation.get("execution") != "replay"
            or observation.get("request_sha256") != approved_request_sha256
            or observation.get("candidate_set_sha256") != selection.get("candidate_set_sha256")
            or type(observation.get("attempted_calls")) is not int
            or observation.get("attempted_calls") != 0
            or observation.get("usage") is not None
            or type(replayed_usage) is not dict
            or set(replayed_usage) != {"input_tokens", "output_tokens"}
            or any(type(value) is not int or value < 0 for value in replayed_usage.values())
            or observation.get("source_revalidated") is not True
            or ranked.get("network_called") is not False
            or type(elapsed_ms) not in (int, float)
            or not math.isfinite(elapsed_ms) or elapsed_ms < 0
            or type(jev_order) is not list
            or any(type(item) is not str or not item for item in jev_order)
            or len(jev_order) != len(set(jev_order))
            or type(observation.get("baseline_order")) is not list
            or any(type(item) is not str or not item
                   for item in observation["baseline_order"])
            or len(observation["baseline_order"]) != len(set(observation["baseline_order"]))
            or set(jev_order) != set(observation["baseline_order"])
            or type(jev_required) is not list
            or any(type(item) is not str or not item for item in jev_required)
            or len(jev_required) != len(set(jev_required))
            or set(jev_required) != set(required_ids)
            or not set(required_ids).issubset(selected_ids)
            or not set(selected_ids).issubset(jev_order)
            or selection.get("order_source") != "reranked"
            or selection.get("jev_source_revalidated") is not True
            or type(jev_decision) is not dict
            or jev_decision.get("jev_observation_applied") is not True
        ):
            raise MeasurementError("installed_graph_find_jev_binding_mismatch")
        jev_required_set = set(jev_required)
        if any(
            candidate_id in jev_required_set and jev_order[index] != candidate_id
            for index, candidate_id in enumerate(observation["baseline_order"])
        ):
            raise MeasurementError("installed_graph_find_jev_binding_mismatch")
        trial.bind(request_sha256=approved_request_sha256)
        trial.current["jev_observation"] = {
            key: observation.get(key) for key in (
                "mode", "status", "reason", "execution", "baseline_order", "order",
                "required_ids", "candidate_set_sha256", "request_sha256",
                "source_revalidated", "resolved_model", "scores", "elapsed_ms",
                "attempted_calls", "replayed_usage", "request_bytes",
                "source_bytes_verified", "rubric_version", "source_set_sha256",
            )
        }
        trial.current["jev_observation"].update({
            "measurement_execution": "replay",
            "order_source": selection["order_source"],
            "jev_source_revalidated": selection["jev_source_revalidated"],
        })
    elif live:
        observation = ranked.get("jev_observation")
        live_observation = observation
        jev_order = observation.get("order") if type(observation) is dict else None
        baseline_order = observation.get("baseline_order") if type(observation) is dict else None
        jev_required = observation.get("required_ids") if type(observation) is dict else None
        jev_usage = observation.get("usage") if type(observation) is dict else None
        elapsed_ms = observation.get("elapsed_ms") if type(observation) is dict else None
        attempted_calls = observation.get("attempted_calls") if type(observation) is dict else None
        jev_decision = selection.get("jev_decision")
        if (
            type(observation) is not dict
            or observation.get("mode") != "rerank"
            or observation.get("execution") != "live"
            or observation.get("request_sha256") != live_request_sha256
            or observation.get("candidate_set_sha256") != selection.get("candidate_set_sha256")
            or type(attempted_calls) is not int or attempted_calls not in {0, 1}
            or type(ranked.get("network_called")) is not bool
            or ranked.get("network_called") != (attempted_calls == 1)
            or type(observation.get("request_bytes")) is not int
            or observation["request_bytes"] != live_request_bytes
            or type(elapsed_ms) not in (int, float)
            or not math.isfinite(elapsed_ms) or elapsed_ms < 0
            or type(jev_order) is not list
            or any(type(item) is not str or not item for item in jev_order)
            or len(jev_order) != len(set(jev_order))
            or type(baseline_order) is not list
            or any(type(item) is not str or not item for item in baseline_order)
            or len(baseline_order) != len(set(baseline_order))
            or set(jev_order) != set(baseline_order)
            or type(jev_required) is not list
            or any(type(item) is not str or not item for item in jev_required)
            or len(jev_required) != len(set(jev_required))
            or set(jev_required) != set(required_ids)
            or type(jev_decision) is not dict
        ):
            raise MeasurementError("installed_graph_find_jev_binding_mismatch")
        if observation.get("status") == "reranked":
            if (
                attempted_calls != 1
                or observation.get("source_revalidated") is not True
                or selection.get("order_source") != "reranked"
                or selection.get("jev_source_revalidated") is not True
                or jev_decision.get("jev_observation_applied") is not True
                or not set(required_ids).issubset(jev_order)
                or not set(required_ids).issubset(selected_ids)
                or not set(selected_ids).issubset(jev_order)
            ):
                raise MeasurementError("installed_graph_find_jev_binding_mismatch")
        elif observation.get("status") == "fallback":
            selected_set = set(selected_ids)
            baseline_selected_order = [
                candidate_id for candidate_id in baseline_order
                if candidate_id in selected_set
            ]
            if (
                selection.get("order_source") != "baseline"
                or selection.get("jev_source_revalidated") is not False
                or jev_decision.get("jev_observation_applied") is not False
                or jev_order != baseline_order
                or baseline_selected_order != selected_ids
                or not set(required_ids).issubset(selected_ids)
            ):
                raise MeasurementError("installed_graph_find_jev_binding_mismatch")
        else:
            raise MeasurementError("installed_graph_find_jev_binding_mismatch")
        if jev_usage is not None and (
            type(jev_usage) is not dict
            or set(jev_usage) != {"input_tokens", "output_tokens"}
            or any(type(value) is not int or value < 0 for value in jev_usage.values())
        ):
            raise MeasurementError("installed_graph_find_jev_usage_invalid")
        if observation.get("replayed_usage") is not None:
            raise MeasurementError("installed_graph_find_jev_usage_invalid")
        resolved_model = observation.get("resolved_model")
        if resolved_model is not None and (type(resolved_model) is not str or not resolved_model):
            raise MeasurementError("installed_graph_find_jev_usage_invalid")
        trial.bind(request_sha256=live_request_sha256)
    for span in spans:
        source = sources.get(span.get("source_path"))
        start, end = span.get("byte_start"), span.get("byte_end")
        content = span.get("content")
        if (
            source is None or span.get("source_sha256") != source.get("sha256")
            or type(start) is not int or type(end) is not int or start < 0
            or end <= start or end > source.get("byte_length")
            or type(content) is not str or len(content.encode("utf-8")) != end - start
        ):
            raise MeasurementError("installed_graph_find_evidence_invalid")
    operations = diagnostics.get("source_operations")
    stages = diagnostics.get("stage_ns")
    if (
        type(operations) is not list or type(stages) is not dict
        or not {"scan", "graph_build", "retrieval", "selection"}.issubset(stages)
        or any(type(value) is not int or value < 0 for value in stages.values())
    ):
        raise MeasurementError("installed_graph_find_diagnostics_invalid")
    for index, operation in enumerate(operations):
        if (
            type(operation) is not dict
            or operation.get("access") not in {"file_read", "memory_read"}
            or type(operation.get("stage")) is not str
            or not _is_sha256(operation.get("source_sha256"))
            or type(operation.get("byte_count")) is not int
            or operation["byte_count"] < 0
        ):
            raise MeasurementError("installed_graph_find_diagnostics_invalid")
        trial.source(
            operation["source_sha256"], 0, operation["byte_count"],
            access=operation["access"], operation_id=f"graph-find-{index}",
        )
    if live_observation is not None:
        usage = live_observation.get("usage")
        trial.current["jev_observation"] = {
            key: live_observation.get(key) for key in (
                "mode", "status", "reason", "execution", "baseline_order", "order",
                "required_ids", "candidate_set_sha256", "request_sha256",
                "source_revalidated", "resolved_model", "scores", "elapsed_ms",
                "attempted_calls", "usage", "request_bytes", "source_bytes_verified",
                "rubric_version",
            )
        }
        trial.current["jev_observation"].update({
            "measurement_execution": "live",
            "order_source": selection["order_source"],
            "jev_source_revalidated": selection["jev_source_revalidated"],
        })
        trial.usage(
            f"jev-{trial.current['attempt_id']}", "jev",
            provenance="provider_reported" if usage is not None else "unavailable",
            model=live_observation.get("resolved_model") or jev.DEFAULT_MODEL,
            input_tokens=usage["input_tokens"] if usage is not None else None,
            output_tokens=usage["output_tokens"] if usage is not None else None,
        )
        if live_observation.get("status") == "fallback":
            with trial.phase("fallback"):
                pass
    trial.bind(
        candidate_set_sha256=selection["candidate_set_sha256"],
        graph_artifact_sha256=candidate_sha256,
    )
    evidence = []
    with trial.phase("context_composition"):
        for span in spans:
            evidence.append({
                "id": span["candidate_id"], "excerpt": span["content"],
                "path": span["source_path"],
                "source_sha256": span["source_sha256"],
                "byte_start": span["byte_start"], "byte_end": span["byte_end"],
            })
    trial.current["candidate_observation"] = {
        "route": "installed_graph_find", "task_id": task_id,
        "candidate_set_sha256": selection["candidate_set_sha256"],
        "candidate_count": plan.get("candidate_count"),
        "selected_candidate_ids": selected_ids,
        "required_candidate_ids": required_ids,
        "source_snapshot_sha256": expected_snapshot,
        "runtime_identity": identity,
        "process_scope": (
            "installed_graph_find_entire_process_including_jev"
            if replay_envelope is not None or live
            else "installed_graph_find_entire_process"
        ),
        "stage_clock": {
            "name": "perf_counter_ns", "domain": "installed_graph_find_process",
        },
        "stage_ns": stages,
        "source_read_count": len(operations),
    }
    trial.current["graph_observation"] = {
        "record_count": payload.get("scan", {}).get("files_scanned"),
        "edge_count": payload.get("scan", {}).get("edges_derived"),
    }
    return {
        "schema_version": "velgraphing-answer-evidence-v3",
        "question": prompt,
        "citation_instruction": "Cite supporting evidence IDs as [cN].",
        "evidence": evidence,
    }


def _pool(
    task_id: str,
    route: str,
    prompt: str,
    graph: Graph,
    snapshot: Any,
    reader: Any,
    retrieval: Any,
    lane: Path,
    selection_task: TaskSpec,
) -> tuple[dict[str, object], dict[str, object]]:
    candidates = ranked_candidates_from_retrieval(
        graph,
        selection_task,
        snapshot,
        reader,
        retrieval,
        maximum_candidates=CANDIDATE_LIMIT,
        maximum_candidate_bytes=CANDIDATE_AGGREGATE_BYTE_BUDGET,
        maximum_unit_bytes=CANDIDATE_UNIT_BYTE_BUDGET,
    )
    if not candidates:
        raise StudyError("candidate_pool_empty")
    selected = select_ranked_context(
        graph,
        selection_task,
        snapshot,
        reader,
        query=prompt,
        candidates=candidates,
        jev_enabled=True,
    )
    if selected.route != "ranked" or selected.projection.fail_closed:
        raise StudyError("candidate_selection_failed_closed")
    packet = _packet(prompt, candidates)
    preview = (
        jev.prepare(packet, lane, jev.DEFAULT_MODEL)
        if selected.jev_decision.jev_call_could_affect_selection
        else None
    )
    identity = {
        "schema_version": "velgraphing-four-arm-pool-v1",
        "pool_id": f"{route}:{task_id}",
        "task_id": task_id,
        "route": route,
        "prompt_sha256": digest(prompt.encode("utf-8")),
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "candidates": [_candidate_row(candidate) for candidate in candidates],
    }
    pool_sha256 = _sha256(identity)
    decision = {
        "schema_version": "velgraphing-four-arm-jev-decision-v1",
        "pool_id": identity["pool_id"],
        "pool_sha256": pool_sha256,
        "candidate_set_sha256": selected.candidate_set_sha256,
        "decision": selected.jev_decision.to_dict(),
        "call_disposition": (
            "planned"
            if selected.jev_decision.jev_call_could_affect_selection
            else "skip_no_membership_effect"
        ),
    }
    decision_sha256 = _sha256(decision)
    excerpt_bytes = sum(
        candidate.byte_end - candidate.byte_start for candidate in candidates
    )
    relationship_count = sum(
        candidate.relationship_parent_candidate_id is not None
        for candidate in candidates
    )
    summary = {
        "pool_id": identity["pool_id"],
        "task_id": task_id,
        "route": route,
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "pool_sha256": pool_sha256,
        "candidate_set_sha256": selected.candidate_set_sha256,
        "candidate_count": len(candidates),
        "aggregate_excerpt_bytes": excerpt_bytes,
        "required_candidate_count": sum(candidate.required for candidate in candidates),
        "relationship_candidate_count": relationship_count,
        "relationship_delta_present": relationship_count > 0,
        "baseline_selected_candidate_count": (
            selected.jev_decision.baseline_selected_candidate_count
        ),
        "baseline_selected_excerpt_bytes": (
            selected.jev_decision.baseline_selected_excerpt_bytes
        ),
        "baseline_omitted_candidate_count": (
            selected.jev_decision.baseline_omitted_candidate_count
        ),
        "baseline_omitted_excerpt_bytes": (
            selected.jev_decision.baseline_omitted_excerpt_bytes
        ),
        "request_sha256": preview["request_sha256"] if preview else None,
        "request_bytes": preview["request_bytes"] if preview else None,
        "source_set_sha256": preview["source_set_sha256"] if preview else None,
        "selection_decision_sha256": decision_sha256,
        "eligibility": {
            "source_revalidated": selected.source_revalidated,
            "fail_closed": selected.projection.fail_closed,
            "selection_reason": selected.reason,
            "jev_reason": selected.jev_decision.reason,
            "jev_call_could_affect_selection": (
                selected.jev_decision.jev_call_could_affect_selection
            ),
            "call_disposition": decision["call_disposition"],
        },
    }
    local = {
        "identity": identity,
        "pool_sha256": pool_sha256,
        "candidate_packet": packet,
        "selection": {
            "candidate_set_sha256": selected.candidate_set_sha256,
            "decision": selected.jev_decision.to_dict(),
            "projection": json.loads(selected.projection.content),
        },
        "decision": decision,
        "selection_decision_sha256": decision_sha256,
        "jev_preview": preview,
    }
    return summary, local


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2,
    ).encode("utf-8") + b"\n"


def _write_json(path: Path, value: Mapping[str, Any]) -> str:
    if path.is_symlink() or path.parent.is_symlink():
        raise StudyError("output_path_invalid")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _json_bytes(value)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)
    return digest(raw)


def prepare_study(
    freeze: Mapping[str, Any],
    questions: Mapping[str, Any],
    benchmark_root: Path,
    lanes_root: Path,
    local_output: Path | None,
    preflight_output: Path | None,
    repo_root: Path = ROOT,
    *,
    persist: bool = True,
) -> dict[str, object]:
    if (
        not lanes_root.is_absolute()
        or persist and (
            local_output is None or preflight_output is None
            or not local_output.is_absolute() or not preflight_output.is_absolute()
        )
    ):
        raise StudyError("prepare_paths_must_be_absolute")
    question_rows = {row["id"]: row for row in questions["questions"]}
    prepared: dict[str, tuple[Any, Any, Any, dict[str, object]]] = {}
    for corpus_id in dict.fromkeys(question_rows[task_id]["corpus"] for task_id in TASKS):
        corpus = freeze["corpora"][corpus_id]
        manifest_path = repo_root / corpus["manifest"]
        manifest = _load_manifest(manifest_path)
        if (
            manifest["commit"] != corpus["commit"]
            or manifest["snapshot_sha256"] != corpus["snapshot_sha256"]
            or digest(manifest_path.read_bytes()) != corpus["manifest_sha256"]
        ):
            raise StudyError("source_binding_invalid")
        graph, snapshot, reader, metadata = _scan_lane(
            lanes_root / corpus_id, manifest, derive_edges=True,
        )
        prepared[corpus_id] = (graph, snapshot, reader, metadata)

    summaries: list[dict[str, object]] = []
    local_pools: list[dict[str, object]] = []
    for task_id in TASKS:
        question = question_rows[task_id]
        prompt = question["prompt"]
        typed_graph, snapshot, reader, metadata = prepared[question["corpus"]]
        plain_graph = Graph(typed_graph.records)
        terms = tuple(dict.fromkeys(
            token.casefold() for token in graph_find_adapter._TOKEN.findall(prompt)
        ))
        retrieval_task = TaskSpec(
            task_id,
            terms,
            node_budget=RETRIEVAL_NODE_LIMIT,
            byte_budget=CANDIDATE_AGGREGATE_BYTE_BUDGET,
            allowed_sensitivities=(Sensitivity.INTERNAL,),
        )
        selection_task = TaskSpec(
            task_id,
            terms,
            node_budget=RETRIEVAL_NODE_LIMIT,
            byte_budget=FINAL_CONTEXT_BYTE_BUDGET,
            allowed_sensitivities=(Sensitivity.INTERNAL,),
        )
        index = build_repository_tag_index(plain_graph, snapshot, reader)
        facets = compile_prompt(prompt, index)

        def run(graph: Graph, *, graph_route: bool) -> Any:
            return retrieve(
                graph,
                retrieval_task,
                index,
                facets,
                snapshot,
                reader,
                channels=("exact", "sparse", "wiki"),
                expand_one_hop=graph_route,
                source_bound_expansion=graph_route,
                maximum_results=RETRIEVAL_NODE_LIMIT,
                minimum_coverage_percent=0.0,
                parallel=False,
            )

        direct = run(plain_graph, graph_route=False)
        if direct.reason == "prompt_facets_insufficient":
            facets = compile_prompt(
                prompt,
                index,
                proof_obligations=compile_proof_obligations(
                    prompt, plain_graph, index, snapshot, reader,
                ),
            )
            direct = run(plain_graph, graph_route=False)
        graph_result = run(typed_graph, graph_route=True)
        if direct.fail_closed or graph_result.fail_closed:
            raise StudyError("retrieval_failed_closed")
        for route, graph, result in (
            ("direct", plain_graph, direct),
            ("graph", typed_graph, graph_result),
        ):
            summary, local = _pool(
                task_id, route, prompt, graph, snapshot, reader, result,
                lanes_root / question["corpus"], selection_task,
            )
            local["corpus"] = question["corpus"]
            local["derived_edge_count"] = metadata["edges_derived"]
            summaries.append(summary)
            local_pools.append(local)

    by_pool = {row["pool_id"]: row for row in summaries}
    trials: list[dict[str, object]] = []
    planned = 0
    for trial_id in DISPATCH:
        arm, task_id = trial_id.split("-", 1)
        contract = ARMS[arm]
        pool = by_pool[f"{contract['route']}:{task_id}"]
        enabled = contract["jev"] == "on"
        can_affect = bool(pool["eligibility"]["jev_call_could_affect_selection"])
        disposition = (
            "treatment_off" if not enabled
            else "planned" if can_affect
            else "skip_no_membership_effect"
        )
        reason = "jev_disabled" if not enabled else pool["eligibility"]["jev_reason"]
        decision_sha256 = (
            pool["selection_decision_sha256"]
            if enabled
            else _sha256({
                "trial_id": trial_id,
                "pool_sha256": pool["pool_sha256"],
                "call_disposition": disposition,
                "reason": reason,
            })
        )
        trials.append({
            "trial_id": trial_id,
            "task_id": task_id,
            "arm": arm,
            "pool_id": pool["pool_id"],
            "pool_sha256": pool["pool_sha256"],
            "selection_decision_sha256": decision_sha256,
            "selection_decision_reason": reason,
            "jev_call_could_affect_selection": can_affect if enabled else False,
            "call_disposition": disposition,
        })
        planned += disposition == "planned"

    preflight = {
        "schema_version": PREFLIGHT_SCHEMA,
        "study_id": freeze["study_id"],
        "product_commit": freeze["product"]["commit"],
        "package_candidate_sha256": freeze["product"]["package_candidate_sha256"],
        "question_registry_sha256": digest(
            (benchmark_root / "questions.json").read_bytes()
        ),
        "rubric_registry_sha256": digest(
            (benchmark_root / "rubrics.json").read_bytes()
        ),
        "candidate_budgets": {
            "retrieval_nodes": RETRIEVAL_NODE_LIMIT,
            "candidate_count": CANDIDATE_LIMIT,
            "aggregate_excerpt_bytes": CANDIDATE_AGGREGATE_BYTE_BUDGET,
            "per_candidate_bytes": CANDIDATE_UNIT_BYTE_BUDGET,
            "final_context_bytes": FINAL_CONTEXT_BYTE_BUDGET,
        },
        "provider_calls_executed": 0,
        "retries": 0,
        "planned_jev_calls": planned,
        "pools": summaries,
        "trials": trials,
    }
    local_artifact = {
        "schema_version": LOCAL_ARTIFACT_SCHEMA,
        "study_id": freeze["study_id"],
        "provider_calls_executed": 0,
        "pools": local_pools,
    }
    preflight_raw = _json_bytes(preflight)
    local_raw = _json_bytes(local_artifact)
    result: dict[str, object] = {
        "local_artifact_sha256": digest(local_raw),
        "planned_jev_calls": planned,
        "preflight_sha256": digest(preflight_raw),
        "pool_count": len(summaries),
        "skipped_jev_calls": 8 - planned,
    }
    if persist:
        assert local_output is not None and preflight_output is not None
        _write_json(preflight_output, preflight)
        _write_json(local_output, local_artifact)
    else:
        result["_preflight"] = preflight
        result["_local_artifact"] = local_artifact
    return result


def _validate_rubrics(value: Mapping[str, Any]) -> None:
    if (
        set(value) != {"schema_version", "governance_rule", "tasks"}
        or value["schema_version"] != "velgraphing-four-arm-rubrics-v1"
        or value["governance_rule"]
        != "Every required fact maps to an explicit prompt ask. Incidental facts are diagnostic only."
        or type(value["tasks"]) is not dict
        or set(value["tasks"]) != set(TASKS)
    ):
        raise StudyError("rubrics_invalid")
    for task_id, rubric in value["tasks"].items():
        if type(rubric) is not dict or set(rubric) != {
            "rubric_version", "asks", "required_facts", "critical_facts",
            "diagnostic_facts", "acceptable_spans",
        }:
            raise StudyError("rubrics_invalid")
        asks = rubric["asks"]
        required = rubric["required_facts"]
        if type(asks) is not list or type(required) is not list or not asks or not required:
            raise StudyError("rubrics_invalid")
        ask_ids = {
            row.get("id") for row in asks if type(row) is dict
            and set(row) == {"id", "text"}
            and type(row.get("id")) is str and row["id"]
            and type(row.get("text")) is str and row["text"]
        }
        facts = [
            row.get("fact") for row in required if type(row) is dict
            and set(row) == {"ask_id", "fact"}
            and row.get("ask_id") in ask_ids
            and type(row.get("fact")) is str and row["fact"]
        ]
        if (
            len(ask_ids) != len(asks)
            or len(facts) != len(required)
            or {row["ask_id"] for row in required} != ask_ids
            or len(set(facts)) != len(facts)
            or type(rubric["critical_facts"]) is not list
            or not set(rubric["critical_facts"]).issubset(facts)
            or type(rubric["diagnostic_facts"]) is not list
            or set(rubric["diagnostic_facts"]).intersection(facts)
            or type(rubric["acceptable_spans"]) is not list
            or not rubric["acceptable_spans"]
        ):
            raise StudyError("rubrics_invalid")
        if task_id == "D-01" and (
            not any("Duplicate values" in fact for fact in facts)
            or not any("base case" in fact.lower() for fact in rubric["diagnostic_facts"])
        ):
            raise StudyError("rubrics_invalid")
        if task_id == "L-01" and (
            any("Kafka" in fact for fact in facts)
            or not any("Kafka" in fact for fact in rubric["diagnostic_facts"])
        ):
            raise StudyError("rubrics_invalid")


def _validate_freeze(
    freeze: Mapping[str, Any], questions: Mapping[str, Any], rubrics: Mapping[str, Any],
    benchmark_root: Path, repo_root: Path,
) -> None:
    rows = questions.get("questions")
    if (
        questions.get("schema_version") != "velgraphing-four-arm-questions-v1"
        or type(rows) is not list
        or len(rows) != len(TASKS)
        or any(type(row) is not dict for row in rows)
        or tuple(row.get("id") for row in rows) != TASKS
        or any(set(row) != {"id", "corpus", "prompt"} for row in rows)
        or any(row.get("corpus") != TASK_CORPORA[row["id"]] for row in rows)
    ):
        raise StudyError("questions_invalid")
    _validate_rubrics(rubrics)
    if (
        set(freeze) != FREEZE_KEYS
        or freeze.get("schema_version") != "velgraphing-four-arm-freeze-v1"
        or freeze.get("study_id") != "velgraphing-four-arm-study-v1"
        or freeze.get("status")
        != "phase_3a_adapter_qualified_pending_lane_manifest_and_provider_authority"
        or freeze.get("tasks") != list(TASKS)
        or freeze.get("arms") != ARMS
        or freeze.get("dispatch_order") != list(DISPATCH)
        or freeze.get("public_source_only") is not True
    ):
        raise StudyError("freeze_identity_invalid")
    product = freeze.get("product")
    if (
        type(product) is not dict
        or not _is_ancestor(repo_root, product.get("commit"))
    ):
        raise StudyError("package_binding_invalid")
    release_path = "plugins/graph-engineering/.codex-plugin/release-manifest.json"
    try:
        release_raw = _git(
            repo_root, "show", f"{product['commit']}:{release_path}",
        )
        release = json.loads(release_raw.decode("utf-8"))
    except (StudyError, UnicodeError, json.JSONDecodeError):
        raise StudyError("package_binding_invalid") from None
    release_package = release.get("package") if type(release) is dict else None
    if (
        type(release) is not dict
        or type(release_package) is not dict
        or product.get("package_candidate_sha256") != release.get("candidate_sha256")
        or product.get("package_name") != release_package.get("name")
        or product.get("package_version") != release_package.get("version")
    ):
        raise StudyError("package_binding_invalid")
    controller = freeze.get("controller", {})
    controller_path = "scripts/benchmarks/four_arm_study_v1.py"
    if controller != {
        "argv": [
            "/usr/bin/env", "python3", "-B",
            controller_path, "validate", "--root",
            "benchmarks/velgraphing-four-arm-study-v1",
        ],
        "prepare_argv_template": PREPARE_ARGV_TEMPLATE,
        "execution_argv_template": EXECUTION_ARGV_TEMPLATE,
        "path": controller_path,
        "sha256": HISTORICAL_CONTROLLER_SHA256,
        "phase": "phase_3a_execution_adapter",
        "provider_answer_and_grader_calls": 0,
    }:
        raise StudyError("controller_binding_invalid")
    pools = freeze.get("candidate_pool_contract", {})
    if (
        pools.get("candidate_count") != 64
        or pools.get("retrieval_nodes") != 12
        or pools.get("aggregate_excerpt_bytes") != 32_768
        or pools.get("per_candidate_bytes") != 4096
        or pools.get("final_context_bytes") != 16_384
        or pools.get("direct_and_graph_authority") != "same_public_source_snapshot"
        or pools.get("direct_and_graph_fallback")
        != "same_caller_allowlisted_exact_source_reads"
        or pools.get("relationship_delta")
        != "graph_may_add_only_source_verified_relationship_context"
        or pools.get("materialized_pool_sha256_frozen") is not True
        or pools.get("local_artifact_sha256") != LOCAL_POOL_SHA256
        or pools.get("pool_pairs") != [
            {"direct": f"direct:{task}", "graph": f"graph:{task}", "task_id": task}
            for task in TASKS
        ]
        or type(pools.get("pool_bindings")) is not dict
        or set(pools["pool_bindings"]) != {
            f"{route}:{task}" for task in TASKS for route in ("direct", "graph")
        }
        or any(not _is_sha256(value) for value in pools["pool_bindings"].values())
    ):
        raise StudyError("candidate_pool_contract_invalid")
    artifacts = freeze.get("artifacts")
    if type(artifacts) is not dict or set(artifacts) != {
        "questions", "rubrics", "preflight",
    }:
        raise StudyError("freeze_artifacts_invalid")
    for name in ("questions", "rubrics", "preflight"):
        binding = artifacts.get(name)
        path = benchmark_root / f"{name}.json"
        if (
            type(binding) is not dict
            or binding != {"path": f"{name}.json", "sha256": digest(path.read_bytes())}
        ):
            raise StudyError("freeze_artifacts_invalid")
    prompt_bindings = freeze.get("prompt_bindings")
    expected_prompts = {
        row["id"]: {
            "bytes": len(row["prompt"].encode("utf-8")),
            "sha256": hashlib.sha256(row["prompt"].encode("utf-8")).hexdigest(),
        }
        for row in rows
    }
    if prompt_bindings != expected_prompts:
        raise StudyError("prompt_binding_invalid")
    corpora = freeze.get("corpora")
    if type(corpora) is not dict or {
        row["corpus"] for row in rows
    } != set(corpora):
        raise StudyError("source_binding_invalid")
    for corpus_id, corpus in corpora.items():
        if type(corpus) is not dict:
            raise StudyError("source_binding_invalid")
        if corpus.get("manifest") != CORPUS_MANIFESTS[corpus_id]:
            raise StudyError("source_binding_invalid")
        manifest_path = repo_root / corpus.get("manifest", "")
        manifest_raw, manifest = _read_json(manifest_path, "source_binding_invalid")
        if (
            not _is_sha256(corpus.get("snapshot_sha256"))
            or type(corpus.get("commit")) is not str
            or len(corpus["commit"]) != 40
            or digest(manifest_raw) != corpus.get("manifest_sha256")
            or manifest.get("commit") != corpus["commit"]
            or manifest.get("snapshot_sha256") != corpus["snapshot_sha256"]
        ):
            raise StudyError("source_binding_invalid")
    bindings = freeze.get("implementation_bindings")
    if type(bindings) is not dict or set(bindings) != {
        *IMPLEMENTATION_PATHS,
        "answer_response_contract_sha256", "grader_response_contract_sha256",
    }:
        raise StudyError("implementation_binding_invalid")
    if (
        bindings.get("answer_response_contract_sha256")
        != digest(canonical(ANSWER_RESPONSE_CONTRACT))
        or bindings.get("grader_response_contract_sha256")
        != digest(canonical(GRADER_RESPONSE_CONTRACT))
    ):
        raise StudyError("implementation_binding_invalid")
    for name, expected_path in IMPLEMENTATION_PATHS.items():
        binding = bindings.get(name)
        historical_benchmark_sha256 = {
            "handoff": HISTORICAL_HANDOFF_SHA256,
            "host": HISTORICAL_HOST_SHA256,
        }.get(name)
        expected_sha256 = (
            historical_benchmark_sha256
            if historical_benchmark_sha256 is not None
            else _bound_blob_sha256(
                repo_root, product["commit"], expected_path,
                "implementation_binding_invalid",
            )
        )
        if (
            type(binding) is not dict
            or set(binding) != {"path", "sha256"}
            or binding["path"] != expected_path
            or binding["sha256"] != expected_sha256
        ):
            raise StudyError("implementation_binding_invalid")
    lane = freeze.get("lane_identity_contract", {})
    if (
        set(lane) != {
            "answer", "argv_contract", "grader", "fresh_no_history",
            "handoff_schema", "host_thread_id", "reuse",
        }
        or lane.get("answer") != {
            "count": 16, "logical_id": "answer:{trial_id}",
            "model": "gpt-5.6-luna", "reasoning": "medium",
        }
        or lane.get("grader") != {
            "count": 16, "logical_id": "grader:{trial_id}",
            "model": "gpt-6-astra", "reasoning": "high",
        }
        or lane.get("fresh_no_history") is not True
        or lane.get("reuse") is not False
        or lane.get("argv_contract") != "exact_handoff_wait_argv_v1"
        or lane.get("handoff_schema") != "velgraphing-v4-luna-lane-manifest-v1"
        or lane.get("host_thread_id")
        != "unique_nonempty_value_required_and_frozen_before_execution"
    ):
        raise StudyError("lane_model_binding_invalid")
    boundary = freeze.get("lane_boundary", {})
    if (
        boundary.get("oracle_labels_available_to_answer") is not False
        or boundary.get("treatment_labels_available_to_answer") is not False
        or boundary.get("treatment_labels_available_to_grader") is not False
        or {"treatment", "arm", "route", "jev"}
        - set(boundary.get("answer_must_not_receive", ()))
        or {"treatment", "arm", "route", "jev"}
        - set(boundary.get("grader_must_not_receive", ()))
    ):
        raise StudyError("lane_blindness_invalid")
    jev = freeze.get("jev", {})
    if (
        jev.get("max_calls") != 8 or jev.get("retries") != 0
        or jev.get("request_byte_set_sha256") != REQUEST_BYTE_SET_SHA256
        or jev.get("request_bytes") != 758_130
        or jev.get("rate_usd_per_million_request_bytes") != str(JEV_RATE)
        or jev.get("total_reservation_usd") != str(TOTAL_RESERVATION)
        or jev.get("candidate_membership") != "frozen_verified_shortlist_only"
        or "offline_select_ranked_context_preflight" not in jev.get("skip_rule", "")
        or type(jev.get("planned_calls")) is not int
        or not 0 <= jev["planned_calls"] <= jev["max_calls"]
        or type(jev.get("planned_trials")) is not list
        or type(jev.get("skipped_trials")) is not list
        or set(jev["planned_trials"]).intersection(jev["skipped_trials"])
        or set(jev["planned_trials"] + jev["skipped_trials"])
        != {f"{arm}-{task}" for task in TASKS for arm in ("B", "D")}
        or type(jev.get("decision_bindings")) is not dict
        or set(jev["decision_bindings"])
        != {f"{arm}-{task}" for task in TASKS for arm in ("B", "D")}
        or any(not _is_sha256(value) for value in jev["decision_bindings"].values())
    ):
        raise StudyError("jev_budget_invalid")
    telemetry = freeze.get("telemetry_schema", {})
    if (
        set(telemetry.get("time_ms", ())) != TIME_METRICS
        or set(telemetry.get("usage", ())) != USAGE_METRICS
        or set(telemetry.get("quality", ()))
        != {"accepted_correctness", "first_pass_correctness"}
        or set(telemetry.get("failure", ())) != {"failure_class", "missingness"}
        or "null" not in telemetry.get("unknown_policy", "")
    ):
        raise StudyError("telemetry_schema_invalid")
    if (
        freeze.get("terms_boundary", {}).get("provider_performance_publication")
        != "forbidden_without_separate_provider_permission"
    ):
        raise StudyError("terms_boundary_invalid")
    if freeze.get("execution_gates") != [
        "sixteen_unique_answer_host_thread_ids_frozen",
        "sixteen_unique_grader_host_thread_ids_frozen",
        "exact_host_argv_arrays_frozen",
        "provider_authority_separately_confirmed",
    ]:
        raise StudyError("execution_gates_invalid")
    _, preflight = _read_json(benchmark_root / "preflight.json", "preflight_invalid")
    validate_preflight(preflight, freeze)


def _current_successor_rubric_bindings(repo_root: Path) -> dict[str, Any]:
    return {
        "controller": {
            "path": "scripts/benchmarks/four_arm_study_v1.py",
            "sha256": digest(
                (repo_root / "scripts/benchmarks/four_arm_study_v1.py").read_bytes()
            ),
        },
        "host": {
            "path": "scripts/benchmarks/time_to_correct_host.py",
            "sha256": digest(
                (repo_root / "scripts/benchmarks/time_to_correct_host.py").read_bytes()
            ),
        },
        "successor_grader_response_contract_sha256": digest(
            canonical(SUCCESSOR_GRADER_RESPONSE_CONTRACT)
        ),
    }


def _validate_successor_rubrics(value: Mapping[str, Any], historical: Mapping[str, Any],
                                benchmark_root: Path, repo_root: Path) -> None:
    if (
        set(value) != {
            "schema_version", "governance_rule", "predecessor", "arm_labels",
            "implementation_bindings", "tasks",
        }
        or value.get("schema_version") != "velgraphing-four-arm-successor-rubrics-v1"
        or value.get("governance_rule") != historical["governance_rule"]
        or value.get("predecessor") != {
            "path": "rubrics.json",
            "sha256": digest((benchmark_root / "rubrics.json").read_bytes()),
        }
        or value.get("arm_labels") != SUCCESSOR_ARM_LABELS
    ):
        raise StudyError("successor_rubrics_invalid")
    if value.get("implementation_bindings") != _current_successor_rubric_bindings(
        repo_root
    ):
        raise StudyError("successor_binding_invalid")
    normalized = {
        "schema_version": "velgraphing-four-arm-rubrics-v1",
        "governance_rule": value["governance_rule"],
        "tasks": value.get("tasks"),
    }
    _validate_rubrics(normalized)
    d01 = value["tasks"]["D-01"]
    m02 = value["tasks"]["M-02"]
    m02_facts = {row["ask_id"]: row["fact"] for row in m02["required_facts"]}
    if (
        any("random" in row["fact"].lower() for row in d01["required_facts"])
        or "any process-documentation choice supported"
        not in m02_facts.get("documentation", "")
    ):
        raise StudyError("successor_rubrics_invalid")


def load_bundle(
    benchmark_root: Path = DEFAULT_ROOT, repo_root: Path = ROOT,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _, freeze = _read_json(benchmark_root / "freeze.json", "freeze_invalid")
    _, questions = _read_json(benchmark_root / "questions.json", "questions_invalid")
    _, rubrics = _read_json(benchmark_root / "rubrics.json", "rubrics_invalid")
    _validate_freeze(freeze, questions, rubrics, benchmark_root, repo_root)
    return freeze, questions, rubrics


def load_successor_rubrics(
    benchmark_root: Path = DEFAULT_ROOT, repo_root: Path = ROOT,
) -> dict[str, Any]:
    _, _, historical = load_bundle(benchmark_root, repo_root)
    _, successor = _read_json(
        benchmark_root / SUCCESSOR_RUBRICS, "successor_rubrics_invalid",
    )
    _validate_successor_rubrics(successor, historical, benchmark_root, repo_root)
    return successor


def _validate_successor_ttc_contract(
    value: Mapping[str, Any], freeze: Mapping[str, Any], successor: Mapping[str, Any],
    benchmark_root: Path, repo_root: Path, custody: Mapping[str, Any],
) -> None:
    if (
        set(value) != {
            "schema_version", "status", "classification", "trial_policy",
            "verifier_policy", "verifier_policy_sha256", "fact_witness_map_sha256",
            "fallback_allowlist_sha256", "witness_custody_sha256",
            "provider_budget_authority", "bindings", "result_contract",
            "remaining_authority",
        }
        or value.get("schema_version") != "velgraphing-four-arm-successor-ttc-v1"
        or value.get("status") not in {
            "pending_lane_manifest_and_final_user_reack",
            "frozen_pending_final_user_reack",
            "ready_after_final_user_reack",
        }
        or value.get("classification") != {
            "study": "oracle_assisted_fallback_ttc",
            "sealed_result": "oracle_assisted_fallback_ttc",
            "claim_boundary": {
                "allowed": ["oracle_assisted_fallback_ttc_under_frozen_contract"],
                "prohibited": [
                    "direct_retrieval_performance", "graph_retrieval_performance",
                    "jev_retrieval_performance",
                    "direct_graph_or_jev_comparative_retrieval_performance",
                ],
            },
        }
        or value.get("trial_policy") != {
            "answer_calls_per_dispatch": 1,
            "grader_calls_per_dispatch": 1,
            "answer_repairs": 0,
            "jev_retries": 0,
            "request_delivery": "exact_inline_request_bytes",
            "response_capture": (
                "parent_retains_raw_validates_contract_then_canonicalizes"
            ),
        }
    ):
        raise StudyError("successor_ttc_contract_invalid")
    if value.get("provider_budget_authority") != PROVIDER_BUDGET_AUTHORITY:
        raise StudyError("successor_provider_budget_authority_invalid")
    verifier = value.get("verifier_policy")
    if (
        verifier != {
            "scope": "all_arms",
            "input": "selected_evidence_identities_only",
            "fact_rule": "all_of_frozen_witness_ids",
            "fallback": "one_exact_source_append_before_answer",
            "source_authority": "same_frozen_task_snapshot",
            "final_context_byte_limit": FINAL_CONTEXT_BYTE_BUDGET,
            "unresolved_or_oversize": "refuse_before_answer_dispatch",
        }
        or value.get("verifier_policy_sha256") != digest(canonical(verifier))
    ):
        raise StudyError("successor_verifier_policy_invalid")
    if (
        type(custody) is not dict
        or set(custody) != {"schema_version", "fact_witness_map", "fallback_allowlist"}
        or custody.get("schema_version")
        != "velgraphing-four-arm-successor-witness-custody-v1"
        or value.get("witness_custody_sha256") != digest(canonical(custody))
    ):
        raise StudyError("successor_witness_custody_invalid")
    witness_map = custody.get("fact_witness_map")
    allowlist = custody.get("fallback_allowlist")
    if (
        type(witness_map) is not dict or set(witness_map) != set(TASKS)
        or type(allowlist) is not dict or set(allowlist) != set(TASKS)
        or value.get("fact_witness_map_sha256") != digest(canonical(witness_map))
        or value.get("fallback_allowlist_sha256") != digest(canonical(allowlist))
    ):
        raise StudyError("successor_witness_map_invalid")
    manifest_sources: dict[str, dict[str, Mapping[str, Any]]] = {}
    for corpus_id, corpus in freeze["corpora"].items():
        _, manifest = _read_json(repo_root / corpus["manifest"], "source_manifest_invalid")
        manifest_sources[corpus_id] = {row["path"]: row for row in manifest["sources"]}
    for task_id in TASKS:
        facts = witness_map[task_id]
        candidates = allowlist[task_id]
        expected_fact_ids = {
            row["ask_id"] for row in successor["tasks"][task_id]["required_facts"]
        }
        if (
            type(facts) is not dict or set(facts) != expected_fact_ids
            or type(candidates) is not list or not candidates
        ):
            raise StudyError("successor_witness_map_invalid")
        by_id: dict[str, Mapping[str, Any]] = {}
        sources = manifest_sources[TASK_CORPORA[task_id]]
        for candidate in candidates:
            if (
                type(candidate) is not dict
                or set(candidate) != {"id", "path", "source_sha256", "byte_start", "byte_end"}
                or not _is_sha256(candidate.get("id"))
                or not _is_sha256(candidate.get("source_sha256"))
                or candidate["id"] in by_id
            ):
                raise StudyError("successor_fallback_allowlist_invalid")
            source = sources.get(candidate["path"])
            if (
                source is None or source["sha256"] != candidate["source_sha256"]
                or type(candidate["byte_start"]) is not int
                or type(candidate["byte_end"]) is not int
                or candidate["byte_start"] < 0
                or candidate["byte_end"] <= candidate["byte_start"]
                or candidate["byte_end"] > source["byte_length"]
                or candidate["byte_end"] - candidate["byte_start"] > CANDIDATE_UNIT_BYTE_BUDGET
            ):
                raise StudyError("successor_fallback_allowlist_invalid")
            by_id[candidate["id"]] = candidate
        for fact_id, rule in facts.items():
            if (
                type(fact_id) is not str or type(rule) is not dict
                or set(rule) != {"all_of"} or type(rule["all_of"]) is not list
                or not rule["all_of"] or len(set(rule["all_of"])) != len(rule["all_of"])
                or any(candidate_id not in by_id for candidate_id in rule["all_of"])
            ):
                raise StudyError("successor_witness_map_invalid")
    bindings = value.get("bindings")
    lane_binding = bindings.get("lane_manifest", {}) if type(bindings) is dict else {}
    pending = value["status"] == "pending_lane_manifest_and_final_user_reack"
    if (
        pending and lane_binding != {
            "schema_version": freeze["lane_identity_contract"]["handoff_schema"],
            "entry_count": 32,
            "sha256": None,
            "status": "pending_parent_freeze",
            "thread_id_semantics": THREAD_ID_SEMANTICS,
        }
        or not pending and (
            lane_binding.get("schema_version")
            != freeze["lane_identity_contract"]["handoff_schema"]
            or lane_binding.get("entry_count") != 32
            or not _is_sha256(lane_binding.get("sha256"))
            or lane_binding.get("status") != "frozen"
            or lane_binding.get("thread_id_semantics") != THREAD_ID_SEMANTICS
        )
    ):
        raise StudyError("successor_ttc_binding_invalid")
    expected_bindings = {
        "controller": {
            "path": "scripts/benchmarks/four_arm_study_v1.py",
            "sha256": digest((repo_root / "scripts/benchmarks/four_arm_study_v1.py").read_bytes()),
        },
        "host": {
            "path": "scripts/benchmarks/time_to_correct_host.py",
            "sha256": digest((repo_root / "scripts/benchmarks/time_to_correct_host.py").read_bytes()),
        },
        "calibration": {
            "path": "scripts/benchmarks/time_to_correct_calibration.py",
            "sha256": digest((repo_root / "scripts/benchmarks/time_to_correct_calibration.py").read_bytes()),
        },
        "successor_rubric": {
            "path": SUCCESSOR_RUBRICS,
            "sha256": digest(canonical(successor)),
        },
        "successor_grader_response_contract_sha256": digest(
            canonical(SUCCESSOR_GRADER_RESPONSE_CONTRACT)
        ),
        "source_snapshots": {
            corpus_id: freeze["corpora"][corpus_id]["snapshot_sha256"]
            for corpus_id in sorted(freeze["corpora"])
        },
        "pool_bindings": freeze["candidate_pool_contract"]["pool_bindings"],
        "request_byte_set_sha256": REQUEST_BYTE_SET_SHA256,
        "lane_manifest": lane_binding,
    }
    if bindings != expected_bindings:
        raise StudyError("successor_ttc_binding_invalid")
    required_result_fields = {
        "successor_ttc_contract_sha256", "successor_rubric_sha256",
        "successor_grader_response_contract_sha256", "controller_sha256",
        "host_sha256", "source_snapshots", "pool_bindings",
        "verifier_policy_sha256", "fact_witness_map_sha256",
        "fallback_allowlist_sha256", "request_byte_set_sha256",
        "witness_custody_sha256", "classification", "claim_boundary",
        "lane_manifest_sha256", "attempt_count", "answer_call_count",
        "grader_call_count", "verified_fallback_invocations",
        "wall_time_ns_by_trial", "confirmed_ttc_ns_by_trial", "usage_missingness",
    }
    if value.get("result_contract") != {
        "schema_version": "velgraphing-four-arm-result-v2",
        "required_fields": sorted(required_result_fields),
        "token_policy": "host_reported_only_never_estimate_from_bytes",
    }:
        raise StudyError("successor_result_contract_invalid")
    pending_authority = {
        "answer_task_names": 16,
        "grader_task_names": 16,
        "exact_host_argv_arrays": 32,
        "absolute_python_executable": None,
        "lane_manifest_sha256": None,
        "final_user_reack": [
            "request_byte_set_sha256", "eight_call_cap",
            "total_authorized_provider_budget_usd",
            "operator_reported_spend_to_date_usd",
            "max_additional_provider_spend_usd",
            "lane_manifest_sha256", "absolute_python_executable",
        ],
        "live_lanes_created": 0,
    }
    frozen_authority = dict(pending_authority)
    frozen_authority.update({
        "absolute_python_executable": value.get("remaining_authority", {}).get(
            "absolute_python_executable"
        ),
        "lane_manifest_sha256": lane_binding.get("sha256"),
    })
    ready_authority = dict(frozen_authority)
    ready_authority["final_user_reack"] = []
    authority = value.get("remaining_authority")
    if (
        pending and authority != pending_authority
        or value["status"] == "frozen_pending_final_user_reack" and (
            authority != frozen_authority
            or type(authority.get("absolute_python_executable")) is not str
            or not Path(authority["absolute_python_executable"]).is_absolute()
        )
        or value["status"] == "ready_after_final_user_reack" and (
            authority != ready_authority
            or type(authority.get("absolute_python_executable")) is not str
            or not Path(authority["absolute_python_executable"]).is_absolute()
        )
    ):
        raise StudyError("successor_remaining_authority_invalid")


def _load_successor_witness_custody(path: Path, repo_root: Path) -> dict[str, Any]:
    expected = repo_root / SUCCESSOR_WITNESS_CUSTODY
    supplied = Path(os.path.abspath(path))
    if supplied != expected or any(
        candidate.is_symlink()
        for candidate in (supplied, supplied.parent, supplied.parent.parent)
    ):
        raise StudyError("successor_witness_custody_path_invalid")
    try:
        raw = supplied.read_bytes()
        custody = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise StudyError("successor_witness_custody_invalid") from None
    if type(custody) is not dict or raw != canonical(custody) + b"\n":
        raise StudyError("successor_witness_custody_noncanonical")
    return custody


def load_successor_ttc_contract(
    benchmark_root: Path = DEFAULT_ROOT, repo_root: Path = ROOT, *, custody_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    freeze, _, _ = load_bundle(benchmark_root, repo_root)
    successor = load_successor_rubrics(benchmark_root, repo_root)
    custody = _load_successor_witness_custody(custody_path, repo_root)
    _, contract = _read_json(
        benchmark_root / SUCCESSOR_TTC_CONTRACT, "successor_ttc_contract_invalid",
    )
    _validate_successor_ttc_contract(
        contract, freeze, successor, benchmark_root, repo_root, custody,
    )
    return contract, custody


def _pending_successor_lane_binding(freeze: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": freeze["lane_identity_contract"]["handoff_schema"],
        "entry_count": 32,
        "sha256": None,
        "status": "pending_parent_freeze",
        "thread_id_semantics": THREAD_ID_SEMANTICS,
    }


def _pending_successor_authority() -> dict[str, Any]:
    return {
        "answer_task_names": 16,
        "grader_task_names": 16,
        "exact_host_argv_arrays": 32,
        "absolute_python_executable": None,
        "lane_manifest_sha256": None,
        "final_user_reack": [
            "request_byte_set_sha256", "eight_call_cap",
            "total_authorized_provider_budget_usd",
            "operator_reported_spend_to_date_usd",
            "max_additional_provider_spend_usd",
            "lane_manifest_sha256", "absolute_python_executable",
        ],
        "live_lanes_created": 0,
    }


def _refresh_successor_inputs(
    benchmark_root: Path, repo_root: Path, *, custody_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    freeze, _, historical = load_bundle(benchmark_root, repo_root)
    _, successor = _read_json(
        benchmark_root / SUCCESSOR_RUBRICS, "successor_rubrics_invalid",
    )
    refreshed_successor = deepcopy(successor)
    refreshed_successor["implementation_bindings"] = (
        _current_successor_rubric_bindings(repo_root)
    )
    _validate_successor_rubrics(
        refreshed_successor, historical, benchmark_root, repo_root,
    )

    custody = _load_successor_witness_custody(custody_path, repo_root)
    _, contract = _read_json(
        benchmark_root / SUCCESSOR_TTC_CONTRACT, "successor_ttc_contract_invalid",
    )
    refreshed_contract = deepcopy(contract)
    bindings = refreshed_contract.get("bindings")
    if type(bindings) is not dict:
        raise StudyError("successor_ttc_binding_invalid")
    for name in ("controller", "host", "calibration"):
        binding = bindings.get(name)
        if type(binding) is not dict or set(binding) != {"path", "sha256"}:
            raise StudyError("successor_ttc_binding_invalid")
    successor_rubric = bindings.get("successor_rubric")
    if type(successor_rubric) is not dict or set(successor_rubric) != {
        "path", "sha256",
    }:
        raise StudyError("successor_ttc_binding_invalid")
    refreshed_contract["status"] = "pending_lane_manifest_and_final_user_reack"
    refreshed_contract["bindings"] = {
        **bindings,
        "controller": refreshed_successor["implementation_bindings"]["controller"],
        "host": refreshed_successor["implementation_bindings"]["host"],
        "calibration": {
            "path": "scripts/benchmarks/time_to_correct_calibration.py",
            "sha256": digest(
                (repo_root / "scripts/benchmarks/time_to_correct_calibration.py")
                .read_bytes()
            ),
        },
        "successor_rubric": {
            "path": SUCCESSOR_RUBRICS,
            "sha256": digest(canonical(refreshed_successor)),
        },
        "lane_manifest": _pending_successor_lane_binding(freeze),
    }
    refreshed_contract["remaining_authority"] = _pending_successor_authority()
    _validate_successor_ttc_contract(
        refreshed_contract, freeze, refreshed_successor, benchmark_root, repo_root,
        custody,
    )
    return freeze, refreshed_successor, refreshed_contract, custody


def validate_successor_execution_bindings(
    contract: Mapping[str, Any], freeze: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
    successor_freeze: Mapping[str, Any] | None = None,
) -> None:
    lane_binding = contract["bindings"]["lane_manifest"]
    if (
        contract.get("status") != "ready_after_final_user_reack"
        or successor_freeze is None
        or successor_freeze.get("schema_version") != SUCCESSOR_FREEZE_SCHEMA
        or successor_freeze.get("bindings", {}).get("successor_ttc_core_sha256")
        != digest(canonical(_successor_ttc_core(contract)))
        or successor_freeze.get("bindings", {}).get("pool_bindings")
        != contract["bindings"]["pool_bindings"]
        or lane_binding.get("status") != "frozen"
        or not _is_sha256(lane_binding.get("sha256"))
        or manifest is None
        or digest(canonical(manifest)) != lane_binding["sha256"]
    ):
        raise StudyError("successor_lane_manifest_not_ready")
    validate_lane_manifest(manifest, freeze)
    if manifest["entries"][0]["argv"][0] != contract["remaining_authority"][
        "absolute_python_executable"
    ]:
        raise StudyError("successor_python_binding_stale")


def _candidate_identity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {key: candidate[key] for key in (
        "id", "path", "source_sha256", "byte_start", "byte_end",
    )}


def apply_verified_fallback(
    task_id: str, packet: Mapping[str, Any], order: Sequence[str],
    contract: Mapping[str, Any], custody: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    candidates = packet.get("candidates")
    if type(candidates) is not list or type(order) not in {list, tuple}:
        raise MeasurementError("source_verifier_input_invalid")
    by_id = {row.get("id"): row for row in candidates if type(row) is dict}
    if len(by_id) != len(candidates) or len(order) != len(set(order)) or any(
        candidate_id not in by_id for candidate_id in order
    ):
        raise MeasurementError("source_verifier_input_invalid")
    try:
        facts = custody["fact_witness_map"][task_id]
        allowlist = custody["fallback_allowlist"][task_id]
        verifier_sha = contract["verifier_policy_sha256"]
        allowlist_sha = contract["fallback_allowlist_sha256"]
        witness_sha = contract["fact_witness_map_sha256"]
        snapshot_sha = contract["bindings"]["source_snapshots"][TASK_CORPORA[task_id]]
    except (KeyError, TypeError):
        raise MeasurementError("source_witness_unresolved") from None
    allowed = {row["id"]: row for row in allowlist}
    selected = set(order)
    for candidate_id in selected.intersection(allowed):
        if _candidate_identity(by_id[candidate_id]) != allowed[candidate_id]:
            raise MeasurementError("source_witness_unresolved")
    required_ids = list(facts)
    satisfied = [fact_id for fact_id in required_ids
                 if set(facts[fact_id]["all_of"]).issubset(selected)]
    missing = [fact_id for fact_id in required_ids if fact_id not in satisfied]
    needed = {
        candidate_id for fact_id in missing for candidate_id in facts[fact_id]["all_of"]
        if candidate_id not in selected
    }
    fallback_candidates = [dict(row) for row in allowlist if row["id"] in needed]
    if needed != {row["id"] for row in fallback_candidates}:
        raise MeasurementError("source_witness_unresolved")
    # The answer packet contains the selected shortlist, not the full discovery
    # pool. Exact fallback witnesses are appended below when required.
    final_candidates = [dict(by_id[candidate_id]) for candidate_id in order]
    final_order = list(order)
    for candidate in fallback_candidates:
        final_candidates.append({**candidate, "required": True})
        final_order.append(candidate["id"])
    final_selected = set(final_order)
    unresolved = [fact_id for fact_id in required_ids
                  if not set(facts[fact_id]["all_of"]).issubset(final_selected)]
    selected_rows = [_candidate_identity(by_id[candidate_id]) for candidate_id in order]
    final_by_id = {row["id"]: row for row in final_candidates}
    final_rows = [_candidate_identity(final_by_id[candidate_id]) for candidate_id in final_order]
    selected_bytes = sum(row["byte_end"] - row["byte_start"] for row in selected_rows)
    final_bytes = sum(row["byte_end"] - row["byte_start"] for row in final_rows)
    if unresolved:
        raise MeasurementError("source_witness_unresolved")
    if final_bytes > FINAL_CONTEXT_BYTE_BUDGET:
        raise MeasurementError("verified_fallback_context_exceeded")
    receipt = {
        "required_fact_ids": required_ids,
        "satisfied_fact_ids": satisfied,
        "missing_fact_ids": missing,
        "post_fallback_missing_fact_ids": unresolved,
        "selected_context_sha256": digest(canonical(selected_rows)),
        "final_context_sha256": digest(canonical(final_rows)),
        "selected_context_bytes": selected_bytes,
        "final_context_bytes": final_bytes,
        "fallback_eligible": bool(missing),
        "exact_fallback_candidates": fallback_candidates,
        "fallback_invocations": 1 if fallback_candidates else 0,
        "source_snapshot_sha256": snapshot_sha,
        "verifier_policy_sha256": verifier_sha,
        "fact_witness_map_sha256": witness_sha,
        "fallback_allowlist_sha256": allowlist_sha,
        "witness_custody_sha256": contract["witness_custody_sha256"],
    }
    return ({**packet, "candidates": final_candidates}, final_order, receipt)


def _bound_grader_contract(freeze: Mapping[str, Any]) -> dict[str, Any]:
    if (
        freeze.get("implementation_bindings", {}).get("grader_response_contract_sha256")
        != digest(canonical(GRADER_RESPONSE_CONTRACT))
    ):
        raise StudyError("execution_binding_stale")
    return GRADER_RESPONSE_CONTRACT


def _require_current_execution_bindings(
    freeze: Mapping[str, Any], benchmark_root: Path, repo_root: Path,
) -> None:
    controller = freeze.get("controller", {})
    bindings = freeze.get("implementation_bindings", {})
    host = bindings.get("host", {})
    rubric = freeze.get("artifacts", {}).get("rubrics", {})
    rubric_path = benchmark_root / rubric.get("path", "")
    if (
        controller.get("sha256")
        != digest((repo_root / "scripts/benchmarks/four_arm_study_v1.py").read_bytes())
        or host.get("sha256")
        != digest((repo_root / "scripts/benchmarks/time_to_correct_host.py").read_bytes())
        or not rubric_path.is_file()
        or rubric.get("sha256") != digest(rubric_path.read_bytes())
    ):
        raise StudyError("execution_binding_stale")
    _bound_grader_contract(freeze)


def validate_lane_manifest(value: Mapping[str, Any], freeze: Mapping[str, Any], *,
                           python_executable: str | Path | None = None,
                           run_root: Path | None = None) -> None:
    entries = value.get("entries")
    if (
        set(value) != {"schema_version", "entries"}
        or value.get("schema_version") != freeze["lane_identity_contract"]["handoff_schema"]
        or type(entries) is not list
        or len(entries) != 32
    ):
        raise StudyError("lane_manifest_invalid")
    if python_executable is None and run_root is None:
        first = entries[0]
        argv = first.get("argv") if type(first) is dict else None
        if (
            type(argv) is not list or not argv or type(argv[0]) is not str
            or argv.count("--run-root") != 1
        ):
            raise StudyError("lane_manifest_invalid")
        index = argv.index("--run-root") + 1
        if index == len(argv) or type(argv[index]) is not str:
            raise StudyError("lane_manifest_invalid")
        try:
            run_root = validate_run_root(argv[index])
        except HandoffError:
            raise StudyError("lane_manifest_invalid") from None
        python_executable = argv[0]
    expected = {(trial_id, role) for trial_id in DISPATCH for role in ("answer", "grader")}
    observed: set[tuple[str, str]] = set()
    threads: set[str] = set()
    for row in entries:
        if type(row) is not dict or set(row) != {
            "trial_id", "role", "thread_id", "model", "reasoning", "argv", "argv_sha256",
        }:
            raise StudyError("lane_manifest_invalid")
        key = (row["trial_id"], row["role"])
        role = freeze["lane_identity_contract"].get(row["role"])
        argv = row["argv"]
        expected_argv = lane_argv(
            row["trial_id"], row["role"], python_executable=python_executable,
            run_root=run_root,
        )
        if (
            key not in expected or key in observed or type(role) is not dict
            or row["model"] != role["model"] or row["reasoning"] != role["reasoning"]
            or not _is_collaboration_task_name(row["thread_id"])
            or row["thread_id"] in threads
            or argv != expected_argv
            or row["argv_sha256"] != _sha256(argv)
        ):
            raise StudyError("lane_manifest_invalid")
        observed.add(key)
        threads.add(row["thread_id"])
    if observed != expected:
        raise StudyError("lane_manifest_invalid")


def lane_argv(trial_id: str, role: str, repo_root: Path = ROOT, *,
              python_executable: str | Path | None = None,
              run_root: Path | None = None) -> list[str]:
    if trial_id not in DISPATCH or role not in {"answer", "grader"}:
        raise StudyError("lane_manifest_invalid")
    target = run_root or repo_root / ".velgraphing-local/velgraphing-four-arm-study-v1"
    try:
        return handoff_argv(target, trial_id, role, 600, python_executable)
    except MeasurementError as error:
        raise StudyError(str(error)) from None


def freeze_lane_manifest(bindings: Mapping[str, Any], freeze: Mapping[str, Any],
                         destination: Path, python_executable: str | Path, *,
                         replace_existing: bool = False) -> str:
    rows = bindings.get("bindings")
    if (
        set(bindings) != {"schema_version", "bindings"}
        or bindings.get("schema_version") != "velgraphing-four-arm-lane-bindings-v1"
        or type(rows) is not list or len(rows) != len(DISPATCH)
    ):
        raise StudyError("lane_bindings_invalid")
    by_trial = {}
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"trial_id", "answer_thread_id", "grader_thread_id"}
            or row.get("trial_id") not in DISPATCH or row["trial_id"] in by_trial
            or any(not _is_collaboration_task_name(row.get(key))
                   for key in ("answer_thread_id", "grader_thread_id"))
        ):
            raise StudyError("lane_bindings_invalid")
        by_trial[row["trial_id"]] = row
    if set(by_trial) != set(DISPATCH):
        raise StudyError("lane_bindings_invalid")
    entries = []
    for trial_id in DISPATCH:
        for role in ("answer", "grader"):
            contract = freeze["lane_identity_contract"][role]
            argv = lane_argv(
                trial_id, role, python_executable=python_executable,
                run_root=destination.parent,
            )
            entries.append({
                "trial_id": trial_id, "role": role,
                # The frozen handoff field stores task_name, not host thread ID.
                "thread_id": by_trial[trial_id][f"{role}_thread_id"],
                "model": contract["model"], "reasoning": contract["reasoning"],
                "argv": argv, "argv_sha256": _sha256(argv),
            })
    manifest = {"schema_version": freeze["lane_identity_contract"]["handoff_schema"],
                "entries": entries}
    validate_lane_manifest(
        manifest, freeze, python_executable=python_executable,
        run_root=destination.parent,
    )
    if replace_existing and (
        destination.is_symlink()
        or destination.exists() and not destination.is_file()
    ):
        raise StudyError("lane_manifest_path_invalid")
    try:
        atomic_write(destination, canonical(manifest), replace=replace_existing)
    except HandoffError as error:
        raise StudyError(str(error)) from None
    return digest(canonical(manifest))


def validate_preflight(
    value: Mapping[str, Any], freeze: Mapping[str, Any], *,
    current_candidate: bool = False,
) -> int:
    rows = value.get("trials")
    pools = value.get("pools")
    if (
        set(value) != {
            "schema_version", "study_id", "product_commit", "package_candidate_sha256",
            "question_registry_sha256", "rubric_registry_sha256", "candidate_budgets",
            "provider_calls_executed", "retries", "planned_jev_calls", "pools", "trials",
        }
        or value.get("schema_version") != PREFLIGHT_SCHEMA
        or value.get("study_id") != freeze["study_id"]
        or value.get("product_commit") != freeze["product"]["commit"]
        or value.get("package_candidate_sha256")
        != freeze["product"]["package_candidate_sha256"]
        or value.get("question_registry_sha256")
        != freeze["artifacts"]["questions"]["sha256"]
        or value.get("rubric_registry_sha256")
        != freeze["artifacts"]["rubrics"]["sha256"]
        or value.get("candidate_budgets") != {
            "retrieval_nodes": RETRIEVAL_NODE_LIMIT,
            "candidate_count": CANDIDATE_LIMIT,
            "aggregate_excerpt_bytes": CANDIDATE_AGGREGATE_BYTE_BUDGET,
            "per_candidate_bytes": CANDIDATE_UNIT_BYTE_BUDGET,
            "final_context_bytes": FINAL_CONTEXT_BYTE_BUDGET,
        }
        or value.get("provider_calls_executed") != 0
        or value.get("retries") != 0
        or type(pools) is not list or len(pools) != 8
        or type(rows) is not list or len(rows) != 16
    ):
        raise StudyError("preflight_invalid")
    observed_pools: dict[str, Mapping[str, Any]] = {}
    for pool in pools:
        if type(pool) is not dict or set(pool) != {
            "pool_id", "task_id", "route", "source_snapshot_sha256",
            "pool_sha256", "candidate_set_sha256", "candidate_count",
            "aggregate_excerpt_bytes", "required_candidate_count",
            "relationship_candidate_count", "relationship_delta_present",
            "baseline_selected_candidate_count", "baseline_selected_excerpt_bytes",
            "baseline_omitted_candidate_count", "baseline_omitted_excerpt_bytes",
            "request_sha256", "request_bytes", "source_set_sha256",
            "selection_decision_sha256", "eligibility",
        }:
            raise StudyError("preflight_pool_invalid")
        pool_id = pool["pool_id"]
        task_id = pool["task_id"]
        route = pool["route"]
        eligibility = pool["eligibility"]
        if type(eligibility) is not dict or set(eligibility) != {
            "source_revalidated", "fail_closed", "selection_reason", "jev_reason",
            "jev_call_could_affect_selection", "call_disposition",
        }:
            raise StudyError("preflight_pool_invalid")
        can_affect = eligibility["jev_call_could_affect_selection"]
        expected_disposition = "planned" if can_affect else "skip_no_membership_effect"
        if (
            task_id not in TASKS or route not in {"direct", "graph"}
            or pool_id != f"{route}:{task_id}" or pool_id in observed_pools
            or not _is_sha256(pool["source_snapshot_sha256"])
            or pool["source_snapshot_sha256"]
            != freeze["corpora"][TASK_CORPORA[task_id]]["snapshot_sha256"]
            or not _is_sha256(pool["pool_sha256"])
            or not _is_sha256(pool["candidate_set_sha256"])
            or not _is_sha256(pool["selection_decision_sha256"])
            or freeze["candidate_pool_contract"]["pool_bindings"].get(pool_id)
            != pool["pool_sha256"]
            or type(pool["candidate_count"]) is not int
            or not 1 <= pool["candidate_count"] <= CANDIDATE_LIMIT
            or type(pool["aggregate_excerpt_bytes"]) is not int
            or not 1 <= pool["aggregate_excerpt_bytes"] <= CANDIDATE_AGGREGATE_BYTE_BUDGET
            or type(pool["required_candidate_count"]) is not int
            or not 0 <= pool["required_candidate_count"] <= pool["candidate_count"]
            or type(pool["relationship_candidate_count"]) is not int
            or not 0 <= pool["relationship_candidate_count"] <= pool["candidate_count"]
            or pool["relationship_delta_present"]
            is not (pool["relationship_candidate_count"] > 0)
            or (route == "direct" and pool["relationship_candidate_count"] != 0)
            or any(
                type(pool[name]) is not int or pool[name] < 0
                for name in (
                    "baseline_selected_candidate_count", "baseline_selected_excerpt_bytes",
                    "baseline_omitted_candidate_count", "baseline_omitted_excerpt_bytes",
                )
            )
            or pool["baseline_selected_candidate_count"]
            + pool["baseline_omitted_candidate_count"] != pool["candidate_count"]
            or pool["baseline_selected_excerpt_bytes"]
            + pool["baseline_omitted_excerpt_bytes"] != pool["aggregate_excerpt_bytes"]
            or type(can_affect) is not bool
            or eligibility["source_revalidated"] is not True
            or eligibility["fail_closed"] is not False
            or eligibility["selection_reason"] != "verified_ranked_context_selected"
            or eligibility["call_disposition"] != expected_disposition
            or (can_affect and eligibility["jev_reason"] != "jev_observation_missing")
            or (can_affect and (
                not _is_sha256(pool["request_sha256"])
                or not _is_sha256(pool["source_set_sha256"])
                or type(pool["request_bytes"]) is not int
                or pool["request_bytes"] <= 0
            ))
            or (not can_affect and any(
                pool[name] is not None
                for name in ("request_sha256", "request_bytes", "source_set_sha256")
            ))
        ):
            raise StudyError("preflight_pool_invalid")
        observed_pools[pool_id] = pool
    expected_pool_ids = {
        f"{route}:{task_id}" for task_id in TASKS for route in ("direct", "graph")
    }
    if set(observed_pools) != expected_pool_ids:
        raise StudyError("preflight_pool_invalid")

    observed: dict[str, Mapping[str, Any]] = {}
    planned = 0
    for row in rows:
        if type(row) is not dict or set(row) != {
            "trial_id", "task_id", "arm", "pool_id", "pool_sha256",
            "selection_decision_sha256", "selection_decision_reason",
            "jev_call_could_affect_selection",
            "call_disposition",
        }:
            raise StudyError("preflight_invalid")
        trial_id = row["trial_id"]
        arm = row["arm"]
        task_id = row["task_id"]
        arm_contract = ARMS.get(arm)
        if arm_contract is None:
            raise StudyError("preflight_invalid")
        pool = observed_pools.get(f"{arm_contract['route']}:{task_id}")
        if pool is None:
            raise StudyError("preflight_invalid")
        enabled = arm_contract["jev"] == "on"
        can_affect = bool(pool["eligibility"]["jev_call_could_affect_selection"])
        expected_disposition = (
            "treatment_off" if not enabled
            else "planned" if can_affect
            else "skip_no_membership_effect"
        )
        expected_reason = "jev_disabled" if not enabled else pool["eligibility"]["jev_reason"]
        expected_decision = (
            pool["selection_decision_sha256"]
            if enabled
            else _sha256({
                "trial_id": trial_id,
                "pool_sha256": pool["pool_sha256"],
                "call_disposition": expected_disposition,
                "reason": expected_reason,
            })
        )
        if (
            trial_id != f"{arm}-{task_id}" or trial_id not in DISPATCH
            or trial_id in observed or row["pool_id"] != f"{arm_contract['route']}:{task_id}"
            or row["pool_sha256"] != pool["pool_sha256"]
            or row["selection_decision_sha256"] != expected_decision
            or row["selection_decision_reason"] != expected_reason
            or row["jev_call_could_affect_selection"] is not (can_affect if enabled else False)
            or row["call_disposition"] != expected_disposition
        ):
            raise StudyError("preflight_invalid")
        observed[trial_id] = row
        planned += expected_disposition == "planned"
    if (
        set(observed) != set(DISPATCH)
        or planned != value.get("planned_jev_calls")
        or planned > freeze["jev"]["max_calls"]
        or not current_candidate and planned != freeze["jev"]["planned_calls"]
    ):
        raise StudyError("preflight_invalid")
    for task_id in TASKS:
        if (
            observed[f"A-{task_id}"]["pool_sha256"]
            != observed[f"B-{task_id}"]["pool_sha256"]
            or observed[f"C-{task_id}"]["pool_sha256"]
            != observed[f"D-{task_id}"]["pool_sha256"]
        ):
            raise StudyError("preflight_pair_mismatch")
    planned_trials = [
        row["trial_id"] for row in rows if row["call_disposition"] == "planned"
    ]
    skipped_trials = [
        row["trial_id"]
        for row in rows if row["call_disposition"] == "skip_no_membership_effect"
    ]
    decision_bindings = {
        row["trial_id"]: row["selection_decision_sha256"]
        for row in rows if ARMS[row["arm"]]["jev"] == "on"
    }
    if (
        not current_candidate
        and (
            freeze["jev"]["planned_trials"] != planned_trials
            or freeze["jev"]["skipped_trials"] != skipped_trials
            or freeze["jev"]["decision_bindings"] != decision_bindings
        )
    ):
        raise StudyError("preflight_invalid")
    return planned


def _current_package_binding(repo_root: Path) -> dict[str, str]:
    path = "plugins/graph-engineering/.codex-plugin/release-manifest.json"
    raw, release = _read_json(repo_root / path, "package_binding_invalid")
    package = release.get("package") if type(release) is dict else None
    if (
        type(package) is not dict
        or not _is_sha256(release.get("candidate_sha256"))
        or type(package.get("name")) is not str
        or type(package.get("version")) is not str
    ):
        raise StudyError("package_binding_invalid")
    return {
        "manifest_path": path,
        "manifest_sha256": digest(raw),
        "name": package["name"],
        "version": package["version"],
        "candidate_sha256": release["candidate_sha256"],
    }


def _successor_ttc_core(contract: Mapping[str, Any]) -> dict[str, Any]:
    core = {key: value for key, value in contract.items()
            if key not in {"status", "remaining_authority"}}
    core["bindings"] = {
        key: value for key, value in contract["bindings"].items()
        if key != "lane_manifest"
    }
    return core


def _build_successor_freeze(
    freeze: Mapping[str, Any], successor: Mapping[str, Any],
    contract: Mapping[str, Any], planned_jev_calls: int,
    benchmark_root: Path, repo_root: Path,
) -> dict[str, Any]:
    if planned_jev_calls != 8:
        raise StudyError("successor_jev_budget_invalid")
    ready = contract["status"] == "ready_after_final_user_reack"
    if contract["status"] not in {
        "pending_lane_manifest_and_final_user_reack",
        "frozen_pending_final_user_reack", "ready_after_final_user_reack",
    }:
        raise StudyError("successor_ttc_contract_invalid")
    ttc_bindings = contract["bindings"]
    implementation = {
        key: ttc_bindings[key]
        for key in ("controller", "host", "calibration")
    }
    return {
        "schema_version": SUCCESSOR_FREEZE_SCHEMA,
        "status": contract["status"],
        "study_id": freeze["study_id"],
        "bindings": {
            "historical_freeze_sha256": digest(
                (benchmark_root / "freeze.json").read_bytes()
            ),
            "historical_preflight_sha256": digest(
                (benchmark_root / "preflight.json").read_bytes()
            ),
            "package_candidate": _current_package_binding(repo_root),
            "implementation": implementation,
            "successor_rubric_sha256": digest(canonical(successor)),
            "successor_ttc_core_sha256": digest(canonical(
                _successor_ttc_core(contract)
            )),
            "source_snapshots": ttc_bindings["source_snapshots"],
            "pool_bindings": ttc_bindings["pool_bindings"],
            "request_byte_set_sha256": ttc_bindings["request_byte_set_sha256"],
            "fact_witness_map_sha256": contract["fact_witness_map_sha256"],
            "fallback_allowlist_sha256": contract["fallback_allowlist_sha256"],
            "witness_custody_sha256": contract["witness_custody_sha256"],
        },
        "trial_matrix": {
            "tasks": list(TASKS),
            "arms": SUCCESSOR_ARM_LABELS,
            "dispatch_order": list(DISPATCH),
            "trial_count": 16,
        },
        "execution_policy": {
            "fresh_answer_lanes": 16,
            "fresh_grader_lanes": 16,
            "exact_host_argv_arrays": 32,
            "fresh_no_history": True,
            "lane_reuse": False,
            "answer_calls_per_trial": 1,
            "grader_calls_per_trial": 1,
            "answer_repairs": 0,
            "task_retries": 0,
            "jev_max_calls": 8,
            "planned_jev_calls": planned_jev_calls,
            "jev_retries": 0,
            "provider_calls_executed": 0,
            "answer_tasks_created": 0,
            "grader_tasks_created": 0,
            "live_lanes_created": 0,
            "execution_ready": ready,
            "final_user_reack_required": not ready,
            "provider_budget_authority": contract["provider_budget_authority"],
            "max_additional_provider_spend_usd": str(
                MAX_ADDITIONAL_PROVIDER_SPEND_USD
            ),
            "provider_spend_authorized": ready,
        },
        "telemetry_schema": freeze["telemetry_schema"],
        "result_contract": contract["result_contract"],
        "claim_boundary": contract["classification"]["claim_boundary"],
        "provider_boundary": {
            "provider_performance_publication": (
                "forbidden_without_separate_provider_permission"
            ),
            "provider_specific_results": "private_without_separate_permission",
            "request_bytes_are_not_a_cost_or_reservation_bound": True,
        },
    }


def approve_successor(
    benchmark_root: Path, custody_path: Path, *,
    approved_max_live_jev_calls: int,
    approved_request_set: str,
    approved_max_additional_provider_spend_usd: str,
    approved_manifest: str,
    approved_python: str,
    repo_root: Path = ROOT,
) -> dict[str, str | int | bool]:
    """Materialize the exact final user re-ack without making external calls."""
    freeze, _, _ = load_bundle(benchmark_root, repo_root)
    successor = load_successor_rubrics(benchmark_root, repo_root)
    contract, custody = load_successor_ttc_contract(
        benchmark_root, repo_root, custody_path=custody_path,
    )
    successor_freeze, successor_preflight = load_successor_freeze(
        benchmark_root, repo_root, custody_path=custody_path,
    )
    if contract["status"] != "frozen_pending_final_user_reack":
        raise StudyError("successor_approval_not_pending")
    lane_binding = contract["bindings"]["lane_manifest"]
    expected_manifest = lane_binding["sha256"]
    expected_python = contract["remaining_authority"][
        "absolute_python_executable"
    ]
    if approved_max_live_jev_calls != 8:
        raise StudyError("approval_jev_cap_mismatch")
    if approved_request_set != REQUEST_BYTE_SET_SHA256:
        raise StudyError("approval_request_byte_set_mismatch")
    _validate_approved_additional_provider_spend(
        approved_max_additional_provider_spend_usd,
    )
    if approved_manifest != expected_manifest:
        raise StudyError("approval_lane_manifest_mismatch")
    if (
        type(approved_python) is not str
        or not Path(approved_python).is_absolute()
        or approved_python != expected_python
    ):
        raise StudyError("approval_python_executable_mismatch")
    if (
        successor_freeze["status"] != "frozen_pending_final_user_reack"
        or successor_freeze["execution_policy"]["execution_ready"]
        or successor_freeze["execution_policy"]["provider_spend_authorized"]
        or successor_preflight["executed_calls"]
        != {"answer": 0, "grader": 0, "jev": 0, "provider": 0}
        or successor_preflight["retries"] != 0
    ):
        raise StudyError("successor_approval_state_invalid")

    ready_contract = deepcopy(contract)
    ready_contract["status"] = "ready_after_final_user_reack"
    ready_contract["remaining_authority"]["final_user_reack"] = []
    _validate_successor_ttc_contract(
        ready_contract, freeze, successor, benchmark_root, repo_root,
        custody,
    )
    ready_freeze = _build_successor_freeze(
        freeze, successor, ready_contract, 8, benchmark_root, repo_root,
    )
    ready_freeze_raw = _json_bytes(ready_freeze)
    ready_freeze_sha = digest(ready_freeze_raw)
    ready_preflight = _build_successor_preflight(
        ready_freeze_sha,
        successor_preflight["source_free_preflight"],
        successor_preflight["source_preflight_sha256"],
        successor_preflight["pool_artifact_sha256"],
        ready_freeze,
    )
    _validate_successor_freeze(
        ready_freeze, freeze, successor, ready_contract, 8,
        benchmark_root, repo_root,
    )
    _validate_successor_preflight(
        ready_preflight, ready_freeze, ready_freeze_sha, freeze, benchmark_root,
    )

    contract_path = benchmark_root / SUCCESSOR_TTC_CONTRACT
    freeze_path = benchmark_root / SUCCESSOR_FREEZE
    preflight_path = benchmark_root / SUCCESSOR_PREFLIGHT
    _write_json(contract_path, ready_contract)
    _write_json(freeze_path, ready_freeze)
    ready_preflight_sha = _write_json(preflight_path, ready_preflight)
    return {
        "successor_ttc_contract_sha256": digest(_json_bytes(ready_contract)),
        "successor_freeze_sha256": ready_freeze_sha,
        "successor_preflight_sha256": ready_preflight_sha,
        "execution_ready": True,
        "provider_spend_authorized": True,
    }


def _build_successor_preflight(
    successor_freeze_sha256: str, source_preflight: Mapping[str, Any],
    source_preflight_sha256: str, pool_artifact_sha256: str,
    successor_freeze: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SUCCESSOR_PREFLIGHT_SCHEMA,
        "successor_freeze_sha256": successor_freeze_sha256,
        "lane_set": "velgraphing-corpus-pilot-v1/v4",
        "source_snapshots": successor_freeze["bindings"]["source_snapshots"],
        "pool_bindings": successor_freeze["bindings"]["pool_bindings"],
        "request_byte_set_sha256": successor_freeze["bindings"][
            "request_byte_set_sha256"
        ],
        "planned_jev_calls": successor_freeze["execution_policy"][
            "planned_jev_calls"
        ],
        "max_jev_calls": successor_freeze["execution_policy"]["jev_max_calls"],
        "executed_calls": {"answer": 0, "grader": 0, "jev": 0, "provider": 0},
        "retries": 0,
        "pool_artifact_sha256": pool_artifact_sha256,
        "source_preflight_sha256": source_preflight_sha256,
        "source_free_preflight": source_preflight,
    }


def _validate_successor_freeze(
    value: Mapping[str, Any], freeze: Mapping[str, Any],
    successor: Mapping[str, Any], contract: Mapping[str, Any],
    planned_jev_calls: int, benchmark_root: Path, repo_root: Path,
) -> None:
    expected = _build_successor_freeze(
        freeze, successor, contract, planned_jev_calls, benchmark_root, repo_root,
    )
    if value != expected:
        raise StudyError("successor_freeze_invalid")


def _validate_successor_preflight(
    value: Mapping[str, Any], successor_freeze: Mapping[str, Any],
    successor_freeze_sha256: str, freeze: Mapping[str, Any],
    benchmark_root: Path,
) -> None:
    source_preflight = value.get("source_free_preflight")
    if type(source_preflight) is not dict:
        raise StudyError("successor_preflight_invalid")
    expected_source_sha = digest(_json_bytes(source_preflight))
    if value.get("source_preflight_sha256") != expected_source_sha:
        raise StudyError("successor_preflight_invalid")
    try:
        planned = validate_preflight(
            source_preflight, freeze, current_candidate=True,
        )
    except StudyError:
        raise StudyError("successor_preflight_invalid") from None
    if (
        planned != 8
        or value.get("source_preflight_sha256") != expected_source_sha
        or not _is_sha256(value.get("pool_artifact_sha256"))
        or value != _build_successor_preflight(
            successor_freeze_sha256, source_preflight, expected_source_sha,
            value["pool_artifact_sha256"], successor_freeze,
        )
    ):
        raise StudyError("successor_preflight_invalid")


def _write_json_batch(values: Mapping[Path, Mapping[str, Any]]) -> dict[Path, str]:
    temporary: list[tuple[Path, Path]] = []
    try:
        for path, value in values.items():
            if path.is_symlink() or path.parent.is_symlink():
                raise StudyError("output_path_invalid")
            path.parent.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            temp_path = Path(name)
            with os.fdopen(handle, "wb") as stream:
                stream.write(_json_bytes(value))
            temporary.append((temp_path, path))
        hashes = {
            path: digest(_json_bytes(value)) for path, value in values.items()
        }
        for temp_path, path in temporary:
            temp_path.replace(path)
        return hashes
    except OSError:
        raise StudyError("output_path_invalid") from None
    finally:
        for temp_path, _ in temporary:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def freeze_successor(
    benchmark_root: Path, lanes_root: Path, custody_path: Path,
    repo_root: Path = ROOT, *, refresh: bool = False,
) -> dict[str, str | int]:
    if refresh:
        freeze, successor, contract, _ = _refresh_successor_inputs(
            benchmark_root, repo_root, custody_path=custody_path,
        )
        _, questions, _ = load_bundle(benchmark_root, repo_root)
        result = prepare_study(
            freeze, questions, benchmark_root, lanes_root, None, None, repo_root,
            persist=False,
        )
        preflight = result.pop("_preflight")
        pools = result.pop("_local_artifact")
        if type(preflight) is not dict or type(pools) is not dict:
            raise StudyError("successor_preflight_invalid")
        planned = validate_preflight(
            preflight, freeze, current_candidate=True,
        )
        if (
            result["pool_count"] != 8
            or result["planned_jev_calls"] != 8
            or result["skipped_jev_calls"] != 0
            or planned != 8
            or pools.get("provider_calls_executed") != 0
        ):
            raise StudyError("successor_pool_reproduction_mismatch")
        source_preflight_sha = result["preflight_sha256"]
        pool_sha = result["local_artifact_sha256"]
        request_bytes = {
            row["trial_id"]: next(
                pool["jev_preview"]["request_bytes"]
                for pool in pools["pools"]
                if pool["identity"]["pool_id"] == row["pool_id"]
            )
            for row in preflight["trials"] if row["call_disposition"] == "planned"
        }
        if digest(canonical(request_bytes)) != REQUEST_BYTE_SET_SHA256:
            raise StudyError("successor_request_byte_set_invalid")
    else:
        freeze, questions, _ = load_bundle(benchmark_root, repo_root)
        successor = load_successor_rubrics(benchmark_root, repo_root)
        contract, _ = load_successor_ttc_contract(
            benchmark_root, repo_root, custody_path=custody_path,
        )
        result = prepare_study(
            freeze, questions, benchmark_root, lanes_root, None, None, repo_root,
            persist=False,
        )
        preflight = result.pop("_preflight")
        pools = result.pop("_local_artifact")
        if type(preflight) is not dict or type(pools) is not dict:
            raise StudyError("successor_preflight_invalid")
        planned = validate_preflight(preflight, freeze)
        if (
            result["pool_count"] != 8
            or result["planned_jev_calls"] != 8
            or result["skipped_jev_calls"] != 0
            or result["preflight_sha256"]
            != freeze["artifacts"]["preflight"]["sha256"]
            or result["local_artifact_sha256"] != LOCAL_POOL_SHA256
            or planned != 8
            or {
                row["pool_id"]: row["pool_sha256"] for row in preflight["pools"]
            } != contract["bindings"]["pool_bindings"]
            or pools.get("provider_calls_executed") != 0
        ):
            raise StudyError("successor_pool_reproduction_mismatch")
        source_preflight_sha = result["preflight_sha256"]
        pool_sha = result["local_artifact_sha256"]
        request_bytes = {
            row["trial_id"]: next(
                pool["jev_preview"]["request_bytes"]
                for pool in pools["pools"]
                if pool["identity"]["pool_id"] == row["pool_id"]
            )
            for row in preflight["trials"] if row["call_disposition"] == "planned"
        }
        if digest(canonical(request_bytes)) != REQUEST_BYTE_SET_SHA256:
            raise StudyError("successor_request_byte_set_invalid")
    successor_freeze = _build_successor_freeze(
        freeze, successor, contract, planned, benchmark_root, repo_root,
    )
    freeze_raw = _json_bytes(successor_freeze)
    freeze_sha = digest(freeze_raw)
    successor_preflight = _build_successor_preflight(
        freeze_sha, preflight, source_preflight_sha, pool_sha, successor_freeze,
    )
    preflight_raw = _json_bytes(successor_preflight)
    _validate_successor_freeze(
        successor_freeze, freeze, successor, contract, planned,
        benchmark_root, repo_root,
    )
    _validate_successor_preflight(
        successor_preflight, successor_freeze, freeze_sha, freeze, benchmark_root,
    )
    if not refresh:
        freeze_path = benchmark_root / SUCCESSOR_FREEZE
        preflight_path = benchmark_root / SUCCESSOR_PREFLIGHT
        if (
            freeze_path.exists() and freeze_path.read_bytes() != freeze_raw
        ):
            raise StudyError("successor_freeze_conflict")
        if (
            preflight_path.exists() and preflight_path.read_bytes() != preflight_raw
        ):
            raise StudyError("successor_preflight_conflict")
        hashes = _write_json_batch({
            freeze_path: successor_freeze,
            preflight_path: successor_preflight,
        })
    else:
        hashes = _write_json_batch({
            benchmark_root / SUCCESSOR_RUBRICS: successor,
            benchmark_root / SUCCESSOR_TTC_CONTRACT: contract,
            benchmark_root / SUCCESSOR_FREEZE: successor_freeze,
            benchmark_root / SUCCESSOR_PREFLIGHT: successor_preflight,
        })
    return {
        "successor_freeze_sha256": hashes[benchmark_root / SUCCESSOR_FREEZE],
        "successor_preflight_sha256": hashes[benchmark_root / SUCCESSOR_PREFLIGHT],
        "planned_jev_calls": planned,
        "pool_count": 8,
        "trial_count": 16,
        "answer_calls_executed": 0,
        "grader_calls_executed": 0,
        "provider_calls_executed": 0,
        "retries": 0,
    }


def bind_successor_lane_manifest(
    benchmark_root: Path, run_root: Path, custody_path: Path,
    python_executable: str | Path, repo_root: Path = ROOT,
) -> dict[str, str | bool]:
    freeze, _, _ = load_bundle(benchmark_root, repo_root)
    successor = load_successor_rubrics(benchmark_root, repo_root)
    contract, custody = load_successor_ttc_contract(
        benchmark_root, repo_root, custody_path=custody_path,
    )
    if contract["status"] != "pending_lane_manifest_and_final_user_reack":
        raise StudyError("successor_ttc_binding_invalid")
    run_root = validate_run_root(str(run_root.resolve()))
    manifest_path = run_root / "lane-manifest.json"
    raw, manifest = read_canonical(manifest_path)
    validate_lane_manifest(manifest, freeze)
    python_executable = str(python_executable)
    if (
        not Path(python_executable).is_absolute()
        or not Path(python_executable).is_file()
        or not os.access(python_executable, os.X_OK)
    ):
        raise StudyError("successor_python_binding_stale")
    entries = manifest["entries"]
    if any(row["argv"][0] != python_executable for row in entries):
        raise StudyError("successor_python_binding_stale")
    manifest_sha = digest(raw)
    frozen_contract = deepcopy(contract)
    frozen_contract["status"] = "frozen_pending_final_user_reack"
    frozen_contract["bindings"]["lane_manifest"] = {
        "schema_version": freeze["lane_identity_contract"]["handoff_schema"],
        "entry_count": 32,
        "sha256": manifest_sha,
        "status": "frozen",
        "thread_id_semantics": THREAD_ID_SEMANTICS,
    }
    frozen_contract["remaining_authority"]["absolute_python_executable"] = (
        python_executable
    )
    frozen_contract["remaining_authority"]["lane_manifest_sha256"] = manifest_sha
    frozen_contract["remaining_authority"]["final_user_reack"] = (
        _pending_successor_authority()["final_user_reack"]
    )
    _validate_successor_ttc_contract(
        frozen_contract, freeze, successor, benchmark_root, repo_root, custody,
    )
    _, source_successor_preflight = _read_json(
        benchmark_root / SUCCESSOR_PREFLIGHT, "successor_preflight_invalid",
    )
    source_preflight = source_successor_preflight.get("source_free_preflight")
    if type(source_preflight) is not dict:
        raise StudyError("successor_preflight_invalid")
    successor_freeze = _build_successor_freeze(
        freeze, successor, frozen_contract, 8, benchmark_root, repo_root,
    )
    successor_freeze_sha = digest(_json_bytes(successor_freeze))
    successor_preflight = _build_successor_preflight(
        successor_freeze_sha,
        source_preflight,
        source_successor_preflight["source_preflight_sha256"],
        source_successor_preflight["pool_artifact_sha256"],
        successor_freeze,
    )
    _validate_successor_freeze(
        successor_freeze, freeze, successor, frozen_contract, 8,
        benchmark_root, repo_root,
    )
    _validate_successor_preflight(
        successor_preflight, successor_freeze, successor_freeze_sha,
        freeze, benchmark_root,
    )
    hashes = _write_json_batch({
        benchmark_root / SUCCESSOR_TTC_CONTRACT: frozen_contract,
        benchmark_root / SUCCESSOR_FREEZE: successor_freeze,
        benchmark_root / SUCCESSOR_PREFLIGHT: successor_preflight,
    })
    return {
        "lane_manifest_sha256": manifest_sha,
        "successor_ttc_contract_sha256": hashes[
            benchmark_root / SUCCESSOR_TTC_CONTRACT
        ],
        "successor_freeze_sha256": hashes[benchmark_root / SUCCESSOR_FREEZE],
        "successor_preflight_sha256": hashes[
            benchmark_root / SUCCESSOR_PREFLIGHT
        ],
        "execution_ready": False,
    }


def load_successor_freeze(
    benchmark_root: Path = DEFAULT_ROOT, repo_root: Path = ROOT, *,
    custody_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    freeze, _, _ = load_bundle(benchmark_root, repo_root)
    successor = load_successor_rubrics(benchmark_root, repo_root)
    contract, _ = load_successor_ttc_contract(
        benchmark_root, repo_root, custody_path=custody_path,
    )
    freeze_path = benchmark_root / SUCCESSOR_FREEZE
    preflight_path = benchmark_root / SUCCESSOR_PREFLIGHT
    _, successor_freeze = _read_json(freeze_path, "successor_freeze_invalid")
    _, successor_preflight = _read_json(
        preflight_path, "successor_preflight_invalid",
    )
    source_preflight = successor_preflight.get("source_free_preflight")
    if type(source_preflight) is not dict:
        raise StudyError("successor_preflight_invalid")
    planned = validate_preflight(
        source_preflight, freeze, current_candidate=True,
    )
    _validate_successor_freeze(
        successor_freeze, freeze, successor, contract, planned,
        benchmark_root, repo_root,
    )
    _validate_successor_preflight(
        successor_preflight, successor_freeze, digest(freeze_path.read_bytes()),
        freeze, benchmark_root,
    )
    return successor_freeze, successor_preflight


def _require_successor_pool_hash(raw: bytes, preflight: Mapping[str, Any]) -> str:
    actual = digest(raw)
    if actual != preflight.get("pool_artifact_sha256"):
        raise StudyError("successor_pool_artifact_hash_invalid")
    return actual


def load_prepared_successor_pool(
    benchmark_root: Path, pool_path: Path, custody_path: Path,
    repo_root: Path = ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_path = repo_root / LOCAL_POOL_ARTIFACT
    if pool_path != expected_path or pool_path.is_symlink():
        raise StudyError("successor_pool_artifact_path_invalid")
    _, successor_preflight = load_successor_freeze(
        benchmark_root, repo_root, custody_path=custody_path,
    )
    try:
        raw = pool_path.read_bytes()
    except OSError:
        raise StudyError("successor_pool_artifact_missing") from None
    _require_successor_pool_hash(raw, successor_preflight)
    freeze, _, _ = load_bundle(benchmark_root, repo_root)
    return load_runtime_inputs(
        benchmark_root, pool_path, freeze,
        validate_historical_reservation=False,
        expected_pool_sha256=successor_preflight["pool_artifact_sha256"],
    )


def prepare_successor_execution(
    benchmark_root: Path, lanes_root: Path, custody_path: Path,
    repo_root: Path = ROOT,
) -> dict[str, str | int]:
    freeze, questions, _ = load_bundle(benchmark_root, repo_root)
    successor_freeze, successor_preflight = load_successor_freeze(
        benchmark_root, repo_root, custody_path=custody_path,
    )
    result = prepare_study(
        freeze, questions, benchmark_root, lanes_root, None, None, repo_root,
        persist=False,
    )
    preflight = result.pop("_preflight")
    pools = result.pop("_local_artifact")
    if (
        type(preflight) is not dict or type(pools) is not dict
        or result["preflight_sha256"]
        != successor_preflight["source_preflight_sha256"]
        or result["local_artifact_sha256"]
        != successor_preflight["pool_artifact_sha256"]
        or result["pool_count"] != 8
        or result["planned_jev_calls"] != 8
        or result["skipped_jev_calls"] != 0
        or validate_preflight(preflight, freeze, current_candidate=True) != 8
        or pools.get("provider_calls_executed") != 0
    ):
        raise StudyError("successor_pool_reproduction_mismatch")
    destination = repo_root / LOCAL_POOL_ARTIFACT
    try:
        _git(repo_root, "check-ignore", "-q", LOCAL_POOL_ARTIFACT)
    except StudyError:
        raise StudyError("successor_pool_artifact_not_ignored") from None
    expected = successor_preflight["pool_artifact_sha256"]
    _require_successor_pool_hash(_json_bytes(pools), successor_preflight)
    _write_json(destination, pools)
    raw = destination.read_bytes()
    _require_successor_pool_hash(raw, successor_preflight)
    load_prepared_successor_pool(
        benchmark_root, destination, custody_path, repo_root,
    )
    return {
        "pool_artifact_sha256": expected,
        "pool_count": 8,
        "planned_jev_calls": 8,
        "answer_calls_executed": 0,
        "grader_calls_executed": 0,
        "provider_calls_executed": 0,
        "retries": 0,
    }


def load_runtime_inputs(benchmark_root: Path, pool_path: Path,
                        freeze: Mapping[str, Any], *,
                        validate_historical_reservation: bool = True,
                        expected_pool_sha256: str = LOCAL_POOL_SHA256,
                        ) -> tuple[dict[str, Any], dict[str, Any]]:
    _, preflight = _read_json(benchmark_root / "preflight.json", "preflight_invalid")
    validate_preflight(preflight, freeze)
    raw, artifact = _read_json(pool_path, "pool_artifact_invalid")
    rows = artifact.get("pools")
    if (
        digest(raw) != expected_pool_sha256
        or artifact.get("schema_version") != LOCAL_ARTIFACT_SCHEMA
        or artifact.get("study_id") != freeze["study_id"]
        or artifact.get("provider_calls_executed") != 0
        or type(rows) is not list or len(rows) != 8
    ):
        raise StudyError("pool_artifact_invalid")
    pools = {}
    for row in rows:
        identity = row.get("identity") if type(row) is dict else None
        pool_id = identity.get("pool_id") if type(identity) is dict else None
        if (
            pool_id in pools or pool_id not in freeze["candidate_pool_contract"]["pool_bindings"]
            or row.get("pool_sha256") != _sha256(identity)
            or row["pool_sha256"] != freeze["candidate_pool_contract"]["pool_bindings"][pool_id]
        ):
            raise StudyError("pool_artifact_invalid")
        pools[pool_id] = row
    registrations = {row["trial_id"]: row for row in preflight["trials"]}
    request_bytes = {
        trial_id: pools[row["pool_id"]]["jev_preview"]["request_bytes"]
        for trial_id, row in registrations.items() if row["call_disposition"] == "planned"
    }
    request_set_valid = digest(canonical(request_bytes)) == REQUEST_BYTE_SET_SHA256
    historical_reservation_valid = not validate_historical_reservation or (
        sum(request_bytes.values()) * JEV_RATE / Decimal(1_000_000)
        == INCREMENTAL_RESERVATION
        and HISTORICAL_RESERVATION + INCREMENTAL_RESERVATION == TOTAL_RESERVATION
        and Decimal("1") - TOTAL_RESERVATION == REMAINING_BUDGET
    )
    if (
        set(pools) != set(freeze["candidate_pool_contract"]["pool_bindings"])
        or set(registrations) != set(DISPATCH)
        or not request_set_valid
        or not historical_reservation_valid
    ):
        raise StudyError("frozen_budget_invalid")
    return registrations, pools


def _corpus_binding(corpus_id: str, freeze: Mapping[str, Any]) -> dict[str, Any]:
    corpus = freeze["corpora"][corpus_id]
    prefix = PurePosixPath("benchmarks/velgraphing-corpus-pilot-v1")
    return {**corpus, "id": corpus_id,
            "manifest": str(PurePosixPath(corpus["manifest"]).relative_to(prefix))}


def _ranked_candidates(pool: Mapping[str, Any]) -> tuple[RankedContextCandidate, ...]:
    return tuple(RankedContextCandidate(
        candidate_id=row["candidate_id"], source_path=row["source_path"],
        source_sha256=row["source_sha256"], byte_start=row["byte_start"],
        byte_end=row["byte_end"], required=row["required"], record_id=row["record_id"],
        relationship_parent_candidate_id=row["relationship_parent_candidate_id"],
        relationship_edge_id=row["relationship_edge_id"],
        relationship_direction=row["relationship_direction"],
        relationship_relation=row["relationship_relation"],
        relationship_sensitivity=(Sensitivity(row["relationship_sensitivity"])
                                  if row["relationship_sensitivity"] else None),
    ) for row in pool["identity"]["candidates"])


def _apply_verified_fallback_measured(
    trial: Trial, task_id: str, packet: Mapping[str, Any], order: Sequence[str],
    contract: Mapping[str, Any], custody: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    with trial.phase("fallback"):
        return apply_verified_fallback(task_id, packet, order, contract, custody)


def _question_prompt(task_id: str) -> str:
    _, questions = _read_json(DEFAULT_ROOT / "questions.json", "questions_invalid")
    return next(row["prompt"] for row in questions["questions"] if row["id"] == task_id)


def _discover_direct(trial: Trial, task_id: str, prompt: str, lane: Path,
                     manifest: Mapping[str, Any]) -> dict[str, Any]:
    read_number = 0

    def scanned(_path: str, raw: bytes) -> None:
        nonlocal read_number
        trial.source(digest(raw), 0, len(raw), access="file_read",
                     operation_id=f"direct-scan-{read_number}")
        read_number += 1

    with trial.phase("candidate_discovery"):
        trial.not_applicable("cold_graph_build", "warm_graph_load")
        graph, snapshot, reader, metadata = _scan_lane(
            lane, manifest, derive_edges=False, source_observer=scanned,
        )
        graph = Graph(graph.records)

    class MeasuredReader:
        def read_bytes(self, path: str) -> bytes:
            nonlocal read_number
            raw = reader.read_bytes(path)
            trial.source(digest(raw), 0, len(raw), access="memory_read",
                         operation_id=f"direct-memory-{read_number}")
            read_number += 1
            return raw

        def is_symlink(self, path: str) -> bool:
            return reader.is_symlink(path)

    measured_reader = MeasuredReader()
    terms = tuple(dict.fromkeys(
        token.casefold() for token in graph_find_adapter._TOKEN.findall(prompt)
    ))
    retrieval_task = TaskSpec(
        task_id, terms, node_budget=RETRIEVAL_NODE_LIMIT,
        byte_budget=CANDIDATE_AGGREGATE_BYTE_BUDGET,
        allowed_sensitivities=(Sensitivity.INTERNAL,),
    )
    selection_task = TaskSpec(
        task_id, terms, node_budget=RETRIEVAL_NODE_LIMIT,
        byte_budget=FINAL_CONTEXT_BYTE_BUDGET,
        allowed_sensitivities=(Sensitivity.INTERNAL,),
    )
    with trial.phase("retrieval"):
        index = build_repository_tag_index(graph, snapshot, measured_reader)
        facets = compile_prompt(prompt, index)
        retrieval = retrieve(
            graph, retrieval_task, index, facets, snapshot, measured_reader,
            channels=("exact", "sparse", "wiki"), expand_one_hop=False,
            source_bound_expansion=False, maximum_results=RETRIEVAL_NODE_LIMIT,
            minimum_coverage_percent=0.0, parallel=False,
        )
        if retrieval.reason == "prompt_facets_insufficient":
            facets = compile_prompt(
                prompt, index,
                proof_obligations=compile_proof_obligations(
                    prompt, graph, index, snapshot, measured_reader,
                ),
            )
            retrieval = retrieve(
                graph, retrieval_task, index, facets, snapshot, measured_reader,
                channels=("exact", "sparse", "wiki"), expand_one_hop=False,
                source_bound_expansion=False, maximum_results=RETRIEVAL_NODE_LIMIT,
                minimum_coverage_percent=0.0, parallel=False,
            )
        if retrieval.fail_closed:
            raise MeasurementError("direct_retrieval_failed_closed")
        candidates = ranked_candidates_from_retrieval(
            graph, selection_task, snapshot, measured_reader, retrieval,
            maximum_candidates=CANDIDATE_LIMIT,
            maximum_candidate_bytes=CANDIDATE_AGGREGATE_BYTE_BUDGET,
            maximum_unit_bytes=CANDIDATE_UNIT_BYTE_BUDGET,
        )
        if not candidates:
            raise MeasurementError("candidate_pool_empty")
    packet = _packet(prompt, candidates)
    candidate_set_sha256 = jev.sha256(jev.canonical(packet["candidates"]))
    trial.bind(candidate_set_sha256=candidate_set_sha256)
    trial.current["candidate_observation"] = {
        "route": "direct", "candidate_set_sha256": candidate_set_sha256,
        "candidate_count": len(candidates),
        "baseline_order_sha256": digest(canonical([
            row["id"] for row in packet["candidates"]
        ])),
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "record_count": len(graph.records), "edge_count": 0,
        "edge_expansion_status": "not_applicable",
        "scan_complete": metadata["scan_complete"],
    }
    return {
        "graph": graph, "snapshot": snapshot, "reader": measured_reader,
        "task": selection_task, "candidates": candidates, "packet": packet,
    }


def _select_direct_payload(
    trial: Trial, discovery: Mapping[str, Any], lane: Path,
    observation: Mapping[str, Any] | None, approved_request_sha256: str | None,
    successor_ttc_contract: Mapping[str, Any] | None = None,
    successor_witness_custody: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    with trial.phase("source_capture"):
        selected = select_ranked_context(
            discovery["graph"], discovery["task"], discovery["snapshot"],
            discovery["reader"], query=discovery["packet"]["query"],
            candidates=discovery["candidates"],
            approved_request_sha256=approved_request_sha256,
            jev_observation=observation,
            jev_enabled=observation is not None,
            jev_observation_qualified=observation is not None,
        )
    if selected.route != "ranked" or selected.projection.fail_closed:
        raise MeasurementError("direct_selection_failed_closed")
    trial.current["candidate_observation"].update({
        "selected_candidate_ids": list(selected.projection.selected_candidate_ids),
        "required_candidate_ids": list(selected.projection.required_candidate_ids),
        "selection_reason": selected.reason,
        "selection_order_source": selected.order_source,
    })
    packet = discovery["packet"]
    order = list(selected.projection.selected_candidate_ids)
    if successor_ttc_contract is not None:
        if successor_witness_custody is None:
            raise MeasurementError("source_witness_custody_missing")
        packet, order, receipt = _apply_verified_fallback_measured(
            trial, discovery["task"].task_id, packet, order,
            successor_ttc_contract, successor_witness_custody,
        )
        trial.current["verified_fallback"] = receipt
    return compose_answer_payload(
        trial, lane, packet, order,
    )


def _selected_payload(trial: Trial, pool: Mapping[str, Any], lane: Path,
                      manifest: Mapping[str, Any], observation: Mapping[str, Any] | None,
                      approved_request_sha256: str | None,
                      installed: tuple[Path, str, str] | None = None,
                      direct_discovery: Mapping[str, Any] | None = None,
                      successor_ttc_contract: Mapping[str, Any] | None = None,
                      successor_witness_custody: Mapping[str, Any] | None = None,
                      replay_envelope: Mapping[str, Any] | None = None,
                      live_request_sha256: str | None = None,
                      live_request_bytes: int | None = None,
                      run_root: Path | None = None) -> dict[str, Any]:
    route = pool["identity"]["route"]
    if route == "graph":
        if observation is not None or installed is None:
            raise MeasurementError("installed_graph_find_jev_path_unavailable")
        task_id = pool["identity"]["task_id"]
        return _installed_graph_payload(
            trial, task_id=task_id, prompt=_question_prompt(task_id), lane=lane,
            source_manifest=manifest, installed=installed, run_root=run_root,
            replay_envelope=replay_envelope,
            approved_request_sha256=approved_request_sha256,
            live_request_sha256=live_request_sha256,
            live_request_bytes=live_request_bytes,
        )
    if direct_discovery is None:
        raise MeasurementError("direct_discovery_missing")
    return _select_direct_payload(
        trial, direct_discovery, lane, observation, approved_request_sha256,
        successor_ttc_contract, successor_witness_custody,
    )


def _trial_identity(freeze: Mapping[str, Any], registration: Mapping[str, Any],
                    corpus_id: str, rubric: Mapping[str, Any], dirty: str,
                    run_id: str, prompt: str) -> dict[str, Any]:
    corpus = freeze["corpora"][corpus_id]
    return {
        "run_id": run_id, "trial_id": registration["trial_id"],
        "task_id": registration["task_id"], "arm": registration["arm"],
        "repository_id": corpus_id, "repository_commit": corpus["commit"],
        "source_snapshot_sha256": corpus["snapshot_sha256"],
        "dirty_state_sha256": dirty,
        "answer_model": freeze["lane_identity_contract"]["answer"]["model"],
        "reasoning": freeze["lane_identity_contract"]["answer"]["reasoning"],
        "prompt_sha256": digest(prompt.encode("utf-8")),
        "rubric_sha256": digest(canonical(rubric)),
        "rubric_version": rubric["rubric_version"],
        "answer_lane_id": f"answer-{registration['trial_id']}",
    }


def _execution_identity(entry: Mapping[str, Any]) -> dict[str, str]:
    return {key: entry[key] for key in ("trial_id", "role", "thread_id", "model", "reasoning")}


def execute_trial(freeze: Mapping[str, Any], registration: Mapping[str, Any],
                  pool: Mapping[str, Any], rubric: Mapping[str, Any], lane_root: Path,
                  run_root: Path, manifest: Mapping[str, Any], manifest_sha256: str, *,
                  execution: str, budget: LiveJevBudget | None = None,
                  replay: Mapping[str, Any] | None = None,
                  successor_ttc_contract: Mapping[str, Any] | None = None,
                  successor_witness_custody: Mapping[str, Any] | None = None) -> dict[str, Any]:
    corpus_id = pool["corpus"]
    corpus = _corpus_binding(corpus_id, freeze)
    lane = lane_root / corpus_id
    _, before = verify_lane(ROOT, corpus, lane)
    identity = _trial_identity(
        freeze, registration, corpus_id, rubric, before["restricted_state_sha256"],
        freeze["study_id"] if execution == "observed" else "four-arm-qualification",
        _question_prompt(registration["task_id"]),
    )
    trial = Trial(identity, Budget(0, 600_000_000_000), execution=execution)
    jev_on = registration["arm"] in {"B", "D"}
    route = pool["identity"]["route"]
    graph_jev = route == "graph" and jev_on
    graph_jev_live = graph_jev and execution == "observed"
    graph_jev_replay = graph_jev and not graph_jev_live
    live_request_bytes = None
    if graph_jev:
        preview = pool.get("jev_preview")
        approved = preview.get("request_sha256") if type(preview) is dict else None
        if not _is_sha256(approved):
            raise MeasurementError("fixture_request_mismatch")
        if graph_jev_live:
            if replay is not None:
                raise MeasurementError("fixture_request_mismatch")
            live_request_bytes = preview.get("request_bytes")
            if type(live_request_bytes) is not int or live_request_bytes <= 0:
                raise MeasurementError("installed_graph_find_jev_live_invalid")
            if budget is None or registration.get("call_disposition") != "planned":
                raise MeasurementError("jev_request_not_approved")
        elif (replay is None or type(replay) is not dict
              or replay.get("request_sha256") != approved):
            raise MeasurementError("fixture_request_mismatch")
    else:
        approved = None
    installed = _install_graph_find(run_root) if route == "graph" else None

    def prepare(current: Trial, _attempt: int) -> dict[str, Any]:
        source_manifest = _load_manifest(ROOT / freeze["corpora"][corpus_id]["manifest"])
        direct_discovery = None
        request_sha256 = approved
        if route == "direct":
            direct_discovery = _discover_direct(
                current, registration["task_id"], _question_prompt(registration["task_id"]),
                lane, source_manifest,
            )
        observation = None
        reserved_receipt = None
        if graph_jev_replay:
            current.not_applicable("operator_approval", "provider")
        elif graph_jev_live:
            with current.phase("operator_approval"):
                reserved_receipt, _call_number = budget.reserve(
                    registration["trial_id"], approved,
                )
        elif jev_on:
            request_sha256 = pool["jev_preview"]["request_sha256"]
            packet = direct_discovery["packet"]
            if execution == "observed":
                with current.phase("operator_approval"):
                    if budget is None or registration["call_disposition"] != "planned":
                        raise MeasurementError("jev_request_not_approved")
                receipt, call_number = budget.reserve(registration["trial_id"], request_sha256)
                observation = evaluate_live(
                    current, ROOT, packet, lane,
                    approved_request_sha256=request_sha256, runtime_approved=True,
                    max_live_calls=budget.cap, call_number=call_number,
                    retain_packet_telemetry=True,
                )
                budget.complete(receipt, observation)
            else:
                current.not_applicable("operator_approval")
                if replay is None:
                    raise MeasurementError("fixture_request_mismatch")
                observation = evaluate_offline(
                    current, ROOT, packet, lane,
                    envelope=dict(replay), retain_packet_telemetry=True,
                )
            jev_answer_payload(packet, observation)
            if observation["status"] == "fallback":
                with current.phase("fallback"):
                    pass
        else:
            current.not_applicable(
                "jev_preparation", "provider", "response_validation",
                "operator_approval",
            )
        payload = _selected_payload(current, pool, lane,
                                    source_manifest, observation, request_sha256, installed,
                                    direct_discovery, successor_ttc_contract,
                                    successor_witness_custody,
                                    replay_envelope=replay if graph_jev_replay else None,
                                    live_request_sha256=approved if graph_jev_live else None,
                                    live_request_bytes=live_request_bytes,
                                    run_root=run_root)
        if graph_jev_live:
            if reserved_receipt is None:
                raise MeasurementError("jev_call_ledger_invalid")
            budget.complete(reserved_receipt, current.current["jev_observation"])
        if current.current["phase_status"]["fallback"] == "missing":
            current.not_applicable("fallback")
        current.coverage(source_operations=True)
        return payload

    entries = {(row["trial_id"], row["role"]): row for row in manifest["entries"]}
    answer = entries[(registration["trial_id"], "answer")]
    grader = entries[(registration["trial_id"], "grader")]
    context = {
        "required_facts": [row["fact"] for row in rubric["required_facts"]],
        "critical_facts": rubric["critical_facts"],
        "acceptable_spans": rubric["acceptable_spans"],
    }
    observed = execution == "observed"
    result = run_process_trial(
        trial, prepare, answer_argv=answer["argv"], grader_argv=grader["argv"],
        cwd=ROOT, answer_timeout_s=601, grader_timeout_s=601,
        grader_context=context, grader_model=grader["model"],
        answer_response_contract=ANSWER_RESPONSE_CONTRACT,
        grader_response_contract=(
            SUCCESSOR_GRADER_RESPONSE_CONTRACT
            if successor_ttc_contract is not None else _bound_grader_contract(freeze)
        ),
        answer_execution_identity=_execution_identity(answer) if observed else None,
        grader_execution_identity=_execution_identity(grader) if observed else None,
    )
    revalidate_lane(ROOT, corpus, lane, before)
    study_binding = {
        "manifest": manifest_sha256, "pool": pool["pool_sha256"],
        "decision": registration["selection_decision_sha256"],
        "rubric": identity["rubric_sha256"], "execution": execution,
    }
    if successor_ttc_contract is not None:
        study_binding["successor_ttc_contract"] = digest(canonical(successor_ttc_contract))
    result["study_binding_sha256"] = digest(canonical(study_binding))
    if len(result["attempts"]) != 1:
        raise MeasurementError("study_retry_forbidden")
    calls = [row.get("kind") for row in result["attempts"][0].get("model_calls", [])]
    if result["terminal_reason"] == "passed" and (
        calls.count("answer") != 1 or calls.count("grader") != 1
    ):
        raise MeasurementError("single_answer_grade_required")
    return result


def _validate_receipts(completed: list[dict[str, Any]], registrations: Mapping[str, Any],
                       expected_bindings: Mapping[str, str], execution: str) -> set[str]:
    seen = set()
    for result in completed:
        identity = result.get("identity", {})
        trial_id = identity.get("trial_id")
        if (
            trial_id not in registrations or trial_id in seen
            or identity.get("task_id") != registrations[trial_id]["task_id"]
            or identity.get("arm") != registrations[trial_id]["arm"]
            or identity.get("run_id") != ("velgraphing-four-arm-study-v1"
                                           if execution == "observed" else "four-arm-qualification")
            or result.get("study_binding_sha256") != expected_bindings[trial_id]
            or result.get("execution") != execution
            or result.get("budget") != {"max_repairs": 0, "wall_limit_ns": 600_000_000_000}
            or len(result.get("attempts", ())) != 1
        ):
            raise MeasurementError("study_result_mismatch")
        seen.add(trial_id)
    return seen


def _seal(run_root: Path, freeze: Mapping[str, Any], registrations: Mapping[str, Any],
          completed: list[dict[str, Any]], manifest_sha256: str,
          execution: str, *, successor_ttc_contract: Mapping[str, Any] | None = None,
          successor_rubrics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    measurements = [_v3_trial_measurement(registrations[result["identity"]["trial_id"]], result)
                    for result in completed]
    provider_calls = sum(row["provider_calls"] or 0 for row in measurements)
    budget = {"request_byte_set_sha256": REQUEST_BYTE_SET_SHA256}
    if successor_ttc_contract is None:
        budget.update({
            "rate_usd_per_million_request_bytes": str(JEV_RATE),
            "incremental_reservation_usd": str(INCREMENTAL_RESERVATION),
            "historical_reservation_usd": str(HISTORICAL_RESERVATION),
            "total_reservation_usd": str(TOTAL_RESERVATION),
            "remaining_usd": str(REMAINING_BUDGET),
        })
    else:
        budget.update({
            "provider_budget_authority": (
                successor_ttc_contract["provider_budget_authority"]
            ),
            "max_additional_provider_spend_usd": str(
                MAX_ADDITIONAL_PROVIDER_SPEND_USD
            ),
            "budget_semantics": "operator_reported_remaining_authority_not_provider_verified",
        })
    value = {
        "schema_version": (
            "velgraphing-four-arm-result-v2"
            if successor_ttc_contract is not None else "velgraphing-four-arm-result-v1"
        ),
        "study_id": freeze["study_id"], "execution": execution,
        "status": "closed", "reported_trials": len(completed),
        "lane_manifest_sha256": manifest_sha256,
        "provider_calls_executed": provider_calls,
        "retries": sum(len(result["attempts"]) - 1 for result in completed),
        "fallback_trials": [
            result["identity"]["trial_id"] for result in completed
            if any(
                attempt.get("jev_observation", {}).get("status") == "fallback"
                or attempt.get("verified_fallback", {}).get("fallback_invocations") == 1
                for attempt in result["attempts"]
            )
        ],
        "receipt_sha256": {result["identity"]["trial_id"]: digest(canonical(result))
                           for result in completed},
        "measurements": measurements,
        "missingness": {row["trial_id"]: sorted(key for key, value in row.items() if value is None)
                        for row in measurements},
        "budget": budget,
    }
    if successor_ttc_contract is not None:
        bindings = successor_ttc_contract["bindings"]
        value.update({
            "classification": successor_ttc_contract["classification"]["sealed_result"],
            "claim_boundary": successor_ttc_contract["classification"]["claim_boundary"],
            "successor_ttc_contract_sha256": digest(canonical(successor_ttc_contract)),
            "successor_rubric_sha256": digest(canonical(successor_rubrics)),
            "successor_grader_response_contract_sha256": bindings[
                "successor_grader_response_contract_sha256"
            ],
            "controller_sha256": bindings["controller"]["sha256"],
            "host_sha256": bindings["host"]["sha256"],
            "source_snapshots": bindings["source_snapshots"],
            "pool_bindings": bindings["pool_bindings"],
            "verifier_policy_sha256": successor_ttc_contract["verifier_policy_sha256"],
            "fact_witness_map_sha256": successor_ttc_contract["fact_witness_map_sha256"],
            "fallback_allowlist_sha256": successor_ttc_contract[
                "fallback_allowlist_sha256"
            ],
            "witness_custody_sha256": successor_ttc_contract["witness_custody_sha256"],
            "request_byte_set_sha256": bindings["request_byte_set_sha256"],
            "attempt_count": sum(len(result["attempts"]) for result in completed),
            "answer_call_count": sum(row["answer_call_count"] for row in measurements),
            "grader_call_count": sum(row["grader_call_count"] for row in measurements),
            "verified_fallback_invocations": sum(
                (row["verified_fallback"] or {}).get("fallback_invocations", 0)
                for row in measurements
            ),
            "wall_time_ns_by_trial": {
                row["trial_id"]: row["user_visible_wall_ns"] for row in measurements
            },
            "confirmed_ttc_ns_by_trial": {
                row["trial_id"]: row["confirmed_time_to_correct_ns"] for row in measurements
            },
            "usage_missingness": {
                row["trial_id"]: row["usage_missingness"] for row in measurements
            },
        })
        missing = set(successor_ttc_contract["result_contract"]["required_fields"]) - set(value)
        if missing:
            raise MeasurementError("successor_result_contract_incomplete")
    path = run_root / "result.json"
    raw = canonical(value)
    try:
        if path.exists():
            if read_canonical(path)[0] != raw:
                raise MeasurementError("result_seal_conflict")
        else:
            atomic_write(path, raw)
    except HandoffError:
        raise MeasurementError("result_seal_invalid") from None
    return value


def _validate_approved_additional_provider_spend(approved: str | None) -> None:
    try:
        approved_cap_usd = Decimal(approved) if approved is not None else None
    except ArithmeticError:
        approved_cap_usd = None
    if approved_cap_usd != MAX_ADDITIONAL_PROVIDER_SPEND_USD:
        raise MeasurementError("max_additional_provider_spend_not_approved")


def run_study(benchmark_root: Path, pool_path: Path, lane_root: Path, run_root: Path,
              manifest_path: Path, custody_path: Path, *, allow_live_jev: bool,
              approved_cap: int | None,
              approved_request_set: str | None,
              approved_max_additional_provider_spend_usd: str | None,
              approved_manifest: str | None, approved_python: str | None) -> dict[str, Any]:
    freeze, _, _ = load_bundle(benchmark_root, ROOT)
    rubrics = load_successor_rubrics(benchmark_root, ROOT)
    successor_ttc_contract, successor_witness_custody = load_successor_ttc_contract(
        benchmark_root, ROOT, custody_path=custody_path,
    )
    successor_freeze, _ = load_successor_freeze(
        benchmark_root, ROOT, custody_path=custody_path,
    )
    registrations, pools = load_prepared_successor_pool(
        benchmark_root, pool_path, custody_path, ROOT,
    )
    if (
        allow_live_jev is not True or approved_cap != 8
        or approved_request_set != REQUEST_BYTE_SET_SHA256
    ):
        raise MeasurementError("live_jev_not_approved")
    _validate_approved_additional_provider_spend(
        approved_max_additional_provider_spend_usd,
    )
    root = validate_run_root(str(run_root))
    if manifest_path != root / "lane-manifest.json":
        raise MeasurementError("lane_manifest_path_invalid")
    raw, manifest = read_canonical(manifest_path)
    validate_successor_execution_bindings(
        successor_ttc_contract, freeze, manifest, successor_freeze,
    )
    if digest(raw) != approved_manifest:
        raise MeasurementError("lane_manifest_not_approved")
    entries = manifest.get("entries")
    if (type(entries) is not list or not entries or type(entries[0]) is not dict
            or type(entries[0].get("argv")) is not list or not entries[0]["argv"]):
        raise MeasurementError("lane_manifest_invalid")
    python_executable = entries[0]["argv"][0]
    if python_executable != approved_python:
        raise MeasurementError("python_executable_not_approved")
    validate_lane_manifest(manifest, freeze, python_executable=python_executable, run_root=root)
    manifest_sha256 = digest(raw)
    bind_controller(root, controller_identity(ROOT))
    expected = list(DISPATCH)
    completed = load_completed_trials(root / "completed", expected)
    bindings = {}
    for trial_id in expected:
        row = registrations[trial_id]
        rubric = rubrics["tasks"][row["task_id"]]
        bindings[trial_id] = digest(canonical({
            "manifest": manifest_sha256, "pool": pools[row["pool_id"]]["pool_sha256"],
            "decision": row["selection_decision_sha256"],
            "rubric": digest(canonical(rubric)), "execution": "observed",
            "successor_ttc_contract": digest(canonical(successor_ttc_contract)),
        }))
    completed_ids = _validate_receipts(completed, registrations, bindings, "observed")
    budget = LiveJevBudget(root, 8)
    for trial_id in expected:
        if trial_id in completed_ids:
            continue
        require_resumable(root, trial_id, completed_ids)
        row = registrations[trial_id]
        result = execute_trial(
            freeze, row, pools[row["pool_id"]], rubrics["tasks"][row["task_id"]],
            lane_root, root, manifest, manifest_sha256, execution="observed", budget=budget,
            successor_ttc_contract=successor_ttc_contract,
            successor_witness_custody=successor_witness_custody,
        )
        save_completed_trial(root / "completed", result)
        completed.append(result)
        completed_ids.add(trial_id)
    return _seal(
        root, freeze, registrations, completed, manifest_sha256, "observed",
        successor_ttc_contract=successor_ttc_contract, successor_rubrics=rubrics,
    )


def qualify(benchmark_root: Path, pool_path: Path, lane_root: Path,
            run_root: Path, python_executable: Path) -> dict[str, Any]:
    freeze, _, _ = load_bundle(benchmark_root, ROOT)
    _require_current_execution_bindings(freeze, benchmark_root, ROOT)
    registrations, pools = load_runtime_inputs(benchmark_root, pool_path, freeze)
    root = validate_run_root(str(run_root))
    manifest_path = root / "lane-manifest.json"
    if not manifest_path.exists():
        bindings = {"schema_version": "velgraphing-four-arm-lane-bindings-v1", "bindings": [
            {"trial_id": trial_id, "answer_thread_id": f"fixture-answer-{trial_id}",
             "grader_thread_id": f"fixture-grader-{trial_id}"} for trial_id in DISPATCH
        ]}
        freeze_lane_manifest(bindings, freeze, manifest_path, python_executable)
    raw, manifest = read_canonical(manifest_path)
    validate_lane_manifest(manifest, freeze, python_executable=python_executable, run_root=root)
    manifest_sha256 = digest(raw)
    trial_ids = [f"{arm}-S-01" for arm in ARMS]
    fixture_rubric = {"rubric_version": "four-arm-fixture-v1",
                      "required_facts": [{"ask_id": "fixture", "fact": "fixture fact"}],
                      "critical_facts": ["fixture fact"], "acceptable_spans": ["fixture"]}
    selected = {trial_id: registrations[trial_id] for trial_id in trial_ids}
    binding = {
        trial_id: digest(canonical({
            "manifest": manifest_sha256,
            "pool": pools[selected[trial_id]["pool_id"]]["pool_sha256"],
            "decision": selected[trial_id]["selection_decision_sha256"],
            "rubric": digest(canonical(fixture_rubric)), "execution": "fixture",
        })) for trial_id in trial_ids
    }
    completed = load_completed_trials(root / "completed", trial_ids)
    completed_ids = _validate_receipts(completed, selected, binding, "fixture")
    for trial_id in trial_ids:
        if trial_id in completed_ids:
            continue
        require_resumable(root, trial_id, completed_ids)
        row = selected[trial_id]
        pool = pools[row["pool_id"]]
        workers = [start_fixture_worker(root, trial_id, role, python_executable=python_executable)
                   for role in ("answer", "grader")]
        envelope = None
        if row["arm"] in {"B", "D"}:
            envelope = replay_envelope(ROOT, pool["candidate_packet"], lane_root / pool["corpus"])
            if row["arm"] == "D":
                envelope["response"]["answers"] = {}
        result = execute_trial(
            freeze, row, pool, fixture_rubric, lane_root, root, manifest,
            manifest_sha256, execution="fixture", replay=envelope,
        )
        finish_workers(workers)
        save_completed_trial(root / "completed", result)
        completed.append(result)
        completed_ids.add(trial_id)
    restarted = load_completed_trials(root / "completed", trial_ids)
    _validate_receipts(restarted, selected, binding, "fixture")
    result = _seal(root, freeze, selected, restarted, manifest_sha256, "fixture")
    if result["provider_calls_executed"] != 0 or result["fallback_trials"] != ["D-S-01"]:
        raise MeasurementError("qualification_result_invalid")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    prepare.add_argument("--lanes-root", type=Path, required=True)
    prepare.add_argument("--local-output", type=Path, required=True)
    prepare.add_argument("--preflight-output", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    validate.add_argument("--lane-manifest", type=Path)
    validate.add_argument("--preflight", type=Path)
    successor_validation = subparsers.add_parser("validate-successor-overlay")
    successor_validation.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    successor_validation.add_argument("--witness-custody", type=Path, required=True)
    successor_freeze_command = subparsers.add_parser("freeze-successor")
    successor_freeze_command.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    successor_freeze_command.add_argument("--lanes-root", type=Path, required=True)
    successor_freeze_command.add_argument("--witness-custody", type=Path, required=True)
    successor_freeze_command.add_argument("--refresh", action="store_true")
    successor_approval = subparsers.add_parser("approve-successor")
    successor_approval.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    successor_approval.add_argument("--witness-custody", type=Path, required=True)
    successor_approval.add_argument("--approved-max-live-jev-calls", type=int, required=True)
    successor_approval.add_argument("--approved-request-byte-set-sha256", required=True)
    successor_approval.add_argument(
        "--approved-max-additional-provider-spend-usd", required=True,
    )
    successor_approval.add_argument("--approved-lane-manifest-sha256", required=True)
    successor_approval.add_argument("--approved-python-executable", required=True)
    successor_prep = subparsers.add_parser("prepare-successor-execution")
    successor_prep.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    successor_prep.add_argument("--lanes-root", type=Path, required=True)
    successor_prep.add_argument("--witness-custody", type=Path, required=True)
    successor_lane_binding = subparsers.add_parser("bind-successor-lanes")
    successor_lane_binding.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    successor_lane_binding.add_argument("--run-root", type=Path, required=True)
    successor_lane_binding.add_argument("--python-executable", type=Path, required=True)
    successor_lane_binding.add_argument("--witness-custody", type=Path, required=True)
    lanes = subparsers.add_parser("freeze-lanes")
    lanes.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    lanes.add_argument("--bindings", type=Path, required=True)
    lanes.add_argument("--run-root", type=Path, required=True)
    lanes.add_argument("--python-executable", type=Path, required=True)
    lanes.add_argument("--witness-custody", type=Path, required=True)
    lanes.add_argument("--refresh", action="store_true")
    run = subparsers.add_parser("run")
    run.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    run.add_argument("--pool-artifact", type=Path, required=True)
    run.add_argument("--lane-root", type=Path, required=True)
    run.add_argument("--run-root", type=Path, required=True)
    run.add_argument("--lane-manifest", type=Path, required=True)
    run.add_argument("--witness-custody", type=Path, required=True)
    run.add_argument("--allow-live-jev", action="store_true")
    run.add_argument("--approved-max-live-jev-calls", type=int)
    run.add_argument("--approved-request-byte-set-sha256")
    run.add_argument("--approved-max-additional-provider-spend-usd")
    run.add_argument("--approved-lane-manifest-sha256")
    run.add_argument("--approved-python-executable")
    qualification = subparsers.add_parser("qualify")
    qualification.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    qualification.add_argument("--pool-artifact", type=Path, required=True)
    qualification.add_argument("--lane-root", type=Path, required=True)
    qualification.add_argument("--run-root", type=Path, required=True)
    qualification.add_argument("--python-executable", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "freeze-successor":
            result = freeze_successor(
                arguments.root.resolve(), arguments.lanes_root.resolve(),
                arguments.witness_custody, ROOT, refresh=arguments.refresh,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "approve-successor":
            result = approve_successor(
                arguments.root.resolve(), arguments.witness_custody,
                approved_max_live_jev_calls=arguments.approved_max_live_jev_calls,
                approved_request_set=arguments.approved_request_byte_set_sha256,
                approved_max_additional_provider_spend_usd=(
                    arguments.approved_max_additional_provider_spend_usd
                ),
                approved_manifest=arguments.approved_lane_manifest_sha256,
                approved_python=arguments.approved_python_executable,
                repo_root=ROOT,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "prepare-successor-execution":
            result = prepare_successor_execution(
                arguments.root.resolve(), arguments.lanes_root.resolve(),
                arguments.witness_custody, ROOT,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "bind-successor-lanes":
            result = bind_successor_lane_manifest(
                arguments.root.resolve(), arguments.run_root.resolve(),
                arguments.witness_custody, arguments.python_executable, ROOT,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "validate-successor-overlay":
            benchmark_root = arguments.root.resolve()
            successor = load_successor_rubrics(benchmark_root, ROOT)
            contract, _ = load_successor_ttc_contract(
                benchmark_root, ROOT, custody_path=arguments.witness_custody,
            )
            successor_freeze, successor_preflight = load_successor_freeze(
                benchmark_root, ROOT, custody_path=arguments.witness_custody,
            )
            bindings = contract["bindings"]
            print(json.dumps({
                "controller": bindings["controller"],
                "grader_contract_sha256": bindings[
                    "successor_grader_response_contract_sha256"
                ],
                "host": bindings["host"],
                "successor_rubric_sha256": digest(canonical(successor)),
                "successor_ttc_contract_sha256": digest(canonical(contract)),
                "successor_freeze_sha256": digest(
                    (benchmark_root / SUCCESSOR_FREEZE).read_bytes()
                ),
                "successor_preflight_sha256": digest(
                    (benchmark_root / SUCCESSOR_PREFLIGHT).read_bytes()
                ),
                "planned_jev_calls": successor_preflight["planned_jev_calls"],
                "execution_ready": successor_freeze["execution_policy"][
                    "execution_ready"
                ],
                "verifier_policy_sha256": contract["verifier_policy_sha256"],
                "fallback_allowlist_sha256": contract["fallback_allowlist_sha256"],
                "witness_custody_sha256": contract["witness_custody_sha256"],
                "classification": contract["classification"],
                "lane_manifest": bindings["lane_manifest"],
                "remaining_authority": contract["remaining_authority"],
                "validation_scope": "successor_overlay",
            }, sort_keys=True))
            return 0
        if arguments.command == "prepare":
            benchmark_root = arguments.root.resolve()
            local_output = arguments.local_output.resolve()
            preflight_output = arguments.preflight_output.resolve()
            if (
                local_output
                != ROOT / ".velgraphing-local/velgraphing-four-arm-study-v1/phase-2-pools.json"
                or preflight_output != benchmark_root / "preflight.json"
            ):
                raise StudyError("prepare_output_path_invalid")
            freeze, questions, _ = load_bundle(benchmark_root, ROOT)
            _require_current_execution_bindings(freeze, benchmark_root, ROOT)
            result = prepare_study(
                freeze,
                questions,
                benchmark_root,
                arguments.lanes_root.resolve(),
                local_output,
                preflight_output,
                ROOT,
            )
            if result["preflight_sha256"] != freeze["artifacts"]["preflight"]["sha256"]:
                raise StudyError("preflight_reproduction_mismatch")
            load_bundle(benchmark_root, ROOT)
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "freeze-lanes":
            benchmark_root = arguments.root.resolve()
            freeze, _, _ = load_bundle(benchmark_root, ROOT)
            load_successor_ttc_contract(
                benchmark_root, ROOT, custody_path=arguments.witness_custody,
            )
            load_prepared_successor_pool(
                benchmark_root, ROOT / LOCAL_POOL_ARTIFACT,
                arguments.witness_custody, ROOT,
            )
            _, bindings = _read_json(arguments.bindings.resolve(), "lane_bindings_invalid")
            run_root = validate_run_root(str(arguments.run_root.resolve()))
            result = freeze_lane_manifest(
                bindings, freeze, run_root / "lane-manifest.json",
                arguments.python_executable,
                replace_existing=arguments.refresh,
            )
            print(json.dumps({"lane_manifest_sha256": result}, sort_keys=True))
            return 0
        if arguments.command == "run":
            result = run_study(
                arguments.root.resolve(), arguments.pool_artifact.resolve(),
                arguments.lane_root.resolve(), arguments.run_root.resolve(),
                arguments.lane_manifest.resolve(), arguments.witness_custody,
                allow_live_jev=arguments.allow_live_jev,
                approved_cap=arguments.approved_max_live_jev_calls,
                approved_request_set=arguments.approved_request_byte_set_sha256,
                approved_max_additional_provider_spend_usd=(
                    arguments.approved_max_additional_provider_spend_usd
                ),
                approved_manifest=arguments.approved_lane_manifest_sha256,
                approved_python=arguments.approved_python_executable,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "qualify":
            result = qualify(
                arguments.root.resolve(), arguments.pool_artifact.resolve(),
                arguments.lane_root.resolve(), arguments.run_root.resolve(),
                arguments.python_executable,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        benchmark_root = arguments.root.resolve()
        freeze, _, _ = load_bundle(benchmark_root, ROOT)
        if arguments.lane_manifest is not None:
            _, lane_manifest = _read_json(arguments.lane_manifest, "lane_manifest_invalid")
            validate_lane_manifest(lane_manifest, freeze)
        planned = freeze["jev"]["planned_calls"]
        if arguments.preflight is not None:
            _, preflight = _read_json(arguments.preflight, "preflight_invalid")
            planned = validate_preflight(preflight, freeze)
    except (ArithmeticError, HandoffError, MeasurementError, OSError, StudyError) as error:
        parser.exit(2, f"study refused: {error}\n")
    print(json.dumps({
        "dispatches": len(DISPATCH),
        "planned_jev_calls": planned,
        "status": freeze["status"],
        "study_id": freeze["study_id"],
        "validation_scope": "historical_bundle",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
