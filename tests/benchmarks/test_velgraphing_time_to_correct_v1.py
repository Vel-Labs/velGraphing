"""Tests for the VelGraphing time-to-correct harness. Zero provider calls.

Validates:
- Monotonic event emission per row.
- Censored-row retention.
- Component-removal events.
- Jev replay path with no key read.
- Refusal when TYPESAFE_API_KEY is set without --allow-network.
- Schema validator rejects malformed events and accepts well-formed ones.
- Per-arm rollup reports censored-row fraction and pass count.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "benchmarks" / "velgraphing_time_to_correct_v1.py"
TRACE = ROOT / "scripts" / "benchmarks" / "velgraphing_time_to_correct_trace.py"
FREEZE = ROOT / "benchmarks" / "velgraphing-time-to-correct-v1" / "freeze.example.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _load("velgraphing_time_to_correct_v1", HARNESS)
trace = _load("velgraphing_time_to_correct_trace", TRACE)


def _replay_envelope(tmp: Path) -> Path:
    replay = {"schema_version": "velgraphing-jev-replay-v1", "request_sha256": "0" * 64, "response": {}}
    replay_path = tmp / "replay.json"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    return replay_path


def _freeze_for_tests(tmp: Path) -> Path:
    payload = json.loads(FREEZE.read_text(encoding="utf-8"))
    payload["corpus"][0]["id"] = "tiny"
    payload["corpus"][0]["materialized_root"] = str(tmp / "corpus")
    payload["corpus"][0]["snapshot_sha256"] = "0" * 64
    payload["dispatch"] = {"seed": 20260917, "order": ["A-t-01", "B-t-01", "C-t-01", "D-t-01"]}
    payload["repair_budget"] = 2
    payload["censored_row_threshold"] = 0.25
    freeze_path = tmp / "freeze.json"
    freeze_path.write_text(json.dumps(payload), encoding="utf-8")
    return freeze_path


def _packet_for(arm_id: str, task_id: str, freeze: dict | None = None) -> dict:
    corpus = (freeze["corpus"][0] if freeze is not None else {"id": "tiny", "root": "/corpus", "snapshot_sha256": "0" * 64})
    return {"packet_id": f"{arm_id}-{task_id}", "task_id": task_id, "corpus": corpus}


class HarnessTests(unittest.TestCase):
    def test_emit_emits_allowed_phase(self):
        buf = io.StringIO()
        harness._emit(
            buf,
            trial_index=0, task_id="t-01", packet_id="A-t-01", arm="A",
            corpus_id="tiny", snapshot_sha256="0" * 64,
            phase="task_accept", t_monotonic_ns=harness._now_ns(),
            details={"x": 1},
        )
        event = json.loads(buf.getvalue().strip())
        self.assertEqual(event["phase"], "task_accept")
        self.assertEqual(event["arm"], "A")

    def test_emit_rejects_unknown_phase(self):
        buf = io.StringIO()
        with self.assertRaises(harness.HarnessError):
            harness._emit(
                buf,
                trial_index=0, task_id="t-01", packet_id="A-t-01", arm="A",
                corpus_id="tiny", snapshot_sha256="0" * 64,
                phase="bogus", t_monotonic_ns=harness._now_ns(),
            )

    def test_refuses_live_key_without_allow_network(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
            with self.assertRaises(harness.HarnessError):
                harness._refuse_live_key(False)

    def test_allows_live_key_with_allow_network(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
            harness._refuse_live_key(True)

    def test_load_freeze_validates_schema_and_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            freeze = harness._load_freeze(freeze_path)
            self.assertEqual({arm["id"] for arm in freeze["arms"]}, {"A", "B", "C", "D"})
            with self.assertRaises(harness.HarnessError):
                bad = json.loads(freeze_path.read_text(encoding="utf-8"))
                bad["schema_version"] = "wrong"
                (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
                harness._load_freeze(tmp_path / "bad.json")

    def test_execute_packet_emits_monotonic_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            freeze = harness._load_freeze(freeze_path)
            events_path = tmp_path / "events.jsonl"
            replay = {"schema_version": "velgraphing-jev-replay-v1", "request_sha256": "0" * 64, "response": {}}
            summary = harness._execute_packet(
                freeze=freeze,
                packet=_packet_for("B", "t-01"),
                arm=freeze["arms"][1],
                lane_subprocess=None,
                cwd=tmp_path,
                events_path=events_path,
                replay_envelope=replay,
                without_jev=False, without_graph=False, without_fallback=False,
                repair_budget=freeze["repair_budget"],
            )
            self.assertEqual(summary["arm"], "B")
            self.assertEqual(summary["terminal_reason"], "pass")
            self.assertEqual(summary["censored"], False)
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertGreater(len(events), 5)
            last = -1
            for event in events:
                self.assertGreaterEqual(event["t_monotonic_ns"], last)
                last = event["t_monotonic_ns"]

    def test_jev_off_arm_has_no_provider_call_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            freeze = harness._load_freeze(freeze_path)
            events_path = tmp_path / "events.jsonl"
            summary = harness._execute_packet(
                freeze=freeze,
                packet=_packet_for("A", "t-01"),
                arm=freeze["arms"][0],
                lane_subprocess=None,
                cwd=tmp_path,
                events_path=events_path,
                replay_envelope=None,
                without_jev=False, without_graph=False, without_fallback=False,
                repair_budget=freeze["repair_budget"],
            )
            self.assertEqual(summary["arm"], "A")
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            phases = {event["phase"] for event in events}
            self.assertNotIn("jev_provider_call_start", phases)
            self.assertNotIn("jev_provider_call_end", phases)

    def test_jev_on_arm_has_provider_call_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            freeze = harness._load_freeze(freeze_path)
            events_path = tmp_path / "events.jsonl"
            replay = {"schema_version": "velgraphing-jev-replay-v1", "request_sha256": "0" * 64, "response": {}}
            harness._execute_packet(
                freeze=freeze,
                packet=_packet_for("D", "t-01"),
                arm=freeze["arms"][3],
                lane_subprocess=None,
                cwd=tmp_path,
                events_path=events_path,
                replay_envelope=replay,
                without_jev=False, without_graph=False, without_fallback=False,
                repair_budget=freeze["repair_budget"],
            )
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            phases = {event["phase"] for event in events}
            self.assertIn("jev_provider_call_start", phases)
            self.assertIn("jev_provider_call_end", phases)

    def test_component_removal_emits_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            freeze = harness._load_freeze(freeze_path)
            events_path = tmp_path / "events.jsonl"
            replay = {"schema_version": "velgraphing-jev-replay-v1", "request_sha256": "0" * 64, "response": {}}
            summary = harness._execute_packet(
                freeze=freeze,
                packet=_packet_for("B", "t-01"),
                arm=freeze["arms"][1],
                lane_subprocess=None,
                cwd=tmp_path,
                events_path=events_path,
                replay_envelope=replay,
                without_jev=True, without_graph=False, without_fallback=False,
                repair_budget=freeze["repair_budget"],
            )
            self.assertIn("jev", summary["component_removals"])
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            removal_events = [event for event in events if event["phase"] == "component_removal"]
            self.assertEqual(len(removal_events), 1)
            self.assertEqual(removal_events[0]["details"]["removed"], "jev")

    def test_harness_refuses_live_key_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
                result = harness.main([
                    "--freeze", str(freeze_path),
                    "--events", str(tmp_path / "events.jsonl"),
                    "--summary", str(tmp_path / "summary.jsonl"),
                    "--packet-ids", "B-t-01",
                ])
            self.assertEqual(result, 2)

    def test_harness_runs_all_four_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            replay_path = _replay_envelope(tmp_path)
            result = harness.main([
                "--freeze", str(freeze_path),
                "--events", str(tmp_path / "events.jsonl"),
                "--summary", str(tmp_path / "summary.jsonl"),
                "--replay", str(replay_path),
            ])
            self.assertEqual(result, 0)
            summary = [json.loads(line) for line in (tmp_path / "summary.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual({row["arm"] for row in summary}, {"A", "B", "C", "D"})
            self.assertEqual(len(summary), 4)


class TraceTests(unittest.TestCase):
    def test_validate_event_accepts_well_formed(self):
        trace._validate_event(
            {"schema_version": trace.SCHEMA_VERSION, "event_id": "x", "trial_index": 0,
             "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
             "snapshot_sha256": "0" * 64, "phase": "task_accept",
             "t_monotonic_ns": 1, "status": "ok", "details": {}},
            index=1,
        )

    def test_validate_event_rejects_unknown_phase(self):
        with self.assertRaises(trace.TraceError):
            trace._validate_event(
                {"schema_version": trace.SCHEMA_VERSION, "event_id": "x", "trial_index": 0,
                 "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
                 "snapshot_sha256": "0" * 64, "phase": "bogus",
                 "t_monotonic_ns": 1, "status": "ok", "details": {}},
                index=1,
            )

    def test_validate_event_rejects_unknown_arm(self):
        with self.assertRaises(trace.TraceError):
            trace._validate_event(
                {"schema_version": trace.SCHEMA_VERSION, "event_id": "x", "trial_index": 0,
                 "task_id": "t-01", "packet_id": "Z-t-01", "arm": "Z", "corpus_id": "tiny",
                 "snapshot_sha256": "0" * 64, "phase": "task_accept",
                 "t_monotonic_ns": 1, "status": "ok", "details": {}},
                index=1,
            )

    def test_validate_event_rejects_bad_schema(self):
        with self.assertRaises(trace.TraceError):
            trace._validate_event(
                {"schema_version": "wrong", "event_id": "x", "trial_index": 0,
                 "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
                 "snapshot_sha256": "0" * 64, "phase": "task_accept",
                 "t_monotonic_ns": 1, "status": "ok", "details": {}},
                index=1,
            )

    def test_validate_monotonicity_rejects_backward_clock(self):
        events = [
            {"schema_version": trace.SCHEMA_VERSION, "event_id": "x", "trial_index": 0,
             "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
             "snapshot_sha256": "0" * 64, "phase": "task_accept",
             "t_monotonic_ns": 2, "status": "ok", "details": {}},
            {"schema_version": trace.SCHEMA_VERSION, "event_id": "y", "trial_index": 0,
             "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
             "snapshot_sha256": "0" * 64, "phase": "discovery_start",
             "t_monotonic_ns": 1, "status": "ok", "details": {}},
        ]
        with self.assertRaises(trace.TraceError):
            trace._validate_monotonicity(events)

    def test_rollup_reports_censored_fraction(self):
        events = [
            {"schema_version": trace.SCHEMA_VERSION, "event_id": "x", "trial_index": 0,
             "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
             "snapshot_sha256": "0" * 64, "phase": "terminal_reason",
             "t_monotonic_ns": 1, "status": "ok", "details": {"reason": "pass"}},
            {"schema_version": trace.SCHEMA_VERSION, "event_id": "y", "trial_index": 0,
             "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
             "snapshot_sha256": "0" * 64, "phase": "user_visible_wall",
             "t_monotonic_ns": 2, "status": "ok", "details": {"user_visible_wall_ms": 100.0}},
            {"schema_version": trace.SCHEMA_VERSION, "event_id": "z", "trial_index": 0,
             "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
             "snapshot_sha256": "0" * 64, "phase": "time_to_correct",
             "t_monotonic_ns": 3, "status": "ok", "details": {"time_to_correct_ms": None}},
            {"schema_version": trace.SCHEMA_VERSION, "event_id": "w", "trial_index": 0,
             "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny",
             "snapshot_sha256": "0" * 64, "phase": "active_execution",
             "t_monotonic_ns": 4, "status": "ok", "details": {"active_execution_ms": 50.0}},
        ]
        rollup = trace._summarize(events, 0.25)
        arm_a = rollup["arms"]["A"]
        self.assertEqual(arm_a["row_count"], 1)
        self.assertEqual(arm_a["censored_row_count"], 1)
        self.assertEqual(arm_a["censored_row_fraction"], 1.0)
        self.assertFalse(arm_a["wall_clock_claim_eligible"])

    def test_trace_cli_rejects_malformed_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            events_path = tmp_path / "events.jsonl"
            events_path.write_text('not json\n', encoding="utf-8")
            rollup_path = tmp_path / "rollup.json"
            result = trace.main(["--events", str(events_path), "--rollup", str(rollup_path)])
            self.assertEqual(result, 2)


class EndToEndTests(unittest.TestCase):
    def test_full_pipeline_produces_rollup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            freeze_path = _freeze_for_tests(tmp_path)
            replay_path = _replay_envelope(tmp_path)
            events_path = tmp_path / "events.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            rollup_path = tmp_path / "rollup.json"
            harness.main([
                "--freeze", str(freeze_path),
                "--events", str(events_path),
                "--summary", str(summary_path),
                "--replay", str(replay_path),
            ])
            result = trace.main([
                "--events", str(events_path),
                "--rollup", str(rollup_path),
            ])
            self.assertEqual(result, 0)
            rollup = json.loads(rollup_path.read_text(encoding="utf-8"))
            self.assertEqual(set(rollup["arms"].keys()), {"A", "B", "C", "D"})
            for arm, payload in rollup["arms"].items():
                self.assertEqual(payload["row_count"], 1)
                self.assertEqual(payload["censored_row_count"], 0)
                self.assertTrue(payload["wall_clock_claim_eligible"])


if __name__ == "__main__":
    unittest.main()
