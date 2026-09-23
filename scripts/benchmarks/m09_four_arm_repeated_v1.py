#!/usr/bin/env python3
"""Fresh, source-selected M09 comparison. Historical successor files are read only."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import four_arm_study_v1 as base
from time_to_correct import TRANSIENT_MODEL_ERRORS, load_completed_trials, save_completed_trial
from time_to_correct_calibration import (
    LiveJevBudget, bind_controller, controller_identity, handoff_argv,
    require_resumable, verify_lane,
)
from time_to_correct_handoff import (
    atomic_write, bound_lane_identity, read_canonical, run_root as validate_run_root,
)


ROOT = base.ROOT
BENCHMARK = base.DEFAULT_ROOT
STUDY_ID = "velgraphing-m09-four-arm-repeated-v1"
SCHEMA = "velgraphing-m09-four-arm-contract-v2"
LANE_SCHEMA = "velgraphing-v4-luna-lane-manifest-v3"
RESULT_SCHEMA = "velgraphing-m09-four-arm-result-v2"
ARMS = ("A", "B", "C", "D")
TASKS = base.TASKS
REPEATS = (1, 2)
JEV_CAP = 48
CALLS = {"answer_base": 32, "answer_max": 96,
         "grader_base": 32, "grader_max": 96,
         "jev_base_max": 16, "jev_max": JEV_CAP, "attempts_per_trial_max": 3}
ANSWER_MODEL = "gpt-6-luna"
ANSWER_REASONING = "medium"


class StudyError(ValueError):
    pass


def _read(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if type(value) is not dict:
        raise StudyError("input_invalid")
    return raw, value


def _sha(path: Path) -> str:
    return base.digest(path.read_bytes())


def _trial_id(base_id: str, repeat: int) -> str:
    return f"{base_id}-R{repeat}"


def _round_ids(freeze: Mapping[str, Any], repeat: int) -> tuple[str, ...]:
    ids = freeze["dispatch_order"]
    if len(ids) != 16 or set(ids) != {
        f"{arm}-{task}" for arm in ARMS for task in TASKS
    }:
        raise StudyError("dispatch_order_invalid")
    return tuple(_trial_id(base_id, repeat) for base_id in ids)


def _study_freeze(historical: Mapping[str, Any]) -> dict[str, Any]:
    lane = historical["lane_identity_contract"]
    return {
        **historical,
        "study_id": STUDY_ID,
        "lane_identity_contract": {
            **lane,
            "answer": {**lane["answer"], "model": ANSWER_MODEL,
                       "reasoning": ANSWER_REASONING},
        },
    }


def _manifest(freeze: Mapping[str, Any], root: Path, repeat: int,
              python: Path) -> dict[str, Any]:
    run_tag = root.name.rsplit("-", 1)[-1]
    if re.fullmatch(r"r[1-9][0-9]*", run_tag) is None:
        raise StudyError("run_tag_invalid")
    entries = []
    for trial_id in _round_ids(freeze, repeat):
        for role in ("answer", "grader"):
            for attempt in range(3):
                task_name = (
                    f"m09_{run_tag}_{trial_id.lower().replace('-', '_')}_{role}_a{attempt}"
                )
                lane = freeze["lane_identity_contract"][role]
                argv = handoff_argv(root, trial_id, role, 600, python, attempt)
                entries.append({
                    "trial_id": trial_id, "role": role, "attempt": attempt,
                    "thread_id": task_name,
                    "canonical_task_path": f"/root/{task_name}",
                    "model": lane["model"], "reasoning": lane["reasoning"],
                    "argv": argv, "argv_sha256": base.digest(base.canonical(argv)),
                })
    return {"schema_version": LANE_SCHEMA, "entries": entries}


def _combined_manifest(freeze: Mapping[str, Any], root: Path,
                       python: Path) -> dict[str, Any]:
    return {
        "schema_version": LANE_SCHEMA,
        "entries": [entry for repeat in REPEATS
                    for entry in _manifest(freeze, root, repeat, python)["entries"]],
    }


def _inputs(lane_root: Path, pool_path: Path
            ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any],
                       dict[str, Any], dict[str, Any]]:
    freeze, _, _ = base.load_bundle(BENCHMARK, ROOT)
    _, rubrics = _read(BENCHMARK / base.SUCCESSOR_RUBRICS)
    _, preflight = _read(BENCHMARK / base.SUCCESSOR_PREFLIGHT)
    _, artifact = _read(pool_path)
    if (set(rubrics.get("tasks", {})) != set(TASKS)
            or artifact.get("schema_version") != base.LOCAL_ARTIFACT_SCHEMA
            or artifact.get("provider_calls_executed") != 0
            or preflight.get("pool_artifact_sha256") != _sha(pool_path)
            or preflight.get("executed_calls")
            != {"answer": 0, "grader": 0, "jev": 0, "provider": 0}):
        raise StudyError("frozen_inputs_invalid")
    base._validate_rubrics({
        "schema_version": "velgraphing-four-arm-rubrics-v1",
        "governance_rule": rubrics["governance_rule"],
        "tasks": rubrics["tasks"],
    })
    pools = {}
    for row in artifact.get("pools", []):
        identity = row.get("identity", {})
        key = f"{identity.get('route')}:{identity.get('task_id')}"
        if (key in pools or key not in freeze["candidate_pool_contract"]["pool_bindings"]
                or row.get("pool_sha256") != base.digest(base.canonical(identity))
                or row["pool_sha256"] != preflight["pool_bindings"].get(key)
                or row.get("corpus") != base.TASK_CORPORA.get(identity.get("task_id"))):
            raise StudyError("pool_identity_invalid")
        pools[key] = row
    if len(pools) != 8:
        raise StudyError("pool_set_invalid")
    registrations = {
        row["trial_id"]: row
        for row in preflight.get("source_free_preflight", {}).get("trials", [])
    }
    if set(registrations) != set(freeze["dispatch_order"]):
        raise StudyError("registration_set_invalid")
    for corpus_id, corpus in freeze["corpora"].items():
        manifest = ROOT / corpus["manifest"]
        if _sha(manifest) != corpus["manifest_sha256"]:
            raise StudyError("corpus_manifest_changed")
        verify_lane(ROOT, base._corpus_binding(corpus_id, freeze), lane_root / corpus_id)
    for key, pool in pools.items():
        task = pool["identity"]["task_id"]
        preview = base.jev.prepare(
            pool["candidate_packet"], lane_root / base.TASK_CORPORA[task],
        )
        if (preview["request_sha256"] != pool["jev_preview"]["request_sha256"]
                or preview["request_bytes"] != pool["jev_preview"]["request_bytes"]):
            raise StudyError(f"jev_preview_changed:{key}")
    return freeze, rubrics, preflight, pools, registrations


def _contract(freeze: Mapping[str, Any], pools: Mapping[str, Any],
              root: Path, lane_root: Path, pool_path: Path,
              manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    installed, candidate_sha, adapter_sha = base._install_graph_find(root)
    release = ROOT / "plugins/graph-engineering/.codex-plugin/release-manifest.json"
    installed_graph_previews = {}
    for task in TASKS:
        corpus_id = base.TASK_CORPORA[task]
        corpus = freeze["corpora"][corpus_id]
        source_manifest = base._load_manifest(ROOT / corpus["manifest"])
        installed_graph_previews[task] = base.installed_graph_jev_preview(
            prompt=base._question_prompt(task), lane=lane_root / corpus_id,
            source_manifest=source_manifest,
            installed=(installed, candidate_sha, adapter_sha),
        )
    jev_requests = {}
    for repeat in REPEATS:
        for arm in ("B", "D"):
            route = freeze["arms"][arm]["route"]
            for task in TASKS:
                trial_id = _trial_id(f"{arm}-{task}", repeat)
                preview = (
                    {
                        "request_sha256": installed_graph_previews[task]["jev_request_sha256"],
                        "request_bytes": installed_graph_previews[task]["jev_request_bytes"],
                    }
                    if arm == "D" else pools[f"{route}:{task}"]["jev_preview"]
                )
                jev_requests[trial_id] = {
                    "request_sha256": preview["request_sha256"],
                    "request_bytes": preview["request_bytes"],
                }
    planned_bytes = sum(row["request_bytes"] for row in jev_requests.values())
    if len(jev_requests) != 16:
        raise StudyError("jev_request_count_invalid")
    return {
        "schema_version": SCHEMA, "study_id": STUDY_ID,
        "candidate": {
            "controller_sha256": _sha(ROOT / "scripts/benchmarks/four_arm_study_v1.py"),
            "runner_sha256": _sha(Path(__file__)),
            "packet_builder_sha256": _sha(
                ROOT / "scripts/benchmarks/time_to_correct_packet.py"
            ),
            "host_sha256": _sha(ROOT / "scripts/benchmarks/time_to_correct_host.py"),
            "jev_adapter_sha256": _sha(ROOT / "scripts/benchmarks/time_to_correct_jev.py"),
            "jev_core_sha256": _sha(ROOT / "packages/core/jev.py"),
            "release_manifest_sha256": _sha(release),
            "installed_package_candidate_sha256": candidate_sha,
            "installed_graph_find_sha256": adapter_sha,
            "installed_graph_find_path": str(installed),
            "answer_contract_sha256": base.digest(base.canonical(base.ANSWER_RESPONSE_CONTRACT)),
            "grader_contract_sha256": base.digest(
                base.canonical(base.SUCCESSOR_GRADER_RESPONSE_CONTRACT)
            ),
        },
        "inputs": {
            "freeze_sha256": _sha(BENCHMARK / "freeze.json"),
            "questions_sha256": _sha(BENCHMARK / "questions.json"),
            "successor_rubrics_sha256": _sha(BENCHMARK / base.SUCCESSOR_RUBRICS),
            "rubric_task_content_sha256": base.digest(base.canonical(
                _read(BENCHMARK / base.SUCCESSOR_RUBRICS)[1]["tasks"]
            )),
            "successor_preflight_sha256": _sha(BENCHMARK / base.SUCCESSOR_PREFLIGHT),
            "successor_preflight_role": "historical_pool_registration_only",
            "pool_artifact_sha256": _sha(pool_path),
            "pool_artifact_path": str(pool_path),
            "pool_sha256_by_route_task": {
                key: pool["pool_sha256"] for key, pool in sorted(pools.items())
            },
            "lane_root": str(lane_root),
            "source_snapshots": {
                key: row["snapshot_sha256"] for key, row in sorted(freeze["corpora"].items())
            },
            "corpus_manifest_sha256": {
                key: row["manifest_sha256"] for key, row in sorted(freeze["corpora"].items())
            },
        },
        "policy": {
            "arms": freeze["arms"], "tasks": list(TASKS),
            "lane_identity_contract": freeze["lane_identity_contract"],
            "historical_answer_model_replaced": "gpt-5.6-luna",
            "repeats_per_arm_task": 2, "dispatch_order": [
                trial_id for repeat in REPEATS for trial_id in _round_ids(freeze, repeat)
            ],
            "final_context_byte_cap": base.FINAL_CONTEXT_BYTE_BUDGET,
            "oracle_source_append_enabled": False,
            "rubric_derived_answer_facets_enabled": False,
            "retry_transient": True, "max_trial_attempts": 3,
            "independent_answer_and_grader_lanes": True,
            "actual_selector_route_required": True,
        },
        "lanes": {
            f"R{repeat}": base.digest(base.canonical(dict(manifests[f"R{repeat}"])))
            for repeat in REPEATS
        },
        "jev": {
            "model": base.jev.DEFAULT_MODEL,
            "max_calls": JEV_CAP, "requests_by_trial": jev_requests,
            "installed_graph_previews_by_task": installed_graph_previews,
            "request_set_sha256": base.digest(base.canonical(jev_requests)),
            "planned_request_bytes": planned_bytes,
        },
        "authority": {
            "planned_calls": dict(CALLS),
            "codex_lane_monetary_cost_usd": None,
            "parent_review_required_before_dispatch": True,
        },
        "result_rules": {
            "required_trial_count": 32, "one_answer_and_grader_per_attempt": True,
            "retry_only_transient_model_failures": True,
            "scored_failure_is_final": True, "route_fallback_is_not_graph": True,
            "jev_configured_is_not_jev_executed": True,
            "missing_token_and_cost_are_unknown": True,
        },
    }


def _write_once(path: Path, value: Mapping[str, Any]) -> str:
    raw = base.canonical(dict(value))
    if path.exists():
        if read_canonical(path)[0] != raw:
            raise StudyError(f"frozen_file_changed:{path.name}")
    else:
        atomic_write(path, raw)
    return base.digest(raw)


def prepare(root: Path, lane_root: Path, pool_path: Path,
            python: Path) -> dict[str, Any]:
    root = validate_run_root(str(root))
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not python.is_absolute() or not python.is_file():
        raise StudyError("python_executable_invalid")
    historical, _, _, pools, _ = _inputs(lane_root, pool_path)
    freeze = _study_freeze(historical)
    manifest = _combined_manifest(freeze, root, python)
    _write_once(root / "lane-manifest.json", manifest)
    manifests = {f"R{repeat}": manifest for repeat in REPEATS}
    contract = _contract(freeze, pools, root, lane_root, pool_path, manifests)
    contract_sha = _write_once(root / "comparison-contract.json", contract)
    return {
        "contract_sha256": contract_sha,
        "lane_manifest_sha256": contract["lanes"],
        "calls": CALLS,
        "planned_jev_request_bytes": contract["jev"]["planned_request_bytes"],
        "jev_monetary_cost_usd": None,
        "codex_lane_monetary_cost_usd": None,
        "status": "prepared_pending_parent_review",
    }


def load_frozen(root: Path) -> tuple[dict[str, Any], dict[str, Any],
                                    dict[str, Any], dict[str, Any],
                                    dict[str, Any], dict[str, Any]]:
    root = validate_run_root(str(root))
    raw, contract = read_canonical(root / "comparison-contract.json")
    if (contract.get("schema_version") != SCHEMA
            or contract.get("study_id") != STUDY_ID
            or contract.get("authority", {}).get("planned_calls") != CALLS
            or contract.get("policy", {}).get("retry_transient") is not True
            or contract.get("policy", {}).get("oracle_source_append_enabled") is not False
            or contract.get("policy", {}).get("rubric_derived_answer_facets_enabled") is not False
            or contract.get("jev", {}).get("max_calls") != JEV_CAP):
        raise StudyError("comparison_contract_invalid")
    inputs = contract["inputs"]
    lane_root = Path(inputs["lane_root"])
    pool_path = Path(inputs["pool_artifact_path"])
    if not lane_root.is_absolute() or not pool_path.is_absolute():
        raise StudyError("comparison_input_path_invalid")
    historical, rubrics, _, pools, registrations = _inputs(lane_root, pool_path)
    freeze = _study_freeze(historical)
    raw_manifest, manifest = read_canonical(root / "lane-manifest.json")
    entries = manifest.get("entries")
    if (manifest.get("schema_version") != LANE_SCHEMA
            or type(entries) is not list or len(entries) != 192):
        raise StudyError("lane_manifest_invalid")
    python = Path(entries[0]["argv"][0])
    if base.canonical(manifest) != base.canonical(
        _combined_manifest(freeze, root, python)
    ):
        raise StudyError("lane_manifest_invalid")
    manifests = {}
    for repeat in REPEATS:
        if contract["lanes"].get(f"R{repeat}") != base.digest(raw_manifest):
            raise StudyError("lane_manifest_invalid")
        manifests[f"R{repeat}"] = manifest
    for entry in entries:
        if bound_lane_identity(
            root, entry["trial_id"], entry["role"], base.digest(raw_manifest),
            entry["attempt"],
        ) != {key: entry[key] for key in (
            "trial_id", "role", "thread_id", "model", "reasoning"
        )}:
            raise StudyError("lane_manifest_identity_invalid")
    expected_contract = _contract(
        freeze, pools, root, lane_root, pool_path, manifests,
    )
    if raw != base.canonical(expected_contract):
        raise StudyError("comparison_binding_stale")
    return contract, freeze, rubrics, pools, registrations, manifests


def _receipt_binding(contract: Mapping[str, Any], registration: Mapping[str, Any],
                     pool: Mapping[str, Any], rubric: Mapping[str, Any],
                     manifest_sha: str) -> str:
    return base.digest(base.canonical({
        "manifest": manifest_sha,
        "pool": pool["pool_sha256"],
        "decision": registration["selection_decision_sha256"],
        "rubric": base.digest(base.canonical(rubric)),
        "execution": "observed",
        "successor_ttc_contract": base.digest(base.canonical(contract)),
        "oracle_source_append_enabled": False,
        "use_public_task_facets": False,
    }))


def _validate_receipt(receipt: Mapping[str, Any], trial_id: str,
                      contract: Mapping[str, Any], registration: Mapping[str, Any],
                      pool: Mapping[str, Any], rubric: Mapping[str, Any]) -> None:
    repeat = int(trial_id[-1])
    identity = receipt.get("identity", {})
    attempts = receipt.get("attempts")
    if (identity.get("run_id") != STUDY_ID
            or identity.get("trial_id") != trial_id
            or identity.get("arm") != registration["arm"]
            or identity.get("task_id") != registration["task_id"]
            or receipt.get("execution") != "observed"
            or receipt.get("budget") != {
                "max_repairs": 2, "wall_limit_ns": 4_200_000_000_000
            }
            or type(attempts) is not list or not 1 <= len(attempts) <= 3
            or receipt.get("study_binding_sha256") != _receipt_binding(
                contract, registration, pool, rubric, contract["lanes"][f"R{repeat}"]
            )):
        raise StudyError(f"trial_receipt_invalid:{trial_id}")
    for earlier in attempts[:-1]:
        if (earlier.get("terminal_reason") != "needs_repair"
                or earlier.get("failure_stage") not in {"answer", "grader"}
                or earlier.get("failure_reason") not in
                TRANSIENT_MODEL_ERRORS | {"callback_timeout"}):
            raise StudyError(f"trial_retry_invalid:{trial_id}")
    attempt = attempts[-1]
    for row in attempts:
        row_calls = row.get("model_calls", [])
        row_kinds = [call.get("kind") for call in row_calls] if type(row_calls) is list else []
        if (row_kinds.count("answer") > 1 or row_kinds.count("grader") > 1
                or row_kinds.count("jev") > (1 if registration["arm"] in {"B", "D"} else 0)):
            raise StudyError(f"trial_calls_invalid:{trial_id}")
    calls = attempt.get("model_calls", [])
    kinds = [row.get("kind") for row in calls] if type(calls) is list else []
    if (receipt.get("terminal_reason") == "passed"
            and (kinds.count("answer") != 1 or kinds.count("grader") != 1)):
        raise StudyError(f"trial_calls_invalid:{trial_id}")
    if "answer" in kinds:
        observation = attempt.get("candidate_observation", {})
        route = observation.get("selection_route")
        if (route not in {"direct", "graph"}
                or registration["arm"] in {"A", "B"} and route != "direct"
                or registration["arm"] in {"C", "D"} and route == "direct"
                and not observation.get("selection_reason")):
            raise StudyError(f"actual_route_missing:{trial_id}")
    if registration["arm"] in {"B", "D"} and "answer" in kinds:
        jev = attempt.get("jev_observation", {})
        attempted = jev.get("attempted_calls")
        if (type(attempted) is not int or attempted not in {0, 1}
                or kinds.count("jev") != attempted
                or jev.get("status") not in {"reranked", "fallback"}
                or attempted == 0 and (
                    jev.get("status") != "fallback"
                    or type(jev.get("reason")) is not str or not jev["reason"]
                )):
            raise StudyError(f"jev_execution_missing:{trial_id}")
    if receipt.get("terminal_reason") in {"passed", "repair_budget_exhausted"}:
        if not _scored_complete(receipt):
            raise StudyError(f"scored_trial_incomplete:{trial_id}")


def _scored_complete(receipt: Mapping[str, Any]) -> bool:
    attempts = receipt.get("attempts")
    if type(attempts) is not list or not 1 <= len(attempts) <= 3:
        return False
    attempt = attempts[-1]
    grade = attempt.get("grade")
    calls = attempt.get("model_calls", [])
    kinds = [row.get("kind") for row in calls] if type(calls) is list else []
    terminal = receipt.get("terminal_reason")
    return (
        terminal in {"passed", "repair_budget_exhausted"}
        and type(grade) is dict and type(grade.get("passed")) is bool
        and grade["passed"] == (terminal == "passed")
        and attempt.get("failure_stage") is None
        and attempt.get("failure_reason") is None
        and kinds.count("answer") == 1 and kinds.count("grader") == 1
    )


def _transient_exhausted(receipt: Mapping[str, Any]) -> bool:
    attempts = receipt.get("attempts")
    if type(attempts) is not list or len(attempts) != 3:
        return False
    final = attempts[-1]
    return (
        receipt.get("terminal_reason") in {"measurement_error", "callback_timeout"}
        and final.get("failure_stage") in {"answer", "grader"}
        and final.get("failure_reason") in TRANSIENT_MODEL_ERRORS | {"callback_timeout"}
    )


def _result(contract: Mapping[str, Any], freeze: Mapping[str, Any],
            registrations: Mapping[str, Any], pools: Mapping[str, Any],
            rubrics: Mapping[str, Any], receipts: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for repeat in REPEATS:
        for trial_id in _round_ids(freeze, repeat):
            receipt = receipts[trial_id]
            base_id = trial_id.rsplit("-R", 1)[0]
            registration = registrations[base_id]
            pool = pools[registration["pool_id"]]
            rubric = rubrics["tasks"][registration["task_id"]]
            _validate_receipt(receipt, trial_id, contract, registration, pool, rubric)
            attempts = receipt["attempts"]
            attempt = attempts[-1]
            measurement = base._v3_trial_measurement(
                {**registration, "trial_id": trial_id}, receipt,
            )
            observation = attempt.get("candidate_observation", {})
            jev = attempt.get("jev_observation", {})
            all_calls = [call for row in attempts for call in row.get("model_calls", [])]
            process_attempts = {
                kind: max(
                    sum(process.get("kind") == kind
                        for row in attempts for process in row.get("host_processes", [])),
                    sum(call.get("kind") == kind for call in all_calls),
                ) for kind in ("answer", "grader")
            }
            rows.append({
                "trial_id": trial_id,
                "corpus": pool["corpus"],
                "task_id": registration["task_id"],
                "arm": registration["arm"],
                "passed": receipt["terminal_reason"] == "passed",
                "first_attempt_passed": len(attempts) == 1 and receipt["terminal_reason"] == "passed",
                "attempt_count": len(attempts),
                "terminal_reason": receipt["terminal_reason"],
                "wall_ns": measurement["user_visible_wall_ns"],
                "answer_request_bytes": measurement["answer_request_bytes"],
                "configured_route": pool["identity"]["route"],
                "actual_route": observation.get("selection_route"),
                "attempt_routes": [
                    row.get("candidate_observation", {}).get("selection_route")
                    for row in attempts
                ],
                "selection_reason": observation.get("selection_reason"),
                "selector_direct_fallback": (
                    registration["arm"] in {"C", "D"}
                    and observation.get("selection_route") == "direct"
                ),
                "jev_configured": registration["arm"] in {"B", "D"},
                "jev_attempted_calls": sum(
                    row.get("jev_observation", {}).get("attempted_calls", 0)
                    for row in attempts
                ),
                "jev_status": jev.get("status"),
                "jev_reason": jev.get("reason"),
                "jev_reranked": jev.get("status") == "reranked",
                "jev_source_revalidated": jev.get(
                    "jev_source_revalidated", jev.get("source_revalidated")
                ),
                "model_calls": all_calls,
                "answer_process_attempts": process_attempts["answer"],
                "grader_process_attempts": process_attempts["grader"],
                "phase_measurements": measurement,
                "receipt_sha256": base.digest(base.canonical(receipt)),
            })
    if len(rows) != 32:
        raise StudyError("result_incomplete")

    def reported_usage(selected: list[dict[str, Any]]) -> dict[str, Any]:
        usage = {}
        for kind in ("answer", "grader", "jev"):
            calls = [
                call for row in selected for call in row["model_calls"]
                if call.get("kind") == kind
            ]
            attempted = sum(
                row["jev_attempted_calls"] if kind == "jev"
                else row[f"{kind}_process_attempts"] for row in selected
            )
            fields = {}
            for field in ("input_tokens", "output_tokens", "cost_usd"):
                values = [call.get(field) for call in calls]
                fields[field] = {
                    "reported_calls": sum(value is not None for value in values),
                    "missing_calls": attempted - sum(value is not None for value in values),
                    "total": (
                        str(sum(Decimal(str(value)) for value in values))
                        if field == "cost_usd" and attempted and len(calls) == attempted and all(
                            value is not None for value in values
                        )
                        else sum(values) if field != "cost_usd" and attempted and len(calls) == attempted and all(
                            type(value) is int for value in values
                        ) else None
                    ),
                }
            usage[kind] = {"calls": attempted, **fields}
        return usage

    by_corpus_arm = {}
    for task in TASKS:
        for arm in ARMS:
            selected = [row for row in rows
                        if row["task_id"] == task and row["arm"] == arm]
            walls = [row["wall_ns"] for row in selected if type(row["wall_ns"]) is int]
            requests = [
                row["answer_request_bytes"] for row in selected
                if type(row["answer_request_bytes"]) is int
            ]
            by_corpus_arm[f"{task}:{arm}"] = {
                "corpus": selected[0]["corpus"],
                "passes": sum(row["passed"] for row in selected),
                "first_attempt_passes": sum(row["first_attempt_passed"] for row in selected),
                "trials": len(selected),
                "measurement_failures": sum(
                    not row["passed"] and row["terminal_reason"] not in {"repair_budget_exhausted"}
                    for row in selected
                ),
                "mean_wall_ns": sum(walls) / len(walls) if walls else None,
                "mean_answer_request_bytes": (
                    sum(requests) / len(requests) if requests else None
                ),
                "actual_routes": {
                    "direct": sum(row["actual_route"] == "direct" for row in selected),
                    "graph": sum(row["actual_route"] == "graph" for row in selected),
                    "unobserved": sum(row["actual_route"] is None for row in selected),
                },
                "selector_direct_fallbacks": sum(
                    row["selector_direct_fallback"] for row in selected
                ),
                "jev_executions": sum(row["jev_attempted_calls"] for row in selected),
                "jev_reranks": sum(row["jev_reranked"] for row in selected),
                "jev_source_accepted": sum(
                    row["jev_source_revalidated"] is True for row in selected
                ),
                "answer_process_attempts": sum(row["answer_process_attempts"] for row in selected),
                "grader_process_attempts": sum(row["grader_process_attempts"] for row in selected),
                "model_usage": reported_usage(selected),
            }
    return {
        "schema_version": RESULT_SCHEMA,
        "study_id": STUDY_ID,
        "comparison_contract_sha256": base.digest(base.canonical(contract)),
        "status": ("closed" if all(
            row["terminal_reason"] in {"passed", "repair_budget_exhausted"}
            for row in rows
        ) else "partial"),
        "metric_definitions": {
            "pass": "controller terminal_reason equals passed after an independent grade; retries are included",
            "first_attempt_pass": "passed with one trial attempt",
            "wall_ns": "controller user_visible_wall_ns for each complete trial",
            "answer_request_bytes": "serialized answer host request size, not model tokens",
            "actual_route": "installed ranked_context plan route, not configured arm",
            "jev_execution": "one observed provider attempt, not merely Jev on",
            "jev_source_accepted": "provider order passed exact-source revalidation",
            "cost": "provider or host reported only; null means unavailable",
        },
        "by_corpus_arm": by_corpus_arm, "trials": rows,
    }


def run(root: Path, approved_contract_sha: str) -> dict[str, Any]:
    contract, freeze, rubrics, pools, registrations, manifests = load_frozen(root)
    contract_sha = base.digest(base.canonical(contract))
    if approved_contract_sha != contract_sha:
        raise StudyError("parent_contract_approval_mismatch")
    if "TYPESAFE_API_KEY" not in os.environ:
        raise StudyError("jev_credential_absent")
    bind_controller(root, controller_identity(ROOT))
    order = contract["policy"]["dispatch_order"]
    prior = load_completed_trials(root / "completed", order)
    receipts = {}
    for receipt in prior:
        trial_id = receipt.get("identity", {}).get("trial_id")
        if trial_id not in order or trial_id in receipts:
            raise StudyError("prior_receipt_invalid")
        base_id = trial_id.rsplit("-R", 1)[0]
        registration = registrations[base_id]
        _validate_receipt(
            receipt, trial_id, contract, registration, pools[registration["pool_id"]],
            rubrics["tasks"][registration["task_id"]],
        )
        receipts[trial_id] = receipt
    budget = LiveJevBudget(root, JEV_CAP)
    for trial_id in order:
        if trial_id in receipts:
            if not _scored_complete(receipts[trial_id]) and not _transient_exhausted(receipts[trial_id]):
                raise StudyError(f"prior_failed_trial_requires_new_manifest:{trial_id}")
            continue
        require_resumable(root, trial_id, set(receipts))
        base_id, repeat_label = trial_id.rsplit("-R", 1)
        registration = {**registrations[base_id], "trial_id": trial_id}
        pool = pools[registration["pool_id"]]
        execution_pool = pool
        if registration["arm"] == "D":
            graph_preview = contract["jev"]["installed_graph_previews_by_task"][
                registration["task_id"]
            ]
            execution_pool = {
                **pool,
                "jev_preview": {
                    "request_sha256": graph_preview["jev_request_sha256"],
                    "request_bytes": graph_preview["jev_request_bytes"],
                },
            }
        manifest = manifests[f"R{repeat_label}"]
        receipt = base.execute_trial(
            freeze, registration, execution_pool,
            rubrics["tasks"][registration["task_id"]],
            Path(contract["inputs"]["lane_root"]), root, manifest,
            contract["lanes"][f"R{repeat_label}"], execution="observed",
            budget=budget, successor_ttc_contract=contract,
            oracle_source_append_enabled=False,
            use_public_task_facets=False,
        )
        _validate_receipt(
            receipt, trial_id, contract, registration, pool,
            rubrics["tasks"][registration["task_id"]],
        )
        save_completed_trial(root / "completed", receipt)
        receipts[trial_id] = receipt
        if not _scored_complete(receipt) and not _transient_exhausted(receipt):
            raise StudyError(f"trial_failed_inspect_before_new_manifest:{trial_id}")
    result = _result(contract, freeze, registrations, pools, rubrics, receipts)
    _write_once(root / "result.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--run-root", type=Path, required=True)
    prep.add_argument("--lane-root", type=Path, required=True)
    prep.add_argument("--pool-artifact", type=Path, required=True)
    prep.add_argument("--python-executable", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--run-root", type=Path, required=True)
    live = commands.add_parser("run")
    live.add_argument("--run-root", type=Path, required=True)
    live.add_argument("--parent-approved-contract-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        root = args.run_root.resolve()
        if args.command == "prepare":
            result = prepare(
                root, args.lane_root.resolve(), args.pool_artifact.resolve(),
                args.python_executable.resolve(),
            )
        elif args.command == "validate":
            contract, _, _, _, _, _ = load_frozen(root)
            result = {
                "status": "frozen_valid_pending_parent_review",
                "contract_sha256": base.digest(base.canonical(contract)),
                "calls": CALLS,
            }
        else:
            result = run(
                root, args.parent_approved_contract_sha256,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ArithmeticError, StudyError, base.StudyError, base.MeasurementError, OSError,
            ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"m09 study refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
