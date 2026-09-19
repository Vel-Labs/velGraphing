#!/usr/bin/env python3
"""Preflight and run the exact D-01 four-arm controller candidate."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager, nullcontext
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))

from time_to_correct import Budget, MeasurementError, Trial, canonical, digest
from time_to_correct_calibration import LiveJevBudget
from time_to_correct_handoff import (
    HandoffError,
    atomic_write,
    atomic_write_at,
    open_contained_directory,
    read_canonical_at,
    run_root as validate_run_root,
)
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
RESTRICTED_STATE_SHA256 = "ea86c846cf76908cca63090dccb6db497e4bc98ab5c20cd208b675109462f39d"
PRIVATE_RESULT_SHA256 = "bd03bd9944c55c142b1fc00773f1253f79dd4442213c3ab2b31c098b94313286"
REPAIRED_CANDIDATE_COMMIT = "dc0fbcd4397e997645de49d831a8c6608f2f3df2"
PACKAGE_CANDIDATE_SHA256 = "48b65ed3ba9d83e63b724ce2afb395f2fbda156d29adb1b9a194bd9c6564d941"
ANSWER_CONTRACT_SHA256 = "e3226c60087d52a8b51b5bfe8a722e16c294264685c749be5e706454c57d6ddb"
GRADER_CONTRACT_SHA256 = "58b94d44ee16b7abd9afd234d5d57b3d96fd864798d414d65b725b9ef2c64ebb"
SUCCESSOR_RUN_ROOT = ".velgraphing-local/retrievel-d01-confirmation-v1"
SUCCESSOR_RESULT_SHA256 = "44fc6a9b6f3cade340906195b60105d187be1185975406bd9f12e330d46f10d2"
SUCCESSOR_B_OBSERVATION_SHA256 = "33bd29d232f461583292ab14a640c2417a7eb55aa254ad43c3571883e2702a76"
REPAIR_RUN_ROOT = ".velgraphing-local/retrievel-d01-d-repair-v2"
REPAIR_MAX_JEV_CALLS = 1
REPAIR_RESULT_SHA256 = "b40d84af3b05d43adcb7bf70130762e8e644f87a1c401cb1bc0b633bbbd11a37"
REPAIR_RESULT_SEAL_SHA256 = "313038939aab0fe2882335d97520a48892e8cbcff166fbcebf3ec47656ad63c8"
REPAIR_RESULT_FILE_COUNT = 11
PROVIDER_TIMEOUT_SECONDS = 10
HANDOFF_WAIT_SECONDS = 600
HANDOFF_PROCESS_TIMEOUT_SECONDS = 610
REPAIR_TRIAL_WALL_LIMIT_SECONDS = 1240
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


class SourceReadAudit:
    def __init__(self, trial: Trial, scanner_expected: int) -> None:
        self.trial = trial
        self.scanner_expected = scanner_expected
        self.counts = {"scanner": 0, "selection": 0, "jev": 0}

    def record(self, kind: str, path: str, raw: bytes) -> None:
        if kind not in self.counts or type(path) is not str or type(raw) is not bytes:
            raise ControllerError("dependency_source_observer_invalid")
        operation = self.counts[kind]
        self.trial.source(
            digest(raw), 0, len(raw), operation_id=f"{kind}-{operation}"
        )
        self.counts[kind] += 1

    def complete(self, packet: Mapping[str, Any], *, require_jev: bool) -> bool:
        unique_sources = len({row["path"] for row in packet["candidates"]})
        minimum_jev = unique_sources * 2 if require_jev else 0
        return (
            self.counts["scanner"] == self.scanner_expected
            and self.counts["selection"] > 0
            and self.counts["jev"] >= minimum_jev
        )


class AuditedReader:
    def __init__(self, reader: Any, audit: SourceReadAudit) -> None:
        self.reader = reader
        self.audit = audit

    def read_bytes(self, path: str) -> bytes:
        raw = self.reader.read_bytes(path)
        self.audit.record("selection", path, raw)
        return raw

    def is_symlink(self, path: str) -> bool:
        return self.reader.is_symlink(path)


@contextmanager
def _observe_jev_reads(audit: SourceReadAudit):
    original = jev._read_source

    def observed(root: Path, relative: str, max_bytes: int = jev.MAX_FILE_BYTES) -> bytes:
        raw = original(root, relative, max_bytes)
        audit.record("jev", relative, raw)
        return raw

    # ponytail: this controller is serial; add a Jev observer parameter before concurrent trials.
    jev._read_source = observed
    try:
        yield
    finally:
        jev._read_source = original


def _read_json(path: Path, reason: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ControllerError(reason) from None
    if type(value) is not dict:
        raise ControllerError(reason)
    return value


def _validate_preserved_observation(
    value: Mapping[str, Any],
    prepared: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = [row["id"] for row in packet["candidates"]]
    required = [row["id"] for row in packet["candidates"] if row["required"]]
    order = value.get("order") if type(value) is dict else None
    scores = value.get("scores") if type(value) is dict else None
    usage = value.get("usage") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != {
            "schema_version", "mode", "status", "reason", "execution",
            "authority_bearing", "sufficient", "baseline_order", "order",
            "suggested_order", "required_ids", "scores", "attempted_calls",
            "usage", "replayed_usage", "resolved_model", "requested_model",
            "source_revalidated", "elapsed_ms", "request_sha256",
            "source_set_sha256", "request_bytes", "source_bytes_verified",
            "candidate_set_sha256", "query_sha256", "rubric_version",
        }
        or value.get("schema_version") != "velgraphing-jev-observation-v1"
        or value.get("mode") != "rerank"
        or value.get("status") != "reranked"
        or value.get("reason") != "advisory_only"
        or value.get("execution") not in {"live", "injected_transport"}
        or value.get("authority_bearing") is not False
        or value.get("sufficient") is not False
        or value.get("source_revalidated") is not True
        or value.get("attempted_calls") != 1
        or value.get("replayed_usage") is not None
        or value.get("requested_model") != MODEL
        or value.get("resolved_model") != MODEL
        or value.get("baseline_order") != baseline
        or value.get("required_ids") != required
        or value.get("suggested_order") != value.get("order")
        or value.get("candidate_set_sha256") != prepared["candidate_set_sha256"]
        or value.get("query_sha256") != prepared["query_sha256"]
        or value.get("source_set_sha256") != prepared["source_set_sha256"]
        or value.get("request_sha256") != prepared["request_sha256"]
        or value.get("request_bytes") != prepared["request_bytes"]
        or value.get("source_bytes_verified") != 2 * prepared["source_bytes_verified"]
        or value.get("rubric_version") != jev.RUBRIC_VERSION
        or type(order) is not list
        or len(order) != len(baseline)
        or len(set(order)) != len(order)
        or set(order) != set(baseline)
        or type(usage) is not dict
        or set(usage) != {"input_tokens", "output_tokens"}
        or any(type(usage[key]) is not int or usage[key] < 0 for key in usage)
        or type(scores) is not list
        or len(scores) != len(baseline)
        or [row.get("id") for row in scores if type(row) is dict] != baseline
        or any(
            set(row) != {
                "id", "score", "probabilities", "distribution_confidence",
            }
            for row in scores
        )
    ):
        raise ControllerError("dependency_replay_observation_invalid")
    return dict(value)


def _persist_observation(ledger: LiveJevBudget, arm: str, value: Mapping[str, Any]) -> None:
    directory = open_contained_directory(
        ledger.root.parent, ("jev-observations",), create=True
    )
    try:
        atomic_write_at(directory, f"{arm}.json", canonical(value))
    finally:
        os.close(directory)


def _load_preserved_observations(root: Path) -> dict[str, dict[str, Any]]:
    root = _validated_run_root(root)
    directory = open_contained_directory(root, ("jev-observations",), create=False)
    try:
        if set(os.listdir(directory)) != {"B.json", "D.json"}:
            raise ControllerError("dependency_replay_observations_incomplete")
        return {
            arm: read_canonical_at(directory, f"{arm}.json")[1]
            for arm in sorted(JEV_ARMS)
        }
    except HandoffError:
        raise ControllerError("dependency_replay_observations_invalid") from None
    finally:
        os.close(directory)


def _load_repair_b_observation(root: Path) -> dict[str, Any]:
    root = _validated_run_root(root)
    root_directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        result_raw, _ = read_canonical_at(root_directory, "result.json")
    finally:
        os.close(root_directory)
    directory = open_contained_directory(root, ("jev-observations",), create=False)
    try:
        observation_raw, observation = read_canonical_at(directory, "B.json")
    finally:
        os.close(directory)
    if (
        digest(result_raw) != SUCCESSOR_RESULT_SHA256
        or digest(observation_raw) != SUCCESSOR_B_OBSERVATION_SHA256
    ):
        raise ControllerError("dependency_repair_replay_identity_mismatch")
    return observation


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
        plan.get("schema_version")
        != "velgraphing-v4-dependency-behavior-canary-plan-v5"
        or plan.get("study_id") != STUDY_ID
        or plan.get("task_id") != TASK_ID
        or plan.get("candidate_artifact_sha256") != CANDIDATE_SHA256
        or plan.get("candidate_selector_commit") != SELECTOR_COMMIT
        or plan.get("source_snapshot_sha256") != SNAPSHOT_SHA256
        or plan.get("restricted_state_sha256") != RESTRICTED_STATE_SHA256
        or plan.get("jev_model") != MODEL
        or plan.get("jev_rubric_version") != jev.RUBRIC_VERSION
        or plan.get("answer_model") != ANSWER_MODEL
        or plan.get("answer_reasoning") != REASONING
        or plan.get("grader_model") != ANSWER_MODEL
        or plan.get("grader_reasoning") != REASONING
        or plan.get("answer_rubric_sha256") != RUBRIC_SHA256
        or digest(canonical(RUBRIC)) != RUBRIC_SHA256
        or plan.get("repaired_candidate_commit") != REPAIRED_CANDIDATE_COMMIT
        or plan.get("package_candidate_sha256") != PACKAGE_CANDIDATE_SHA256
        or plan.get("answer_response_contract_sha256") != ANSWER_CONTRACT_SHA256
        or digest(canonical(ANSWER_RESPONSE_CONTRACT)) != ANSWER_CONTRACT_SHA256
        or plan.get("grader_response_contract_sha256") != GRADER_CONTRACT_SHA256
        or digest(canonical(GRADER_RESPONSE_CONTRACT)) != GRADER_CONTRACT_SHA256
        or plan.get("successor_run_root") != SUCCESSOR_RUN_ROOT
        or plan.get("successor_result_sha256") != SUCCESSOR_RESULT_SHA256
        or plan.get("successor_b_observation_sha256") != SUCCESSOR_B_OBSERVATION_SHA256
        or plan.get("repair_run_root") != REPAIR_RUN_ROOT
        or plan.get("repair_result_sha256") != REPAIR_RESULT_SHA256
        or plan.get("repair_result_seal_sha256") != REPAIR_RESULT_SEAL_SHA256
        or plan.get("repair_result_file_count") != REPAIR_RESULT_FILE_COUNT
        or plan.get("maximum_cost_usd") != 1.0
        or plan.get("aggregate_authorized_call_total") != 6
        or plan.get("aggregate_completed_call_total") != 6
        or plan.get("aggregate_authorization_envelope_usd") != 0.033030144
        or plan.get("successor_incremental_authorization_usd") != 0.011010048
        or plan.get("successor_jev_calls_authorized") != MAX_JEV_CALLS
        or plan.get("repair_incremental_authorization_usd") != 0.005505024
        or plan.get("repair_jev_calls_authorized") != REPAIR_MAX_JEV_CALLS
        or plan.get("repair_provider_calls_executed") != 1
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
        or plan.get("private_result_sha256") != PRIVATE_RESULT_SHA256
        or plan.get("live_authorized") is not expected_live_authorized
        or plan.get("provider_calls_executed") != 2
        or plan.get("successor_provider_calls_executed") != 2
    ):
        raise ControllerError("dependency_plan_mismatch")
    return plan


def _phase(trial: Trial | None, name: str):
    return trial.phase(name) if trial is not None else nullcontext()


def lane_state_sha256(lane: Path, snapshot_sha256: str) -> str:
    state = {
        "git_head": generator._git(lane, "rev-parse", "HEAD").decode("ascii").strip(),
        "index_sha256": digest(generator._git(lane, "ls-files", "--stage", "-z")),
        "status_sha256": digest(generator._git(
            lane, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        )),
        "untracked_sha256": digest(generator._git(
            lane, "ls-files", "--others", "--exclude-standard", "-z"
        )),
        "selected_source_snapshot_sha256": snapshot_sha256,
    }
    return digest(canonical(state))


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
    audit = SourceReadAudit(trial, manifest["source_count"] * 2) if trial else None
    observer = (
        lambda path, raw: audit.record("scanner", path, raw)
        if audit is not None else None
    )
    with _phase(trial, "cold_graph_build"):
        plain_graph, plain_snapshot, plain_reader, _ = generator.scan_lane(
            lane_root, manifest, derive_edges=False, source_observer=observer
        )
        typed_graph, typed_snapshot, typed_reader, _ = generator.scan_lane(
            lane_root, manifest, derive_edges=True, source_observer=observer
        )
    if (
        plain_snapshot != typed_snapshot
        or plain_graph.records != typed_graph.records
        or plain_snapshot.snapshot_sha256 != SNAPSHOT_SHA256
    ):
        raise ControllerError("dependency_snapshot_drift")
    audited_reader = AuditedReader(plain_reader, audit) if audit is not None else plain_reader
    with _phase(trial, "candidate_discovery"):
        index = generator.build_repository_tag_index(
            plain_graph, plain_snapshot, audited_reader
        )
        facets = generator.compile_prompt(question["prompt"], index)
        if not facets.sufficient:
            facets = generator.compile_prompt(
                question["prompt"],
                index,
                proof_obligations=generator.compile_proof_obligations(
                    question["prompt"], plain_graph, index, plain_snapshot, audited_reader
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
            audited_reader,
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
        "reader": audited_reader,
        "restricted_state_sha256": lane_state_sha256(
            lane_root, plain_snapshot.snapshot_sha256
        ),
        "source_audit": audit,
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
        "instructions": [
            "Evidence list order is not source order. Determine source adjacency "
            "only from matching path values and byte_start and byte_end coordinates."
        ],
        "citation_instruction": (
            "Cite each supporting evidence ID exactly as shown, enclosed in brackets."
        ),
        "evidence": [
            {
                "id": span["candidate_id"],
                "path": span["source_path"],
                "source_sha256": span["source_sha256"],
                "byte_start": span["byte_start"],
                "byte_end": span["byte_end"],
                "relationship_parent_candidate_id": span[
                    "relationship_parent_candidate_id"
                ],
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
    restricted_states: set[str] = set()
    for arm, route in ARMS.items():
        run, lane = regenerate_pool(route, question, manifests_root, lanes_root)
        restricted_states.add(lane["restricted_state_sha256"])
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
        or restricted_states != {RESTRICTED_STATE_SHA256}
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
        "restricted_state_sha256": RESTRICTED_STATE_SHA256,
    }


def trial_identity(
    arm: str,
    repository_commit: str,
    restricted_state_sha256: str,
    run_id: str = "velgraphing-d01-four-arm-v1",
) -> dict[str, Any]:
    if arm not in ARMS:
        raise ControllerError("invalid_dependency_arm")
    return {
        "run_id": run_id,
        "trial_id": f"{arm}-D-01",
        "task_id": TASK_ID,
        "arm": arm,
        "repository_id": "thealgorithms-python",
        "repository_commit": repository_commit,
        "source_snapshot_sha256": SNAPSHOT_SHA256,
        "dirty_state_sha256": restricted_state_sha256,
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
    restricted_state_sha256: str,
    question: Mapping[str, str],
    frozen_run: Mapping[str, Any],
    regenerate: Callable[[Trial, str], tuple[dict[str, Any], dict[str, Any]]],
    *,
    answer_argv: list[str],
    grader_argv: list[str],
    cwd: Path,
    ledger: LiveJevBudget,
    evaluate: Callable[..., Mapping[str, Any]] = jev.evaluate,
    replay_observation: Mapping[str, Any] | None = None,
    live_authorized: bool = False,
    execution: str = "observed",
    run_id: str = "velgraphing-d01-four-arm-v1",
    answer_timeout_seconds: float = 180,
    grader_timeout_seconds: float = 120,
    trial_wall_limit_seconds: int = 600,
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
        trial_identity(arm, repository_commit, restricted_state_sha256, run_id),
        Budget(
            max_repairs=0,
            wall_limit_ns=trial_wall_limit_seconds * 1_000_000_000,
        ),
        execution=execution,
    )

    def prepare(current: Trial, _: int) -> dict[str, Any]:
        current.not_applicable("warm_graph_load", "host_queue", "operator_approval")
        run, lane = regenerate(current, ARMS[arm])
        if _frozen_fields(run) != _frozen_fields(frozen_run):
            raise ControllerError("dependency_regenerated_pool_drift")
        packet = _packet(run, question)
        current.bind(candidate_set_sha256=digest(canonical(packet["candidates"])))
        observation = None
        jev_execution = "off"
        if arm in JEV_ARMS:
            audit = lane.get("source_audit")
            if type(audit) is not SourceReadAudit:
                raise ControllerError("dependency_source_coverage_incomplete")
            with current.phase("jev_preparation"):
                with _observe_jev_reads(audit):
                    prepared = jev.prepare(packet, lane["lane"], MODEL)
            if prepared["request_bytes"] > REQUEST_BYTES:
                raise ControllerError("dependency_request_budget_exceeded")
            current.bind(request_sha256=prepared["request_sha256"])
            if replay_observation is not None:
                current.not_applicable("provider")
                with current.phase("response_validation"):
                    observation = _validate_preserved_observation(
                        replay_observation, prepared, packet
                    )
                    with _observe_jev_reads(audit):
                        refreshed = jev.prepare(packet, lane["lane"], MODEL)
                    if refreshed["request_sha256"] != prepared["request_sha256"]:
                        raise ControllerError("dependency_replay_source_changed")
                current.not_applicable("fallback")
                jev_execution = "replay"
            else:
                receipt, _ = ledger.reserve(
                    current.identity["trial_id"], prepared["request_sha256"]
                )
                with current.phase("provider"):
                    with _observe_jev_reads(audit):
                        observation = evaluate(
                            packet,
                            lane["lane"],
                            mode="rerank",
                            allow_network=True,
                            approved_request_sha256=prepared["request_sha256"],
                            model=MODEL,
                            timeout_s=PROVIDER_TIMEOUT_SECONDS,
                        )
                ledger.complete(receipt, observation)
                usage = observation.get("usage")
                with current.phase("response_validation"):
                    if observation.get("attempted_calls") not in {0, 1}:
                        raise ControllerError("dependency_retry_detected")
                if observation.get("status") == "fallback":
                    with current.phase("fallback"):
                        observation = None
                else:
                    current.not_applicable("fallback")
                    observation = _validate_preserved_observation(
                        observation, prepared, packet
                    )
                    _persist_observation(ledger, arm, observation)
                    jev_execution = "live"
                current.usage(
                    f"jev-{arm}",
                    "jev",
                    provenance=(
                        "provider_reported" if usage is not None else "unavailable"
                    ),
                    input_tokens=(
                        usage.get("input_tokens") if usage is not None else None
                    ),
                    output_tokens=(
                        usage.get("output_tokens") if usage is not None else None
                    ),
                    cached_input_tokens=None,
                    reasoning_output_tokens=None,
                    cost_usd=None,
                    model=MODEL,
                )
            if observation is not None:
                current._attempt()["jev_observation"] = observation
        else:
            current.not_applicable(
                "jev_preparation", "provider", "response_validation", "fallback",
            )
        with current.phase("source_revalidation"):
            with current.phase("source_capture"):
                selected = _selection(run, lane, question, arm, observation)
        with current.phase("context_composition"):
            payload = _answer_evidence(question["prompt"], selected)
        current._attempt()["candidate_observation"] = {
            "pool_sha256": digest(canonical(run["candidates"])),
            "selected_candidate_ids": list(selected.projection.selected_candidate_ids),
            "required_candidate_ids": list(selected.projection.required_candidate_ids),
            "order_source": selected.order_source,
            "jev_execution": jev_execution,
            "source_operation_count": len(current._attempt()["source_operations"]),
        }
        audit = lane.get("source_audit")
        if (
            type(audit) is not SourceReadAudit
            or not audit.complete(packet, require_jev=arm in JEV_ARMS)
        ):
            raise ControllerError("dependency_source_coverage_incomplete")
        current.coverage(source_operations=True)
        return payload

    return run_process_trial(
        trial,
        prepare,
        answer_argv=answer_argv,
        grader_argv=grader_argv,
        cwd=cwd,
        answer_timeout_s=answer_timeout_seconds,
        grader_timeout_s=grader_timeout_seconds,
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
    jev_observations: Mapping[str, Mapping[str, Any]] | None = None,
    execution: str = "observed",
) -> dict[str, Any]:
    if execution == "observed":
        run_root = _validated_run_root(run_root)
    preflight_started = time.monotonic_ns()
    preflight_result = preflight(
        candidates_path,
        questions_path,
        manifests_root,
        lanes_root,
        preview_path,
        expected_live_authorized=live_authorized,
    )
    preflight_elapsed_ns = time.monotonic_ns() - preflight_started
    if live_authorized is not True:
        raise ControllerError("dependency_live_not_authorized")
    if set(answer_argv) != set(ARMS) or set(grader_argv) != set(ARMS):
        raise ControllerError("dependency_lane_commands_mismatch")
    if jev_observations is not None and set(jev_observations) != JEV_ARMS:
        raise ControllerError("dependency_replay_observations_incomplete")
    artifact, questions = preview._load_inputs(
        candidates_path, CANDIDATE_SHA256, questions_path, STUDY_ID
    )
    frozen = {(run["task_id"], run["route"]): run for run in artifact["runs"]}
    question = questions[TASK_ID]
    manifest = generator._manifest(
        manifests_root / generator.CORPUS_MANIFESTS[question["corpus"]]
    )
    lane_root = (lanes_root / question["corpus"]).resolve(strict=True)
    restricted_state = lane_state_sha256(lane_root, SNAPSHOT_SHA256)
    ledger = LiveJevBudget(run_root, MAX_JEV_CALLS)
    results = []
    for arm, route in ARMS.items():
        results.append(run_arm(
            arm,
            manifest["commit"],
            restricted_state,
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
            replay_observation=(
                jev_observations.get(arm) if jev_observations is not None else None
            ),
            live_authorized=live_authorized,
            execution=execution,
        ))
        if lane_state_sha256(lane_root, SNAPSHOT_SHA256) != restricted_state:
            raise ControllerError("dependency_lane_changed_during_run")
        coverage = results[-1]["attempts"][-1]["coverage"]
        if results[-1]["terminal_reason"] in {
            "measurement_error", "deadline_exceeded", "callback_timeout"
        } or not coverage["model_calls"] or not coverage["context_deliveries"]:
            raise ControllerError("dependency_systemic_trial_failure")
    return {
        "schema_version": "velgraphing-d01-four-arm-result-v1",
        "preflight": preflight_result,
        "controller_preflight": {
            "elapsed_ns": preflight_elapsed_ns,
            "ttc_allocation": "separate_not_in_arm_ttc",
            "jev_execution": (
                "replay" if jev_observations is not None else "live"
            ),
        },
        "results": results,
    }


def run_d_confirmation(
    candidates_path: Path,
    questions_path: Path,
    manifests_root: Path,
    lanes_root: Path,
    preview_path: Path,
    run_root: Path,
    *,
    answer_argv: list[str],
    grader_argv: list[str],
    b_observation: Mapping[str, Any],
    live_authorized: bool = False,
    evaluate: Callable[..., Mapping[str, Any]] = jev.evaluate,
    execution: str = "observed",
) -> dict[str, Any]:
    if execution == "observed":
        run_root = _validated_run_root(run_root)
    preflight_result = preflight(
        candidates_path,
        questions_path,
        manifests_root,
        lanes_root,
        preview_path,
        expected_live_authorized=live_authorized,
    )
    preflight_result = {
        **preflight_result,
        "maximum_jev_calls": REPAIR_MAX_JEV_CALLS,
    }
    if live_authorized is not True:
        raise ControllerError("dependency_live_not_authorized")
    artifact, questions = preview._load_inputs(
        candidates_path, CANDIDATE_SHA256, questions_path, STUDY_ID
    )
    frozen = {(run["task_id"], run["route"]): run for run in artifact["runs"]}
    question = questions[TASK_ID]
    manifest = generator._manifest(
        manifests_root / generator.CORPUS_MANIFESTS[question["corpus"]]
    )
    lane_root = (lanes_root / question["corpus"]).resolve(strict=True)
    restricted_state = lane_state_sha256(lane_root, SNAPSHOT_SHA256)

    b_run, b_lane = regenerate_pool(
        ARMS["B"], question, manifests_root, lanes_root
    )
    if _frozen_fields(b_run) != _frozen_fields(frozen[(TASK_ID, ARMS["B"])]):
        raise ControllerError("dependency_regenerated_pool_drift")
    b_packet = _packet(b_run, question)
    b_prepared = jev.prepare(b_packet, b_lane["lane"], MODEL)
    b_validated = _validate_preserved_observation(
        b_observation, b_prepared, b_packet
    )
    b_selection = _selection(b_run, b_lane, question, "B", b_validated)
    if b_selection.order_source != "reranked":
        raise ControllerError("dependency_repair_b_replay_not_applied")

    ledger = LiveJevBudget(run_root, REPAIR_MAX_JEV_CALLS)
    d_result = run_arm(
        "D",
        manifest["commit"],
        restricted_state,
        question,
        frozen[(TASK_ID, ARMS["D"])],
        lambda trial, selected_route: regenerate_pool(
            selected_route, question, manifests_root, lanes_root, trial
        ),
        answer_argv=answer_argv,
        grader_argv=grader_argv,
        cwd=ROOT,
        ledger=ledger,
        evaluate=evaluate,
        live_authorized=live_authorized,
        execution=execution,
        run_id="velgraphing-d01-d-repair-v2",
        answer_timeout_seconds=HANDOFF_PROCESS_TIMEOUT_SECONDS,
        grader_timeout_seconds=HANDOFF_PROCESS_TIMEOUT_SECONDS,
        trial_wall_limit_seconds=REPAIR_TRIAL_WALL_LIMIT_SECONDS,
    )
    candidate_observation = d_result["attempts"][-1]["candidate_observation"]
    coverage = d_result["attempts"][-1]["coverage"]
    if (
        candidate_observation["jev_execution"] != "live"
        or candidate_observation["order_source"] != "reranked"
        or d_result["terminal_reason"] in {
            "measurement_error", "deadline_exceeded", "callback_timeout"
        }
        or not coverage["model_calls"]
        or not coverage["context_deliveries"]
        or lane_state_sha256(lane_root, SNAPSHOT_SHA256) != restricted_state
    ):
        raise ControllerError("dependency_d_confirmation_failed")
    return {
        "schema_version": "velgraphing-d01-d-repair-result-v1",
        "preflight": preflight_result,
        "b_replay": {
            "request_sha256": b_validated["request_sha256"],
            "candidate_set_sha256": b_validated["candidate_set_sha256"],
            "selected_candidate_ids": list(
                b_selection.projection.selected_candidate_ids
            ),
            "order_source": b_selection.order_source,
        },
        "result": d_result,
    }


def _argv_map(
    path: Path,
    root: Path,
    expected_arms: set[str] | frozenset[str] = frozenset(ARMS),
) -> dict[str, list[str]]:
    if (
        not path.is_absolute()
        or path.parent != root
        or path.is_symlink()
        or path.resolve(strict=True) != path
    ):
        raise ControllerError("dependency_lane_commands_invalid")
    raw = path.read_bytes()
    value = _read_json(path, "dependency_lane_commands_invalid")
    if raw != canonical(value) or set(value) != expected_arms:
        raise ControllerError("dependency_lane_commands_invalid")
    for command in value.values():
        if (
            type(command) is not list
            or not command
            or not all(type(argument) is str and argument for argument in command)
        ):
            raise ControllerError("dependency_lane_commands_invalid")
        executable = Path(command[0])
        try:
            resolved_executable = executable.resolve(strict=True)
            valid_executable = (
                executable.is_absolute()
                and resolved_executable.is_file()
                and os.access(resolved_executable, os.X_OK)
            )
        except OSError:
            valid_executable = False
        if not valid_executable:
            raise ControllerError("dependency_lane_commands_invalid")
    return value


def _repair_argv(path: Path, root: Path, lane: str) -> list[str]:
    command = _argv_map(path, root, {"D"})["D"]
    if command[1:] != [
        "scripts/benchmarks/time_to_correct_handoff.py", "wait",
        "--run-root", str(root), "--trial-id", "D-D-01", "--attempt", "0",
        "--lane", lane, "--wait-seconds", str(HANDOFF_WAIT_SECONDS),
    ]:
        raise ControllerError("dependency_lane_commands_invalid")
    return command


def _validated_run_root(path: Path) -> Path:
    local = ROOT / ".velgraphing-local"
    try:
        local_metadata = local.lstat()
        root_metadata = path.lstat()
    except OSError:
        raise ControllerError("dependency_run_root_invalid") from None
    if (
        not path.is_absolute()
        or path.parent != local
        or stat.S_ISLNK(local_metadata.st_mode)
        or not stat.S_ISDIR(local_metadata.st_mode)
        or stat.S_IMODE(local_metadata.st_mode) & 0o077
        or stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_IMODE(root_metadata.st_mode) & 0o077
        or path.resolve(strict=True) != path
    ):
        raise ControllerError("dependency_run_root_invalid")
    try:
        generator._git(ROOT, "check-ignore", "-q", "--", ".velgraphing-local")
        return validate_run_root(str(path))
    except (OSError, ValueError, generator.GenerationError, HandoffError):
        raise ControllerError("dependency_run_root_invalid") from None


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
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
    run_parser.add_argument("--replay-observations-root", type=Path)
    run_parser.add_argument("--output", type=Path, required=True)
    repair_parser = commands.add_parser("confirm-d")
    _add_inputs(repair_parser)
    repair_parser.add_argument("--run-root", type=Path, required=True)
    repair_parser.add_argument("--answer-argv-json", type=Path, required=True)
    repair_parser.add_argument("--grader-argv-json", type=Path, required=True)
    repair_parser.add_argument("--replay-observations-root", type=Path, required=True)
    repair_parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        inputs = (
            arguments.candidates.resolve(strict=True),
            arguments.questions.resolve(strict=True),
            arguments.manifests_root.resolve(strict=True),
            arguments.lanes_root.resolve(strict=True),
            arguments.preview.resolve(strict=True),
        )
        if arguments.command == "preflight":
            result = preflight(*inputs, expected_live_authorized=True)
            print(canonical(result).decode("utf-8"))
            return 0
        validate_plan(expected_live_authorized=True)
        root = _validated_run_root(arguments.run_root)
        if arguments.command == "confirm-d":
            replay_root = arguments.replay_observations_root.resolve(strict=True)
            if (
                root != (ROOT / REPAIR_RUN_ROOT).resolve()
                or replay_root != (ROOT / SUCCESSOR_RUN_ROOT).resolve()
            ):
                raise ControllerError("dependency_run_root_plan_mismatch")
            output = arguments.output
            if (
                not output.is_absolute()
                or output.parent != root
                or output.name != "result.json"
                or output.exists()
                or output.is_symlink()
            ):
                raise ControllerError("dependency_output_invalid")
            result = run_d_confirmation(
                *inputs,
                root,
                answer_argv=_repair_argv(arguments.answer_argv_json, root, "answer"),
                grader_argv=_repair_argv(arguments.grader_argv_json, root, "grader"),
                b_observation=_load_repair_b_observation(replay_root),
                live_authorized=True,
            )
            atomic_write(output, canonical(result))
            print(canonical({
                "output": str(output),
                "output_sha256": digest(canonical(result)),
                "status": "written",
            }).decode("utf-8"))
            return 0
        replay_observations = None
        if arguments.replay_observations_root is not None:
            replay_root = arguments.replay_observations_root.resolve(strict=True)
            if replay_root == root:
                raise ControllerError("dependency_replay_root_not_fresh")
            replay_observations = _load_preserved_observations(replay_root)
        elif root != (ROOT / SUCCESSOR_RUN_ROOT).resolve():
            raise ControllerError("dependency_run_root_plan_mismatch")
        output = arguments.output
        if (
            not output.is_absolute()
            or output.parent != root
            or output.name != "result.json"
            or output.exists()
            or output.is_symlink()
        ):
            raise ControllerError("dependency_output_invalid")
        result = run_four_arm(
            *inputs,
            root,
            answer_argv=_argv_map(arguments.answer_argv_json, root),
            grader_argv=_argv_map(arguments.grader_argv_json, root),
            live_authorized=True,
            jev_observations=replay_observations,
        )
        atomic_write(output, canonical(result))
        print(canonical({
            "output": str(output),
            "output_sha256": digest(canonical(result)),
            "status": "written",
        }).decode("utf-8"))
        return 0
    except (
        ControllerError, HandoffError, MeasurementError, OSError, ValueError
    ) as error:
        reason = error.reason if isinstance(error, MeasurementError) else "dependency_preflight_failed"
        print(f"dependency-controller: {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
