#!/usr/bin/env python3
"""Freeze and run the four-task Luna v4 successor through existing seams."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))

import time_to_correct_dependency_v4 as dependency
from time_to_correct import (
    Budget,
    MeasurementError,
    Trial,
    canonical,
    digest,
    load_completed_trials,
    save_completed_trial,
)
from time_to_correct_calibration import LiveJevBudget, require_resumable
from time_to_correct_handoff import HandoffError, atomic_write, atomic_write_at, open_contained_directory
from time_to_correct_host import ANSWER_RESPONSE_CONTRACT, GRADER_RESPONSE_CONTRACT, run_process_trial

from packages.core import RankedContextCandidate, Sensitivity, TaskSpec, select_ranked_context
from packages.core import jev


generator = dependency.generator
preview = dependency.preview
evaluator = dependency.evaluator

STUDY_ID = evaluator.LUNA_SUCCESSOR_STUDY
TASK_ARMS = (
    ("S-01", "ABDC"),
    ("D-01", "BCAD"),
    ("L-01", "CDBA"),
    ("M-02", "DACB"),
)
DISPATCH = tuple(f"{arm}-{task}" for task, arms in TASK_ARMS for arm in arms)
ARMS = {"A": "direct", "B": "direct", "C": "typed_graph", "D": "typed_graph"}
JEV_ARMS = {"B", "D"}
ANSWER_MODEL = "gpt-5.6-luna"
GRADER_MODEL = "gpt-5.6-luna"
REASONING = "medium"
REQUIRE_ANSWER_EVIDENCE_CITATION = False
JEV_MODEL = "jev-1.13.0"
FINAL_ANSWER_BYTES = 16_384
REQUEST_BYTES = 131_072
PROVIDER_TIMEOUT_SECONDS = 10
ANSWER_TIMEOUT_SECONDS = 180
GRADER_TIMEOUT_SECONDS = 120
TRIAL_WALL_LIMIT_SECONDS = 600
SOURCE_RUN_ROOT = ".velgraphing-local/retrievel-t030-luna-successor-r15"
RUN_ROOT = ".velgraphing-local/retrievel-t030-luna-successor-r16"
SOURCE_LANE_MANIFEST_SHA256 = "05474868d4bef62adf26f7158345e125d2d3d52971b7ae271200df636c86fa44"
SOURCE_RUN_CUSTODY_SHA256 = "9ed63df410b0ca340a55339d88ce4fda0eddefcf4da6d9c724554a0b4dbb8f50"
PENDING_TRIALS = ("C-M-02", "B-M-02")
IMPORTED_TRIALS = tuple(trial_id for trial_id in DISPATCH if trial_id not in PENDING_TRIALS)
IMPORTED_JEV_TRIALS = (
    "B-D-01", "B-L-01", "B-S-01", "D-D-01", "D-L-01", "D-M-02", "D-S-01",
)
PENDING_LANE_SLOTS = tuple(
    {"trial_id": trial_id, "role": role}
    for trial_id in PENDING_TRIALS for role in ("answer", "grader")
)
CONTINUATION_IMPORT_SCHEMA = "velgraphing-v4-luna-successor-continuation-import-v1"
LANE_ROLES = ("answer", "grader")
LANE_MANIFEST_SCHEMA = "velgraphing-v4-luna-lane-manifest-v1"
LANE_ENTRY_FIELDS = (
    "trial_id", "role", "thread_id", "model", "reasoning", "argv", "argv_sha256",
)
LANE_MANIFEST_CONTRACT = {
    "schema_version": LANE_MANIFEST_SCHEMA,
    "entry_count": len(DISPATCH) * len(LANE_ROLES),
    "roles": list(LANE_ROLES),
    "required_identity_fields": list(LANE_ENTRY_FIELDS),
    "model": ANSWER_MODEL,
    "reasoning": REASONING,
    "thread_reuse": "forbidden",
    "argv_identity": "sha256_of_canonical_argv",
}
QUESTIONS_PATH = ROOT / "benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json"
RUBRICS_PATH = ROOT / "benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json"
PLAN_PATH = ROOT / "benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json"
SNAPSHOTS = {
    "thealgorithms-python": "5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09",
    "engineering-handbook": "594aa47760172eba049e18c5f3a2f602a7b96b73a315756876955d7be81cd402",
    "openchain-reference-material": "7b06041a211f9365686f934eb7f37a0646f65ac4866d6837e37714ffb1e7679b",
}
GOVERNANCE_RULE = (
    "Every required fact maps to an explicit prompt ask. Incidental facts are diagnostic only."
)
STOP_RULES = [
    "stop_before_provider_if_live_authorized_is_not_true",
    "stop_on_candidate_question_rubric_snapshot_or_preview_hash_mismatch",
    "skip_jev_when_offline_preflight_cannot_change_final_membership",
    "stop_on_required_evidence_loss_or_source_revalidation_failure",
    "stop_on_provider_retry_or_call_cap_exhaustion",
    "stop_on_answer_or_grader_model_mismatch",
    "stop_on_lane_manifest_or_execution_identity_mismatch",
    "stop_on_continuation_receipt_lane_or_provider_link_mismatch",
    "stop_on_lane_state_change",
    "stop_after_any_systemic_trial_failure",
]
CALL_AUTHORIZATION = {
    "maximum_cost_usd": 1.0,
    "completed_prior_calls": 46,
    "planned_calls": 1,
    "aggregate_authorized_calls": 47,
    "price_usd_per_million_input_tokens": 0.042,
    "request_bytes_per_call_max": REQUEST_BYTES,
    "per_call_worst_case_usd": 0.005505024,
    "prior_authorization_envelope_usd": 0.253231104,
    "incremental_authorization_envelope_usd": 0.005505024,
    "aggregate_authorization_envelope_usd": 0.258736128,
    "authorization_remaining_usd": 0.741263872,
}

CONTINUATION_IMPORT_BINDING = {
    "path": f"{RUN_ROOT}/continuation-import.json",
    "sha256": "60740d89c0b9f16c878daf1c99530ba560711bf78453c5e58a31e8f8ec6ae4c4",
    "source_run_root": SOURCE_RUN_ROOT,
    "source_run_custody_sha256": SOURCE_RUN_CUSTODY_SHA256,
    "source_lane_manifest_sha256": SOURCE_LANE_MANIFEST_SHA256,
    "imported_trials": list(IMPORTED_TRIALS),
    "pending_trials": list(PENDING_TRIALS),
    "pending_lane_slots": list(PENDING_LANE_SLOTS),
}

CANDIDATE_ARTIFACT = {
    "path": ".inputs/t030-luna-successor-ranked-candidates-2255d9e.json",
    "sha256": "be5c4449581d46dab3aecc3e00dd8966cf8478ccabb174b98bec4741cace88dc",
    "selector_commit": "2255d9e51bccc6132b58a8bb2fe4ec485a57a5c9",
}
PREVIEW_ARTIFACT = {
    "path": ".inputs/t030-luna-successor-jev-preview-2255d9e.json",
    "sha256": "5969bc6330868823412ae7b9abe774e0c4fd4f90182ac5626fb85caf033cb8db",
    "adapter_commit": "2255d9e51bccc6132b58a8bb2fe4ec485a57a5c9",
}
LANE_MANIFEST_BINDING = {
    "path": f"{RUN_ROOT}/lane-manifest.json",
    "sha256": None,
    "status": "pending_host_lane_allocation",
    "entry_count": len(DISPATCH) * len(LANE_ROLES),
    "answer_lanes": len(DISPATCH),
    "grader_lanes": len(DISPATCH),
}
CONTROLLER_ARGV = [
    "/usr/bin/env", "python3",
    "scripts/benchmarks/time_to_correct_luna_successor_v4.py",
    "run",
    "--candidates", f"benchmarks/velgraphing-time-to-correct-v4/{CANDIDATE_ARTIFACT['path']}",
    "--questions", "benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json",
    "--rubrics", "benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json",
    "--manifests-root", "benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests",
    "--lanes-root", "../../benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4",
    "--preview", f"benchmarks/velgraphing-time-to-correct-v4/{PREVIEW_ARTIFACT['path']}",
    "--run-root", RUN_ROOT,
    "--lane-manifest", f"{RUN_ROOT}/lane-manifest.json",
    "--output", f"{RUN_ROOT}/result.json",
]
CONTROLLER = {
    "cwd": "repository_root",
    "argv": CONTROLLER_ARGV,
    "argv_sha256": digest(canonical(CONTROLLER_ARGV)),
}
TELEMETRY_SCHEMA = {
    "result_schema_version": "velgraphing-v4-luna-successor-result-v1",
    "answer_response_contract_sha256": digest(canonical(ANSWER_RESPONSE_CONTRACT)),
    "grader_response_contract_sha256": digest(canonical(GRADER_RESPONSE_CONTRACT)),
    "usage_null_means_unavailable": True,
    "completion_fields": ["model_calls_complete", "context_deliveries_complete"],
    "execution_identity_required": True,
}
HOST_TRANSPORT_CONTRACT = {
    "schema_version": "velgraphing-v4-host-transport-v2",
    "producer": "bound_luna_lane",
    "draft_scope": "exact_lane_directory",
    "transport_owner": "parent",
    "attestation_schema": "velgraphing-lane-completion-attestation-v1",
    "attestation_command": [
        "/usr/bin/env", "python3", "scripts/benchmarks/time_to_correct_handoff.py",
        "attest", "--run-root", "<absolute_frozen_run_root>",
        "--trial-id", "<trial_id>", "--attempt", "0", "--lane", "<role>",
        "--draft-file", "<exact_lane_generated_draft>",
        "--thread-id", "<bound_thread_id>", "--model", "gpt-5.6-luna",
        "--reasoning", "medium", "--lane-manifest-sha256",
        "<frozen_lane_manifest_sha256>", "--thread-status", "completed",
        "--draft-status", "stable-final",
    ],
    "publish_command": [
        "/usr/bin/env", "python3", "scripts/benchmarks/time_to_correct_handoff.py",
        "respond", "--run-root", "<absolute_frozen_run_root>",
        "--trial-id", "<trial_id>", "--attempt", "0", "--lane", "<role>",
        "--response-file", "<exact_lane_generated_draft>",
        "--thread-id", "<bound_thread_id>", "--model", "gpt-5.6-luna",
        "--reasoning", "medium", "--lane-manifest-sha256",
        "<frozen_lane_manifest_sha256>", "--normalize-json",
    ],
    "timing": "after_bound_lane_thread_terminal_completed_and_exact_draft_stable_final",
    "attestation_binding": [
        "trial_id", "role", "thread_id", "execution_identity",
        "lane_manifest_sha256", "draft_path", "draft_size_bytes", "draft_sha256",
    ],
    "content_policy": "canonical_json_only_no_edit_regeneration_or_substitution",
    "accounting": "host_transport_not_model_retry",
    "failure_policy": "fail_closed_on_missing_invalid_identity_or_contract",
}


class SuccessorError(MeasurementError):
    pass


def _read_json(path: Path, reason: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SuccessorError(reason) from None
    if type(value) is not dict:
        raise SuccessorError(reason)
    return value


def _semantic_sha256(value: object) -> str:
    return digest(generator._canonical(value))


def _canonical_file(path: Path, reason: str) -> tuple[bytes, dict[str, Any]]:
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SuccessorError(reason) from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or type(value) is not dict
        or raw != canonical(value)
    ):
        raise SuccessorError(reason)
    return raw, value


def tree_custody_sha256(root: Path) -> str:
    """Hash sorted file hashes and relative paths without parsing payloads."""
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise SuccessorError("successor_continuation_source_invalid")
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise SuccessorError("successor_continuation_source_invalid")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            rows.append(f"{digest(path.read_bytes())}  {relative}\n".encode("utf-8"))
    if not rows:
        raise SuccessorError("successor_continuation_source_invalid")
    return digest(b"".join(rows))


def _validate_completed_result(
    result: Mapping[str, Any],
    identity: Mapping[str, Any],
    candidate_set_sha256: str,
    lane_manifest: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    trial_id = identity["trial_id"]
    attempts = result.get("attempts")
    attempt = attempts[-1] if type(attempts) is list and attempts else {}
    if (
        result.get("schema_version") != "velgraphing-time-to-correct-v1"
        or result.get("identity") != identity
        or attempt.get("bindings", {}).get("candidate_set_sha256")
        != candidate_set_sha256
        or attempt.get("answer_boundary", {}).get("execution_identity")
        != _lane_execution_identity(lane_manifest[(trial_id, "answer")])
        or attempt.get("grader_boundary", {}).get("execution_identity")
        != _lane_execution_identity(lane_manifest[(trial_id, "grader")])
    ):
        raise SuccessorError("successor_completed_trial_conflict")
    _require_accepted_trial(result)


def _validate_jev_link(
    trial_id: str,
    result: Mapping[str, Any],
    ledger: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> str:
    attempt = result["attempts"][-1]
    request_sha256 = attempt.get("bindings", {}).get("request_sha256")
    if (
        ledger.get("schema_version") != "velgraphing-jev-call-receipt-v1"
        or ledger.get("trial_id") != trial_id
        or ledger.get("request_sha256") != request_sha256
        or ledger.get("status") != "consumed"
        or ledger.get("attempted_calls") != 1
        or observation.get("schema_version") != "velgraphing-jev-observation-v1"
        or observation.get("request_sha256") != request_sha256
        or observation.get("attempted_calls") != 1
        or attempt.get("jev_observation") != observation
    ):
        raise SuccessorError("successor_continuation_jev_link_invalid")
    return request_sha256


def _validate_copied_file(source: Path, destination: Path, sha256: str) -> None:
    try:
        source_raw = source.read_bytes()
        destination_raw = destination.read_bytes()
    except OSError:
        raise SuccessorError("successor_continuation_import_invalid") from None
    if (
        source.is_symlink() or destination.is_symlink()
        or source_raw != destination_raw
        or digest(source_raw) != sha256
    ):
        raise SuccessorError("successor_continuation_receipt_hash_invalid")


def freeze_continuation(
    source_root: Path,
    target_root: Path,
    identities: Mapping[str, Mapping[str, Any]],
    candidate_sets: Mapping[str, str],
    *,
    expected_source_custody_sha256: str = SOURCE_RUN_CUSTODY_SHA256,
    expected_source_lane_manifest_sha256: str = SOURCE_LANE_MANIFEST_SHA256,
) -> dict[str, Any]:
    """Copy accepted terminal receipts and their linked Jev evidence once."""
    if (
        not source_root.is_absolute()
        or not target_root.is_absolute()
        or source_root.resolve() != (ROOT / SOURCE_RUN_ROOT).resolve()
        or target_root.resolve() != (ROOT / RUN_ROOT).resolve()
        or target_root.exists()
    ):
        raise SuccessorError("successor_continuation_target_invalid")
    source_custody = tree_custody_sha256(source_root)
    if source_custody != expected_source_custody_sha256:
        raise SuccessorError("successor_continuation_source_drift")
    source_lanes = _lane_manifest(
        source_root / "lane-manifest.json", source_root,
        expected_sha256=expected_source_lane_manifest_sha256,
    )
    source_results = {
        result["identity"]["trial_id"]: result
        for result in load_completed_trials(source_root / "completed", DISPATCH)
    }
    if (
        set(source_results) != set(IMPORTED_TRIALS) | {"C-M-02"}
        or source_results["C-M-02"].get("terminal_reason") != "measurement_error"
        or source_results["C-M-02"].get("attempts", [{}])[-1].get("grade") is not None
    ):
        raise SuccessorError("successor_continuation_source_invalid")

    copies: list[tuple[str, str, str, str, bytes]] = []
    links = []
    for trial_id in IMPORTED_TRIALS:
        result = source_results[trial_id]
        _validate_completed_result(
            result, identities[trial_id], candidate_sets[trial_id], source_lanes
        )
        source_path = source_root / "completed" / f"{trial_id}.json"
        raw = source_path.read_bytes()
        copies.append((
            "completed_trial", trial_id, f"completed/{trial_id}.json",
            digest(raw), raw,
        ))
        if trial_id not in IMPORTED_JEV_TRIALS:
            continue
        ledger_raw, ledger = _canonical_file(
            source_root / "jev-calls" / f"{trial_id}.json",
            "successor_continuation_jev_link_invalid",
        )
        observation_raw, observation = _canonical_file(
            source_root / "jev-observations" / f"{trial_id}.json",
            "successor_continuation_jev_link_invalid",
        )
        request_sha256 = _validate_jev_link(trial_id, result, ledger, observation)
        ledger_path = f"imports/jev-calls/{trial_id}.json"
        observation_path = f"imports/jev-observations/{trial_id}.json"
        copies.extend((
            ("jev_call_receipt", trial_id, ledger_path, digest(ledger_raw), ledger_raw),
            ("jev_observation", trial_id, observation_path,
             digest(observation_raw), observation_raw),
        ))
        links.append({
            "trial_id": trial_id,
            "request_sha256": request_sha256,
            "ledger_path": ledger_path,
            "ledger_sha256": digest(ledger_raw),
            "observation_path": observation_path,
            "observation_sha256": digest(observation_raw),
        })

    target_root.mkdir(mode=0o700, parents=True)
    os.chmod(target_root, 0o700)
    file_rows = []
    for kind, trial_id, relative, sha256, raw in copies:
        destination = target_root / relative
        atomic_write(destination, raw)
        file_rows.append({
            "kind": kind,
            "trial_id": trial_id,
            "source_path": str(Path(SOURCE_RUN_ROOT) / relative.replace("imports/", "")),
            "destination_path": relative,
            "sha256": sha256,
        })
    imported_lanes = [
        dict(source_lanes[(trial_id, role)])
        for trial_id in IMPORTED_TRIALS for role in LANE_ROLES
    ]
    manifest = {
        "schema_version": CONTINUATION_IMPORT_SCHEMA,
        "source_run_root": SOURCE_RUN_ROOT,
        "source_run_custody_sha256": source_custody,
        "source_lane_manifest_sha256": expected_source_lane_manifest_sha256,
        "candidate_artifact_sha256": CANDIDATE_ARTIFACT["sha256"],
        "imported_trials": list(IMPORTED_TRIALS),
        "pending_trials": list(PENDING_TRIALS),
        "pending_lane_slots": list(PENDING_LANE_SLOTS),
        "files": file_rows,
        "lane_entries": imported_lanes,
        "jev_links": links,
    }
    atomic_write(target_root / "continuation-import.json", canonical(manifest))
    return manifest


def load_questions(path: Path = QUESTIONS_PATH) -> tuple[dict[str, dict[str, str]], str]:
    try:
        rows, registry_sha256 = generator._questions(path)
    except (OSError, generator.GenerationError):
        raise SuccessorError("successor_questions_invalid") from None
    questions = {row["id"]: row for row in rows}
    if tuple(questions) != tuple(task for task, _ in TASK_ARMS):
        raise SuccessorError("successor_questions_invalid")
    return questions, registry_sha256


def load_rubrics(path: Path = RUBRICS_PATH) -> tuple[dict[str, dict[str, Any]], str]:
    value = _read_json(path, "successor_rubrics_invalid")
    if (
        set(value) != {"schema_version", "governance_rule", "tasks"}
        or value["schema_version"] != "velgraphing-v4-luna-successor-rubrics-v1"
        or value["governance_rule"] != GOVERNANCE_RULE
        or type(value["tasks"]) is not dict
        or set(value["tasks"]) != {task for task, _ in TASK_ARMS}
    ):
        raise SuccessorError("successor_rubrics_invalid")
    for task, rubric in value["tasks"].items():
        if type(rubric) is not dict or set(rubric) != {
            "rubric_version", "asks", "required_facts", "critical_facts",
            "diagnostic_facts", "acceptable_spans",
        }:
            raise SuccessorError("successor_rubrics_invalid")
        asks = rubric["asks"]
        required = rubric["required_facts"]
        if type(asks) is not list or type(required) is not list or not asks or not required:
            raise SuccessorError("successor_rubrics_invalid")
        ask_ids: set[str] = set()
        for ask in asks:
            if (
                type(ask) is not dict
                or set(ask) != {"id", "text"}
                or type(ask["id"]) is not str
                or not ask["id"]
                or ask["id"] in ask_ids
                or type(ask["text"]) is not str
                or not ask["text"]
            ):
                raise SuccessorError("successor_rubrics_invalid")
            ask_ids.add(ask["id"])
        facts: list[str] = []
        for row in required:
            if (
                type(row) is not dict
                or set(row) != {"ask_id", "fact"}
                or row["ask_id"] not in ask_ids
                or type(row["fact"]) is not str
                or not row["fact"]
                or row["fact"] in facts
            ):
                raise SuccessorError("successor_rubrics_invalid")
            facts.append(row["fact"])
        critical = rubric["critical_facts"]
        diagnostic = rubric["diagnostic_facts"]
        spans = rubric["acceptable_spans"]
        if (
            type(rubric["rubric_version"]) is not str
            or not rubric["rubric_version"]
            or type(critical) is not list
            or not critical
            or not set(critical).issubset(facts)
            or type(diagnostic) is not list
            or any(type(fact) is not str or not fact for fact in diagnostic)
            or set(diagnostic).intersection(facts)
            or type(spans) is not list
            or not spans
            or any(type(span) is not str or not span for span in spans)
        ):
            raise SuccessorError("successor_rubrics_invalid")
        if task == "D-01" and not any("base case" in fact.lower() for fact in diagnostic):
            raise SuccessorError("successor_rubrics_invalid")
        if task == "L-01" and not any("Kafka" in fact for fact in diagnostic):
            raise SuccessorError("successor_rubrics_invalid")
    return value["tasks"], _semantic_sha256(value)


def grader_rubric(rubric: Mapping[str, Any]) -> dict[str, list[str]]:
    return {
        "required_facts": [row["fact"] for row in rubric["required_facts"]],
        "critical_facts": list(rubric["critical_facts"]),
        "acceptable_spans": list(rubric["acceptable_spans"]),
    }


def load_plan(path: Path = PLAN_PATH, *, expected_live_authorized: bool = False) -> dict[str, Any]:
    plan = _read_json(path, "successor_plan_invalid")
    candidate = plan.get("candidate_artifact")
    preview_artifact = plan.get("preview_artifact")
    questions = plan.get("question_registry")
    rubric = plan.get("rubric_manifest")
    call_authorization = plan.get("call_authorization")
    continuation_import = plan.get("continuation_import")
    if (
        set(plan) != {
            "schema_version", "study_id", "status", "candidate_artifact",
            "preview_artifact", "question_registry", "rubric_manifest",
            "source_snapshots", "models", "limits", "dispatch_order",
            "arm_preflight", "stop_rules", "call_authorization", "run_root",
            "live_authorized", "provider_calls_executed", "lane_manifest_contract",
            "lane_manifest", "controller", "telemetry_schema", "host_transport_contract",
            "continuation_import",
        }
        or plan["schema_version"] != "velgraphing-v4-luna-successor-plan-v5"
        or plan["study_id"] != STUDY_ID
        or plan["status"] != (
            "live_authorized_lane_manifest_frozen"
            if expected_live_authorized
            else "frozen_lane_manifest_pending_live_authorization"
        )
        or plan["run_root"] != RUN_ROOT
        or plan["live_authorized"] is not expected_live_authorized
        or plan["provider_calls_executed"] != 0
        or plan["dispatch_order"] != list(DISPATCH)
        or plan["source_snapshots"] != SNAPSHOTS
        or plan["lane_manifest_contract"] != LANE_MANIFEST_CONTRACT
        or plan["controller"] != CONTROLLER
        or plan["telemetry_schema"] != TELEMETRY_SCHEMA
        or plan["host_transport_contract"] != HOST_TRANSPORT_CONTRACT
        or candidate != CANDIDATE_ARTIFACT
        or preview_artifact != PREVIEW_ARTIFACT
        or questions != {
            "path": "luna-successor-questions.json",
            "sha256": evaluator.LUNA_SUCCESSOR_QUESTION_REGISTRY_SHA256,
        }
        or rubric != {
            "path": "luna-successor-rubrics.json",
            "sha256": "e1e9665d7136a260ee63f8db46bb833675f396777f9c2dd1c1fff4b50d8b6094",
            "governance_rule": GOVERNANCE_RULE,
        }
        or plan["stop_rules"] != STOP_RULES
        or call_authorization != CALL_AUTHORIZATION
        or continuation_import != CONTINUATION_IMPORT_BINDING
        or plan["models"] != {
            "answer": ANSWER_MODEL,
            "grader": GRADER_MODEL,
            "reasoning": REASONING,
            "jev": JEV_MODEL,
            "jev_rubric_version": jev.RUBRIC_VERSION,
        }
        or plan["limits"] != {
            "candidate_count": 64,
            "candidate_aggregate_bytes": 32_768,
            "candidate_unit_bytes": 4096,
            "final_answer_bytes": FINAL_ANSWER_BYTES,
            "request_bytes": REQUEST_BYTES,
            "answer_calls": len(PENDING_TRIALS),
            "grader_calls": len(PENDING_TRIALS),
            "maximum_jev_calls": CALL_AUTHORIZATION["planned_calls"],
            "retries": 0,
            "provider_timeout_seconds": PROVIDER_TIMEOUT_SECONDS,
            "answer_timeout_seconds": ANSWER_TIMEOUT_SECONDS,
            "grader_timeout_seconds": GRADER_TIMEOUT_SECONDS,
            "trial_wall_limit_seconds": TRIAL_WALL_LIMIT_SECONDS,
        }
    ):
        raise SuccessorError("successor_plan_invalid")
    binding = plan["lane_manifest"]
    common_binding = {
        key: LANE_MANIFEST_BINDING[key]
        for key in ("path", "entry_count", "answer_lanes", "grader_lanes")
    }
    if (
        type(binding) is not dict
        or set(binding) != set(LANE_MANIFEST_BINDING)
        or any(binding.get(key) != value for key, value in common_binding.items())
    ):
        raise SuccessorError("successor_plan_invalid")
    if not expected_live_authorized:
        if binding != LANE_MANIFEST_BINDING:
            raise SuccessorError("successor_plan_invalid")
        return plan
    manifest_sha256 = binding["sha256"]
    if (
        binding["status"] != "frozen"
        or type(manifest_sha256) is not str
        or len(manifest_sha256) != 64
        or any(character not in "0123456789abcdef" for character in manifest_sha256)
    ):
        raise SuccessorError("successor_plan_invalid")
    manifest_root = ROOT / RUN_ROOT
    manifest_path = ROOT / binding["path"]
    _lane_manifest(manifest_path, manifest_root, expected_sha256=manifest_sha256)
    return plan


def _frozen_fields(run: Mapping[str, Any]) -> dict[str, Any]:
    return {key: run[key] for key in (
        "task_id", "corpus", "prompt_sha256", "route", "source_snapshot_sha256",
        "sources", "candidates", "controls",
    )}


def regenerate_pool(
    task_id: str,
    route: str,
    question: Mapping[str, str],
    manifests_root: Path,
    lanes_root: Path,
    trial: Trial | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if route not in {"direct", "typed_graph"}:
        raise SuccessorError("successor_route_invalid")
    corpus = question["corpus"]
    manifest = generator._manifest(manifests_root / generator.CORPUS_MANIFESTS[corpus])
    lane_root = (lanes_root / corpus).resolve(strict=True)
    audit = dependency.SourceReadAudit(trial, manifest["source_count"] * 2) if trial else None
    observer = (lambda path, raw: audit.record("scanner", path, raw)) if audit else None
    phase = trial.phase("cold_graph_build") if trial else nullcontext()
    with phase:
        plain_graph, plain_snapshot, plain_reader, _ = generator.scan_lane(
            lane_root, manifest, derive_edges=False, source_observer=observer
        )
        typed_graph, typed_snapshot, typed_reader, _ = generator.scan_lane(
            lane_root, manifest, derive_edges=True, source_observer=observer
        )
    if (
        plain_snapshot != typed_snapshot
        or plain_graph.records != typed_graph.records
        or plain_snapshot.snapshot_sha256 != SNAPSHOTS[corpus]
    ):
        raise SuccessorError("successor_snapshot_drift")
    reader = dependency.AuditedReader(plain_reader, audit) if audit else plain_reader
    phase = trial.phase("candidate_discovery") if trial else nullcontext()
    with phase:
        index = generator.build_repository_tag_index(plain_graph, plain_snapshot, reader)
        facets = generator.compile_prompt(question["prompt"], index)
        if not facets.sufficient:
            facets = generator.compile_prompt(
                question["prompt"], index,
                proof_obligations=generator.compile_proof_obligations(
                    question["prompt"], plain_graph, index, plain_snapshot, reader
                ),
            )
    task = TaskSpec(
        task_id=task_id,
        query_terms=tuple(dict.fromkeys(
            token.casefold() for token in generator.graph_adapter._TOKEN.findall(question["prompt"])
        )),
        node_budget=generator.RETRIEVAL_NODE_LIMIT,
        byte_budget=32_768,
        allowed_sensitivities=(Sensitivity.PUBLIC, Sensitivity.INTERNAL),
    )
    graph = plain_graph if route == "direct" else typed_graph
    phase = trial.phase("retrieval") if trial else nullcontext()
    with phase:
        run, _ = generator._route_run(
            task, route, graph, plain_snapshot, reader, index, facets,
            derived_edge_count=0 if route == "direct" else len(typed_graph.edges),
            active_edge_count=0 if route == "direct" else len(typed_graph.edges),
            source_bound_expansion=route == "typed_graph",
            expand_one_hop=route == "typed_graph",
            candidate_limit=64,
            candidate_aggregate_byte_budget=32_768,
            candidate_unit_byte_budget=4096,
        )
    run.update({"corpus": corpus, "prompt_sha256": digest(question["prompt"].encode())})
    return run, {
        "lane": lane_root,
        "plain_graph": plain_graph,
        "typed_graph": typed_graph,
        "snapshot": plain_snapshot,
        "reader": reader,
        "restricted_state_sha256": dependency.lane_state_sha256(
            lane_root, plain_snapshot.snapshot_sha256
        ),
        "source_audit": audit,
    }


def _selection(
    task_id: str,
    arm: str,
    run: Mapping[str, Any],
    lane: Mapping[str, Any],
    question: Mapping[str, str],
    observation: Mapping[str, Any] | None,
) -> Any:
    candidates = tuple(RankedContextCandidate(
        row["id"], row["path"], row["source_sha256"], row["byte_start"],
        row["byte_end"], row["required"], row["record_id"],
        row["relationship_parent_candidate_id"],
    ) for row in run["candidates"])
    result = select_ranked_context(
        lane["plain_graph"] if run["route"] == "direct" else lane["typed_graph"],
        TaskSpec(
            task_id=f"{task_id}-{arm}",
            query_terms=(task_id,),
            byte_budget=FINAL_ANSWER_BYTES,
            allowed_sensitivities=(Sensitivity.PUBLIC, Sensitivity.INTERNAL),
        ),
        lane["snapshot"], lane["reader"], query=question["prompt"],
        candidates=candidates,
        approved_request_sha256=(observation.get("request_sha256") if observation else None),
        jev_observation=observation,
        jev_enabled=arm in JEV_ARMS,
        jev_observation_qualified=observation is not None,
    )
    if (
        result.projection.fail_closed
        or result.projection.serialized_byte_count > FINAL_ANSWER_BYTES
        or not set(result.projection.required_candidate_ids).issubset(
            result.projection.selected_candidate_ids
        )
        or not result.source_revalidated
    ):
        raise SuccessorError("successor_selection_invalid")
    return result


def preflight(
    candidates_path: Path,
    questions_path: Path,
    rubrics_path: Path,
    manifests_root: Path,
    lanes_root: Path,
    preview_path: Path,
    *,
    expected_live_authorized: bool = False,
    plan_path: Path = PLAN_PATH,
) -> dict[str, Any]:
    plan = load_plan(plan_path, expected_live_authorized=expected_live_authorized)
    questions, registry_sha256 = load_questions(questions_path)
    rubrics, rubric_sha256 = load_rubrics(rubrics_path)
    candidate_raw = candidates_path.read_bytes()
    preview_raw = preview_path.read_bytes()
    artifact, loaded_questions = preview._load_inputs(
        candidates_path, plan["candidate_artifact"]["sha256"], questions_path, STUDY_ID
    )
    regenerated, _ = generator.generate(
        questions_path, manifests_root, lanes_root,
        artifact["selector_commit"], study_id=STUDY_ID,
    )
    frozen_runs = {
        (run["task_id"], run["route"]): _frozen_fields(run)
        for run in artifact["runs"]
    }
    regenerated_runs = {
        (run["task_id"], run["route"]): _frozen_fields(run)
        for run in regenerated["runs"]
    }
    if (
        regenerated["schema_version"] != artifact["schema_version"]
        or regenerated["study_id"] != artifact["study_id"]
        or regenerated["selector_commit"] != artifact["selector_commit"]
        or regenerated["question_registry_sha256"]
        != artifact["question_registry_sha256"]
        or regenerated_runs != frozen_runs
    ):
        raise SuccessorError("successor_candidate_regeneration_mismatch")
    preview_value = json.loads(preview_raw)
    preview.validate_preview(
        preview_value,
        expected_candidate_artifact_sha256=plan["candidate_artifact"]["sha256"],
        expected_candidate_selector_commit=plan["candidate_artifact"]["selector_commit"],
        expected_adapter_commit=plan["preview_artifact"]["adapter_commit"],
        expected_study_id=STUDY_ID,
    )
    if (
        digest(candidate_raw) != plan["candidate_artifact"]["sha256"]
        or digest(preview_raw) != plan["preview_artifact"]["sha256"]
        or registry_sha256 != plan["question_registry"]["sha256"]
        or rubric_sha256 != plan["rubric_manifest"]["sha256"]
        or plan["rubric_manifest"]["governance_rule"] != GOVERNANCE_RULE
        or loaded_questions != questions
    ):
        raise SuccessorError("successor_artifact_identity_mismatch")
    runs = {(run["task_id"], run["route"]): run for run in artifact["runs"]}
    index = {f"{row['arm']}-{row['task_id']}": row for row in preview_value["index"]}
    preview_records = {
        f"{row['arm']}-{row['task_id']}": row for row in preview_value["records"]
    }
    observed: list[dict[str, Any]] = []
    planned_calls = 0
    for task_id, arms in TASK_ARMS:
        pools: dict[str, str] = {}
        for arm in arms:
            trial_id = f"{arm}-{task_id}"
            route = ARMS[arm]
            run = runs[(task_id, route)]
            pools[arm] = digest(canonical(run["candidates"]))
            row = index[trial_id]
            can_affect = bool(row["jev_call_could_affect_selection"])
            if trial_id in IMPORTED_TRIALS:
                disposition = "imported_completed"
                request_sha256 = row["request_sha256"] if arm in JEV_ARMS else None
                preview_sha256 = (
                    digest(canonical(preview_records[trial_id])) if arm in JEV_ARMS else None
                )
            elif arm not in JEV_ARMS:
                disposition = "treatment_off"
                request_sha256 = None
                preview_sha256 = None
            elif can_affect:
                disposition = "planned"
                request_sha256 = row["request_sha256"]
                preview_sha256 = digest(canonical(preview_records[trial_id]))
                planned_calls += 1
            else:
                disposition = "skip_no_membership_effect"
                request_sha256 = row["request_sha256"]
                preview_sha256 = digest(canonical(preview_records[trial_id]))
            observed.append({
                "trial_id": trial_id,
                "task_id": task_id,
                "arm": arm,
                "route": route,
                "pool_sha256": pools[arm],
                "preview_sha256": preview_sha256,
                "request_sha256": request_sha256,
                "jev_call_could_affect_selection": can_affect,
                "call_disposition": disposition,
            })
        if pools["A"] != pools["B"] or pools["C"] != pools["D"]:
            raise SuccessorError("successor_pair_mismatch")
    if (
        observed != plan["arm_preflight"]
        or planned_calls != plan["call_authorization"]["planned_calls"]
        or planned_calls > 8
    ):
        raise SuccessorError("successor_preflight_mismatch")
    identities = {}
    candidate_sets = {}
    for trial_id in DISPATCH:
        arm, task_id = trial_id.split("-", 1)
        identities[trial_id] = _current_trial_identity(
            task_id, arm, questions[task_id], rubrics[task_id],
            manifests_root, lanes_root,
        )[0]
        packet = dependency._packet(runs[(task_id, ARMS[arm])], questions[task_id])
        candidate_sets[trial_id] = digest(canonical(packet["candidates"]))
    continuation = validate_continuation(
        (ROOT / RUN_ROOT).resolve(), identities, candidate_sets
    )
    return {
        "schema_version": "velgraphing-v4-luna-successor-preflight-v1",
        "study_id": STUDY_ID,
        "candidate_artifact_sha256": digest(candidate_raw),
        "preview_artifact_sha256": digest(preview_raw),
        "planned_jev_calls": planned_calls,
        "provider_calls_executed": 0,
        "live_authorized": expected_live_authorized,
        "lane_manifest_contract_sha256": digest(canonical(LANE_MANIFEST_CONTRACT)),
        "lane_manifest_binding_sha256": digest(canonical(plan["lane_manifest"])),
        "controller_argv_sha256": CONTROLLER["argv_sha256"],
        "telemetry_schema_sha256": digest(canonical(TELEMETRY_SCHEMA)),
        "host_transport_contract_sha256": digest(canonical(HOST_TRANSPORT_CONTRACT)),
        "continuation_import_sha256": digest(canonical(continuation)),
        "arm_preflight": observed,
    }


def trial_identity(
    task_id: str,
    arm: str,
    question: Mapping[str, str],
    rubric: Mapping[str, Any],
    repository_commit: str,
    restricted_state_sha256: str,
) -> dict[str, Any]:
    return {
        "run_id": STUDY_ID,
        "trial_id": f"{arm}-{task_id}",
        "task_id": task_id,
        "arm": arm,
        "repository_id": question["corpus"],
        "repository_commit": repository_commit,
        "source_snapshot_sha256": SNAPSHOTS[question["corpus"]],
        "dirty_state_sha256": restricted_state_sha256,
        "answer_model": ANSWER_MODEL,
        "reasoning": REASONING,
        "prompt_sha256": digest(question["prompt"].encode()),
        "rubric_sha256": _semantic_sha256(grader_rubric(rubric)),
        "rubric_version": rubric["rubric_version"],
        "answer_lane_id": f"answer-{arm}-{task_id}",
    }


def _persist_observation(ledger: LiveJevBudget, trial_id: str, value: Mapping[str, Any]) -> None:
    directory = open_contained_directory(
        ledger.root.parent, ("jev-observations",), create=True
    )
    try:
        atomic_write_at(directory, f"{trial_id}.json", canonical(value))
    finally:
        os.close(directory)


def run_trial(
    task_id: str,
    arm: str,
    question: Mapping[str, str],
    rubric: Mapping[str, Any],
    frozen_run: Mapping[str, Any],
    manifests_root: Path,
    lanes_root: Path,
    call_disposition: str,
    *,
    answer_lane: Mapping[str, Any],
    grader_lane: Mapping[str, Any],
    ledger: LiveJevBudget,
    evaluate: Callable[..., Mapping[str, Any]] = jev.evaluate,
    execution: str = "observed",
) -> dict[str, Any]:
    identity, lane_root, restricted_state = _current_trial_identity(
        task_id, arm, question, rubric, manifests_root, lanes_root
    )
    trial = Trial(
        identity,
        Budget(max_repairs=0, wall_limit_ns=TRIAL_WALL_LIMIT_SECONDS * 1_000_000_000),
        execution=execution,
    )

    def prepare(current: Trial, _: int) -> dict[str, Any]:
        current.not_applicable("warm_graph_load", "host_queue", "operator_approval")
        run, lane = regenerate_pool(
            task_id, ARMS[arm], question, manifests_root, lanes_root, current
        )
        if _frozen_fields(run) != _frozen_fields(frozen_run):
            raise SuccessorError("successor_regenerated_pool_drift")
        packet = dependency._packet(run, question)
        current.bind(candidate_set_sha256=digest(canonical(packet["candidates"])))
        observation = None
        jev_execution = "off" if arm not in JEV_ARMS else "skipped"
        if call_disposition == "planned":
            audit = lane["source_audit"]
            with current.phase("jev_preparation"):
                with dependency._observe_jev_reads(audit):
                    prepared = jev.prepare(packet, lane["lane"], JEV_MODEL)
            if prepared["request_bytes"] > REQUEST_BYTES:
                raise SuccessorError("successor_request_budget_exceeded")
            current.bind(request_sha256=prepared["request_sha256"])
            receipt, _ = ledger.reserve(current.identity["trial_id"], prepared["request_sha256"])
            with current.phase("provider"):
                with dependency._observe_jev_reads(audit):
                    observation = evaluate(
                        packet, lane["lane"], mode="rerank", allow_network=True,
                        approved_request_sha256=prepared["request_sha256"],
                        model=JEV_MODEL, timeout_s=PROVIDER_TIMEOUT_SECONDS,
                    )
            ledger.complete(receipt, observation)
            with current.phase("response_validation"):
                if observation.get("attempted_calls") not in {0, 1}:
                    raise SuccessorError("successor_retry_detected")
            usage = observation.get("usage")
            if observation.get("status") == "fallback":
                with current.phase("fallback"):
                    observation = None
            else:
                current.not_applicable("fallback")
                observation = dependency._validate_preserved_observation(
                    observation, prepared, packet
                )
                _persist_observation(ledger, current.identity["trial_id"], observation)
                jev_execution = "live"
            current.usage(
                f"jev-{current.identity['trial_id']}", "jev",
                provenance="provider_reported" if usage is not None else "unavailable",
                input_tokens=usage.get("input_tokens") if usage else None,
                output_tokens=usage.get("output_tokens") if usage else None,
                cached_input_tokens=None, reasoning_output_tokens=None,
                cost_usd=None, model=JEV_MODEL,
            )
            if observation is not None:
                current._attempt()["jev_observation"] = observation
        else:
            current.not_applicable(
                "jev_preparation", "provider", "response_validation", "fallback"
            )
        with current.phase("source_revalidation"):
            with current.phase("source_capture"):
                selected = _selection(task_id, arm, run, lane, question, observation)
        with current.phase("context_composition"):
            payload = dependency._answer_evidence(question["prompt"], selected)
        current._attempt()["candidate_observation"] = {
            "pool_sha256": digest(canonical(run["candidates"])),
            "selected_candidate_ids": list(selected.projection.selected_candidate_ids),
            "required_candidate_ids": list(selected.projection.required_candidate_ids),
            "order_source": selected.order_source,
            "jev_execution": jev_execution,
            "source_operation_count": len(current._attempt()["source_operations"]),
        }
        if not lane["source_audit"].complete(
            packet, require_jev=call_disposition == "planned"
        ):
            raise SuccessorError("successor_source_coverage_incomplete")
        current.coverage(source_operations=True)
        return payload

    result = run_process_trial(
        trial, prepare, answer_argv=answer_lane["argv"], grader_argv=grader_lane["argv"],
        cwd=ROOT, answer_timeout_s=ANSWER_TIMEOUT_SECONDS,
        grader_timeout_s=GRADER_TIMEOUT_SECONDS,
        grader_context=grader_rubric(rubric), grader_model=GRADER_MODEL,
        answer_response_contract=ANSWER_RESPONSE_CONTRACT,
        grader_response_contract=GRADER_RESPONSE_CONTRACT,
        answer_execution_identity=_lane_execution_identity(answer_lane),
        grader_execution_identity=_lane_execution_identity(grader_lane),
        require_answer_evidence_citation=REQUIRE_ANSWER_EVIDENCE_CITATION,
    )
    if dependency.lane_state_sha256(
        lane_root, SNAPSHOTS[question["corpus"]]
    ) != restricted_state:
        raise SuccessorError("successor_lane_changed_during_trial")
    return result


def _lane_execution_identity(entry: Mapping[str, Any]) -> dict[str, str]:
    return {key: entry[key] for key in ("model", "reasoning", "role", "trial_id", "thread_id")}


def _validate_lane_entries(value: Any) -> dict[tuple[str, str], dict[str, Any]]:
    if type(value) is not list or len(value) != LANE_MANIFEST_CONTRACT["entry_count"]:
        raise SuccessorError("successor_lane_manifest_invalid")
    expected = {(trial_id, role) for trial_id in DISPATCH for role in LANE_ROLES}
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    threads: set[str] = set()
    for entry in value:
        if type(entry) is not dict or set(entry) != set(LANE_ENTRY_FIELDS):
            raise SuccessorError("successor_lane_manifest_invalid")
        trial_id = entry["trial_id"]
        role = entry["role"]
        thread_id = entry["thread_id"]
        command = entry["argv"]
        if (
            (trial_id, role) not in expected
            or type(thread_id) is not str or not thread_id or thread_id in threads
            or entry["model"] != ANSWER_MODEL or entry["reasoning"] != REASONING
            or type(command) is not list or not command
            or not all(type(argument) is str and argument for argument in command)
            or not Path(command[0]).is_absolute()
            or not Path(command[0]).is_file()
            or not os.access(command[0], os.X_OK)
            or entry["argv_sha256"] != digest(canonical(command))
            or (trial_id, role) in entries
        ):
            raise SuccessorError("successor_lane_manifest_invalid")
        entries[(trial_id, role)] = entry
        threads.add(thread_id)
    if set(entries) != expected:
        raise SuccessorError("successor_lane_manifest_invalid")
    return entries


def _lane_manifest(
    path: Path,
    root: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.is_absolute() or path.parent != root or path.is_symlink():
        raise SuccessorError("successor_lane_manifest_invalid")
    value = _read_json(path, "successor_lane_manifest_invalid")
    raw = path.read_bytes()
    if (
        raw != canonical(value)
        or set(value) != {"schema_version", "entries"}
        or value["schema_version"] != LANE_MANIFEST_SCHEMA
        or expected_sha256 is not None and digest(raw) != expected_sha256
    ):
        raise SuccessorError("successor_lane_manifest_invalid")
    return _validate_lane_entries(value["entries"])


def validate_continuation(
    root: Path,
    identities: Mapping[str, Mapping[str, Any]],
    candidate_sets: Mapping[str, str],
    *,
    live_lanes: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if (
        not root.is_absolute()
        or root.is_symlink()
        or not root.is_dir()
        or stat.S_IMODE(root.stat().st_mode) != 0o700
    ):
        raise SuccessorError("successor_continuation_import_invalid")
    manifest_raw, manifest = _canonical_file(
        root / "continuation-import.json", "successor_continuation_import_invalid"
    )
    if (
        digest(manifest_raw) != CONTINUATION_IMPORT_BINDING["sha256"]
        or set(manifest) != {
            "schema_version", "source_run_root", "source_run_custody_sha256",
            "source_lane_manifest_sha256", "candidate_artifact_sha256",
            "imported_trials", "pending_trials", "pending_lane_slots", "files",
            "lane_entries", "jev_links",
        }
        or manifest["schema_version"] != CONTINUATION_IMPORT_SCHEMA
        or manifest["source_run_root"] != SOURCE_RUN_ROOT
        or manifest["source_run_custody_sha256"] != SOURCE_RUN_CUSTODY_SHA256
        or manifest["source_lane_manifest_sha256"] != SOURCE_LANE_MANIFEST_SHA256
        or manifest["candidate_artifact_sha256"] != CANDIDATE_ARTIFACT["sha256"]
        or manifest["imported_trials"] != list(IMPORTED_TRIALS)
        or manifest["pending_trials"] != list(PENDING_TRIALS)
        or manifest["pending_lane_slots"] != list(PENDING_LANE_SLOTS)
    ):
        raise SuccessorError("successor_continuation_import_invalid")

    source_root = ROOT / SOURCE_RUN_ROOT
    if tree_custody_sha256(source_root) != SOURCE_RUN_CUSTODY_SHA256:
        raise SuccessorError("successor_continuation_source_drift")
    source_lanes = _lane_manifest(
        source_root / "lane-manifest.json", source_root,
        expected_sha256=SOURCE_LANE_MANIFEST_SHA256,
    )
    expected_lanes = [
        dict(source_lanes[(trial_id, role)])
        for trial_id in IMPORTED_TRIALS for role in LANE_ROLES
    ]
    if manifest["lane_entries"] != expected_lanes:
        raise SuccessorError("successor_continuation_lane_identity_invalid")
    if live_lanes is not None and any(
        live_lanes.get((entry["trial_id"], entry["role"])) != entry
        for entry in expected_lanes
    ):
        raise SuccessorError("successor_continuation_lane_identity_invalid")

    files = manifest["files"]
    if type(files) is not list or any(type(row) is not dict for row in files):
        raise SuccessorError("successor_continuation_import_invalid")
    by_destination = {row.get("destination_path"): row for row in files}
    expected_destinations = {
        *(f"completed/{trial_id}.json" for trial_id in IMPORTED_TRIALS),
        *(f"imports/jev-calls/{trial_id}.json" for trial_id in IMPORTED_JEV_TRIALS),
        *(f"imports/jev-observations/{trial_id}.json" for trial_id in IMPORTED_JEV_TRIALS),
    }
    actual_files = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    runtime_files = {
        "continuation-import.json", "lane-manifest.json", "controller.log", "result.json",
        *(f"completed/{trial_id}.json" for trial_id in PENDING_TRIALS),
        "jev-calls/B-M-02.json", "jev-observations/B-M-02.json",
    }
    unexpected = actual_files - expected_destinations - runtime_files
    if (
        len(by_destination) != len(files)
        or set(by_destination) != expected_destinations
        or not expected_destinations.issubset(actual_files)
        or any(
            not any(path.startswith(f"trials/{trial_id}/") for trial_id in PENDING_TRIALS)
            for path in unexpected
        )
    ):
        raise SuccessorError("successor_continuation_import_invalid")
    for relative, row in by_destination.items():
        if set(row) != {
            "kind", "trial_id", "source_path", "destination_path", "sha256"
        }:
            raise SuccessorError("successor_continuation_import_invalid")
        source = ROOT / row["source_path"]
        destination = root / relative
        _validate_copied_file(source, destination, row["sha256"])

    results = {
        result["identity"]["trial_id"]: result
        for result in load_completed_trials(root / "completed", IMPORTED_TRIALS)
    }
    if set(results) != set(IMPORTED_TRIALS):
        raise SuccessorError("successor_continuation_import_invalid")
    for trial_id, result in results.items():
        _validate_completed_result(
            result, identities[trial_id], candidate_sets[trial_id], source_lanes
        )

    links = manifest["jev_links"]
    if (
        type(links) is not list
        or len(links) != len(IMPORTED_JEV_TRIALS)
        or {row.get("trial_id") for row in links} != set(IMPORTED_JEV_TRIALS)
    ):
        raise SuccessorError("successor_continuation_jev_link_invalid")
    for link in links:
        if set(link) != {
            "trial_id", "request_sha256", "ledger_path", "ledger_sha256",
            "observation_path", "observation_sha256",
        }:
            raise SuccessorError("successor_continuation_jev_link_invalid")
        trial_id = link["trial_id"]
        ledger_raw, ledger = _canonical_file(
            root / link["ledger_path"], "successor_continuation_jev_link_invalid"
        )
        observation_raw, observation = _canonical_file(
            root / link["observation_path"], "successor_continuation_jev_link_invalid"
        )
        request_sha256 = _validate_jev_link(
            trial_id, results[trial_id], ledger, observation
        )
        if (
            link["request_sha256"] != request_sha256
            or link["ledger_sha256"] != digest(ledger_raw)
            or link["observation_sha256"] != digest(observation_raw)
        ):
            raise SuccessorError("successor_continuation_jev_link_invalid")
    return manifest


def _validated_run_root(path: Path) -> Path:
    expected = (ROOT / RUN_ROOT).resolve()
    if path.resolve() != expected:
        raise SuccessorError("successor_run_root_mismatch")
    return dependency._validated_run_root(path)


def _controller_run_root(path: Path) -> Path:
    return _validated_run_root(path if path.is_absolute() else ROOT / path)


def _current_trial_identity(
    task_id: str,
    arm: str,
    question: Mapping[str, str],
    rubric: Mapping[str, Any],
    manifests_root: Path,
    lanes_root: Path,
) -> tuple[dict[str, Any], Path, str]:
    manifest = generator._manifest(
        manifests_root / generator.CORPUS_MANIFESTS[question["corpus"]]
    )
    lane_root = (lanes_root / question["corpus"]).resolve(strict=True)
    restricted_state = dependency.lane_state_sha256(
        lane_root, SNAPSHOTS[question["corpus"]]
    )
    return (
        trial_identity(
            task_id, arm, question, rubric, manifest["commit"], restricted_state
        ),
        lane_root,
        restricted_state,
    )


def _load_current_completed(
    receipt_root: Path,
    identities: Mapping[str, Mapping[str, Any]],
    candidate_sets: Mapping[str, str],
    lane_manifest: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    completed = load_completed_trials(receipt_root, DISPATCH)
    by_id: dict[str, dict[str, Any]] = {}
    for result in completed:
        trial_id = result["identity"]["trial_id"]
        _validate_completed_result(
            result, identities[trial_id], candidate_sets[trial_id], lane_manifest
        )
        by_id[trial_id] = result
    return by_id


def _require_accepted_trial(result: Mapping[str, Any]) -> None:
    attempts = result.get("attempts")
    attempt = attempts[-1] if type(attempts) is list and attempts else {}
    coverage = attempt.get("coverage", {})
    if (
        result.get("terminal_reason") in {
            "measurement_error", "deadline_exceeded", "callback_timeout"
        }
        or not coverage.get("model_calls")
        or not coverage.get("context_deliveries")
    ):
        raise SuccessorError("successor_systemic_trial_failure")


def run_successor(
    candidates_path: Path,
    questions_path: Path,
    rubrics_path: Path,
    manifests_root: Path,
    lanes_root: Path,
    preview_path: Path,
    run_root: Path,
    *,
    lane_manifest: Mapping[tuple[str, str], Mapping[str, Any]],
    evaluate: Callable[..., Mapping[str, Any]] = jev.evaluate,
    execution: str = "observed",
) -> dict[str, Any]:
    preflight_started = time.monotonic_ns()
    frozen = preflight(
        candidates_path, questions_path, rubrics_path, manifests_root,
        lanes_root, preview_path, expected_live_authorized=True,
    )
    preflight_elapsed_ns = time.monotonic_ns() - preflight_started
    plan = load_plan(expected_live_authorized=True)
    questions, _ = load_questions(questions_path)
    rubrics, _ = load_rubrics(rubrics_path)
    artifact, _ = preview._load_inputs(
        candidates_path, plan["candidate_artifact"]["sha256"], questions_path, STUDY_ID
    )
    runs = {(row["task_id"], row["route"]): row for row in artifact["runs"]}
    dispositions = {row["trial_id"]: row["call_disposition"] for row in frozen["arm_preflight"]}
    validated_lanes = _validate_lane_entries(list(lane_manifest.values()))
    if set(lane_manifest) != set(validated_lanes):
        raise SuccessorError("successor_lane_manifest_invalid")
    lane_manifest = validated_lanes
    identities = {}
    candidate_sets = {}
    for trial_id in DISPATCH:
        arm, task_id = trial_id.split("-", 1)
        identities[trial_id] = _current_trial_identity(
            task_id, arm, questions[task_id], rubrics[task_id],
            manifests_root, lanes_root,
        )[0]
        packet = dependency._packet(runs[(task_id, ARMS[arm])], questions[task_id])
        candidate_sets[trial_id] = digest(canonical(packet["candidates"]))
    validate_continuation(
        run_root, identities, candidate_sets, live_lanes=lane_manifest
    )
    receipt_root = run_root / "completed"
    results_by_id = _load_current_completed(
        receipt_root, identities, candidate_sets, lane_manifest
    )
    completed_ids = set(results_by_id)
    for trial_id in DISPATCH:
        require_resumable(run_root, trial_id, completed_ids)
        if trial_id in completed_ids:
            _require_accepted_trial(results_by_id[trial_id])
    ledger = LiveJevBudget(run_root, plan["call_authorization"]["planned_calls"])
    for trial_id in DISPATCH:
        if trial_id in completed_ids:
            continue
        arm, task_id = trial_id.split("-", 1)
        question = questions[task_id]
        result = run_trial(
            task_id, arm, question, rubrics[task_id], runs[(task_id, ARMS[arm])],
            manifests_root, lanes_root, dispositions[trial_id],
            answer_lane=lane_manifest[(trial_id, "answer")],
            grader_lane=lane_manifest[(trial_id, "grader")],
            ledger=ledger, evaluate=evaluate, execution=execution,
        )
        save_completed_trial(receipt_root, result)
        results_by_id[trial_id] = result
        _require_accepted_trial(result)
    results = [results_by_id[trial_id] for trial_id in DISPATCH]
    return {
        "schema_version": "velgraphing-v4-luna-successor-result-v1",
        "preflight": frozen,
        "controller_preflight": {
            "elapsed_ns": preflight_elapsed_ns,
            "ttc_allocation": "separate_not_in_arm_ttc",
        },
        "results": results,
    }


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--rubrics", type=Path, required=True)
    parser.add_argument("--manifests-root", type=Path, required=True)
    parser.add_argument("--lanes-root", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight_parser = commands.add_parser("preflight")
    _add_inputs(preflight_parser)
    run_parser = commands.add_parser("run")
    _add_inputs(run_parser)
    run_parser.add_argument("--run-root", type=Path, required=True)
    run_parser.add_argument("--lane-manifest", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        inputs = (
            arguments.candidates.resolve(strict=True),
            arguments.questions.resolve(strict=True),
            arguments.rubrics.resolve(strict=True),
            arguments.manifests_root.resolve(strict=True),
            arguments.lanes_root.resolve(strict=True),
            arguments.preview.resolve(strict=True),
        )
        if arguments.command == "preflight":
            print(canonical(preflight(*inputs)).decode())
            return 0
        root = _controller_run_root(arguments.run_root)
        lane_manifest_path = arguments.lane_manifest
        if not lane_manifest_path.is_absolute():
            lane_manifest_path = ROOT / lane_manifest_path
        lane_manifest_path = lane_manifest_path.resolve(strict=True)
        live_plan = load_plan(expected_live_authorized=True)
        expected_manifest_path = (ROOT / live_plan["lane_manifest"]["path"]).resolve(strict=True)
        if lane_manifest_path != expected_manifest_path:
            raise SuccessorError("successor_lane_manifest_invalid")
        output = arguments.output if arguments.output.is_absolute() else ROOT / arguments.output
        if (
            not output.is_absolute() or output.parent != root
            or output.name != "result.json" or output.exists() or output.is_symlink()
        ):
            raise SuccessorError("successor_output_invalid")
        result = run_successor(
            *inputs, root,
            lane_manifest=_lane_manifest(
                lane_manifest_path,
                root,
                expected_sha256=live_plan["lane_manifest"]["sha256"],
            ),
        )
        atomic_write(output, canonical(result))
        print(canonical({
            "output": str(output),
            "output_sha256": digest(canonical(result)),
            "status": "written",
        }).decode())
        return 0
    except (
        HandoffError, MeasurementError, OSError, ValueError
    ) as error:
        reason = error.reason if isinstance(error, MeasurementError) else "successor_preflight_failed"
        print(f"luna-successor-controller: {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
