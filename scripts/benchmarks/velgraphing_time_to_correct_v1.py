#!/usr/bin/env python3
"""Measure real time-to-correct phases through frozen subprocess seams.

The harness never invents answer, grade, Jev, or wall-clock values. It calls the
canonical Jev implementation with a deterministic replay envelope, executes the
frozen answer and grader commands, and records failed or censored rows.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from packages.core import jev as canonical_jev  # noqa: E402


SCHEMA_VERSION = "velgraphing-time-to-correct-event-v1"
SUMMARY_SCHEMA_VERSION = "velgraphing-time-to-correct-summary-v1"
ALLOWED_ARMS = {"A", "B", "C", "D"}
ALLOWED_RETRIEVAL = {"direct", "graph_assisted"}
ALLOWED_JEV = {"off", "on"}
ALLOWED_PHASES = {
    "task_accept",
    "graph_build_or_load:cold",
    "graph_build_or_load:warm",
    "discovery_start",
    "discovery_end",
    "jev_prepare_start",
    "jev_prepare_end",
    "jev_provider_call_start",
    "jev_provider_call_end",
    "jev_revalidate_end",
    "answer_dispatch_start",
    "answer_dispatch_end",
    "grade_start",
    "grade_end",
    "repair_attempt_n_start",
    "repair_attempt_n_end",
    "first_pass_correctness",
    "time_to_correct",
    "active_execution",
    "queue_approval",
    "user_visible_wall",
    "component_removal",
    "terminal_reason",
}


class HarnessError(RuntimeError):
    """Raised for malformed inputs or a prohibited provider boundary."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _now_ns() -> int:
    return time.monotonic_ns()


def _emit(stream, **fields) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "event_id": uuid.uuid4().hex, **fields}
    if payload["phase"] not in ALLOWED_PHASES:
        raise HarnessError(f"unknown phase: {payload['phase']!r}")
    payload.setdefault("status", "ok")
    stream.write(_canonical(payload).decode("utf-8"))
    stream.flush()


def _refuse_live_key() -> None:
    if os.environ.get("TYPESAFE_API_KEY"):
        raise HarnessError("TYPESAFE_API_KEY is set; live provider calls are disabled")


def _command(value: object, label: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value or not all(isinstance(part, str) and part for part in value):
        raise HarnessError(f"{label} must be a non-empty argv list")
    return value[:]


def _load_freeze(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "velgraphing-time-to-correct-freeze-v1":
        raise HarnessError("freeze schema_version mismatch")
    if {arm["id"] for arm in payload.get("arms", [])} != ALLOWED_ARMS:
        raise HarnessError(f"arms must be exactly {sorted(ALLOWED_ARMS)}")
    for arm in payload["arms"]:
        if arm["retrieval"] not in ALLOWED_RETRIEVAL or arm["jev"] not in ALLOWED_JEV:
            raise HarnessError(f"invalid arm definition: {arm.get('id')}")
    if not isinstance(payload.get("repair_budget"), int) or payload["repair_budget"] < 0:
        raise HarnessError("repair_budget must be a non-negative integer")
    boundary = payload.get("answer_lane_boundary", {})
    if not isinstance(boundary, dict):
        raise HarnessError("answer_lane_boundary must be an object")
    _command(boundary.get("answer_command"), "answer_lane_boundary.answer_command")
    grader = payload.get("grader", {})
    if not isinstance(grader, dict):
        raise HarnessError("grader must be an object")
    _command(grader.get("command"), "grader.command")
    return payload


def _run_command(command: list[str], payload: dict, cwd: Path, timeout_s: float) -> dict:
    started = _now_ns()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            input=_canonical(payload),
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
        timed_out = False
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
    return {
        "exit_code": exit_code,
        "wall_ms": (_now_ns() - started) / 1_000_000,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
    }


def _safe_json(raw: bytes) -> dict | None:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _grade_pass(grade: dict) -> bool:
    return (
        grade.get("required_fact_recall") == 1.0
        and grade.get("critical_facts_exact") is True
        and grade.get("unsupported_material_claims") == 0
        and grade.get("critical_errors") == 0
    )


def _replay_for(replay: dict | None, packet_id: str) -> dict | None:
    if replay is None:
        return None
    candidate = replay.get(packet_id) if packet_id in replay else replay
    return candidate if isinstance(candidate, dict) else None


def _terminal(stream, *, trial_index: int = 0, task_id: str, packet_id: str, arm: str, corpus_id: str, snapshot_sha256: str, reason: str) -> None:
    _emit(
        stream,
        trial_index=trial_index,
        task_id=task_id,
        packet_id=packet_id,
        arm=arm,
        corpus_id=corpus_id,
        snapshot_sha256=snapshot_sha256,
        phase="terminal_reason",
        t_monotonic_ns=_now_ns(),
        details={"reason": reason},
    )


def _censored_terminal(stream, common: dict, summary: dict, started: int, reason: str, active_ms: float) -> None:
    summary.update({
        "censored": True,
        "terminal_reason": reason,
        "active_execution_ms": active_ms,
        "queue_approval_ms": None,
        "user_visible_wall_ms": (_now_ns() - started) / 1_000_000,
    })
    _emit(stream, **common, phase="time_to_correct", t_monotonic_ns=_now_ns(), details={"time_to_correct_ms": None})
    _emit(stream, **common, phase="active_execution", t_monotonic_ns=_now_ns(), details={"active_execution_ms": active_ms})
    _emit(stream, **common, phase="queue_approval", t_monotonic_ns=_now_ns(), details={"queue_approval_ms": None, "owner": "parent_operator"})
    _emit(stream, **common, phase="user_visible_wall", t_monotonic_ns=_now_ns(), details={"user_visible_wall_ms": summary["user_visible_wall_ms"]})
    _terminal(stream, **common, reason=reason)


def _execute_packet(
    *,
    freeze: dict,
    packet: dict,
    arm: dict,
    cwd: Path,
    events_path: Path,
    replay_envelope: dict | None,
    without_jev: bool,
    without_graph: bool,
    without_fallback: bool,
    repair_budget: int,
) -> dict:
    task_id = packet["task_id"]
    packet_id = packet["packet_id"]
    arm_id = arm["id"]
    retrieval = arm["retrieval"]
    jev_mode = arm["jev"]
    corpus = packet["corpus"]
    corpus_id = corpus["id"]
    snapshot = corpus.get("snapshot_sha256", "")
    corpus_root = Path(corpus.get("materialized_root") or corpus.get("root") or cwd)
    started = _now_ns()
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "packet_id": packet_id,
        "task_id": task_id,
        "arm": arm_id,
        "retrieval": retrieval,
        "jev": jev_mode,
        "trial_index": 0,
        "censored": False,
        "terminal_reason": None,
        "first_pass_correctness": None,
        "time_to_correct_ms": None,
        "active_execution_ms": 0.0,
        "queue_approval_ms": None,
        "user_visible_wall_ms": None,
        "repair_attempts_used": 0,
        "answer_attempts": 0,
        "grade_attempts": 0,
        "component_removals": [],
    }
    with events_path.open("a", encoding="utf-8") as events:
        with contextlib.redirect_stdout(events):
            common = {
                "trial_index": 0,
                "task_id": task_id,
                "packet_id": packet_id,
                "arm": arm_id,
                "corpus_id": corpus_id,
                "snapshot_sha256": snapshot,
            }
            _emit(
                sys.stdout,
                **common,
                phase="task_accept",
                t_monotonic_ns=started,
                details={"freeze_sha256": hashlib.sha256(_canonical(freeze)).hexdigest()},
            )
            for removed, enabled in (("jev", without_jev), ("graph", without_graph), ("fallback", without_fallback)):
                if enabled:
                    summary["component_removals"].append(removed)
                    _emit(sys.stdout, **common, phase="component_removal", t_monotonic_ns=_now_ns(), details={"removed": removed})

            active_ms = 0.0
            jev_observation = {"status": "off", "order": []}
            if jev_mode == "on" and not without_jev:
                replay = _replay_for(replay_envelope, packet_id)
                jev_packet = packet.get("jev_packet")
                if not isinstance(jev_packet, dict) or replay is None:
                    reason = "jev_replay_unavailable"
                    summary.update({"censored": True, "terminal_reason": reason, "user_visible_wall_ms": (_now_ns() - started) / 1_000_000})
                    _terminal(sys.stdout, **common, reason=reason)
                    return summary
                _emit(sys.stdout, **common, phase="jev_prepare_start", t_monotonic_ns=_now_ns(), details={"mode": "rerank"})
                provider_start = _now_ns()
                _emit(sys.stdout, **common, phase="jev_provider_call_start", t_monotonic_ns=provider_start, details={"transport": "replay"})
                jev_result = canonical_jev.evaluate(
                    jev_packet,
                    corpus_root,
                    mode="rerank",
                    allow_network=False,
                    replay=replay,
                )
                provider_end = _now_ns()
                call_ms = (provider_end - provider_start) / 1_000_000
                _emit(
                    sys.stdout,
                    **common,
                    phase="jev_prepare_end",
                    t_monotonic_ns=provider_end,
                    details={"mode": "rerank", "canonical": True},
                )
                _emit(
                    sys.stdout,
                    **common,
                    phase="jev_provider_call_end",
                    t_monotonic_ns=provider_end,
                    details={
                        "transport": "replay",
                        "elapsed_ms": call_ms,
                        "canonical_elapsed_ms": jev_result.get("elapsed_ms"),
                        "status": jev_result.get("status"),
                        "attempted_calls": jev_result.get("attempted_calls"),
                    },
                )
                revalidate_end = _now_ns()
                _emit(
                    sys.stdout,
                    **common,
                    phase="jev_revalidate_end",
                    t_monotonic_ns=revalidate_end,
                    details={"source_revalidated": jev_result.get("source_revalidated", False)},
                )
                active_ms += call_ms
                jev_observation = {
                    key: jev_result.get(key)
                    for key in ("status", "reason", "order", "suggested_order", "source_revalidated", "attempted_calls", "replayed_usage")
                }
                if jev_result.get("status") != "reranked":
                    reason = f"jev_error:{jev_result.get('reason', 'unknown')}"
                    _censored_terminal(sys.stdout, common, summary, started, reason, active_ms)
                    return summary

            answer_command = _command(freeze.get("answer_lane_boundary", {}).get("answer_command"), "answer_lane_boundary.answer_command")
            grader_command = _command(freeze.get("grader", {}).get("command"), "grader.command")
            if answer_command is None:
                reason = "answer_lane_unavailable"
                _censored_terminal(sys.stdout, common, summary, started, reason, active_ms)
                return summary
            if grader_command is None:
                reason = "grader_unavailable"
                _censored_terminal(sys.stdout, common, summary, started, reason, active_ms)
                return summary

            answer_timeout = float(freeze.get("timeouts", {}).get("answer_s", 60))
            grader_timeout = float(freeze.get("timeouts", {}).get("grader_s", 60))
            first_pass = None
            terminal_reason = "fail_no_pass_under_budget"
            censored = False
            for attempt in range(repair_budget + 1):
                _emit(sys.stdout, **common, phase="repair_attempt_n_start", t_monotonic_ns=_now_ns(), details={"attempt_index": attempt})
                answer_payload = {
                    "schema_version": "velgraphing-time-to-correct-answer-input-v1",
                    "task_id": task_id,
                    "packet_id": packet_id,
                    "arm": arm_id,
                    "retrieval": retrieval,
                    "jev": jev_mode,
                    "question": packet.get("question", ""),
                    "jev_observation": jev_observation,
                    "repair_attempt": attempt,
                }
                _emit(sys.stdout, **common, phase="answer_dispatch_start", t_monotonic_ns=_now_ns(), details={"attempt_index": attempt})
                answer_result = _run_command(answer_command, answer_payload, cwd, answer_timeout)
                active_ms += answer_result["wall_ms"]
                summary["answer_attempts"] += 1
                _emit(
                    sys.stdout,
                    **common,
                    phase="answer_dispatch_end",
                    t_monotonic_ns=_now_ns(),
                    status="censored" if answer_result["timed_out"] else ("ok" if answer_result["exit_code"] == 0 else "failed"),
                    details={
                        "attempt_index": attempt,
                        "exit_code": answer_result["exit_code"],
                        "wall_ms": answer_result["wall_ms"],
                        "stdout_sha256": hashlib.sha256(answer_result["stdout"]).hexdigest(),
                        "stderr_sha256": hashlib.sha256(answer_result["stderr"]).hexdigest(),
                    },
                )
                if answer_result["timed_out"]:
                    terminal_reason = "answer_timeout"
                    censored = True
                    break
                answer = _safe_json(answer_result["stdout"]) if answer_result["exit_code"] == 0 else None
                if answer is None or not isinstance(answer.get("answer_text"), str):
                    terminal_reason = "fail_invalid_response"
                    _emit(sys.stdout, **common, phase="repair_attempt_n_end", t_monotonic_ns=_now_ns(), details={"attempt_index": attempt, "reason": terminal_reason})
                    continue

                grade_payload = {
                    "schema_version": "velgraphing-time-to-correct-grade-input-v1",
                    "task_id": task_id,
                    "packet_id": packet_id,
                    "arm": arm_id,
                    "question": packet.get("question", ""),
                    "answer": answer,
                    "repair_attempt": attempt,
                }
                _emit(sys.stdout, **common, phase="grade_start", t_monotonic_ns=_now_ns(), details={"attempt_index": attempt})
                grade_result = _run_command(grader_command, grade_payload, cwd, grader_timeout)
                active_ms += grade_result["wall_ms"]
                summary["grade_attempts"] += 1
                grade = _safe_json(grade_result["stdout"]) if grade_result["exit_code"] == 0 and not grade_result["timed_out"] else None
                if grade_result["timed_out"]:
                    terminal_reason = "grader_timeout"
                    censored = True
                elif grade is None:
                    terminal_reason = "fail_invalid_grade"
                else:
                    required = ("required_fact_score", "required_fact_max", "required_fact_recall", "critical_facts_exact", "unsupported_material_claims", "critical_errors", "source_support")
                    if any(key not in grade for key in required):
                        terminal_reason = "fail_invalid_grade"
                        grade = None
                    else:
                        passed = _grade_pass(grade)
                        if attempt == 0:
                            first_pass = passed
                        terminal_reason = "pass" if passed else "fail_no_pass_under_budget"
                        if passed:
                            summary.update({
                                "first_pass_correctness": first_pass,
                                "time_to_correct_ms": (_now_ns() - started) / 1_000_000,
                                "censored": False,
                            })
                _emit(
                    sys.stdout,
                    **common,
                    phase="grade_end",
                    t_monotonic_ns=_now_ns(),
                    status="censored" if grade_result["timed_out"] else ("ok" if grade is not None else "failed"),
                    details={
                        "attempt_index": attempt,
                        "exit_code": grade_result["exit_code"],
                        "wall_ms": grade_result["wall_ms"],
                        "grade": grade,
                        "stderr_sha256": hashlib.sha256(grade_result["stderr"]).hexdigest(),
                    },
                )
                if grade is not None:
                    _emit(
                        sys.stdout,
                        **common,
                        phase="first_pass_correctness",
                        t_monotonic_ns=_now_ns(),
                        details={"attempt_index": attempt, "value": _grade_pass(grade), "required_fact_recall": grade.get("required_fact_recall")},
                    )
                _emit(sys.stdout, **common, phase="repair_attempt_n_end", t_monotonic_ns=_now_ns(), details={"attempt_index": attempt, "reason": terminal_reason})
                if terminal_reason == "pass" or censored:
                    break

            summary.update({
                "terminal_reason": terminal_reason,
                "censored": censored,
                "active_execution_ms": active_ms,
                "queue_approval_ms": None,
                "user_visible_wall_ms": (_now_ns() - started) / 1_000_000,
            })
            if terminal_reason == "pass":
                _emit(sys.stdout, **common, phase="time_to_correct", t_monotonic_ns=_now_ns(), details={"time_to_correct_ms": summary["time_to_correct_ms"]})
            elif censored:
                _emit(sys.stdout, **common, phase="time_to_correct", t_monotonic_ns=_now_ns(), details={"time_to_correct_ms": None})
            _emit(sys.stdout, **common, phase="active_execution", t_monotonic_ns=_now_ns(), details={"active_execution_ms": active_ms})
            _emit(sys.stdout, **common, phase="queue_approval", t_monotonic_ns=_now_ns(), details={"queue_approval_ms": None, "owner": "parent_operator"})
            _emit(sys.stdout, **common, phase="user_visible_wall", t_monotonic_ns=_now_ns(), details={"user_visible_wall_ms": summary["user_visible_wall_ms"]})
            _terminal(sys.stdout, **common, reason=terminal_reason)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--without-jev", action="store_true")
    parser.add_argument("--without-graph", action="store_true")
    parser.add_argument("--without-fallback", action="store_true")
    parser.add_argument("--packet-ids", nargs="*")
    args = parser.parse_args(argv)
    try:
        _refuse_live_key()
        freeze = _load_freeze(args.freeze)
        replay = json.loads(args.replay.read_text(encoding="utf-8")) if args.replay else None
        packets = freeze.get("packets", {})
        events_path = args.events
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text("", encoding="utf-8")
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        with args.summary.open("w", encoding="utf-8") as summary_file:
            for arm in freeze["arms"]:
                for packet_id in freeze["dispatch"]["order"]:
                    if args.packet_ids and packet_id not in args.packet_ids:
                        continue
                    if not packet_id.startswith(arm["id"] + "-"):
                        continue
                    packet = packets.get(packet_id)
                    if not isinstance(packet, dict):
                        packet = {"packet_id": packet_id, "task_id": packet_id[len(arm["id"]) + 1:], "corpus": freeze["corpus"][0]}
                    row = _execute_packet(
                        freeze=freeze,
                        packet=packet,
                        arm=arm,
                        cwd=Path.cwd(),
                        events_path=events_path,
                        replay_envelope=replay,
                        without_jev=args.without_jev,
                        without_graph=args.without_graph,
                        without_fallback=args.without_fallback,
                        repair_budget=freeze["repair_budget"],
                    )
                    summary_file.write(_canonical(row).decode("utf-8"))
                    summary_file.flush()
        return 0
    except (HarnessError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
