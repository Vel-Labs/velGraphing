"""Offline qualification for the 24-trial calibration coordinator."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))
from time_to_correct import Budget, MeasurementError, Trial, canonical, digest, summarize
from time_to_correct_calibration import (HANDOFF_PATH, LiveJevBudget, bind_controller,
                                         controller_identity, fixture_identity,
                                         jev_answer_payload, load_calibration, qualify,
                                         require_resumable, revalidate_lane,
                                         start_fixture_worker, summarize_calibration,
                                         validate_live_authority, verify_lane)
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
        protocol = json.loads((ROOT / "benchmarks/velgraphing-time-to-correct-v1/protocol.json").read_text())
        self.assertEqual(protocol["document_role"],
                         "historical_proposed_design_not_executable_authority")
        self.assertEqual(protocol["executable_calibration_authority"], {
            "file": "calibration.json", "registered_trials": 24,
            "max_repairs": 0, "max_live_jev_calls": 12,
        })
        self.assertNotIn("repair_budget", protocol)
        self.assertEqual(protocol["historical_proposed_repair_budget"]["max_repairs"], 2)

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

    def test_response_file_cli_publishes_canonical_draft(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            lane = root / "trials/publish/attempt-0/answer"
            lane.mkdir(parents=True)
            response = canonical({"schema_version": "fixture-response-v1", "answer": "published"})
            draft = lane / "draft-response.json"
            draft.write_bytes(response)
            completed = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "respond", "--run-root", str(root),
                 "--trial-id", "publish", "--attempt", "0", "--lane", "answer",
                 "--response-file", str(draft)],
                cwd=ROOT, env={}, capture_output=True, check=False,
            )
            published = (lane / "response.json").read_bytes()
            draft_value = read_canonical(draft)[1]
        self.assertEqual((completed.returncode, completed.stderr), (0, b""))
        self.assertEqual(published, response)
        self.assertEqual(draft_value["answer"], "published")

    def test_handoff_rejects_symlinked_trial_directory(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            outside = Path(raw) / "outside"
            (root / "trials").mkdir(parents=True)
            outside.mkdir()
            (root / "trials/escape").symlink_to(outside, target_is_directory=True)
            completed = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "wait", "--run-root", str(root),
                 "--trial-id", "escape", "--attempt", "0", "--lane", "answer",
                 "--wait-seconds", "0.1"],
                cwd=ROOT, env={}, input=canonical({"request": "contained"}),
                capture_output=True, check=False,
            )
            escaped = outside / "attempt-0"
            escaped_exists = escaped.exists()
        self.assertEqual(completed.returncode, 3)
        self.assertIn(b"handoff_lane_invalid", completed.stderr)
        self.assertFalse(escaped_exists)

    def test_jev_order_resolves_exact_candidates_for_answer_lane(self):
        candidates = [
            {"id": "required", "path": "a.py", "source_sha256": "a" * 64,
             "byte_start": 0, "byte_end": 8, "required": True},
            {"id": "low", "path": "b.py", "source_sha256": "b" * 64,
             "byte_start": 2, "byte_end": 10, "required": False},
            {"id": "high", "path": "c.py", "source_sha256": "c" * 64,
             "byte_start": 4, "byte_end": 12, "required": False},
        ]
        result = {"status": "reranked", "order": ["required", "high", "low"],
                  "baseline_order": ["required", "low", "high"],
                  "required_ids": ["required"]}
        payload = jev_answer_payload({"candidates": candidates}, result)
        self.assertEqual(payload["order"], result["order"])
        self.assertEqual([row["id"] for row in payload["ordered_candidates"]], result["order"])
        self.assertEqual({row["id"]: row for row in payload["ordered_candidates"]},
                         {row["id"]: row for row in candidates})
        fallback = jev_answer_payload(
            {"candidates": candidates},
            {**result, "status": "fallback", "order": result["baseline_order"]},
        )
        self.assertEqual([row["id"] for row in fallback["ordered_candidates"]],
                         result["baseline_order"])

    def test_mixed_arm_finalization_returns_four_complete_summaries(self):
        config = load_calibration(ROOT)
        results = []
        for row in config["registered_trials"]:
            results.append({
                "identity": {
                    "run_id": config["calibration_id"], "trial_id": row["trial_id"],
                    "arm": row["arm"], "answer_model": config["answer_model"],
                    "reasoning": config["reasoning"], "rubric_version": "task-rubric-v1",
                    "rubric_sha256": digest(row["task_id"].encode("utf-8")),
                },
                "budget": config["repair_budget"], "pass_recall_min": 0.9,
                "execution": "observed", "terminal_reason": "passed",
                "first_pass_correct": True, "user_visible_wall_ns": 100,
                "confirmed_time_to_correct_ns": 90, "all_attempt_cost_usd": None,
            })
        expected_ids = [row["trial_id"] for row in config["registered_trials"]]
        with self.assertRaisesRegex(MeasurementError, "incomparable_trials"):
            summarize(expected_ids, results)
        controller = {"schema_version": "velgraphing-controller-identity-v1",
                      "git_head": "a" * 40, "tracked_state_sha256": "b" * 64}
        output = summarize_calibration(config, results, controller)
        self.assertEqual((output["status"], output["registered_trials"],
                          output["reported_trials"], output["coverage_complete"]),
                         ("closed", 24, 24, True))
        self.assertEqual(output["controller_identity"], controller)
        self.assertEqual(set(output["arm_summaries"]), {"A", "B", "C", "D"})
        for arm, summary in output["arm_summaries"].items():
            self.assertEqual((summary["registered_trials"], summary["reported_trials"],
                              summary["coverage_complete"]), (6, 6, True), arm)

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

    def test_jev_budget_allows_twelve_then_refuses_duplicate_and_thirteenth(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            budget = LiveJevBudget(root, 12)
            first = budget.reserve("trial-0", f"{0:064x}")
            budget.complete(first[0], {
                "attempted_calls": 1, "status": "reranked", "reason": "advisory_only"})
            reservations = [first] + [
                budget.reserve(f"trial-{index}", f"{index:064x}")
                for index in range(1, 12)
            ]
            self.assertEqual([number for _, number in reservations], list(range(1, 13)))
            with self.assertRaisesRegex(MeasurementError, "jev_call_already_reserved"):
                budget.reserve("trial-0", "f" * 64)
            with self.assertRaisesRegex(MeasurementError, "jev_call_cap_exhausted"):
                budget.reserve("trial-12", "f" * 64)

    def test_jev_budget_rejects_symlinked_ledger_directory(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            outside = Path(raw) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "jev-calls").symlink_to(outside, target_is_directory=True)
            budget = LiveJevBudget(root, 12)
            with self.assertRaisesRegex(MeasurementError, "jev_call_ledger_invalid"):
                budget.reserve("trial-0", "a" * 64)
            escaped = (outside / "trial-0.json").exists()
        self.assertFalse(escaped)

    def test_controller_identity_ignores_untracked_and_rejects_tracked_changes(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            repo = Path(raw) / "controller"
            repo.mkdir()
            tracked = repo / "controller.py"
            tracked.write_text("VERSION = 1\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "controller.py"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                            "fixture"], check=True)
            identity = controller_identity(repo)
            (repo / "untracked-run-data").write_text("ignored by identity\n", encoding="utf-8")
            self.assertEqual(controller_identity(repo), identity)
            run_root = Path(raw) / ".velgraphing-local/controller-run"
            self.assertEqual(bind_controller(run_root, identity), identity)
            with self.assertRaisesRegex(MeasurementError, "controller_identity_changed"):
                bind_controller(run_root, {**identity, "git_head": "f" * 40})
            tracked.write_text("VERSION = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(MeasurementError, "controller_checkout_not_clean"):
                controller_identity(repo)

    def test_post_trial_corpus_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            repo = Path(raw) / "controller"
            corpus_root = Path(raw) / "corpus"
            corpus_root.mkdir()
            source = corpus_root / "source.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(corpus_root)], check=True)
            subprocess.run(["git", "-C", str(corpus_root), "add", "source.py"], check=True)
            subprocess.run(["git", "-C", str(corpus_root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                            "fixture"], check=True)
            commit = subprocess.run(["git", "-C", str(corpus_root), "rev-parse", "HEAD"],
                                    capture_output=True, check=True, text=True).stdout.strip()
            raw_source = source.read_bytes()
            rows = [{"path": "source.py", "byte_length": len(raw_source),
                     "sha256": digest(raw_source)}]
            snapshot = digest(canonical({"sources": rows}))
            manifest = repo / "benchmarks/velgraphing-corpus-pilot-v1/manifests/test.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_bytes(canonical({"sources": rows, "snapshot_sha256": snapshot}))
            corpus = {"id": "fixture", "commit": commit,
                      "snapshot_sha256": snapshot, "manifest": "manifests/test.json"}
            _, before = verify_lane(repo, corpus, corpus_root)
            source.write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(MeasurementError, "corpus_changed_during_trial"):
                revalidate_lane(repo, corpus, corpus_root, before)
            source.write_bytes(raw_source)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(MeasurementError, "corpus_changed_during_trial"):
                revalidate_lane(repo, corpus, corpus_root, before)

    def test_incomplete_trial_is_not_resumed(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            (root / "trials/A-C-01").mkdir(parents=True)
            with self.assertRaisesRegex(MeasurementError, "incomplete_trial_requires_parent_audit"):
                require_resumable(root, "A-C-01", set())
            require_resumable(root, "A-C-01", {"A-C-01"})


if __name__ == "__main__":
    unittest.main()
