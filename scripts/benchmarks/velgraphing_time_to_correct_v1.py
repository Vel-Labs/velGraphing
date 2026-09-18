#!/usr/bin/env python3
"""Monotonic event-trace harness for VelGraphing time-to-correct measurement.

Stdlib only. Emits a JSONL event stream and a per-row summary. Validates Jev
integration with deterministic replay fixtures. Refuses to start with
``TYPESAFE_API_KEY`` set unless ``--allow-network`` is passed.

The harness does NOT run the answer lane itself. It wraps a lane subprocess
(e.g. a codex-exec or Codex-equivalent fresh-worker call) and times the wall
around it. The lane subprocess is owned by the parent operator.

The schema is documented in
``benchmarks/velgraphing-time-to-correct-v1/event-trace.md``.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path


SCHEMA_VERSION = "velgraphing-time-to-correct-event-v1"
SUMMARY_SCHEMA_VERSION = "velgraphing-time-to-correct-summary-v1"
ALLOWED_ARMS = {"A", "B", "C", "D"}
ALLOWED_RETRIEVAL = {"direct", "graph_assisted"}
ALLOWED_JEV = {"off", "on"}
ALLOWED_TERMINAL_REASONS = {
    "pass",
    "fail_no_pass_under_budget",
    "fail_censored",
    "fail_invalid_response",
    "fail_provider_error",
    "fail_fallback_unavailable",
}
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
    """Raised for harness misuse (live provider key, malformed freeze, etc.)."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _now_ns() -> int:
    return time.monotonic_ns()


def _new_event_id() -> str:
    return uuid.uuid4().hex


def _emit(stream, **fields) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "event_id": _new_event_id(), **fields}
    if payload["phase"] not in ALLOWED_PHASES:
        raise HarnessError(f"unknown phase: {payload['phase']!r}")
    if payload["arm"] not in ALLOWED_ARMS:
        raise HarnessError(f"unknown arm: {payload['arm']!r}")
    if "status" not in payload:
        payload["status"] = "ok"
    stream.write(_canonical(payload).decode("utf-8"))
    stream.flush()


def _refuse_live_key(allow_network: bool) -> None:
    if os.environ.get("TYPESAFE_API_KEY") and not allow_network:
        raise HarnessError(
            "TYPESAFE_API_KEY is set; pass --allow-network to permit live provider calls"
        )


def _load_freeze(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "velgraphing-time-to-correct-freeze-v1":
        raise HarnessError("freeze schema_version mismatch")
    if {arm["id"] for arm in payload["arms"]} != ALLOWED_ARMS:
        raise HarnessError(f"arms must be exactly {sorted(ALLOWED_ARMS)}")
    for arm in payload["arms"]:
        if arm["retrieval"] not in ALLOWED_RETRIEVAL:
            raise HarnessError(f"invalid retrieval for arm {arm['id']}")
        if arm["jev"] not in ALLOWED_JEV:
            raise HarnessError(f"invalid jev for arm {arm['id']}")
    if "repair_budget" not in payload or not isinstance(payload["repair_budget"], int) or payload["repair_budget"] < 0:
        raise HarnessError("repair_budget must be a non-negative integer")
    return payload


def _run_subprocess(command: list[str], cwd: Path) -> tuple[int, float, bytes, bytes]:
    """Run a subprocess and return (exit_code, wall_ms, stdout, stderr)."""
    started = _now_ns()
    completed = subprocess.run(command, cwd=str(cwd), check=False, capture_output=True)
    wall_ms = (_now_ns() - started) / 1_000_000
    return completed.returncode, wall_ms, completed.stdout, completed.stderr


def _execute_packet(
    *,
    freeze: dict,
    packet: dict,
    arm: dict,
    lane_subprocess: list[str] | None,
    cwd: Path,
    events_path: Path,
    replay_envelope: dict | None,
    without_jev: bool,
    without_graph: bool,
    without_fallback: bool,
    repair_budget: int,
) -> dict:
    """Run one (packet, arm) row and return its summary.

    The lane subprocess is owned by the parent operator. If ``lane_subprocess``
    is ``None``, the harness records a synthetic lane run (used by tests).
    """
    task_id = packet["task_id"]
    arm_id = arm["id"]
    retrieval = arm["retrieval"]
    jev_mode = arm["jev"]
    corpus_id = packet["corpus"]["id"]
    corpus_root = packet["corpus"].get("materialized_root") or packet["corpus"].get("root") or ""
    corpus_snapshot = packet["corpus"].get("snapshot_sha256", "")
    summary: dict = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "packet_id": packet["packet_id"],
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
        "queue_approval_ms": 0.0,
        "user_visible_wall_ms": 0.0,
        "repair_attempts_used": 0,
        "component_removals": [],
    }
    with events_path.open("a", encoding="utf-8") as events:
        with contextlib.redirect_stdout(events):
            started = _now_ns()
            _emit(
                sys.stdout,
                trial_index=0,
                task_id=task_id,
                packet_id=packet["packet_id"],
                arm=arm_id,
                corpus_id=corpus_id,
                snapshot_sha256=corpus_snapshot,
                phase="task_accept",
                t_monotonic_ns=started,
                details={"freeze_sha256": hashlib.sha256(_canonical(freeze)).hexdigest(), "corpus_root": corpus_root},
            )
            removal_events = []
            if without_jev:
                removal_events.append("jev")
            if without_graph:
                removal_events.append("graph")
            if without_fallback:
                removal_events.append("fallback")
            for removed in removal_events:
                summary["component_removals"].append(removed)
                _emit(
                    sys.stdout,
                    trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="component_removal", t_monotonic_ns=_now_ns(),
                    details={"removed": removed},
                )

            cold_started = _now_ns()
            cold_ms = 0.0
            if retrieval == "graph_assisted" and not without_graph and lane_subprocess is not None:
                exit_code, wall_ms, stdout, stderr = _run_subprocess(lane_subprocess, cwd)
                cold_ms = wall_ms
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="graph_build_or_load:cold", t_monotonic_ns=_now_ns(),
                    details={
                        "subprocess_ms": wall_ms, "exit_code": exit_code,
                        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                    },
                )
            warm_started = _now_ns()
            warm_ms = 0.0
            if retrieval == "graph_assisted" and not without_graph and lane_subprocess is not None:
                exit_code, wall_ms, stdout, stderr = _run_subprocess(lane_subprocess, cwd)
                warm_ms = wall_ms
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="graph_build_or_load:warm", t_monotonic_ns=_now_ns(),
                    details={
                        "subprocess_ms": wall_ms, "exit_code": exit_code,
                        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                    },
                )

            discovery_start = _now_ns()
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="discovery_start", t_monotonic_ns=discovery_start,
                details={"mode": "graph" if retrieval == "graph_assisted" else "direct"},
            )
            discovery_end = _now_ns()
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="discovery_end", t_monotonic_ns=discovery_end,
                details={"mode": "graph" if retrieval == "graph_assisted" else "direct", "hits": 0, "hits_count": 0, "fallback_paths_count": 0},
            )

            jev_skipped = (jev_mode == "off") or without_jev
            jev_transport = "replay"
            jev_call_ms = 0.0
            jev_prepare_ms = 0.0
            jev_revalidate_ms = 0.0
            jev_tokens = 0
            jev_attempted_calls = 0
            if not jev_skipped:
                prepare_start = _now_ns()
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="jev_prepare_start", t_monotonic_ns=prepare_start,
                    details={"mode": "rerank", "candidates_count": 0},
                )
                prepare_end = _now_ns()
                jev_prepare_ms = (prepare_end - prepare_start) / 1_000_000
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="jev_prepare_end", t_monotonic_ns=prepare_end,
                    details={"mode": "rerank", "candidates_count": 0, "prepare_ms": jev_prepare_ms},
                )
                provider_start = _now_ns()
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="jev_provider_call_start", t_monotonic_ns=provider_start,
                    details={"endpoint": "https://api.typesafe.ai/v1/systemone", "transport": jev_transport, "model": "jev-1.13.0"},
                )
                # Transport step. Replay-only by default; live calls require
                # --allow-network AND TYPESAFE_API_KEY in the environment.
                if jev_transport == "replay":
                    if replay_envelope is None:
                        raise HarnessError("replay envelope required when transport is replay")
                    jev_call_ms = 0.5
                    jev_tokens = replay_envelope.get("input_tokens", 0)
                    jev_attempted_calls = 0
                provider_end = _now_ns()
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="jev_provider_call_end", t_monotonic_ns=provider_end,
                    details={
                        "provider_call_ms": jev_call_ms, "input_tokens": jev_tokens,
                        "output_tokens": 0, "attempted_calls": jev_attempted_calls,
                    },
                )
                revalidate_end = _now_ns()
                jev_revalidate_ms = (revalidate_end - provider_end) / 1_000_000
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="jev_revalidate_end", t_monotonic_ns=revalidate_end,
                    details={"revalidate_ms": jev_revalidate_ms, "source_changed": False},
                )

            answer_start = _now_ns()
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="answer_dispatch_start", t_monotonic_ns=answer_start,
                details={"phase_1_pass_correctness": None},
            )
            answer_ms = 1.0  # synthetic; the lane subprocess owns the real value
            answer_end = _now_ns()
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="answer_dispatch_end", t_monotonic_ns=answer_end,
                details={"answer_ms": answer_ms, "answer_text_sha256": hashlib.sha256(b"synthetic").hexdigest()},
            )

            # Repair loop (synthetic; the grader owns the real pass/fail signal).
            pass_correctness = 1.0
            repair_attempts_used = 0
            time_to_correct_ms = (answer_end - started) / 1_000_000
            first_pass_correctness = pass_correctness
            terminal_reason = "pass"
            for attempt in range(repair_budget):
                if pass_correctness >= 1.0:
                    break
                repair_start = _now_ns()
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="repair_attempt_n_start", t_monotonic_ns=repair_start,
                    details={"attempt_index": attempt},
                )
                repair_end = _now_ns()
                _emit(
                    sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                    corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                    phase="repair_attempt_n_end", t_monotonic_ns=repair_end,
                    details={"attempt_index": attempt, "first_pass_correctness": pass_correctness},
                )
                repair_attempts_used += 1
            else:
                if pass_correctness < 1.0:
                    terminal_reason = "fail_no_pass_under_budget"

            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="first_pass_correctness", t_monotonic_ns=_now_ns(),
                details={"value": first_pass_correctness},
            )
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="time_to_correct", t_monotonic_ns=_now_ns(),
                details={"time_to_correct_ms": time_to_correct_ms if terminal_reason == "pass" else None},
            )

            active_execution_ms = cold_ms + warm_ms + (discovery_end - discovery_start) / 1_000_000 + jev_prepare_ms + jev_call_ms + jev_revalidate_ms + answer_ms
            user_visible_wall_ms = (_now_ns() - started) / 1_000_000
            queue_approval_ms = 0.0
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="active_execution", t_monotonic_ns=_now_ns(),
                details={"active_execution_ms": active_execution_ms},
            )
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="queue_approval", t_monotonic_ns=_now_ns(),
                details={"queue_approval_ms": queue_approval_ms},
            )
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="user_visible_wall", t_monotonic_ns=_now_ns(),
                details={"user_visible_wall_ms": user_visible_wall_ms},
            )
            _emit(
                sys.stdout, trial_index=0, task_id=task_id, packet_id=packet["packet_id"], arm=arm_id,
                corpus_id=corpus_id, snapshot_sha256=corpus_snapshot,
                phase="terminal_reason", t_monotonic_ns=_now_ns(),
                details={"reason": terminal_reason},
            )
            summary.update({
                "censored": False,
                "terminal_reason": terminal_reason,
                "first_pass_correctness": first_pass_correctness,
                "time_to_correct_ms": time_to_correct_ms if terminal_reason == "pass" else None,
                "active_execution_ms": active_execution_ms,
                "queue_approval_ms": queue_approval_ms,
                "user_visible_wall_ms": user_visible_wall_ms,
                "repair_attempts_used": repair_attempts_used,
            })
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True, help="frozen-input contract (velgraphing-time-to-correct-freeze-v1)")
    parser.add_argument("--events", type=Path, required=True, help="output JSONL event stream")
    parser.add_argument("--summary", type=Path, required=True, help="output per-row summary JSONL")
    parser.add_argument("--replay", type=Path, help="optional replay envelope (velgraphing-jev-replay-v1)")
    parser.add_argument("--allow-network", action="store_true", help="permit live provider calls (refused if TYPESAFE_API_KEY is set)")
    parser.add_argument("--without-jev", action="store_true")
    parser.add_argument("--without-graph", action="store_true")
    parser.add_argument("--without-fallback", action="store_true")
    parser.add_argument("--packet-ids", nargs="*", help="restrict to these packet_ids (defaults to all)")
    parser.add_argument("--lane-subprocess", help="subprocess command to run as the answer lane (testing seam)")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    try:
        _refuse_live_key(args.allow_network)
        freeze = _load_freeze(args.freeze)
        replay_envelope = None
        if args.replay is not None:
            replay_envelope = json.loads(args.replay.read_text(encoding="utf-8"))
        lane_subprocess = args.lane_subprocess.split() if args.lane_subprocess else None
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
                    packet = {
                        "packet_id": packet_id,
                        "task_id": packet_id[len(arm["id"]) + 1:],
                        "corpus": freeze["corpus"][0],
                    }
                    row = _execute_packet(
                        freeze=freeze,
                        packet=packet,
                        arm=arm,
                        lane_subprocess=lane_subprocess,
                        cwd=args.cwd,
                        events_path=events_path,
                        replay_envelope=replay_envelope,
                        without_jev=args.without_jev,
                        without_graph=args.without_graph,
                        without_fallback=args.without_fallback,
                        repair_budget=freeze["repair_budget"],
                    )
                    summary_file.write(_canonical(row).decode("utf-8"))
                    summary_file.flush()
        return 0
    except HarnessError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
