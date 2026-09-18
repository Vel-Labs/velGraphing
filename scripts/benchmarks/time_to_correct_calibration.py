#!/usr/bin/env python3
"""Serial 24-trial calibration coordinator. Native lanes use file handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from typing import Any, Mapping
import uuid

from time_to_correct import (Budget, MeasurementError, Trial, canonical, digest,
                             load_completed_trials, save_completed_trial, summarize)
from time_to_correct_graph import observe_graph_find
from time_to_correct_handoff import atomic_write, read_canonical, run_root as validate_run_root, write_response
from time_to_correct_host import USAGE_KEYS, _invoke, run_process_trial
from time_to_correct_jev import evaluate_live, evaluate_offline, load_jev, prepare_preview


REPO_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = REPO_ROOT / "benchmarks/velgraphing-time-to-correct-v1/calibration.json"
HANDOFF_PATH = REPO_ROOT / "scripts/benchmarks/time_to_correct_handoff.py"
TASKS = ("C-01", "C-02", "S-01", "L-01", "M-01", "M-02")
ARMS = ("A", "B", "C", "D")
JEV_ARMS = {"B", "D"}


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise MeasurementError("calibration_input_invalid") from None
    if type(value) is not dict:
        raise MeasurementError("calibration_input_invalid")
    return value


def load_calibration(repo: Path = REPO_ROOT) -> dict[str, Any]:
    config = read_json(repo / "benchmarks/velgraphing-time-to-correct-v1/calibration.json")
    registrations = config.get("registered_trials")
    if (config.get("schema_version") != "velgraphing-ttc-calibration-v1"
            or config.get("calibration_id") != "velgraphing-ttc-calibration-v1"
            or config.get("status") != "approved_not_executed"
            or config.get("base_commit") != "8b52fdaac9ce61feb09b06381c2081509df273c7"
            or config.get("package_version") != "0.1.6"
            or config.get("max_live_jev_calls") != 12
            or config.get("provider_retries") != 0
            or config.get("answer_model") != "gpt-5.6-sol"
            or config.get("reasoning") != "medium"
            or type(registrations) is not list or len(registrations) != 24):
        raise MeasurementError("calibration_freeze_invalid")
    expected = {(arm, task) for task in TASKS for arm in ARMS}
    observed = set()
    trial_ids = set()
    for row in registrations:
        if (type(row) is not dict or set(row) != {"trial_id", "packet_id", "task_id", "arm"}
                or row["trial_id"] != row["packet_id"] or row["trial_id"] in trial_ids):
            raise MeasurementError("calibration_registration_invalid")
        trial_ids.add(row["trial_id"])
        observed.add((row["arm"], row["task_id"]))
    if observed != expected or sum(row["arm"] in JEV_ARMS for row in registrations) != 12:
        raise MeasurementError("calibration_registration_invalid")
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


def verify_lane(repo: Path, corpus: Mapping[str, Any], corpus_root: Path) -> tuple[list[str], str]:
    if not corpus_root.is_absolute() or corpus_root.is_symlink():
        raise MeasurementError("corpus_root_invalid")
    manifest = read_json(repo / "benchmarks/velgraphing-corpus-pilot-v1" / corpus["manifest"])
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
    if digest(canonical({"sources": rows})) != corpus["snapshot_sha256"]:
        raise MeasurementError("corpus_snapshot_mismatch")
    head = subprocess.run(["git", "-C", str(corpus_root), "rev-parse", "HEAD"],
                          capture_output=True, check=False).stdout.decode("ascii", "ignore").strip()
    status = subprocess.run(["git", "-C", str(corpus_root), "status", "--porcelain=v1", "-z"],
                            capture_output=True, check=False).stdout
    if head != corpus["commit"] or status:
        raise MeasurementError("corpus_checkout_not_clean")
    return [row["path"] for row in rows], digest(status)


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


def handoff_argv(run_root: Path, trial_id: str, lane: str, wait_seconds: float) -> list[str]:
    return [sys.executable, str(HANDOFF_PATH), "wait", "--run-root", str(run_root),
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


def request_candidates(trial: Trial, repo: Path, run_root: Path, payload: dict[str, Any],
                       wait_seconds: float) -> dict[str, Any]:
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

    def reserve(self, trial_id: str, request_sha256: str) -> tuple[Path, int]:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        existing = sorted(self.root.glob("*.json"))
        path = self.root / f"{trial_id}.json"
        if path.exists():
            raise MeasurementError("jev_call_already_reserved")
        if len(existing) >= self.cap:
            raise MeasurementError("jev_call_cap_exhausted")
        number = len(existing) + 1
        atomic_write(path, canonical({
            "schema_version": "velgraphing-jev-call-receipt-v1",
            "trial_id": trial_id,
            "request_sha256": request_sha256,
            "call_number": number,
            "max_live_jev_calls": self.cap,
            "status": "reserved_unknown_if_consumed",
            "attempted_calls": None,
        }))
        return path, number

    def complete(self, path: Path, result: Mapping[str, Any]) -> None:
        reserved = read_canonical(path)[1]
        atomic_write(path, canonical({
            **reserved,
            "status": "consumed",
            "attempted_calls": result.get("attempted_calls"),
            "provider_status": result.get("status"),
            "provider_reason": result.get("reason"),
        }), replace=True)


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


def run_registered_trial(repo: Path, run_root: Path, lane_root: Path,
                         config: Mapping[str, Any], registration: Mapping[str, Any],
                         packet: Mapping[str, Any], corpus: Mapping[str, Any],
                         oracle: Mapping[str, Any], budget: LiveJevBudget) -> dict[str, Any]:
    corpus_id = corpus.get("id")
    if type(corpus_id) is not str or not corpus_id or PurePosixPath(corpus_id).name != corpus_id:
        raise MeasurementError("corpus_root_invalid")
    corpus_root = lane_root / corpus_id
    scope, dirty = verify_lane(repo, corpus, corpus_root)
    identity = trial_identity(config, registration, packet, corpus, oracle, dirty)
    trial = Trial(identity, Budget(**config["repair_budget"]), execution="observed")
    timeouts = config["timeouts_seconds"]

    def prepare(current: Trial, attempt: int) -> dict[str, Any]:
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
            candidate = request_candidates(current, repo, run_root, base, timeouts["preparation"])
            prepared = prepare_preview(current, repo, candidate, corpus_root)
            approval_response(current, repo, run_root, prepared, timeouts["jev_approval"], budget.cap)
            receipt_path, call_number = budget.reserve(registration["trial_id"], prepared["request_sha256"])
            result = evaluate_live(
                current, repo, candidate, corpus_root,
                approved_request_sha256=prepared["request_sha256"], runtime_approved=True,
                max_live_calls=budget.cap, call_number=call_number,
            )
            budget.complete(receipt_path, result)
            base["jev"] = {
                key: result.get(key) for key in (
                    "status", "reason", "baseline_order", "order", "required_ids",
                    "request_sha256", "source_revalidated", "resolved_model",
                )
            }
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
    return run_process_trial(
        trial, prepare, answer_argv=answer_command, grader_argv=grader_command,
        cwd=repo, answer_timeout_s=timeouts["answer"] + 1,
        grader_timeout_s=timeouts["grader"] + 1, grader_context=grader_context,
    )


def run_calibration(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo_root).resolve()
    if repo != REPO_ROOT.resolve():
        raise MeasurementError("repository_root_mismatch")
    config = load_calibration(repo)
    validate_live_authority(config, args.allow_live_jev, args.approved_max_live_jev_calls)
    root = calibration_run_root(repo, config, args.run_root)
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
    completed_ids = {row["identity"]["trial_id"] for row in completed}
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
    return summarize(expected_ids, completed)


def start_fixture_worker(root: Path, trial_id: str, lane: str, wait: float = 5) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(HANDOFF_PATH), "fixture-worker", "--run-root", str(root),
         "--trial-id", trial_id, "--attempt", "0", "--lane", lane,
         "--wait-seconds", str(wait)],
        cwd=str(REPO_ROOT), env={}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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


def qualify(repo: Path = REPO_ROOT) -> dict[str, Any]:
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
            return {"fixture_answer": "distinct direct fixture answer", "source_scope": ["README.md", "cancel.py"]}
        direct = run_process_trial(
            direct_trial, direct_prepare,
            answer_argv=handoff_argv(handoff_root, "direct-off", "answer", 1),
            grader_argv=handoff_argv(handoff_root, "direct-off", "grader", 1),
            cwd=repo, answer_timeout_s=1.5, grader_timeout_s=1.5,
        )
        finish_workers(direct_workers)

        graph_workers = [start_fixture_worker(handoff_root, "graph-on", lane) for lane in ("preparation", "answer", "grader")]
        graph_trial = Trial(fixture_identity("graph-on", "D", snapshot), Budget(0, 3_000_000_000), execution="fixture")
        def graph_prepare(trial: Trial, _: int) -> dict[str, Any]:
            navigation = observe_graph_find(
                trial, repo, ["--root", str(source), "--prompt", "Find cancel_task cancellation implementation and documentation"],
            )
            evidence = navigation["evidence"]
            if not evidence:
                raise MeasurementError("qualification_graph_evidence_missing")
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
            )
            envelope = replay_envelope(repo, captured, source)
            result = evaluate_offline(trial, repo, captured, source, envelope=envelope)
            trial.not_applicable("operator_approval")
            return {"fixture_answer": "distinct graph replay fixture answer",
                    "graph_navigation": navigation, "jev_order": result["order"]}
        graph = run_process_trial(
            graph_trial, graph_prepare,
            answer_argv=handoff_argv(handoff_root, "graph-on", "answer", 1),
            grader_argv=handoff_argv(handoff_root, "graph-on", "grader", 1),
            cwd=repo, answer_timeout_s=1.5, grader_timeout_s=1.5,
        )
        finish_workers(graph_workers)

        missing_trial = Trial(fixture_identity("missing-response", "A", snapshot),
                              Budget(0, 1_000_000_000), execution="fixture")
        def missing_prepare(trial: Trial, _: int) -> dict[str, Any]:
            trial.not_applicable("cold_graph_build", "warm_graph_load", "jev_preparation", "provider",
                                 "source_revalidation", "response_validation", "operator_approval")
            return {}
        missing = run_process_trial(
            missing_trial, missing_prepare,
            answer_argv=handoff_argv(handoff_root, "missing-response", "answer", 0.05),
            grader_argv=handoff_argv(handoff_root, "missing-response", "grader", 0.05),
            cwd=repo, answer_timeout_s=0.5, grader_timeout_s=0.5,
        )
        receipt = read_canonical(handoff_root / "trials/missing-response/attempt-0/answer/receipt.json")[1]
        config = load_calibration(repo)
        try:
            validate_live_authority(config, False, None)
        except MeasurementError as error:
            refusal = error.reason
        else:
            raise MeasurementError("live_refusal_missing")
        return {
            "schema_version": "velgraphing-ttc-calibration-qualification-v1",
            "provider_calls_made": 0,
            "direct_off": {"terminal_reason": direct["terminal_reason"],
                           "answer_sha256": direct["attempts"][0]["answer_sha256"]},
            "graph_on_replay": {"terminal_reason": graph["terminal_reason"],
                                "graph_records": graph["attempts"][0]["graph_observation"]["record_count"],
                                "jev_execution": graph["attempts"][0]["jev_observation"]["measurement_execution"]},
            "missing_response": {"terminal_reason": missing["terminal_reason"],
                                 "handoff_status": receipt["status"]},
            "live_refusal": refusal,
        }
    finally:
        shutil.rmtree(root)


def approve(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo_root).resolve()
    config = load_calibration(repo)
    root = calibration_run_root(repo, config, args.run_root)
    validate_live_authority(config, True, args.approved_max_live_jev_calls)
    request_path = root / "trials" / args.trial_id / "attempt-0/jev-approval/request.json"
    request = read_canonical(request_path)[1]
    if (request.get("schema_version") != "velgraphing-jev-approval-request-v1"
            or request.get("trial_id") != args.trial_id
            or request.get("request_sha256") != args.request_sha256
            or request.get("max_live_jev_calls") != 12):
        raise MeasurementError("jev_request_not_approved")
    response = {
        "schema_version": "velgraphing-jev-approval-v1",
        "trial_id": args.trial_id,
        "request_sha256": args.request_sha256,
        "approved": True,
        "max_live_jev_calls": 12,
    }
    write_response(root, args.trial_id, 0, "jev-approval", canonical(response))
    return {"status": "approved", "trial_id": args.trial_id,
            "request_sha256": args.request_sha256}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    commands.add_parser("qualify")
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
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "plan":
            config = load_calibration(REPO_ROOT)
            output = {"calibration_id": config["calibration_id"],
                      "registered_trials": [row["trial_id"] for row in config["registered_trials"]],
                      "max_live_jev_calls": config["max_live_jev_calls"],
                      "provider_calls_made": 0}
        elif args.command == "qualify":
            output = qualify(REPO_ROOT)
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
