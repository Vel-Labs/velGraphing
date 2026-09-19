#!/usr/bin/env python3
"""Preflight and run the exact D-01 four-arm controller candidate."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))

from time_to_correct import Budget, MeasurementError, Trial, canonical, digest
from time_to_correct_calibration import LiveJevBudget
from time_to_correct_host import (
    ANSWER_RESPONSE_CONTRACT,
    GRADER_RESPONSE_CONTRACT,
    run_process_trial,
)


def _module(name: str, relative: str) -> Any:
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _module(
    "dependency_controller_generator",
    "scripts/benchmarks/time_to_correct_ranked_candidates_v4.py",
)
preview = _module(
    "dependency_controller_preview",
    "scripts/benchmarks/time_to_correct_jev_v4.py",
)
evaluator = _module(
    "dependency_controller_evaluator",
    "scripts/benchmarks/time_to_correct_retrieval_eval_v4.py",
)

from packages.core import RankedContextCandidate, Sensitivity, TaskSpec, select_ranked_context
from packages.core import jev


STUDY_ID = "velgraphing-v4-thealgorithms-dependency-behavior-canary-v1"
TASK_ID = "D-01"
ARMS = {"A": "direct", "B": "direct", "C": "typed_graph", "D": "typed_graph"}
JEV_ARMS = {"B", "D"}
MODEL = "jev-1.13.0"
ANSWER_MODEL = "gpt-5.6-sol"
REASONING = "medium"
FINAL_ANSWER_BYTES = 16_384
REQUEST_BYTES = 131_072
MAX_JEV_CALLS = 2
CANDIDATE_SHA256 = "8a75f792aefbabe5679fdfb934e440f723649a5993cb46196d63a437486c9ce7"
SELECTOR_COMMIT = "79adf45e8ff245c7e90701ea172d8de269228f83"
SNAPSHOT_SHA256 = "5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09"
PLAN_PATH = ROOT / "benchmarks/velgraphing-time-to-correct-v4/dependency-behavior-canary-plan.json"
RUBRIC = {
    "required_facts": [
        "The imported implementation is quick_sort.",
        "quick_sort returns the collection unchanged when it has fewer than two items.",
        "quick_sort removes a randomly indexed pivot, partitions remaining values at the pivot, and recursively recombines lesser, pivot, and greater in ascending order.",
    ],
    "critical_facts": [
        "The imported implementation is quick_sort.",
        "quick_sort removes a randomly indexed pivot, partitions remaining values at the pivot, and recursively recombines lesser, pivot, and greater in ascending order.",
    ],
    "acceptable_spans": [
        "sorts/benchmark_sorts.py dependency import after merge_sort",
        "sorts/quick_sort.py quick_sort implementation",
    ],
}
RUBRIC_SHA256 = "bfd1265ff03a1347280646c76258f5e79e11b140a66cd638f169df63551877ef"


class ControllerError(MeasurementError):
    pass


def _read_json(path: Path, reason: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ControllerError(reason) from None
    if type(value) is not dict:
        raise ControllerError(reason)
    return value


def validate_plan(
    path: Path = PLAN_PATH,
    *,
    expected_live_authorized: bool = False,
) -> dict[str, Any]:
    plan = _read_json(path, "invalid_dependency_plan")
    limits = plan.get("limits")
    requests = plan.get("request_sha256")
    pools = plan.get("pool_sha256")
    if (
        plan.get("study_id") != STUDY_ID
        or plan.get("task_id") != TASK_ID
        or plan.get("candidate_artifact_sha256") != CANDIDATE_SHA256
        or plan.get("candidate_selector_commit") != SELECTOR_COMMIT
        or plan.get("source_snapshot_sha256") != SNAPSHOT_SHA256
        or plan.get("jev_model") != MODEL
        or plan.get("jev_rubric_version") != jev.RUBRIC_VERSION
        or plan.get("answer_model") != ANSWER_MODEL
        or plan.get("answer_reasoning") != REASONING
        or plan.get("grader_model") != ANSWER_MODEL
        or plan.get("grader_reasoning") != REASONING
        or plan.get("answer_rubric_sha256") != RUBRIC_SHA256
        or digest(canonical(RUBRIC)) != RUBRIC_SHA256
        or type(limits) is not dict
        or limits.get("candidate_count") != 64
        or limits.get("candidate_aggregate_bytes") != 32_768
        or limits.get("candidate_unit_bytes") != 4096
        or limits.get("final_answer_bytes") != FINAL_ANSWER_BYTES
        or limits.get("request_bytes") != REQUEST_BYTES
        or limits.get("maximum_jev_calls") != MAX_JEV_CALLS
        or limits.get("retries") != 0
        or type(requests) is not dict
        or set(requests) != {"B", "D"}
        or type(pools) is not dict
        or set(pools) != {"A_B", "C_D"}
        or plan.get("live_authorized") is not expected_live_authorized
        or plan.get("provider_calls_executed") != 0
    ):
        raise ControllerError("dependency_plan_mismatch")
    return plan


def _phase(trial: Trial | None, name: str):
    return trial.phase(name) if trial is not None else nullcontext()


def regenerate_pool(
    route: str,
    question: Mapping[str, str],
    manifests_root: Path,
    lanes_root: Path,
    trial: Trial | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if route not in {"direct", "typed_graph"}:
        raise ControllerError("invalid_dependency_route")
    corpus = question["corpus"]
    manifest = generator._manifest(manifests_root / generator.CORPUS_MANIFESTS[corpus])
    lane_root = (lanes_root / corpus).resolve(strict=True)
    with _phase(trial, "cold_graph_build"):
        plain_graph, plain_snapshot, plain_reader, _ = generator.scan_lane(
            lane_root, manifest, derive_edges=False
        )
        typed_graph, typed_snapshot, typed_reader, _ = generator.scan_lane(
            lane_root, manifest, derive_edges=True
        )
    if (
        plain_snapshot != typed_snapshot
        or plain_graph.records != typed_graph.records
        or plain_snapshot.snapshot_sha256 != SNAPSHOT_SHA256
    ):
        raise ControllerError("dependency_snapshot_drift")
    with _phase(trial, "candidate_discovery"):
        index = generator.build_repository_tag_index(
            plain_graph, plain_snapshot, plain_reader
        )
        facets = generator.compile_prompt(question["prompt"], index)
        if not facets.sufficient:
            facets = generator.compile_prompt(
                question["prompt"],
                index,
                proof_obligations=generator.compile_proof_obligations(
                    question["prompt"], plain_graph, index, plain_snapshot, plain_reader
                ),
            )
    task = TaskSpec(
        task_id=TASK_ID,
        query_terms=tuple(dict.fromkeys(
            token.casefold()
            for token in generator.graph_adapter._TOKEN.findall(question["prompt"])
        )),
        node_budget=generator.RETRIEVAL_NODE_LIMIT,
        byte_budget=32_768,
        allowed_sensitivities=(Sensitivity.PUBLIC, Sensitivity.INTERNAL),
    )
    graph = plain_graph if route == "direct" else typed_graph
    with _phase(trial, "retrieval"):
        run, _ = generator._route_run(
            task,
            route,
            graph,
            plain_snapshot,
            plain_reader,
            index,
            facets,
            derived_edge_count=0 if route == "direct" else len(typed_graph.edges),
            active_edge_count=0 if route == "direct" else len(typed_graph.edges),
            source_bound_expansion=route == "typed_graph",
            expand_one_hop=route == "typed_graph",
            candidate_limit=64,
            candidate_aggregate_byte_budget=32_768,
            candidate_unit_byte_budget=4096,
        )
    run.update({
        "corpus": corpus,
        "prompt_sha256": digest(question["prompt"].encode("utf-8")),
    })
    return run, {
        "lane": lane_root,
        "plain_graph": plain_graph,
        "typed_graph": typed_graph,
        "snapshot": plain_snapshot,
        "reader": plain_reader,
    }


def _frozen_fields(run: Mapping[str, Any]) -> dict[str, Any]:
    return {key: run[key] for key in (
        "task_id", "corpus", "prompt_sha256", "route", "source_snapshot_sha256",
        "sources", "candidates", "controls",
    )}


def _packet(run: Mapping[str, Any], question: Mapping[str, str]) -> dict[str, Any]:
    return jev.validate_packet({
        "schema_version": jev.PACKET_VERSION,
        "query": question["prompt"],
        "candidates": [
            {key: row[key] for key in (
                "id", "path", "source_sha256", "byte_start", "byte_end", "required"
            )}
            for row in run["candidates"]
        ],
    })


def _selection(
    run: Mapping[str, Any],
    lane: Mapping[str, Any],
    question: Mapping[str, str],
    arm: str,
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
            task_id=f"{TASK_ID}-{arm}",
            query_terms=(TASK_ID,),
            byte_budget=FINAL_ANSWER_BYTES,
            allowed_sensitivities=(Sensitivity.PUBLIC, Sensitivity.INTERNAL),
        ),
        lane["snapshot"],
        lane["reader"],
        query=question["prompt"],
        candidates=candidates,
        approved_request_sha256=(
            observation.get("request_sha256") if observation is not None else None
        ),
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
        raise ControllerError("dependency_selection_invalid")
    return result


def _answer_evidence(question: str, selection: Any) -> dict[str, Any]:
    payload = json.loads(selection.projection.content)
    return {
        "schema_version": "velgraphing-answer-evidence-v3",
        "question": question,
        "citation_instruction": "Cite supporting evidence IDs as [cN].",
        "evidence": [
            {
                "id": span["candidate_id"],
                "path": span["source_path"],
                "excerpt": span["content"],
            }
            for span in payload["spans"]
        ],
    }


def preflight(
    candidates_path: Path,
    questions_path: Path,
    manifests_root: Path,
    lanes_root: Path,
    preview_path: Path,
    *,
    expected_live_authorized: bool = False,
) -> dict[str, Any]:
    plan = validate_plan(expected_live_authorized=expected_live_authorized)
    artifact, questions = preview._load_inputs(
        candidates_path, CANDIDATE_SHA256, questions_path, STUDY_ID
    )
    frozen = {(run["task_id"], run["route"]): run for run in artifact["runs"]}
    question = questions[TASK_ID]
    pool_hashes: dict[str, str] = {}
    request_hashes: dict[str, str] = {}
    can_affect: dict[str, bool] = {}
    for arm, route in ARMS.items():
        run, lane = regenerate_pool(route, question, manifests_root, lanes_root)
        if _frozen_fields(run) != _frozen_fields(frozen[(TASK_ID, route)]):
            raise ControllerError("dependency_regenerated_pool_drift")
        pool_hashes[arm] = digest(canonical(run["candidates"]))
        if arm in JEV_ARMS:
            record, row = preview._preview_record(
                run, question, arm, route, lane, 64, 32_768
            )
            request_hashes[arm] = record["prepared"]["request_sha256"]
            can_affect[arm] = row["jev_call_could_affect_selection"]
            if record["prepared"]["request_bytes"] > REQUEST_BYTES:
                raise ControllerError("dependency_request_budget_exceeded")
    if (
        pool_hashes["A"] != pool_hashes["B"]
        or pool_hashes["C"] != pool_hashes["D"]
        or can_affect != {"B": True, "D": True}
        or request_hashes != plan["request_sha256"]
        or {"A_B": pool_hashes["A"], "C_D": pool_hashes["C"]}
        != plan["pool_sha256"]
    ):
        raise ControllerError("dependency_preflight_mismatch")
    preview_raw = preview._canonical_file(
        preview_path, "invalid_preview_artifact_file"
    )
    if digest(preview_raw) != plan["preview_artifact_sha256"]:
        raise ControllerError("dependency_preview_identity_mismatch")
    frozen_preview = json.loads(preview_raw)
    preview.validate_preview(
        frozen_preview,
        expected_candidate_artifact_sha256=CANDIDATE_SHA256,
        expected_candidate_selector_commit=SELECTOR_COMMIT,
        expected_adapter_commit=plan["preview_adapter_commit"],
        expected_study_id=STUDY_ID,
    )
    return {
        "schema_version": "velgraphing-d01-controller-preflight-v1",
        "study_id": STUDY_ID,
        "task_id": TASK_ID,
        "pair_identity": {
            "A_B": pool_hashes["A"],
            "C_D": pool_hashes["C"],
        },
        "request_sha256": request_hashes,
        "can_affect": can_affect,
        "maximum_jev_calls": MAX_JEV_CALLS,
        "retries": 0,
        "live_authorized": expected_live_authorized,
        "provider_calls_executed": 0,
    }


def trial_identity(arm: str, repository_commit: str) -> dict[str, Any]:
    if arm not in ARMS:
        raise ControllerError("invalid_dependency_arm")
    return {
        "run_id": "velgraphing-d01-four-arm-v1",
        "trial_id": f"{arm}-D-01",
        "task_id": TASK_ID,
        "arm": arm,
        "repository_id": "thealgorithms-python",
        "repository_commit": repository_commit,
        "source_snapshot_sha256": SNAPSHOT_SHA256,
        "dirty_state_sha256": digest(b""),
        "answer_model": ANSWER_MODEL,
        "reasoning": REASONING,
        "prompt_sha256": evaluator.THEALGORITHMS_DEPENDENCY_BEHAVIOR_CANARY_QUESTIONS[TASK_ID][1],
        "rubric_sha256": RUBRIC_SHA256,
        "rubric_version": "velgraphing-d01-answer-rubric-v1",
        "answer_lane_id": f"answer-{arm}-D-01",
    }


def run_arm(
    arm: str,
    repository_commit: str,
    question: Mapping[str, str],
    frozen_run: Mapping[str, Any],
    regenerate: Callable[[Trial, str], tuple[dict[str, Any], dict[str, Any]]],
    *,
    answer_argv: list[str],
    grader_argv: list[str],
    cwd: Path,
    ledger: LiveJevBudget,
    evaluate: Callable[..., Mapping[str, Any]] = jev.evaluate,
    live_authorized: bool = False,
    execution: str = "observed",
) -> dict[str, Any]:
    if live_authorized is not True:
        raise ControllerError("dependency_live_not_authorized")
    if execution not in {"observed", "fixture"}:
        raise ControllerError("invalid_dependency_execution")
    if execution == "observed":
        try:
            validate_plan(expected_live_authorized=True)
        except MeasurementError:
            raise ControllerError("dependency_live_not_authorized") from None
    trial = Trial(
        trial_identity(arm, repository_commit),
        Budget(max_repairs=0, wall_limit_ns=600_000_000_000),
        execution=execution,
    )

    def prepare(current: Trial, _: int) -> dict[str, Any]:
        current.not_applicable("warm_graph_load", "source_capture", "host_queue", "operator_approval")
        run, lane = regenerate(current, ARMS[arm])
        if _frozen_fields(run) != _frozen_fields(frozen_run):
            raise ControllerError("dependency_regenerated_pool_drift")
        packet = _packet(run, question)
        current.bind(candidate_set_sha256=digest(canonical(packet["candidates"])))
        observation = None
        if arm in JEV_ARMS:
            with current.phase("jev_preparation"):
                prepared = jev.prepare(packet, lane["lane"], MODEL)
            if prepared["request_bytes"] > REQUEST_BYTES:
                raise ControllerError("dependency_request_budget_exceeded")
            current.bind(request_sha256=prepared["request_sha256"])
            receipt, _ = ledger.reserve(
                current.identity["trial_id"], prepared["request_sha256"]
            )
            with current.phase("provider"):
                observation = evaluate(
                    packet,
                    lane["lane"],
                    mode="rerank",
                    allow_network=True,
                    approved_request_sha256=prepared["request_sha256"],
                    model=MODEL,
                    timeout_s=10,
                )
            ledger.complete(receipt, observation)
            usage = observation.get("usage")
            with current.phase("source_revalidation"):
                refreshed = jev.prepare(packet, lane["lane"], MODEL)
                if refreshed["request_sha256"] != prepared["request_sha256"]:
                    raise ControllerError("dependency_source_changed")
            with current.phase("response_validation"):
                if observation.get("attempted_calls") not in {0, 1}:
                    raise ControllerError("dependency_retry_detected")
            if observation.get("status") == "fallback":
                with current.phase("fallback"):
                    observation = None
            else:
                current.not_applicable("fallback")
            current.usage(
                f"jev-{arm}",
                "jev",
                provenance="provider_reported" if usage is not None else "unavailable",
                input_tokens=usage.get("input_tokens") if usage is not None else None,
                output_tokens=usage.get("output_tokens") if usage is not None else None,
                cached_input_tokens=None,
                reasoning_output_tokens=None,
                cost_usd=None,
                model=MODEL,
            )
        else:
            current.not_applicable(
                "jev_preparation", "provider", "source_revalidation",
                "response_validation", "fallback",
            )
        with current.phase("context_composition"):
            selected = _selection(run, lane, question, arm, observation)
            payload = _answer_evidence(question["prompt"], selected)
        current._attempt()["candidate_observation"] = {
            "pool_sha256": digest(canonical(run["candidates"])),
            "selected_candidate_ids": list(selected.projection.selected_candidate_ids),
            "required_candidate_ids": list(selected.projection.required_candidate_ids),
            "order_source": selected.order_source,
        }
        return payload

    return run_process_trial(
        trial,
        prepare,
        answer_argv=answer_argv,
        grader_argv=grader_argv,
        cwd=cwd,
        answer_timeout_s=180,
        grader_timeout_s=120,
        grader_context=RUBRIC,
        answer_response_contract=ANSWER_RESPONSE_CONTRACT,
        grader_response_contract=GRADER_RESPONSE_CONTRACT,
    )


def run_four_arm(
    candidates_path: Path,
    questions_path: Path,
    manifests_root: Path,
    lanes_root: Path,
    preview_path: Path,
    run_root: Path,
    *,
    answer_argv: Mapping[str, list[str]],
    grader_argv: Mapping[str, list[str]],
    live_authorized: bool = False,
    evaluate: Callable[..., Mapping[str, Any]] = jev.evaluate,
    execution: str = "observed",
) -> dict[str, Any]:
    preflight_result = preflight(
        candidates_path,
        questions_path,
        manifests_root,
        lanes_root,
        preview_path,
        expected_live_authorized=live_authorized,
    )
    if live_authorized is not True:
        raise ControllerError("dependency_live_not_authorized")
    if set(answer_argv) != set(ARMS) or set(grader_argv) != set(ARMS):
        raise ControllerError("dependency_lane_commands_mismatch")
    artifact, questions = preview._load_inputs(
        candidates_path, CANDIDATE_SHA256, questions_path, STUDY_ID
    )
    frozen = {(run["task_id"], run["route"]): run for run in artifact["runs"]}
    question = questions[TASK_ID]
    manifest = generator._manifest(
        manifests_root / generator.CORPUS_MANIFESTS[question["corpus"]]
    )
    ledger = LiveJevBudget(run_root, MAX_JEV_CALLS)
    results = []
    for arm, route in ARMS.items():
        results.append(run_arm(
            arm,
            manifest["commit"],
            question,
            frozen[(TASK_ID, route)],
            lambda trial, selected_route: regenerate_pool(
                selected_route, question, manifests_root, lanes_root, trial
            ),
            answer_argv=answer_argv[arm],
            grader_argv=grader_argv[arm],
            cwd=ROOT,
            ledger=ledger,
            evaluate=evaluate,
            live_authorized=live_authorized,
            execution=execution,
        ))
    return {
        "schema_version": "velgraphing-d01-four-arm-result-v1",
        "preflight": preflight_result,
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--manifests-root", type=Path, required=True)
    parser.add_argument("--lanes-root", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        result = preflight(
            arguments.candidates.resolve(strict=True),
            arguments.questions.resolve(strict=True),
            arguments.manifests_root.resolve(strict=True),
            arguments.lanes_root.resolve(strict=True),
            arguments.preview.resolve(strict=True),
        )
        print(canonical(result).decode("utf-8"))
        return 0
    except (ControllerError, MeasurementError, OSError, ValueError) as error:
        reason = error.reason if isinstance(error, MeasurementError) else "dependency_preflight_failed"
        print(f"dependency-controller: {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
