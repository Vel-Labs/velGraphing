#!/usr/bin/env python3
"""Serial 24-trial calibration coordinator. Native lanes use file handoff."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from typing import Any, Mapping
import uuid

from time_to_correct import (Answer, Budget, Grade, MeasurementError, Trial, canonical, digest,
                             identifier, load_completed_trials, save_completed_trial,
                             summarize)
from time_to_correct_graph import observe_graph_find
from time_to_correct_handoff import (HandoffError, atomic_write, atomic_write_at,
                                     open_contained_directory, read_canonical,
                                     read_canonical_at, read_lane,
                                     run_root as validate_run_root, write_response)
from time_to_correct_host import (ANSWER_RESPONSE_CONTRACT, GRADER_RESPONSE_CONTRACT,
                                  USAGE_KEYS, _invoke, run_process_trial)
from time_to_correct_jev import evaluate_live, evaluate_offline, load_jev, prepare_preview
from time_to_correct_packet import (EVIDENCE_BUDGET_BYTES, MAX_CANDIDATES,
                                    MAX_SPAN_BYTES, build_candidate_packet,
                                    compose_answer_payload)


REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_PATH = REPO_ROOT / "scripts/benchmarks/time_to_correct_handoff.py"
TASKS = ("C-01", "C-02", "S-01", "L-01", "M-01", "M-02")
ARMS = ("A", "B", "C", "D")
JEV_ARMS = {"B", "D"}
DEFAULT_CALIBRATION_ID = "velgraphing-ttc-calibration-v1"
V2_CALIBRATION_ID = "velgraphing-ttc-calibration-v2"
V3_CALIBRATION_ID = "velgraphing-ttc-calibration-v3"
V3_CANDIDATE_POLICY = {
    "max_candidates": MAX_CANDIDATES,
    "max_span_bytes": MAX_SPAN_BYTES,
    "answer_evidence_budget_bytes": EVIDENCE_BUDGET_BYTES,
    "incremental_batches": False,
    "dynamic_fallback": False,
    "direct_route": "direct_flat",
    "graph_route": "graph_find_tag_index",
    "graph_edge_expansion": "not_available",
}
V3_MEASUREMENT_CONTRACT = {
    "version": "velgraphing-ttc-measurement-v3",
    "metrics": [
        "registered_reported_pass_and_time_to_correct",
        "full_and_operator_approval_excluded_wall_and_time_to_correct",
        "active_wait_and_unattributed_time",
        "answer_request_bytes", "answer_model_usage_when_complete",
        "grader_usage_when_complete",
        "source_operation_count_and_range_bytes_with_completeness",
        "source_capture_candidate_discovery_and_context_composition",
        "answer_generation_and_grading",
        "cold_graph_build_status_and_duration", "retrieval_status_and_duration",
        "fallback_status_and_duration", "jev_request_state_and_questions_bytes",
        "jev_candidate_and_question_counts", "jev_rubric_version",
        "jev_source_bytes_verified", "jev_scores_probabilities_and_distribution_confidence",
        "jev_evaluator_elapsed_ms", "provider_input_and_output_tokens",
        "provider_call_count_and_interval", "provider_and_task_retries",
        "confidence_linked_task_failures", "paired_arm_contrasts",
    ],
    "unknown_boundaries": {
        "shared_state_tokens": "provider_does_not_report_request_token_split",
        "question_suffix_tokens": "provider_does_not_report_request_token_split",
        "candidate_calibration": "unscored_without_candidate_level_oracle",
        "missing_measurements": "null_never_zero",
        "warm_graph_load": "not_applicable_for_current_cold_in_memory_route",
    },
    "primary_provider_budget": {"calls": 12, "retries": 0},
    "sensitivity_ablation": {
        "status": "future_companion_not_authorized",
        "requires": ["distinct_provider_call_budget", "candidate_level_labels"],
    },
}
CALIBRATION_SPECS = {
    DEFAULT_CALIBRATION_ID: {
        "path": "benchmarks/velgraphing-time-to-correct-v1/calibration.json",
        "base_commit": "8b52fdaac9ce61feb09b06381c2081509df273c7",
        "repair_budget": {"max_repairs": 0, "wall_limit_ns": 300_000_000_000},
        "timeouts_seconds": {"preparation": 60, "jev_approval": 60,
                             "answer": 120, "grader": 60},
    },
    V2_CALIBRATION_ID: {
        "path": "benchmarks/velgraphing-time-to-correct-v2/calibration.json",
        "base_commit": "ac5ba612da42d4d677250e7bd94c720b521d9f68",
        "repair_budget": {"max_repairs": 0, "wall_limit_ns": 600_000_000_000},
        "timeouts_seconds": {"preparation": 180, "jev_approval": 60,
                             "answer": 180, "grader": 120},
    },
    V3_CALIBRATION_ID: {
        "path": "benchmarks/velgraphing-time-to-correct-v3/calibration.json",
        "base_commit": "031a8390ae3accce7fe4b3756f01f98f2c606ee6",
        "repair_budget": {"max_repairs": 0, "wall_limit_ns": 600_000_000_000},
        "timeouts_seconds": {"preparation": 180, "jev_approval": 60,
                             "answer": 180, "grader": 120},
    },
}
TRIAL_ORDER = (
    ("C-01", "ABDC"), ("C-02", "BCAD"), ("S-01", "CDBA"),
    ("L-01", "DACB"), ("M-01", "ABDC"), ("M-02", "BCAD"),
)
EXPECTED_REGISTRATIONS = [
    {"trial_id": f"{arm}-{task}", "packet_id": f"{arm}-{task}",
     "task_id": task, "arm": arm}
    for task, arms in TRIAL_ORDER for arm in arms
]
PREPARATION_RESPONSE_CONTRACT = {
    "schema_version": "velgraphing-response-contract-v1",
    "encoding": "canonical-json",
    "json_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "candidate_packet", "usage",
                     "model_calls_complete", "context_deliveries_complete"],
        "properties": {
            "schema_version": {"const": "velgraphing-preparation-output-v1"},
            "candidate_packet": {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema_version", "query", "candidates"],
                "properties": {
                    "schema_version": {"const": "velgraphing-jev-candidates-v1"},
                    "query": {"type": "string"},
                    "candidates": {
                        "type": "array", "maxItems": 6,
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["id", "path", "source_sha256", "byte_start",
                                         "byte_end", "required"],
                            "properties": {
                                "id": {"type": "string"}, "path": {"type": "string"},
                                "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "byte_start": {"type": "integer", "minimum": 0},
                                "byte_end": {"type": "integer", "minimum": 0},
                                "required": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
            "usage": {"type": ["object", "null"]},
            "model_calls_complete": {"type": "boolean"},
            "context_deliveries_complete": {"type": "boolean"},
        },
    },
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise MeasurementError("calibration_input_invalid") from None
    if type(value) is not dict:
        raise MeasurementError("calibration_input_invalid")
    return value


def load_calibration(repo: Path = REPO_ROOT,
                     calibration_id: str = DEFAULT_CALIBRATION_ID) -> dict[str, Any]:
    spec = CALIBRATION_SPECS.get(calibration_id)
    if spec is None:
        raise MeasurementError("calibration_selection_invalid")
    config = read_json(repo / spec["path"])
    registrations = config.get("registered_trials")
    if (config.get("schema_version") != calibration_id
            or config.get("calibration_id") != calibration_id
            or config.get("status") != "approved_not_executed"
            or config.get("base_commit") != spec["base_commit"]
            or config.get("package_version") != "0.1.6"
            or config.get("max_live_jev_calls") != 12
            or config.get("provider_retries") != 0
            or config.get("answer_model") != "gpt-5.6-sol"
            or config.get("reasoning") != "medium"
            or config.get("repair_budget") != spec["repair_budget"]
            or config.get("timeouts_seconds") != spec["timeouts_seconds"]
            or config.get("dispatch_design") != "balanced_latin_square_abdc_bcad_cdba_dacb_repeated_for_six_tasks"
            or registrations != EXPECTED_REGISTRATIONS
            or (calibration_id == V3_CALIBRATION_ID
                and (config.get("measurement_contract") != V3_MEASUREMENT_CONTRACT
                     or config.get("candidate_policy") != V3_CANDIDATE_POLICY))):
        raise MeasurementError("calibration_freeze_invalid")
    source = config.get("source_pilot", {})
    paths = {
        "freeze": "benchmarks/velgraphing-corpus-pilot-v1/freeze.json",
        "packets": "benchmarks/velgraphing-corpus-pilot-v1/packets.json",
    }
    if type(source) is not dict or any(source.get(key) != value for key, value in paths.items()):
        raise MeasurementError("sealed_pilot_identity_changed")
    for key, relative in (("freeze_sha256", paths["freeze"]),
                          ("packets_sha256", paths["packets"]),
                          ("questions_sha256", "benchmarks/velgraphing-corpus-pilot-v1/corpus/questions.json"),
                          ("oracle_sha256", "benchmarks/velgraphing-corpus-pilot-v1/corpus/oracle.json")):
        try:
            if digest((repo / relative).read_bytes()) != source[key]:
                raise MeasurementError("sealed_pilot_identity_changed")
        except (KeyError, OSError):
            raise MeasurementError("sealed_pilot_identity_changed") from None
    return config


def load_pilot(repo: Path, config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    packets = read_json(repo / config["source_pilot"]["packets"])
    freeze = read_json(repo / config["source_pilot"]["freeze"])
    oracle = read_json(repo / "benchmarks/velgraphing-corpus-pilot-v1/corpus/oracle.json")
    packet_rows = packets.get("packets")
    if type(packet_rows) is not list or len(packet_rows) != 24:
        raise MeasurementError("sealed_pilot_packets_invalid")
    packet_by_id = {row.get("packet_id"): row for row in packet_rows if type(row) is dict}
    corpus_by_id = {row.get("id"): row for row in freeze.get("corpus", []) if type(row) is dict}
    tasks = oracle.get("tasks")
    if len(packet_by_id) != 24 or set(tasks or {}) != set(TASKS):
        raise MeasurementError("sealed_pilot_packets_invalid")
    return packet_by_id, corpus_by_id, tasks


def _git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if completed.returncode:
        raise MeasurementError("git_identity_unavailable")
    return completed.stdout


def controller_identity(repo: Path) -> dict[str, Any]:
    """Bind execution to a clean tracked checkout while ignoring untracked run data."""
    head = _git(repo, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    tree = _git(repo, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    status = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=no")
    index = _git(repo, "diff", "--cached", "--binary", "--no-ext-diff", "HEAD", "--")
    worktree = _git(repo, "diff", "--binary", "--no-ext-diff", "HEAD", "--")
    if status or index or worktree:
        raise MeasurementError("controller_checkout_not_clean")
    identity = {
        "schema_version": "velgraphing-controller-identity-v1",
        "git_head": head,
        "git_tree": tree,
        "tracked_status_sha256": digest(status),
        "index_diff_sha256": digest(index),
        "worktree_diff_sha256": digest(worktree),
    }
    identity["tracked_state_sha256"] = digest(canonical(identity))
    return identity


def bind_controller(root: Path, identity: Mapping[str, Any]) -> dict[str, Any]:
    path = root / "controller.json"
    raw = canonical(identity)
    if path.exists():
        if read_canonical(path)[0] != raw:
            raise MeasurementError("controller_identity_changed")
    else:
        atomic_write(path, raw)
    return dict(identity)


def verify_lane(repo: Path, corpus: Mapping[str, Any], corpus_root: Path) -> tuple[list[str], dict[str, Any]]:
    if not corpus_root.is_absolute() or corpus_root.is_symlink():
        raise MeasurementError("corpus_root_invalid")
    manifest_path = repo / "benchmarks/velgraphing-corpus-pilot-v1" / corpus["manifest"]
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise MeasurementError("corpus_manifest_invalid") from None
    if type(manifest) is not dict:
        raise MeasurementError("corpus_manifest_invalid")
    sources = manifest.get("sources")
    if type(sources) is not list or manifest.get("snapshot_sha256") != corpus["snapshot_sha256"]:
        raise MeasurementError("corpus_manifest_invalid")
    rows = []
    for source in sources:
        path = source.get("path")
        relative = PurePosixPath(path) if type(path) is str else None
        if (relative is None or relative.is_absolute() or relative.as_posix() != path
                or any(part in {".", ".."} for part in relative.parts)):
            raise MeasurementError("corpus_source_invalid")
        target = corpus_root
        for part in relative.parts:
            target /= part
            if target.is_symlink():
                raise MeasurementError("corpus_source_invalid")
        try:
            if target.is_symlink() or not target.is_file():
                raise MeasurementError("corpus_source_invalid")
            raw = target.read_bytes()
        except OSError:
            raise MeasurementError("corpus_source_invalid") from None
        if len(raw) != source.get("byte_length") or digest(raw) != source.get("sha256"):
            raise MeasurementError("corpus_source_invalid")
        rows.append({"path": path, "byte_length": len(raw), "sha256": digest(raw)})
    snapshot_sha256 = digest(canonical({"sources": rows}))
    if snapshot_sha256 != corpus["snapshot_sha256"]:
        raise MeasurementError("corpus_snapshot_mismatch")
    head = _git(corpus_root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    index = _git(corpus_root, "ls-files", "--stage", "-z")
    entries = []
    try:
        for raw_entry in (entry for entry in index.split(b"\0") if entry):
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode, object_id, stage = metadata.split(b" ")
            entries.append((mode.decode("ascii"), object_id.decode("ascii"),
                            stage.decode("ascii"), raw_path.decode("utf-8")))
    except (UnicodeError, ValueError):
        raise MeasurementError("corpus_index_invalid") from None
    expected_paths = [row["path"] for row in rows]
    indexed_paths = [entry[3] for entry in entries]
    if (head != corpus["commit"] or len(set(expected_paths)) != len(expected_paths)
            or len(entries) != len(expected_paths) or set(indexed_paths) != set(expected_paths)
            or any(mode not in {"100644", "100755"} or stage != "0"
                   for mode, _, stage, _ in entries)):
        raise MeasurementError("corpus_index_invalid")
    worktree_diff = _git(corpus_root, "diff", "--no-ext-diff", "--binary", "--")
    untracked = _git(corpus_root, "ls-files", "--others", "--exclude-standard", "-z")
    if worktree_diff or untracked:
        raise MeasurementError("corpus_checkout_not_clean")
    identity = {
        "git_head": head,
        "index_sha256": digest(index),
        "index_entry_count": len(entries),
        "selected_worktree_diff_sha256": digest(worktree_diff),
        "untracked_sha256": digest(untracked),
        "manifest_sha256": digest(manifest_raw),
        "snapshot_sha256": snapshot_sha256,
    }
    identity["restricted_state_sha256"] = digest(canonical(identity))
    return expected_paths, identity


def revalidate_lane(repo: Path, corpus: Mapping[str, Any], corpus_root: Path,
                    expected: Mapping[str, Any]) -> None:
    try:
        _, observed = verify_lane(repo, corpus, corpus_root)
    except MeasurementError:
        raise MeasurementError("corpus_changed_during_trial") from None
    if observed != expected:
        raise MeasurementError("corpus_changed_during_trial")


def replace_runtime(value: str, repo: Path, corpus_root: Path, question: str) -> str:
    return (value.replace("$VELGRAPHING_ROOT", str(repo))
            .replace(f"$LANE_ROOT/{corpus_root.name}", str(corpus_root))
            .replace("$QUESTION", question))


def graph_argv(packet: Mapping[str, Any], repo: Path, corpus_root: Path) -> list[str]:
    command = packet.get("graph_command")
    if type(command) is not list or "--root" not in command:
        raise MeasurementError("graph_command_invalid")
    resolved = [replace_runtime(value, repo, corpus_root, packet["question"]) for value in command]
    return resolved[resolved.index("--root"):]


def _python_executable(value: str | Path | None) -> str:
    if value is None:
        return sys.executable
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise MeasurementError("python_executable_invalid")
    return str(path)


def handoff_argv(run_root: Path, trial_id: str, lane: str, wait_seconds: float,
                 python_executable: str | Path | None = None) -> list[str]:
    return [_python_executable(python_executable), str(HANDOFF_PATH), "wait", "--run-root", str(run_root),
            "--trial-id", trial_id, "--attempt", "0", "--lane", lane,
            "--wait-seconds", str(wait_seconds)]


def record_usage(trial: Trial, output: Mapping[str, Any], call_id: str) -> None:
    usage = output.get("usage")
    if usage is None:
        trial.usage(call_id, "answer", provenance="unavailable",
                    model=trial.identity["answer_model"])
        return
    if type(usage) is not dict or set(usage) != USAGE_KEYS or usage.get("model") != trial.identity["answer_model"]:
        raise MeasurementError("invalid_process_usage")
    trial.usage(call_id, "answer", **usage)


def jev_answer_payload(packet: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the evaluator order to the exact private source candidates."""
    candidates = packet.get("candidates")
    order = result.get("order")
    if type(candidates) is not list or type(order) is not list:
        raise MeasurementError("jev_order_invalid")
    by_id = {row.get("id"): row for row in candidates if type(row) is dict}
    if (not all(type(candidate_id) is str for candidate_id in order)
            or len(by_id) != len(candidates) or len(order) != len(candidates)
            or len(set(order)) != len(order) or set(order) != set(by_id)):
        raise MeasurementError("jev_order_invalid")
    for index, candidate in enumerate(candidates):
        if candidate.get("required") is True and order[index] != candidate.get("id"):
            raise MeasurementError("jev_required_position_changed")
    if result.get("status") == "fallback" and order != result.get("baseline_order"):
        raise MeasurementError("jev_fallback_order_invalid")
    payload = {
        key: result.get(key) for key in (
            "status", "reason", "baseline_order", "order", "required_ids",
            "request_sha256", "source_revalidated", "resolved_model",
        )
    }
    payload["ordered_candidates"] = [dict(by_id[candidate_id]) for candidate_id in order]
    return payload


V3_NUMERIC_METRICS = (
    "user_visible_wall_ns", "confirmed_time_to_correct_ns", "answer_request_bytes",
    "wall_excluding_operator_approval_ns", "ttc_excluding_operator_approval_ns",
    "observed_active_execution_ns", "observed_wait_union_ns", "unattributed_ns",
    "operator_approval_ns", "answer_input_tokens", "answer_output_tokens",
    "grader_input_tokens", "grader_output_tokens", "source_operation_count",
    "source_range_bytes", "source_capture_ns", "candidate_discovery_ns",
    "context_composition_ns", "answer_generation_ns", "grading_ns",
    "cold_graph_build_ns", "retrieval_ns", "fallback_ns",
    "jev_request_bytes", "jev_shared_state_bytes", "jev_questions_bytes",
    "jev_candidate_count", "jev_question_count", "jev_source_bytes_verified",
    "jev_evaluator_elapsed_ms", "provider_input_tokens",
    "provider_output_tokens", "provider_calls", "provider_interval_ns",
    "provider_retries", "task_retries", "graph_record_count", "graph_edge_count",
)


def _phase_measurement(result: Mapping[str, Any], name: str) -> dict[str, Any]:
    phase = result.get("phases", {}).get(name, {})
    return {
        "status": phase.get("status", "missing"),
        "duration_ns": phase.get("inclusive_union_ns"),
    }


def _usage(attempts: list[Mapping[str, Any]], kind: str,
           complete: bool) -> tuple[int | None, int | None]:
    rows = [row for attempt in attempts for row in attempt.get("model_calls", [])
            if row.get("kind") == kind]
    if (not complete or not rows
            or any(row.get("provenance") == "unavailable"
                   or row.get("input_tokens") is None
                   or row.get("output_tokens") is None for row in rows)):
        return None, None
    return (sum(row["input_tokens"] for row in rows),
            sum(row["output_tokens"] for row in rows))


def _usage_missingness(attempts: list[Mapping[str, Any]], kind: str,
                       complete: bool) -> str | None:
    rows = [row for attempt in attempts for row in attempt.get("model_calls", [])
            if row.get("kind") == kind]
    if not complete:
        return "model_call_incomplete"
    if not rows:
        return "model_call_missing"
    if any(row.get("provenance") == "unavailable" for row in rows):
        return "host_usage_unavailable"
    if any(row.get("input_tokens") is None or row.get("output_tokens") is None
           for row in rows):
        return "host_token_fields_missing"
    return None


def _v3_trial_measurement(registration: Mapping[str, Any],
                          result: Mapping[str, Any] | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "trial_id": registration["trial_id"],
        "task_id": registration["task_id"],
        "terminal_reason": "missing" if result is None else result.get("terminal_reason"),
    }
    if result is None:
        row.update({key: None for key in V3_NUMERIC_METRICS})
        row.update({
            "first_pass_correct": None,
            "source_operations_complete": False,
            "cold_graph_build": {"status": "missing", "duration_ns": None},
            "warm_graph_load": {"status": "missing", "duration_ns": None},
            "source_capture": {"status": "missing", "duration_ns": None},
            "candidate_discovery": {"status": "missing", "duration_ns": None},
            "context_composition": {"status": "missing", "duration_ns": None},
            "answer_generation": {"status": "missing", "duration_ns": None},
            "grading": {"status": "missing", "duration_ns": None},
            "retrieval": {"status": "missing", "duration_ns": None},
            "fallback": {"status": "missing", "duration_ns": None},
            "provider": {"status": "missing", "duration_ns": None},
            "jev_rubric_version": None,
            "answer_usage_complete": False,
            "grader_usage_complete": False,
            "attempt_count": 0,
            "answer_call_count": 0,
            "grader_call_count": 0,
            "verified_fallback": None,
            "usage_missingness": {
                "answer": "model_call_missing",
                "grader": "model_call_missing",
                "provider": "model_call_missing",
            },
            "jev_score_observation": None,
            "shared_state_tokens": None,
            "question_suffix_tokens": None,
            "confidence_linked_failure": None,
        })
        return row

    attempts = result.get("attempts", [])
    answer_complete = bool(attempts) and all(
        attempt.get("coverage", {}).get("model_calls") is True
        and attempt.get("answer_boundary", {}).get("model_calls_complete") is True
        for attempt in attempts
    )
    answer_input, answer_output = _usage(attempts, "answer", answer_complete)
    grader_complete = bool(attempts) and all(
        attempt.get("coverage", {}).get("model_calls") is True for attempt in attempts)
    grader_input, grader_output = _usage(attempts, "grader", grader_complete)
    source_complete = bool(attempts) and all(
        attempt.get("coverage", {}).get("source_operations") is True for attempt in attempts)
    source_operations = [operation for attempt in attempts
                         for operation in attempt.get("source_operations", [])]
    answer_requests = [delivery for attempt in attempts
                       for delivery in attempt.get("context_deliveries", [])
                       if delivery.get("kind") == "answer_request"]
    jev_observations = [attempt["jev_observation"] for attempt in attempts
                        if type(attempt.get("jev_observation")) is dict]
    candidate_observations = [attempt["candidate_observation"] for attempt in attempts
                              if type(attempt.get("candidate_observation")) is dict]
    jev = jev_observations[0] if len(jev_observations) == 1 else {}
    candidate = candidate_observations[0] if len(candidate_observations) == 1 else {}
    provider_status = _phase_measurement(result, "provider")
    approval_status = _phase_measurement(result, "operator_approval")
    provider_complete = provider_status["status"] in {"observed", "not_applicable"}
    provider_input, provider_output = _usage(attempts, "jev", provider_complete)
    provider_calls = (0 if provider_status["status"] == "not_applicable"
                      else sum(observation.get("attempted_calls", 0)
                               for observation in jev_observations)
                      if jev_observations and all(
                          type(observation.get("attempted_calls")) is int
                          for observation in jev_observations) else None)
    confidences = [score.get("distribution_confidence") for observation in jev_observations
                   for score in observation.get("scores", [])
                   if type(score.get("distribution_confidence")) in (int, float)]
    failed = result.get("terminal_reason") != "passed"
    confidence_failure = None
    if failed and confidences:
        confidence_failure = {
            "terminal_reason": result.get("terminal_reason"),
            "candidate_count": len(confidences),
            "mean_distribution_confidence": sum(confidences) / len(confidences),
            "max_distribution_confidence": max(confidences),
            "interpretation": "descriptive_not_candidate_calibration",
        }
    row.update({
        "first_pass_correct": result.get("first_pass_correct"),
        "user_visible_wall_ns": result.get("user_visible_wall_ns"),
        "confirmed_time_to_correct_ns": result.get("confirmed_time_to_correct_ns"),
        "operator_approval_ns": approval_status["duration_ns"],
        "wall_excluding_operator_approval_ns": (
            result.get("user_visible_wall_ns") - approval_status["duration_ns"]
            if result.get("user_visible_wall_ns") is not None
            and approval_status["duration_ns"] is not None else None),
        "ttc_excluding_operator_approval_ns": (
            result.get("confirmed_time_to_correct_ns") - approval_status["duration_ns"]
            if result.get("confirmed_time_to_correct_ns") is not None
            and approval_status["duration_ns"] is not None else None),
        "observed_active_execution_ns": result.get("observed_active_execution_ns"),
        "observed_wait_union_ns": result.get("observed_wait_union_ns"),
        "unattributed_ns": result.get("unattributed_ns"),
        "answer_request_bytes": (answer_requests[-1].get("bytes")
                                 if answer_requests and any(
                                     attempt.get("phase_status", {}).get("answer_generation") == "observed"
                                     for attempt in attempts) else None),
        "answer_input_tokens": answer_input,
        "answer_output_tokens": answer_output,
        "answer_usage_complete": answer_complete,
        "grader_input_tokens": grader_input,
        "grader_output_tokens": grader_output,
        "grader_usage_complete": grader_complete,
        "attempt_count": len(attempts),
        "answer_call_count": sum(
            1 for attempt in attempts for call in attempt.get("model_calls", [])
            if call.get("kind") == "answer"
        ),
        "grader_call_count": sum(
            1 for attempt in attempts for call in attempt.get("model_calls", [])
            if call.get("kind") == "grader"
        ),
        "verified_fallback": (
            attempts[0].get("verified_fallback") if len(attempts) == 1 else None
        ),
        "usage_missingness": {
            "answer": _usage_missingness(attempts, "answer", answer_complete),
            "grader": _usage_missingness(attempts, "grader", grader_complete),
            "provider": (
                "not_applicable" if provider_status["status"] == "not_applicable"
                else _usage_missingness(attempts, "jev", provider_complete)
            ),
        },
        "source_operation_count": len(source_operations) if source_complete else None,
        "source_range_bytes": (sum(operation["byte_end"] - operation["byte_start"]
                                   for operation in source_operations)
                               if source_complete else None),
        "source_operations_complete": source_complete,
        "source_capture": _phase_measurement(result, "source_capture"),
        "candidate_discovery": _phase_measurement(result, "candidate_discovery"),
        "context_composition": _phase_measurement(result, "context_composition"),
        "answer_generation": _phase_measurement(result, "answer_generation"),
        "grading": _phase_measurement(result, "grading"),
        "cold_graph_build": _phase_measurement(result, "cold_graph_build"),
        "warm_graph_load": _phase_measurement(result, "warm_graph_load"),
        "retrieval": _phase_measurement(result, "retrieval"),
        "fallback": _phase_measurement(result, "fallback"),
        "provider": provider_status,
        "source_capture_ns": _phase_measurement(result, "source_capture")["duration_ns"],
        "candidate_discovery_ns": _phase_measurement(result, "candidate_discovery")["duration_ns"],
        "context_composition_ns": _phase_measurement(result, "context_composition")["duration_ns"],
        "answer_generation_ns": _phase_measurement(result, "answer_generation")["duration_ns"],
        "grading_ns": _phase_measurement(result, "grading")["duration_ns"],
        "cold_graph_build_ns": _phase_measurement(result, "cold_graph_build")["duration_ns"],
        "retrieval_ns": _phase_measurement(result, "retrieval")["duration_ns"],
        "fallback_ns": _phase_measurement(result, "fallback")["duration_ns"],
        "jev_request_bytes": jev.get("request_bytes"),
        "jev_shared_state_bytes": jev.get("shared_state_bytes"),
        "jev_questions_bytes": jev.get("questions_bytes"),
        "jev_candidate_count": jev.get("candidate_count"),
        "jev_question_count": jev.get("question_count"),
        "jev_source_bytes_verified": jev.get("source_bytes_verified"),
        "jev_evaluator_elapsed_ms": jev.get("elapsed_ms"),
        "jev_rubric_version": jev.get("rubric_version"),
        "jev_score_observation": (jev.get("scores") if jev_observations else None),
        "shared_state_tokens": None,
        "question_suffix_tokens": None,
        "provider_input_tokens": provider_input,
        "provider_output_tokens": provider_output,
        "provider_calls": provider_calls,
        "provider_interval_ns": provider_status["duration_ns"],
        "provider_retries": max(0, provider_calls - 1) if provider_calls is not None else None,
        "task_retries": max(0, len(attempts) - 1),
        "graph_record_count": candidate.get("record_count"),
        "graph_edge_count": candidate.get("edge_count"),
        "discovery_route": candidate.get("route"),
        "edge_expansion_status": candidate.get("edge_expansion_status"),
        "confidence_linked_failure": confidence_failure,
    })
    return row


def _metric_summary(rows: list[Mapping[str, Any]], metric: str) -> dict[str, Any]:
    values = [row[metric] for row in rows if type(row.get(metric)) in (int, float)]
    return {
        "observed_trials": len(values),
        "missing_trials": len(rows) - len(values),
        "mean": sum(values) / len(values) if values else None,
    }


def _paired_contrast(left: str, right: str,
                     rows_by_arm: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    left_by_task = {row["task_id"]: row for row in rows_by_arm[left]}
    right_by_task = {row["task_id"]: row for row in rows_by_arm[right]}
    metrics = {}
    for metric in V3_NUMERIC_METRICS:
        deltas = []
        for task in TASKS:
            left_value = left_by_task[task].get(metric)
            right_value = right_by_task[task].get(metric)
            if type(left_value) in (int, float) and type(right_value) in (int, float):
                deltas.append(left_value - right_value)
        metrics[metric] = {
            "paired_tasks": len(deltas),
            "missing_pairs": len(TASKS) - len(deltas),
            "mean_delta_left_minus_right": sum(deltas) / len(deltas) if deltas else None,
        }
    return {"left_arm": left, "right_arm": right, "metrics": metrics}


def _v3_measurements(config: Mapping[str, Any], completed: list[dict[str, Any]],
                     arm_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    results = {result["identity"]["trial_id"]: result for result in completed}
    for task in TASKS:
        for left, right in (("A", "B"), ("C", "D")):
            pair = [results.get(f"{arm}-{task}") for arm in (left, right)]
            if any(result is None for result in pair):
                continue
            observations = []
            for result in pair:
                attempts = result.get("attempts", [])
                found = [attempt.get("candidate_observation") for attempt in attempts
                         if type(attempt.get("candidate_observation")) is dict]
                if len(found) != 1:
                    raise MeasurementError("paired_candidate_packet_missing")
                observations.append(found[0])
            for key in ("candidate_packet_sha256", "baseline_order_sha256"):
                if (type(observations[0].get(key)) is not str
                        or observations[0][key] != observations[1].get(key)):
                    raise MeasurementError("paired_candidate_packet_mismatch")
    rows_by_arm: dict[str, list[dict[str, Any]]] = {}
    summaries = {}
    for arm in ARMS:
        registrations = [row for row in config["registered_trials"] if row["arm"] == arm]
        rows = [_v3_trial_measurement(row, results.get(row["trial_id"])) for row in registrations]
        rows_by_arm[arm] = rows
        summaries[arm] = {
            "outcomes": {key: arm_summaries[arm][key] for key in (
                "registered_trials", "reported_trials", "passed_within_budget",
                "pass_rate_registered", "first_pass_correct_registered",
                "mean_observed_terminal_wall_ns", "mean_time_to_correct_ns",
                "ttc_mean_policy", "coverage_complete",
            )},
            "metrics": {metric: _metric_summary(rows, metric)
                        for metric in V3_NUMERIC_METRICS},
            "trials": rows,
            "confidence_linked_task_failures": [
                {"trial_id": row["trial_id"], **row["confidence_linked_failure"]}
                for row in rows if row["confidence_linked_failure"] is not None
            ],
            "jev_score_observations": [
                {"trial_id": row["trial_id"], "scores": row["jev_score_observation"]}
                for row in rows if row["jev_score_observation"] is not None
            ],
        }
    return {
        "measurement_summaries": summaries,
        "paired_contrasts": {
            name: _paired_contrast(left, right, rows_by_arm)
            for name, left, right in (
                ("B-A", "B", "A"), ("D-C", "D", "C"),
                ("C-A", "C", "A"), ("D-B", "D", "B"),
            )
        },
        "candidate_calibration": {
            "status": "unscored",
            "reason": "no_candidate_level_oracle_exists",
            "confidence_linked_failures_are": "descriptive_only",
        },
    }


def summarize_calibration(config: Mapping[str, Any], completed: list[dict[str, Any]],
                          controller: Mapping[str, Any]) -> dict[str, Any]:
    """Close one mixed-arm calibration without weakening protocol comparison."""
    registrations = config["registered_trials"]
    expected = {row["trial_id"]: row["arm"] for row in registrations}
    seen: set[str] = set()
    for result in completed:
        identity = result.get("identity", {})
        trial_id, arm = identity.get("trial_id"), identity.get("arm")
        if (identity.get("run_id") != config["calibration_id"] or trial_id not in expected
                or trial_id in seen or expected[trial_id] != arm):
            raise MeasurementError("calibration_result_mismatch")
        seen.add(trial_id)
    oracle_set_sha256 = config["source_pilot"]["oracle_sha256"]
    arm_summaries = {}
    for arm in ARMS:
        trial_ids = [row["trial_id"] for row in registrations if row["arm"] == arm]
        results = []
        for result in completed:
            if result["identity"]["arm"] == arm:
                # Each task has its own rubric; the sealed oracle file is the arm-level protocol.
                results.append({
                    **result,
                    "identity": {**result["identity"], "rubric_sha256": oracle_set_sha256},
                })
        arm_summaries[arm] = summarize(trial_ids, results)
    coverage_complete = all(row["coverage_complete"] for row in arm_summaries.values())
    output = {
        "schema_version": "velgraphing-ttc-calibration-result-v1",
        "calibration_id": config["calibration_id"],
        "status": "closed" if coverage_complete else "incomplete",
        "oracle_set_sha256": oracle_set_sha256,
        "controller_identity": dict(controller),
        "registered_trials": len(registrations),
        "reported_trials": len(completed),
        "coverage_complete": coverage_complete,
        "arm_summaries": arm_summaries,
    }
    if config["calibration_id"] == V3_CALIBRATION_ID:
        measurements = _v3_measurements(config, completed, arm_summaries)
        output.update({
            "schema_version": "velgraphing-ttc-calibration-result-v3",
            "measurement_contract": config["measurement_contract"],
            **measurements,
        })
    return output


def request_candidates(trial: Trial, repo: Path, run_root: Path, payload: dict[str, Any],
                       wait_seconds: float,
                       response_contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {
        "schema_version": "velgraphing-preparation-input-v1",
        "identity": {
            key: trial.identity[key] for key in (
                "run_id", "trial_id", "task_id", "arm", "repository_id",
                "repository_commit", "source_snapshot_sha256", "answer_model",
                "reasoning", "prompt_sha256",
            )
        },
        "payload": payload,
    }
    if response_contract is not None:
        request["response_contract"] = dict(response_contract)
    trial.context(canonical(request), kind="answer_request")
    with trial.phase("source_capture"):
        output = _invoke(
            trial, "preparation", handoff_argv(run_root, trial.identity["trial_id"], "preparation", wait_seconds),
            request, repo, wait_seconds + 1,
        )
    expected = {"schema_version", "candidate_packet", "usage", "model_calls_complete", "context_deliveries_complete"}
    if (set(output) != expected or output["schema_version"] != "velgraphing-preparation-output-v1"
            or type(output["model_calls_complete"]) is not bool
            or type(output["context_deliveries_complete"]) is not bool):
        raise MeasurementError("invalid_preparation_output")
    record_usage(trial, output, "answer-preparation-0")
    module = load_jev(repo)
    return module.validate_packet(output["candidate_packet"])


def validate_live_authority(config: Mapping[str, Any], approved: bool, cap: int | None) -> None:
    if approved is not True:
        raise MeasurementError("live_jev_not_approved")
    if type(cap) is not int or cap != config["max_live_jev_calls"] or cap != 12:
        raise MeasurementError("live_jev_cap_not_bound")


def calibration_run_root(repo: Path, config: Mapping[str, Any], value: str) -> Path:
    root = validate_run_root(value)
    expected = (repo / ".velgraphing-local" / config["calibration_id"]).resolve()
    if root.resolve() != expected:
        raise MeasurementError("calibration_run_root_mismatch")
    return root


def require_resumable(root: Path, trial_id: str, completed_ids: set[str]) -> None:
    if trial_id not in completed_ids and (root / "trials" / trial_id).exists():
        raise MeasurementError("incomplete_trial_requires_parent_audit")


class LiveJevBudget:
    def __init__(self, root: Path, cap: int) -> None:
        self.root = root / "jev-calls"
        self.cap = cap

    def _open(self, *, create: bool) -> int:
        try:
            return open_contained_directory(
                self.root.parent, (self.root.name,), create=create)
        except HandoffError:
            raise MeasurementError("jev_call_ledger_invalid") from None

    def _receipts(self, directory: int) -> dict[str, dict[str, Any]]:
        receipts = {}
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            raise MeasurementError("jev_call_ledger_invalid") from None
        for name in names:
            if not name.endswith(".json") or Path(name).name != name:
                raise MeasurementError("jev_call_ledger_invalid")
            try:
                receipt = read_canonical_at(directory, name)[1]
            except HandoffError:
                raise MeasurementError("jev_call_ledger_invalid") from None
            trial_id = receipt.get("trial_id")
            number = receipt.get("call_number")
            if (receipt.get("schema_version") != "velgraphing-jev-call-receipt-v1"
                    or type(trial_id) is not str or name != f"{trial_id}.json"
                    or type(number) is not int or not 1 <= number <= self.cap
                    or receipt.get("max_live_jev_calls") != self.cap
                    or receipt.get("status") not in {"reserved_unknown_if_consumed", "consumed"}):
                raise MeasurementError("jev_call_ledger_invalid")
            receipts[name] = receipt
        numbers = {receipt["call_number"] for receipt in receipts.values()}
        if numbers != set(range(1, len(receipts) + 1)):
            raise MeasurementError("jev_call_ledger_invalid")
        return receipts

    def reserve(self, trial_id: str, request_sha256: str) -> tuple[Path, int]:
        trial_id = identifier(trial_id)
        name = f"{trial_id}.json"
        directory = self._open(create=True)
        try:
            existing = self._receipts(directory)
            if name in existing:
                raise MeasurementError("jev_call_already_reserved")
            if len(existing) >= self.cap:
                raise MeasurementError("jev_call_cap_exhausted")
            number = len(existing) + 1
            try:
                atomic_write_at(directory, name, canonical({
                    "schema_version": "velgraphing-jev-call-receipt-v1",
                    "trial_id": trial_id,
                    "request_sha256": request_sha256,
                    "call_number": number,
                    "max_live_jev_calls": self.cap,
                    "status": "reserved_unknown_if_consumed",
                    "attempted_calls": None,
                }))
            except HandoffError:
                raise MeasurementError("jev_call_ledger_invalid") from None
        finally:
            os.close(directory)
        return self.root / name, number

    def complete(self, path: Path, result: Mapping[str, Any]) -> None:
        if path.parent != self.root:
            raise MeasurementError("jev_call_ledger_invalid")
        directory = self._open(create=False)
        try:
            receipts = self._receipts(directory)
            reserved = receipts.get(path.name)
            if reserved is None or reserved["status"] != "reserved_unknown_if_consumed":
                raise MeasurementError("jev_call_ledger_invalid")
            try:
                atomic_write_at(directory, path.name, canonical({
                    **reserved,
                    "status": "consumed",
                    "attempted_calls": result.get("attempted_calls"),
                    "provider_status": result.get("status"),
                    "provider_reason": result.get("reason"),
                }), replace=True)
            except HandoffError:
                raise MeasurementError("jev_call_ledger_invalid") from None
        finally:
            os.close(directory)


def approval_response(trial: Trial, repo: Path, run_root: Path, prepared: Mapping[str, Any],
                      wait_seconds: float, cap: int) -> dict[str, Any]:
    payload = {
        "schema_version": "velgraphing-jev-approval-request-v1",
        "trial_id": trial.identity["trial_id"],
        "request_sha256": prepared["request_sha256"],
        "max_live_jev_calls": cap,
        "request": prepared["request"],
    }
    with trial.phase("operator_approval"):
        response = _invoke(
            trial, "jev_approval", handoff_argv(run_root, trial.identity["trial_id"], "jev-approval", wait_seconds),
            payload, repo, wait_seconds + 1,
        )
    expected = {"schema_version", "trial_id", "request_sha256", "approved", "max_live_jev_calls"}
    if (set(response) != expected or response["schema_version"] != "velgraphing-jev-approval-v1"
            or response["trial_id"] != trial.identity["trial_id"]
            or response["request_sha256"] != prepared["request_sha256"]
            or response["approved"] is not True or response["max_live_jev_calls"] != cap):
        raise MeasurementError("jev_request_not_approved")
    return response


def trial_identity(config: Mapping[str, Any], registration: Mapping[str, Any],
                   packet: Mapping[str, Any], corpus: Mapping[str, Any],
                   oracle: Mapping[str, Any], dirty_sha256: str) -> dict[str, Any]:
    return {
        "run_id": config["calibration_id"],
        "trial_id": registration["trial_id"],
        "task_id": registration["task_id"],
        "arm": registration["arm"],
        "repository_id": corpus["id"],
        "repository_commit": corpus["commit"],
        "source_snapshot_sha256": corpus["snapshot_sha256"],
        "dirty_state_sha256": dirty_sha256,
        "answer_model": config["answer_model"],
        "reasoning": config["reasoning"],
        "prompt_sha256": digest(packet["question"].encode("utf-8")),
        "rubric_sha256": digest(canonical(oracle)),
        "rubric_version": "velgraphing-corpus-pilot-oracle-v1",
        "answer_lane_id": f"answer-{registration['trial_id']}",
    }


def validate_completed_receipts(config: Mapping[str, Any], completed: list[dict[str, Any]],
                                packets: Mapping[str, Any], corpora: Mapping[str, Any],
                                oracle: Mapping[str, Any]) -> set[str]:
    registrations = {row["trial_id"]: row for row in config["registered_trials"]}
    seen: set[str] = set()
    for result in completed:
        identity = result.get("identity")
        trial_id = identity.get("trial_id") if type(identity) is dict else None
        registration = registrations.get(trial_id)
        if registration is None or trial_id in seen:
            raise MeasurementError("calibration_result_mismatch")
        packet = packets[registration["packet_id"]]
        corpus = corpora[packet["corpus"]["id"]]
        dirty = identity.get("dirty_state_sha256")
        expected = trial_identity(
            config, registration, packet, corpus, oracle[registration["task_id"]], dirty)
        if (type(dirty) is not str or len(dirty) != 64
                or any(character not in "0123456789abcdef" for character in dirty)
                or identity != expected or result.get("budget") != config["repair_budget"]
                or result.get("pass_recall_min") != 0.9
                or result.get("execution") != "observed"):
            raise MeasurementError("calibration_result_mismatch")
        seen.add(trial_id)
    return seen


def run_registered_trial(repo: Path, run_root: Path, lane_root: Path,
                         config: Mapping[str, Any], registration: Mapping[str, Any],
                         packet: Mapping[str, Any], corpus: Mapping[str, Any],
                         oracle: Mapping[str, Any], budget: LiveJevBudget) -> dict[str, Any]:
    corpus_id = corpus.get("id")
    if type(corpus_id) is not str or not corpus_id or PurePosixPath(corpus_id).name != corpus_id:
        raise MeasurementError("corpus_root_invalid")
    corpus_root = lane_root / corpus_id
    scope, lane_before = verify_lane(repo, corpus, corpus_root)
    identity = trial_identity(
        config, registration, packet, corpus, oracle,
        lane_before["restricted_state_sha256"])
    trial = Trial(identity, Budget(**config["repair_budget"]), execution="observed")
    timeouts = config["timeouts_seconds"]
    contracted = config["calibration_id"] in {V2_CALIBRATION_ID, V3_CALIBRATION_ID}
    v3 = config["calibration_id"] == V3_CALIBRATION_ID

    def prepare(current: Trial, attempt: int) -> dict[str, Any]:
        if v3:
            navigation = None
            route = "direct"
            if registration["arm"] in {"C", "D"}:
                route = "graph"
                navigation = observe_graph_find(
                    current, repo, graph_argv(packet, repo, corpus_root))
            else:
                current.not_applicable("cold_graph_build", "warm_graph_load")
            current.not_applicable("fallback")
            candidate = build_candidate_packet(
                current, corpus_root, packet["question"], scope,
                route=route, graph_navigation=navigation,
            )
            order = [row["id"] for row in candidate["candidates"]]
            if registration["arm"] in JEV_ARMS:
                prepared = prepare_preview(current, repo, candidate, corpus_root)
                approval_response(
                    current, repo, run_root, prepared,
                    timeouts["jev_approval"], budget.cap,
                )
                receipt_path, call_number = budget.reserve(
                    registration["trial_id"], prepared["request_sha256"])
                result = evaluate_live(
                    current, repo, candidate, corpus_root,
                    approved_request_sha256=prepared["request_sha256"],
                    runtime_approved=True, max_live_calls=budget.cap,
                    call_number=call_number, retain_packet_telemetry=True,
                )
                budget.complete(receipt_path, result)
                order = jev_answer_payload(candidate, result)["order"]
            else:
                current.not_applicable(
                    "jev_preparation", "provider", "source_revalidation",
                    "response_validation", "operator_approval",
                )
            answer_payload = compose_answer_payload(
                current, corpus_root, candidate, order)
            current.coverage(source_operations=True)
            return answer_payload

        base = {
            "schema_version": "velgraphing-native-lane-packet-v1",
            "trial_id": registration["trial_id"],
            "task_id": registration["task_id"],
            "arm": registration["arm"],
            "question": packet["question"],
            "corpus_root": str(corpus_root),
            "source_scope": scope,
            "instructions": packet["instructions"],
            "route": packet["arm"]["retrieval"],
            "graph_navigation": None,
            "jev": {"mode": "off"},
        }
        if registration["arm"] in {"C", "D"}:
            base["graph_navigation"] = observe_graph_find(current, repo, graph_argv(packet, repo, corpus_root))
        else:
            current.not_applicable("cold_graph_build", "warm_graph_load")
        if registration["arm"] in JEV_ARMS:
            candidate = request_candidates(
                current, repo, run_root, base, timeouts["preparation"],
                PREPARATION_RESPONSE_CONTRACT if contracted else None,
            )
            prepared = prepare_preview(current, repo, candidate, corpus_root)
            approval_response(current, repo, run_root, prepared, timeouts["jev_approval"], budget.cap)
            receipt_path, call_number = budget.reserve(registration["trial_id"], prepared["request_sha256"])
            result = evaluate_live(
                current, repo, candidate, corpus_root,
                approved_request_sha256=prepared["request_sha256"], runtime_approved=True,
                max_live_calls=budget.cap, call_number=call_number,
            )
            budget.complete(receipt_path, result)
            base["jev"] = jev_answer_payload(candidate, result)
        else:
            current.not_applicable(
                "jev_preparation", "provider", "source_revalidation",
                "response_validation", "operator_approval",
            )
        return base

    answer_command = handoff_argv(run_root, registration["trial_id"], "answer", timeouts["answer"])
    grader_command = handoff_argv(run_root, registration["trial_id"], "grader", timeouts["grader"])
    grader_context = {
        "schema_version": "velgraphing-grader-context-v1",
        "task_id": registration["task_id"],
        "corpus_root": str(corpus_root),
        "source_scope": scope,
        "required_facts": oracle["required_facts"],
        "critical_facts": oracle["critical_facts"],
        "acceptable_spans": oracle["acceptable_spans"],
    }
    result = run_process_trial(
        trial, prepare, answer_argv=answer_command, grader_argv=grader_command,
        cwd=repo, answer_timeout_s=timeouts["answer"] + 1,
        grader_timeout_s=timeouts["grader"] + 1, grader_context=grader_context,
        answer_response_contract=ANSWER_RESPONSE_CONTRACT if contracted else None,
        grader_response_contract=GRADER_RESPONSE_CONTRACT if contracted else None,
    )
    revalidate_lane(repo, corpus, corpus_root, lane_before)
    return result


def run_calibration(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo_root).resolve()
    if repo != REPO_ROOT.resolve():
        raise MeasurementError("repository_root_mismatch")
    controller = controller_identity(repo)
    config = load_calibration(repo, args.calibration_id)
    validate_live_authority(config, args.allow_live_jev, args.approved_max_live_jev_calls)
    root = calibration_run_root(repo, config, args.run_root)
    controller = bind_controller(root, controller)
    lane_root = Path(args.lane_root).resolve()
    allowed_lane_root = (repo / "benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes").resolve()
    try:
        relative_lane = lane_root.relative_to(allowed_lane_root)
    except ValueError:
        raise MeasurementError("lane_root_outside_frozen_inputs") from None
    if not relative_lane.parts:
        raise MeasurementError("lane_root_must_be_materialized_child")
    packets, corpora, oracle = load_pilot(repo, config)
    expected_ids = [row["trial_id"] for row in config["registered_trials"]]
    receipt_root = root / "completed"
    completed = load_completed_trials(receipt_root, expected_ids)
    completed_ids = validate_completed_receipts(config, completed, packets, corpora, oracle)
    budget = LiveJevBudget(root, config["max_live_jev_calls"])
    for registration in config["registered_trials"]:
        trial_id = registration["trial_id"]
        if trial_id in completed_ids:
            continue
        require_resumable(root, trial_id, completed_ids)
        packet = packets[registration["packet_id"]]
        if packet.get("question_id") != registration["task_id"] or packet.get("arm", {}).get("jev") != ("on" if registration["arm"] in JEV_ARMS else "off"):
            raise MeasurementError("calibration_packet_mismatch")
        corpus = corpora[packet["corpus"]["id"]]
        result = run_registered_trial(repo, root, lane_root, config, registration,
                                      packet, corpus, oracle[registration["task_id"]], budget)
        save_completed_trial(receipt_root, result)
        completed.append(result)
        completed_ids.add(trial_id)
    return summarize_calibration(config, completed, controller)


def start_fixture_worker(root: Path, trial_id: str, lane: str, wait: float = 5,
                         python_executable: str | Path | None = None) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [_python_executable(python_executable), str(HANDOFF_PATH), "fixture-worker", "--run-root", str(root),
         "--trial-id", trial_id, "--attempt", "0", "--lane", lane,
         "--wait-seconds", str(wait)],
        cwd=str(REPO_ROOT), env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def finish_workers(workers: list[subprocess.Popen[bytes]]) -> None:
    for worker in workers:
        stdout, stderr = worker.communicate(timeout=10)
        if worker.returncode:
            raise MeasurementError("fixture_worker_failed")
        if stdout or stderr:
            raise MeasurementError("fixture_worker_output_unexpected")


def fixture_identity(trial_id: str, arm: str, snapshot: str) -> dict[str, Any]:
    return {
        "run_id": "calibration-qualification", "trial_id": trial_id,
        "task_id": "fixture-task", "arm": arm, "repository_id": "fixture-repository",
        "repository_commit": "a" * 40, "source_snapshot_sha256": snapshot,
        "dirty_state_sha256": digest(b""), "answer_model": "fixture-model",
        "reasoning": "none", "prompt_sha256": digest(b"fixture prompt"),
        "rubric_sha256": digest(b"fixture rubric"), "rubric_version": "fixture-v1",
        "answer_lane_id": f"answer-{trial_id}",
    }


def fixture_repo(root: Path) -> tuple[Path, str]:
    source = root / "source"
    source.mkdir()
    (source / "cancel.py").write_text("def cancel_task(task):\n    return task.cancel()\n", encoding="utf-8")
    (source / "README.md").write_text("# Cancellation\ncancel_task requests cancellation.\n", encoding="utf-8")
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "core.hooksPath=/dev/null", "add", "cancel.py", "README.md"], check=True)
    rows = [{"path": path.name, "byte_length": len(path.read_bytes()), "sha256": digest(path.read_bytes())}
            for path in sorted((source / "README.md", source / "cancel.py"))]
    return source, digest(canonical({"sources": rows}))


def replay_envelope(repo: Path, packet: dict[str, Any], source: Path) -> dict[str, Any]:
    module = load_jev(repo)
    prepared = module.prepare(packet, source)
    legend = {str(index): value for index, value in enumerate(module._rubric_criteria())}
    scores = [0] + [2] * (len(packet["candidates"]) - 1)
    return {
        "schema_version": "velgraphing-jev-replay-v1",
        "request_sha256": prepared["request_sha256"],
        "response": {
            "model": module.DEFAULT_MODEL,
            "answers": {
                f"candidate_{index}": {
                    "type": "score", "score": score, "confidence": 1.0,
                    "probabilities": {str(value): int(value == score) for value in range(3)},
                    "legend": legend,
                }
                for index, score in enumerate(scores)
            },
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }


def qualify(repo: Path = REPO_ROOT,
            calibration_id: str = DEFAULT_CALIBRATION_ID) -> dict[str, Any]:
    config = load_calibration(repo, calibration_id)
    contracted = config["calibration_id"] in {V2_CALIBRATION_ID, V3_CALIBRATION_ID}
    v3 = config["calibration_id"] == V3_CALIBRATION_ID
    local_root = repo / ".velgraphing-local"
    local_root.mkdir(mode=0o700, exist_ok=True)
    root = local_root / f"ttc-calibration-qualification-{uuid.uuid4().hex}"
    root.mkdir(mode=0o700)
    try:
        source, snapshot = fixture_repo(root)
        handoff_root = root / "run"
        direct_workers = [start_fixture_worker(handoff_root, "direct-off", lane) for lane in ("answer", "grader")]
        direct_trial = Trial(fixture_identity("direct-off", "A", snapshot), Budget(0, 2_000_000_000), execution="fixture")
        def direct_prepare(trial: Trial, _: int) -> dict[str, Any]:
            trial.not_applicable("cold_graph_build", "warm_graph_load", "jev_preparation", "provider",
                                 "source_revalidation", "response_validation", "operator_approval")
            if v3:
                trial.not_applicable("fallback")
                candidate = build_candidate_packet(
                    trial, source,
                    "Find cancel_task cancellation implementation and documentation",
                    ["README.md", "cancel.py"], route="direct")
                payload = compose_answer_payload(
                    trial, source, candidate,
                    [row["id"] for row in candidate["candidates"]])
                trial.coverage(source_operations=True)
                return payload
            return {
                "question": "Find cancel_task cancellation implementation and documentation",
                "evidence": [],
            }
        direct = run_process_trial(
            direct_trial, direct_prepare,
            answer_argv=handoff_argv(handoff_root, "direct-off", "answer", 1),
            grader_argv=handoff_argv(handoff_root, "direct-off", "grader", 1),
            cwd=repo, answer_timeout_s=1.5, grader_timeout_s=1.5,
            answer_response_contract=ANSWER_RESPONSE_CONTRACT if contracted else None,
            grader_response_contract=GRADER_RESPONSE_CONTRACT if contracted else None,
        )
        finish_workers(direct_workers)

        graph_lanes = ("answer", "grader") if v3 else ("preparation", "answer", "grader")
        graph_workers = [start_fixture_worker(handoff_root, "graph-on", lane) for lane in graph_lanes]
        graph_trial = Trial(fixture_identity("graph-on", "D", snapshot), Budget(0, 3_000_000_000), execution="fixture")
        qualified_navigation: dict[str, Any] = {}
        def graph_prepare(trial: Trial, _: int) -> dict[str, Any]:
            qualification_question = (
                "cancel_task" if v3
                else "Find cancel_task cancellation implementation and documentation")
            navigation = observe_graph_find(
                trial, repo, ["--root", str(source), "--prompt", qualification_question],
            )
            qualified_navigation["value"] = navigation
            evidence = navigation["evidence"]
            if not evidence:
                raise MeasurementError("qualification_graph_evidence_missing")
            if v3:
                trial.not_applicable("fallback", "operator_approval", "provider")
                candidate = build_candidate_packet(
                    trial, source,
                    qualification_question,
                    ["README.md", "cancel.py"], route="graph",
                    graph_navigation=navigation)
                envelope = replay_envelope(repo, candidate, source)
                result = evaluate_offline(
                    trial, repo, candidate, source, envelope=envelope,
                    retain_packet_telemetry=True)
                payload = compose_answer_payload(trial, source, candidate, result["order"])
                trial.coverage(source_operations=True)
                return payload
            candidates = [{
                "id": f"c{index}", "path": item["source_path"],
                "source_sha256": item["source_sha256"], "byte_start": item["byte_start"],
                "byte_end": item["byte_end"], "required": index == len(evidence[:6]) - 1,
            } for index, item in enumerate(evidence[:6])]
            packet = {"schema_version": "velgraphing-jev-candidates-v1",
                      "query": "Find cancel_task cancellation implementation and documentation",
                      "candidates": candidates}
            captured = request_candidates(
                trial, repo, handoff_root,
                {"fixture_candidate_packet": packet, "graph_navigation": navigation}, 1,
                PREPARATION_RESPONSE_CONTRACT if contracted else None,
            )
            envelope = replay_envelope(repo, captured, source)
            result = evaluate_offline(trial, repo, captured, source, envelope=envelope)
            trial.not_applicable("operator_approval")
            return {
                "question": "Find cancel_task cancellation implementation and documentation",
                "evidence": [],
                "graph_navigation": navigation,
                "jev": jev_answer_payload(captured, result),
            }
        graph = run_process_trial(
            graph_trial, graph_prepare,
            answer_argv=handoff_argv(handoff_root, "graph-on", "answer", 1),
            grader_argv=handoff_argv(handoff_root, "graph-on", "grader", 1),
            cwd=repo, answer_timeout_s=1.5, grader_timeout_s=1.5,
            answer_response_contract=ANSWER_RESPONSE_CONTRACT if contracted else None,
            grader_response_contract=GRADER_RESPONSE_CONTRACT if contracted else None,
        )
        finish_workers(graph_workers)

        pair_proof = None
        if v3:
            def paired_observation(arm: str, route: str,
                                   navigation: Mapping[str, Any] | None = None) -> dict[str, Any]:
                paired = Trial(fixture_identity(f"pair-{arm}", arm, snapshot),
                               Budget(0, 1_000_000_000), execution="fixture")
                def prepare_pair(current: Trial, _: int) -> dict[str, Any]:
                    current.not_applicable(
                        "cold_graph_build", "warm_graph_load", "fallback",
                        "jev_preparation", "provider", "source_revalidation",
                        "response_validation", "operator_approval",
                    )
                    if navigation is not None:
                        current.current["graph_observation"] = graph["attempts"][0]["graph_observation"]
                    pair_question = (
                        "cancel_task" if route == "graph"
                        else "Find cancel_task cancellation implementation and documentation"
                    )
                    candidate = build_candidate_packet(
                        current, source,
                        pair_question,
                        ["README.md", "cancel.py"], route=route,
                        graph_navigation=navigation)
                    payload = compose_answer_payload(
                        current, source, candidate,
                        [row["id"] for row in candidate["candidates"]])
                    current.coverage(source_operations=True)
                    return payload
                def answer_pair(current: Trial, payload: Mapping[str, Any], _: int) -> Answer:
                    current.context(canonical(payload))
                    current.usage(f"answer-pair-{arm}", "answer", provenance="fixture",
                                  model="fixture-model", input_tokens=1, output_tokens=1)
                    return Answer("pair qualification")
                def grade_pair(current: Trial, _answer: Answer, _: int) -> Grade:
                    current.coverage(model_calls=True, context_deliveries=True)
                    return Grade(True, 1, 1, True, 0, "pair-grader", digest(b"fixture rubric"))
                result = paired.run(prepare_pair, answer_pair, grade_pair)
                return result["attempts"][0]["candidate_observation"]
            direct_a = direct["attempts"][0]["candidate_observation"]
            direct_b = paired_observation("B", "direct")
            graph_d = graph["attempts"][0]["candidate_observation"]
            graph_c = paired_observation("C", "graph", qualified_navigation["value"])
            pair_proof = {
                "direct": {
                    "candidate_packet_sha256": direct_a["candidate_packet_sha256"],
                    "baseline_order_sha256": direct_a["baseline_order_sha256"],
                    "a_b_match": all(direct_a[key] == direct_b[key] for key in (
                        "candidate_packet_sha256", "baseline_order_sha256")),
                },
                "graph": {
                    "candidate_packet_sha256": graph_d["candidate_packet_sha256"],
                    "baseline_order_sha256": graph_d["baseline_order_sha256"],
                    "c_d_match": all(graph_c[key] == graph_d[key] for key in (
                        "candidate_packet_sha256", "baseline_order_sha256")),
                },
                "answer_evidence_budget_bytes": V3_CANDIDATE_POLICY["answer_evidence_budget_bytes"],
            }

        missing_trial = Trial(fixture_identity("missing-response", "A", snapshot),
                              Budget(0, 1_000_000_000), execution="fixture")
        def missing_prepare(trial: Trial, _: int) -> dict[str, Any]:
            trial.not_applicable("cold_graph_build", "warm_graph_load", "jev_preparation", "provider",
                                 "source_revalidation", "response_validation", "operator_approval")
            return {"question": "missing response fixture", "evidence": []}
        missing = run_process_trial(
            missing_trial, missing_prepare,
            answer_argv=handoff_argv(handoff_root, "missing-response", "answer", 0.05),
            grader_argv=handoff_argv(handoff_root, "missing-response", "grader", 0.05),
            cwd=repo, answer_timeout_s=0.5, grader_timeout_s=0.5,
            answer_response_contract=ANSWER_RESPONSE_CONTRACT if contracted else None,
            grader_response_contract=GRADER_RESPONSE_CONTRACT if contracted else None,
        )
        receipt = read_lane(
            handoff_root, "missing-response", 0, "answer", "receipt.json")[1]
        try:
            validate_live_authority(config, False, None)
        except MeasurementError as error:
            refusal = error.reason
        else:
            raise MeasurementError("live_refusal_missing")
        return {
            "schema_version": "velgraphing-ttc-calibration-qualification-v1",
            "calibration_id": config["calibration_id"],
            "provider_calls_made": 0,
            "direct_off": {"terminal_reason": direct["terminal_reason"],
                           "answer_sha256": direct["attempts"][0]["answer_sha256"]},
            "graph_on_replay": {"terminal_reason": graph["terminal_reason"],
                                "graph_records": graph["attempts"][0]["graph_observation"]["record_count"],
                                "jev_execution": graph["attempts"][0]["jev_observation"]["measurement_execution"]},
            **({"pair_proof": pair_proof} if pair_proof is not None else {}),
            "missing_response": {"terminal_reason": missing["terminal_reason"],
                                 "handoff_status": receipt["status"]},
            "live_refusal": refusal,
        }
    finally:
        shutil.rmtree(root)


def approve(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo_root).resolve()
    config = load_calibration(repo, args.calibration_id)
    root = calibration_run_root(repo, config, args.run_root)
    validate_live_authority(config, True, args.approved_max_live_jev_calls)
    trial_id = identifier(args.trial_id)
    request = read_lane(root, trial_id, 0, "jev-approval", "request.json")[1]
    if (request.get("schema_version") != "velgraphing-jev-approval-request-v1"
            or request.get("trial_id") != trial_id
            or request.get("request_sha256") != args.request_sha256
            or request.get("max_live_jev_calls") != 12):
        raise MeasurementError("jev_request_not_approved")
    response = {
        "schema_version": "velgraphing-jev-approval-v1",
        "trial_id": trial_id,
        "request_sha256": args.request_sha256,
        "approved": True,
        "max_live_jev_calls": 12,
    }
    write_response(root, trial_id, 0, "jev-approval", canonical(response))
    return {"status": "approved", "trial_id": trial_id,
            "request_sha256": args.request_sha256}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    qualify_command = commands.add_parser("qualify")
    run = commands.add_parser("run")
    run.add_argument("--repo-root", required=True)
    run.add_argument("--lane-root", required=True)
    run.add_argument("--run-root", required=True)
    run.add_argument("--allow-live-jev", action="store_true")
    run.add_argument("--approved-max-live-jev-calls", type=int)
    approval = commands.add_parser("approve-jev")
    approval.add_argument("--repo-root", required=True)
    approval.add_argument("--run-root", required=True)
    approval.add_argument("--trial-id", required=True)
    approval.add_argument("--request-sha256", required=True)
    approval.add_argument("--approved-max-live-jev-calls", type=int, required=True)
    for command in (plan, qualify_command, run, approval):
        command.add_argument("--calibration-id", choices=sorted(CALIBRATION_SPECS),
                             default=DEFAULT_CALIBRATION_ID)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "plan":
            config = load_calibration(REPO_ROOT, args.calibration_id)
            output = {"calibration_id": config["calibration_id"],
                      "registered_trials": [row["trial_id"] for row in config["registered_trials"]],
                      "max_live_jev_calls": config["max_live_jev_calls"],
                      "provider_calls_made": 0}
        elif args.command == "qualify":
            output = qualify(REPO_ROOT, args.calibration_id)
        elif args.command == "approve-jev":
            output = approve(args)
        else:
            output = run_calibration(args)
        sys.stdout.buffer.write(canonical(output))
        return 0
    except MeasurementError as error:
        sys.stdout.buffer.write(canonical({"status": "refused", "reason": error.reason}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
