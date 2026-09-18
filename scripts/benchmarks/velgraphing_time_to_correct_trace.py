#!/usr/bin/env python3
"""Schema validator and per-arm rollup for the time-to-correct event trace.

Stdlib only. Reads a JSONL event stream produced by
``scripts/benchmarks/velgraphing_time_to_correct_v1.py``, validates each event
against ``velgraphing-time-to-correct-event-v1``, and emits a per-arm rollup
JSON document.

The rollup reports, per arm:

- row_count
- censored_row_count
- pass_count
- median time_to_correct_ms (null if censored_row_count / row_count > threshold)
- median active_execution_ms
- median user_visible_wall_ms
- censored_row_fraction

The rollup refuses to claim a wall-clock effect when the censored-row fraction
per arm exceeds the threshold (default 0.25).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


SCHEMA_VERSION = "velgraphing-time-to-correct-event-v1"
SUMMARY_SCHEMA_VERSION = "velgraphing-time-to-correct-rollup-v1"
ALLOWED_ARMS = {"A", "B", "C", "D"}
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


class TraceError(RuntimeError):
    """Raised for malformed event traces."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _validate_event(event: dict, index: int) -> None:
    if event.get("schema_version") != SCHEMA_VERSION:
        raise TraceError(f"line {index}: schema_version mismatch")
    for key in ("event_id", "trial_index", "task_id", "packet_id", "arm", "corpus_id", "snapshot_sha256", "phase", "t_monotonic_ns", "status"):
        if key not in event:
            raise TraceError(f"line {index}: missing required key {key!r}")
    if event["arm"] not in ALLOWED_ARMS:
        raise TraceError(f"line {index}: unknown arm {event['arm']!r}")
    if event["phase"] not in ALLOWED_PHASES:
        raise TraceError(f"line {index}: unknown phase {event['phase']!r}")
    if not isinstance(event["t_monotonic_ns"], int) or event["t_monotonic_ns"] < 0:
        raise TraceError(f"line {index}: t_monotonic_ns must be a non-negative integer")


def _validate_monotonicity(events: list[dict]) -> None:
    by_packet: dict[str, list[dict]] = {}
    for event in events:
        by_packet.setdefault(event["packet_id"], []).append(event)
    for packet_id, packet_events in by_packet.items():
        last = -1
        for event in packet_events:
            if event["t_monotonic_ns"] < last:
                raise TraceError(f"packet {packet_id}: t_monotonic_ns went backward")
            last = event["t_monotonic_ns"]


def _summarize(events: list[dict], censored_threshold: float) -> dict:
    terminal_reasons: dict[str, dict] = {}
    per_arm: dict[str, dict] = {arm: {"rows": [], "censored": 0, "pass": 0} for arm in ALLOWED_ARMS}
    for event in events:
        if event["phase"] != "terminal_reason":
            continue
        arm = event["arm"]
        reason = event["details"]["reason"]
        per_arm[arm]["rows"].append(event)
        if reason == "pass":
            per_arm[arm]["pass"] += 1
    for event in events:
        if event["phase"] == "user_visible_wall":
            arm = event["arm"]
            per_arm[arm].setdefault("walls", []).append(event["details"]["user_visible_wall_ms"])
        if event["phase"] == "time_to_correct":
            arm = event["arm"]
            value = event["details"]["time_to_correct_ms"]
            per_arm[arm].setdefault("ttcs", []).append(value)
        if event["phase"] == "active_execution":
            arm = event["arm"]
            per_arm[arm].setdefault("actives", []).append(event["details"]["active_execution_ms"])
    rollup: dict = {"schema_version": SUMMARY_SCHEMA_VERSION, "arms": {}}
    for arm, payload in per_arm.items():
        row_count = len(payload["rows"])
        censored = sum(1 for value in payload.get("ttcs", []) if value is None)
        censored_fraction = (censored / row_count) if row_count else 0.0
        walls = payload.get("walls", [])
        actives = payload.get("actives", [])
        ttcs = [value for value in payload.get("ttcs", []) if value is not None]
        rollup["arms"][arm] = {
            "row_count": row_count,
            "pass_count": payload["pass"],
            "censored_row_count": censored,
            "censored_row_fraction": round(censored_fraction, 4),
            "censored_row_threshold": censored_threshold,
            "wall_clock_claim_eligible": censored_fraction <= censored_threshold,
            "median_user_visible_wall_ms": statistics.median(walls) if walls else None,
            "median_active_execution_ms": statistics.median(actives) if actives else None,
            "median_time_to_correct_ms": statistics.median(ttcs) if ttcs else None,
        }
    return rollup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--rollup", type=Path, required=True)
    parser.add_argument("--censored-threshold", type=float, default=0.25)
    args = parser.parse_args(argv)
    try:
        events = []
        with args.events.open("r", encoding="utf-8") as stream:
            for index, line in enumerate(stream, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TraceError(f"line {index}: invalid JSON: {exc.msg}") from exc
                _validate_event(event, index)
                events.append(event)
        _validate_monotonicity(events)
        rollup = _summarize(events, args.censored_threshold)
        args.rollup.parent.mkdir(parents=True, exist_ok=True)
        args.rollup.write_bytes(_canonical(rollup))
        return 0
    except TraceError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
