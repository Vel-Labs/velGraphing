"""Offline qualification for the 24-trial calibration coordinator."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))
from time_to_correct import Budget, MeasurementError, Trial, canonical, digest
from time_to_correct_calibration import (HANDOFF_PATH, fixture_identity, load_calibration,
                                         qualify, require_resumable, start_fixture_worker,
                                         validate_live_authority)
from time_to_correct_handoff import read_canonical
from time_to_correct_jev import evaluate_live


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local_root = ROOT / ".velgraphing-local"
        cls.local_root.mkdir(mode=0o700, exist_ok=True)

    def test_freeze_registers_exact_counterbalanced_24_and_12_jev(self):
        config = load_calibration(ROOT)
        rows = config["registered_trials"]
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({row["trial_id"] for row in rows}), 24)
        self.assertEqual(sum(row["arm"] in {"B", "D"} for row in rows), 12)
        sequences = []
        for task in ("C-01", "C-02", "S-01", "L-01", "M-01", "M-02"):
            sequences.append("".join(row["arm"] for row in rows if row["task_id"] == task))
        self.assertEqual(sequences, ["ABDC", "BCAD", "CDBA", "DACB", "ABDC", "BCAD"])

    def test_freeze_refuses_redirected_pilot_path(self):
        config = deepcopy(load_calibration(ROOT))
        config["source_pilot"]["packets"] = "elsewhere/packets.json"
        with patch("time_to_correct_calibration.read_json", return_value=config):
            with self.assertRaisesRegex(MeasurementError, "sealed_pilot_identity_changed"):
                load_calibration(ROOT)

    def test_file_handoff_records_exact_request_and_response_hashes(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            worker = start_fixture_worker(root, "handoff", "answer")
            request = canonical({"identity": {"answer_model": "fixture-model"},
                                 "payload": {"fixture_answer": "distinct handoff answer"}})
            completed = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "wait", "--run-root", str(root),
                 "--trial-id", "handoff", "--attempt", "0", "--lane", "answer",
                 "--wait-seconds", "1"],
                cwd=ROOT, env={}, input=request, capture_output=True, check=False,
            )
            stdout, stderr = worker.communicate(timeout=5)
            self.assertEqual((completed.returncode, worker.returncode, stderr, stdout), (0, 0, b"", b""))
            receipt = read_canonical(root / "trials/handoff/attempt-0/answer/receipt.json")[1]
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["request_sha256"], digest(request))
        self.assertEqual(receipt["response_sha256"], digest(completed.stdout))

    def test_offline_qualification_exercises_required_lifecycle(self):
        result = qualify(ROOT)
        self.assertEqual(result["provider_calls_made"], 0)
        self.assertEqual(result["direct_off"]["terminal_reason"], "passed")
        self.assertEqual(result["graph_on_replay"], {
            "terminal_reason": "passed", "graph_records": 2, "jev_execution": "replay"})
        self.assertEqual(result["missing_response"], {
            "terminal_reason": "measurement_error", "handoff_status": "response_timeout"})
        self.assertEqual(result["live_refusal"], "live_jev_not_approved")

    def test_live_path_refuses_before_network_without_approval_or_cap(self):
        config = load_calibration(ROOT)
        with patch("urllib.request.build_opener") as network:
            with self.assertRaisesRegex(MeasurementError, "live_jev_not_approved"):
                validate_live_authority(config, False, None)
            trial = Trial(fixture_identity("refusal", "B", "b" * 64),
                          Budget(0, 1_000_000_000), execution="observed")
            with self.assertRaisesRegex(MeasurementError, "live_jev_not_approved"):
                evaluate_live(trial, ROOT, {}, self.local_root,
                              approved_request_sha256="c" * 64, runtime_approved=False,
                              max_live_calls=12, call_number=1)
            network.assert_not_called()
        with self.assertRaisesRegex(MeasurementError, "live_jev_cap_not_bound"):
            validate_live_authority(config, True, 11)

    def test_incomplete_trial_is_not_resumed(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            (root / "trials/A-C-01").mkdir(parents=True)
            with self.assertRaisesRegex(MeasurementError, "incomplete_trial_requires_parent_audit"):
                require_resumable(root, "A-C-01", set())
            require_resumable(root, "A-C-01", {"A-C-01"})


if __name__ == "__main__":
    unittest.main()
