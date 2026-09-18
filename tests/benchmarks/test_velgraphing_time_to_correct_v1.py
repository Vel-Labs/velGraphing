"""Focused offline tests for the real time-to-correct seams."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts/benchmarks/velgraphing_time_to_correct_v1.py"
TRACE = ROOT / "scripts/benchmarks/velgraphing_time_to_correct_trace.py"
FREEZE = ROOT / "benchmarks/velgraphing-time-to-correct-v1/freeze.example.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _load("velgraphing_time_to_correct_v1", HARNESS)
trace = _load("velgraphing_time_to_correct_trace", TRACE)


def _write_lanes(tmp: Path, *, passing: bool = True) -> tuple[list[str], list[str], Path, Path]:
    answer_marker = tmp / "answer.marker"
    grade_marker = tmp / "grade.marker"
    answer = tmp / "answer.py"
    grader = tmp / "grader.py"
    answer.write_text(
        "import json, pathlib, sys\n"
        "payload = json.load(sys.stdin)\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(payload), encoding='utf-8')\n"
        "print(json.dumps({'answer_text': 'observed answer', 'source_pointers': []}))\n",
        encoding="utf-8",
    )
    grade = {
        "required_fact_score": 1 if passing else 0,
        "required_fact_max": 1,
        "required_fact_recall": 1.0 if passing else 0.0,
        "critical_facts_exact": passing,
        "unsupported_material_claims": 0,
        "critical_errors": 0 if passing else 1,
        "source_support": 1.0 if passing else 0.0,
    }
    grader.write_text(
        "import json, pathlib, sys\n"
        "payload = json.load(sys.stdin)\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(payload), encoding='utf-8')\n"
        f"print(json.dumps({grade!r}))\n",
        encoding="utf-8",
    )
    return [sys.executable, str(answer), str(answer_marker)], [sys.executable, str(grader), str(grade_marker)], answer_marker, grade_marker


def _corpus_and_replay(tmp: Path) -> tuple[dict, dict]:
    root = tmp / "corpus"
    root.mkdir()
    (root / "a.py").write_text("# background\nx = 1\n", encoding="utf-8")
    (root / "b.py").write_text("def cancel():\n    return 'cancelled'\n", encoding="utf-8")
    (root / "c.py").write_text("assert cancel() == 'cancelled'\n", encoding="utf-8")
    packet = harness.canonical_jev.capture(root, "Find cancellation and its test", ["a.py:1:2", "b.py:1:2", "c.py:1:1"])
    prepared = harness.canonical_jev.prepare(packet, root)
    legend = {str(i): criterion for i, criterion in enumerate(harness.canonical_jev._rubric_criteria())}
    response = {
        "model": harness.canonical_jev.DEFAULT_MODEL,
        "answers": {
            f"candidate_{i}": {
                "type": "score", "score": level,
                "probabilities": {str(j): float(j == level) for j in range(3)},
                "legend": legend, "confidence": 1.0,
            }
            for i, level in enumerate((0, 2, 1))
        },
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }
    replay = {
        "schema_version": "velgraphing-jev-replay-v1",
        "request_sha256": prepared["request_sha256"],
        "response": response,
    }
    return {"root": root, "packet": packet}, replay


def _freeze(tmp: Path, answer_command: list[str] | None, grader_command: list[str] | None, *, repair_budget: int = 0) -> tuple[dict, dict]:
    corpus, replay = _corpus_and_replay(tmp)
    payload = json.loads(FREEZE.read_text(encoding="utf-8"))
    payload["corpus"][0].update({"id": "tiny", "materialized_root": str(corpus["root"]), "snapshot_sha256": "0" * 64})
    payload["dispatch"] = {"seed": 20260917, "order": ["A-t-01", "B-t-01", "C-t-01", "D-t-01"]}
    payload["repair_budget"] = repair_budget
    payload["answer_lane_boundary"]["answer_command"] = answer_command
    payload["grader"] = {"command": grader_command}
    payload["timeouts"] = {"answer_s": 10, "grader_s": 10}
    packets = {}
    for arm in "ABCD":
        packet = dict(corpus["packet"])
        packet.update({"packet_id": f"{arm}-t-01", "task_id": "t-01", "question": "Find cancellation and its test", "corpus": payload["corpus"][0], "jev_packet": corpus["packet"]})
        packets[packet["packet_id"]] = packet
    payload["packets"] = packets
    return payload, replay


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class HarnessTests(unittest.TestCase):
    def test_canonical_replay_and_frozen_subprocesses_run(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            answer_cmd, grader_cmd, answer_marker, grade_marker = _write_lanes(tmp)
            freeze, replay = _freeze(tmp, answer_cmd, grader_cmd)
            events_path = tmp / "events.jsonl"
            summary = harness._execute_packet(
                freeze=freeze, packet=freeze["packets"]["B-t-01"], arm=freeze["arms"][1], cwd=tmp,
                events_path=events_path, replay_envelope=replay, without_jev=False,
                without_graph=False, without_fallback=False, repair_budget=0,
            )
            self.assertTrue(answer_marker.exists())
            self.assertTrue(grade_marker.exists())
            self.assertEqual(summary["terminal_reason"], "pass")
            self.assertEqual(summary["answer_attempts"], 1)
            self.assertEqual(summary["grade_attempts"], 1)
            self.assertIsNotNone(summary["time_to_correct_ms"])
            phases = [event["phase"] for event in _events(events_path)]
            for phase in ("jev_provider_call_start", "jev_provider_call_end", "answer_dispatch_start", "answer_dispatch_end", "grade_start", "grade_end", "time_to_correct"):
                self.assertIn(phase, phases)
            self.assertNotIn("synthetic", events_path.read_text(encoding="utf-8").lower())

    def test_missing_answer_lane_is_censored_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _, grader_cmd, _, _ = _write_lanes(tmp)
            freeze, replay = _freeze(tmp, None, grader_cmd)
            events_path = tmp / "events.jsonl"
            summary = harness._execute_packet(
                freeze=freeze, packet=freeze["packets"]["B-t-01"], arm=freeze["arms"][1], cwd=tmp,
                events_path=events_path, replay_envelope=replay, without_jev=False,
                without_graph=False, without_fallback=False, repair_budget=0,
            )
            self.assertEqual(summary["terminal_reason"], "answer_lane_unavailable")
            self.assertTrue(summary["censored"])
            self.assertNotIn("answer_dispatch_start", {event["phase"] for event in _events(events_path)})

    def test_failed_grade_is_retained_without_synthetic_pass(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            answer_cmd, grader_cmd, answer_marker, grade_marker = _write_lanes(tmp, passing=False)
            freeze, replay = _freeze(tmp, answer_cmd, grader_cmd)
            events_path = tmp / "events.jsonl"
            summary = harness._execute_packet(
                freeze=freeze, packet=freeze["packets"]["B-t-01"], arm=freeze["arms"][1], cwd=tmp,
                events_path=events_path, replay_envelope=replay, without_jev=False,
                without_graph=False, without_fallback=False, repair_budget=0,
            )
            self.assertTrue(answer_marker.exists())
            self.assertTrue(grade_marker.exists())
            self.assertEqual(summary["terminal_reason"], "fail_no_pass_under_budget")
            self.assertFalse(summary["censored"])
            self.assertFalse(summary["first_pass_correctness"])
            self.assertIsNone(summary["time_to_correct_ms"])
            phases = {event["phase"] for event in _events(events_path)}
            self.assertIn("grade_start", phases)
            self.assertIn("grade_end", phases)
            self.assertNotIn("time_to_correct", phases)

    def test_replay_mismatch_blocks_answer(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            answer_cmd, grader_cmd, answer_marker, _ = _write_lanes(tmp)
            freeze, replay = _freeze(tmp, answer_cmd, grader_cmd)
            replay["request_sha256"] = "0" * 64
            events_path = tmp / "events.jsonl"
            summary = harness._execute_packet(
                freeze=freeze, packet=freeze["packets"]["B-t-01"], arm=freeze["arms"][1], cwd=tmp,
                events_path=events_path, replay_envelope=replay, without_jev=False,
                without_graph=False, without_fallback=False, repair_budget=0,
            )
            self.assertEqual(summary["terminal_reason"], "jev_error:replay_request_mismatch")
            self.assertTrue(summary["censored"])
            self.assertFalse(answer_marker.exists())

    def test_component_removal_is_recorded(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            answer_cmd, grader_cmd, _, _ = _write_lanes(tmp)
            freeze, _ = _freeze(tmp, answer_cmd, grader_cmd)
            events_path = tmp / "events.jsonl"
            summary = harness._execute_packet(
                freeze=freeze, packet=freeze["packets"]["A-t-01"], arm=freeze["arms"][0], cwd=tmp,
                events_path=events_path, replay_envelope=None, without_jev=False,
                without_graph=True, without_fallback=False, repair_budget=0,
            )
            self.assertEqual(summary["terminal_reason"], "pass")
            self.assertEqual(summary["component_removals"], ["graph"])

    def test_main_runs_four_arms_with_observed_boundaries(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            answer_cmd, grader_cmd, _, _ = _write_lanes(tmp)
            freeze, replay = _freeze(tmp, answer_cmd, grader_cmd)
            freeze_path = tmp / "freeze.json"
            replay_path = tmp / "replay.json"
            freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
            replay_path.write_text(json.dumps(replay), encoding="utf-8")
            self.assertEqual(harness.main(["--freeze", str(freeze_path), "--events", str(tmp / "events.jsonl"), "--summary", str(tmp / "summary.jsonl"), "--replay", str(replay_path)]), 0)
            rows = [json.loads(line) for line in (tmp / "summary.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["arm"] for row in rows}, {"A", "B", "C", "D"})
            self.assertTrue(all(row["terminal_reason"] == "pass" for row in rows))
            self.assertEqual(trace.main(["--events", str(tmp / "events.jsonl"), "--rollup", str(tmp / "rollup.json")]), 0)
            rollup = json.loads((tmp / "rollup.json").read_text(encoding="utf-8"))
            self.assertEqual({arm: data["pass_count"] for arm, data in rollup["arms"].items() if data["row_count"]}, {"A": 1, "B": 1, "C": 1, "D": 1})

    def test_refuses_live_key(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
            with self.assertRaises(harness.HarnessError):
                harness._refuse_live_key()

    def test_trace_rejects_unknown_phase_and_backward_clock(self):
        event = {"schema_version": trace.SCHEMA_VERSION, "event_id": "x", "trial_index": 0, "task_id": "t-01", "packet_id": "A-t-01", "arm": "A", "corpus_id": "tiny", "snapshot_sha256": "0" * 64, "phase": "task_accept", "t_monotonic_ns": 1, "status": "ok", "details": {}}
        trace._validate_event(event, index=1)
        with self.assertRaises(trace.TraceError):
            trace._validate_event(dict(event, phase="unknown"), index=1)
        with self.assertRaises(trace.TraceError):
            trace._validate_monotonicity([event, dict(event, event_id="y", t_monotonic_ns=0)])


if __name__ == "__main__":
    unittest.main()
