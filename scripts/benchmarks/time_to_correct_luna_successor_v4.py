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
from time_to_correct import Budget, MeasurementError, Trial, canonical, digest
from time_to_correct_calibration import LiveJevBudget
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
JEV_MODEL = "jev-1.13.0"
FINAL_ANSWER_BYTES = 16_384
REQUEST_BYTES = 131_072
PROVIDER_TIMEOUT_SECONDS = 10
ANSWER_TIMEOUT_SECONDS = 180
GRADER_TIMEOUT_SECONDS = 120
TRIAL_WALL_LIMIT_SECONDS = 600
RUN_ROOT = ".velgraphing-local/retrievel-t030-luna-successor-v1"
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
    "stop_on_lane_state_change",
    "stop_after_any_systemic_trial_failure",
]
CALL_AUTHORIZATION = {
    "maximum_cost_usd": 1.0,
    "completed_prior_calls": 6,
    "planned_calls": 8,
    "aggregate_authorized_calls": 14,
    "price_usd_per_million_input_tokens": 0.042,
    "request_bytes_per_call_max": REQUEST_BYTES,
    "per_call_worst_case_usd": 0.005505024,
    "prior_authorization_envelope_usd": 0.033030144,
    "incremental_authorization_envelope_usd": 0.044040192,
    "aggregate_authorization_envelope_usd": 0.077070336,
    "authorization_remaining_usd": 0.922929664,
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
    if (
        set(plan) != {
            "schema_version", "study_id", "status", "candidate_artifact",
            "preview_artifact", "question_registry", "rubric_manifest",
            "source_snapshots", "models", "limits", "dispatch_order",
            "arm_preflight", "stop_rules", "call_authorization", "run_root",
            "live_authorized", "provider_calls_executed",
        }
        or plan["schema_version"] != "velgraphing-v4-luna-successor-plan-v1"
        or plan["study_id"] != STUDY_ID
        or plan["status"] != "offline_frozen_parent_and_blind_review_pending"
        or plan["run_root"] != RUN_ROOT
        or plan["live_authorized"] is not expected_live_authorized
        or plan["provider_calls_executed"] != 0
        or plan["dispatch_order"] != list(DISPATCH)
        or plan["source_snapshots"] != SNAPSHOTS
        or candidate != {
            "path": ".inputs/t030-luna-successor-ranked-candidates-717f378.json",
            "sha256": "a3b39fea1d189d92e1dd1751e16f64642147383310fa23c41bb8c69449f4ec30",
            "selector_commit": "717f378103f692586647ded6d45fe7c699ba77d5",
        }
        or preview_artifact != {
            "path": ".inputs/t030-luna-successor-jev-preview-717f378.json",
            "sha256": "c1c77f0eeb155fdc8ebfde0a407f8f63658313ee36722908660fef1512457d7a",
            "adapter_commit": "717f378103f692586647ded6d45fe7c699ba77d5",
        }
        or questions != {
            "path": "luna-successor-questions.json",
            "sha256": evaluator.LUNA_SUCCESSOR_QUESTION_REGISTRY_SHA256,
        }
        or rubric != {
            "path": "luna-successor-rubrics.json",
            "sha256": "9cd4e4c191f2fb1932103f11a544e14f5bdabf83c8271a88bc49f4bcd1a43299",
            "governance_rule": GOVERNANCE_RULE,
        }
        or plan["stop_rules"] != STOP_RULES
        or call_authorization != CALL_AUTHORIZATION
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
            "answer_calls": 16,
            "grader_calls": 16,
            "maximum_jev_calls": CALL_AUTHORIZATION["planned_calls"],
            "retries": 0,
            "provider_timeout_seconds": PROVIDER_TIMEOUT_SECONDS,
            "answer_timeout_seconds": ANSWER_TIMEOUT_SECONDS,
            "grader_timeout_seconds": GRADER_TIMEOUT_SECONDS,
            "trial_wall_limit_seconds": TRIAL_WALL_LIMIT_SECONDS,
        }
    ):
        raise SuccessorError("successor_plan_invalid")
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
) -> dict[str, Any]:
    plan = load_plan(expected_live_authorized=expected_live_authorized)
    questions, registry_sha256 = load_questions(questions_path)
    _, rubric_sha256 = load_rubrics(rubrics_path)
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
            if arm not in JEV_ARMS:
                disposition = "treatment_off"
                request_sha256 = None
            elif can_affect:
                disposition = "planned"
                request_sha256 = row["request_sha256"]
                planned_calls += 1
            else:
                disposition = "skip_no_membership_effect"
                request_sha256 = row["request_sha256"]
            observed.append({
                "trial_id": trial_id,
                "task_id": task_id,
                "arm": arm,
                "route": route,
                "pool_sha256": pools[arm],
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
    return {
        "schema_version": "velgraphing-v4-luna-successor-preflight-v1",
        "study_id": STUDY_ID,
        "candidate_artifact_sha256": digest(candidate_raw),
        "preview_artifact_sha256": digest(preview_raw),
        "planned_jev_calls": planned_calls,
        "provider_calls_executed": 0,
        "live_authorized": expected_live_authorized,
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
    answer_argv: list[str],
    grader_argv: list[str],
    ledger: LiveJevBudget,
    evaluate: Callable[..., Mapping[str, Any]] = jev.evaluate,
    execution: str = "observed",
) -> dict[str, Any]:
    manifest = generator._manifest(
        manifests_root / generator.CORPUS_MANIFESTS[question["corpus"]]
    )
    lane_root = (lanes_root / question["corpus"]).resolve(strict=True)
    restricted_state = dependency.lane_state_sha256(
        lane_root, SNAPSHOTS[question["corpus"]]
    )
    trial = Trial(
        trial_identity(
            task_id, arm, question, rubric, manifest["commit"], restricted_state
        ),
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
        trial, prepare, answer_argv=answer_argv, grader_argv=grader_argv,
        cwd=ROOT, answer_timeout_s=ANSWER_TIMEOUT_SECONDS,
        grader_timeout_s=GRADER_TIMEOUT_SECONDS,
        grader_context=grader_rubric(rubric), grader_model=GRADER_MODEL,
        answer_response_contract=ANSWER_RESPONSE_CONTRACT,
        grader_response_contract=GRADER_RESPONSE_CONTRACT,
    )
    if dependency.lane_state_sha256(
        lane_root, SNAPSHOTS[question["corpus"]]
    ) != restricted_state:
        raise SuccessorError("successor_lane_changed_during_trial")
    return result


def _argv_map(path: Path, root: Path) -> dict[str, list[str]]:
    if not path.is_absolute() or path.parent != root or path.is_symlink():
        raise SuccessorError("successor_lane_commands_invalid")
    value = _read_json(path, "successor_lane_commands_invalid")
    if path.read_bytes() != canonical(value) or set(value) != set(DISPATCH):
        raise SuccessorError("successor_lane_commands_invalid")
    for trial_id, command in value.items():
        if (
            type(command) is not list or not command
            or not all(type(argument) is str and argument for argument in command)
            or not Path(command[0]).is_absolute()
            or not Path(command[0]).is_file()
            or not os.access(command[0], os.X_OK)
            or trial_id not in DISPATCH
        ):
            raise SuccessorError("successor_lane_commands_invalid")
    return value


def _validated_run_root(path: Path) -> Path:
    expected = (ROOT / RUN_ROOT).resolve()
    if path.resolve() != expected:
        raise SuccessorError("successor_run_root_mismatch")
    return dependency._validated_run_root(path)


def run_successor(
    candidates_path: Path,
    questions_path: Path,
    rubrics_path: Path,
    manifests_root: Path,
    lanes_root: Path,
    preview_path: Path,
    run_root: Path,
    *,
    answer_argv: Mapping[str, list[str]],
    grader_argv: Mapping[str, list[str]],
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
    if set(answer_argv) != set(DISPATCH) or set(grader_argv) != set(DISPATCH):
        raise SuccessorError("successor_lane_commands_invalid")
    ledger = LiveJevBudget(run_root, plan["call_authorization"]["planned_calls"])
    results = []
    for trial_id in DISPATCH:
        arm, task_id = trial_id.split("-", 1)
        question = questions[task_id]
        result = run_trial(
            task_id, arm, question, rubrics[task_id], runs[(task_id, ARMS[arm])],
            manifests_root, lanes_root, dispositions[trial_id],
            answer_argv=answer_argv[trial_id], grader_argv=grader_argv[trial_id],
            ledger=ledger, evaluate=evaluate, execution=execution,
        )
        results.append(result)
        coverage = result["attempts"][-1]["coverage"]
        if (
            result["terminal_reason"] in {
                "measurement_error", "deadline_exceeded", "callback_timeout"
            }
            or not coverage["model_calls"]
            or not coverage["context_deliveries"]
        ):
            raise SuccessorError("successor_systemic_trial_failure")
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
    run_parser.add_argument("--answer-argv-json", type=Path, required=True)
    run_parser.add_argument("--grader-argv-json", type=Path, required=True)
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
        root = _validated_run_root(arguments.run_root)
        output = arguments.output
        if (
            not output.is_absolute() or output.parent != root
            or output.name != "result.json" or output.exists() or output.is_symlink()
        ):
            raise SuccessorError("successor_output_invalid")
        result = run_successor(
            *inputs, root,
            answer_argv=_argv_map(arguments.answer_argv_json, root),
            grader_argv=_argv_map(arguments.grader_argv_json, root),
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
