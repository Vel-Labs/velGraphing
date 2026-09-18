"""Real subprocess boundary tests. No shell, provider, credential, or Codex CLI."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))
from time_to_correct import Budget, MeasurementError, Trial, digest
from time_to_correct_host import run_process_trial


def identity():
    return dict(
        run_id="host-fixture", trial_id="trial1", task_id="task1", arm="A",
        repository_id="fixture-repository", repository_commit="a" * 40,
        source_snapshot_sha256="b" * 64, dirty_state_sha256="c" * 64,
        answer_model="fixture-model", reasoning="none", prompt_sha256="d" * 64,
        rubric_sha256="e" * 64, rubric_version="v1", answer_lane_id="answer-lane",
    )


ANSWER_CODE = r'''
import json, sys
payload = json.load(sys.stdin)
if "rubric_sha256" in payload["identity"]:
    raise SystemExit(9)
if "response_contract" in payload:
    raise SystemExit(8)
result = {
    "answer_text": "observed subprocess answer",
    "context_deliveries_complete": True,
    "model_calls_complete": True,
    "schema_version": "velgraphing-answer-output-v1",
    "usage": {
        "cached_input_tokens": 2,
        "cost_usd": 0.01,
        "input_tokens": 10,
        "model": "fixture-model",
        "output_tokens": 2,
        "provenance": "fixture",
        "reasoning_output_tokens": 1
    }
}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
'''

ANSWER_UNKNOWN_USAGE_CODE = r'''
import json, sys
json.load(sys.stdin)
result = {
    "answer_text": "answer with unknown usage",
    "context_deliveries_complete": False,
    "model_calls_complete": False,
    "schema_version": "velgraphing-answer-output-v1",
    "usage": None
}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
'''


GRADER_CODE = r'''
import json, sys
payload = json.load(sys.stdin)
if "response_contract" in payload:
    raise SystemExit(8)
result = {
    "critical_facts_exact": True,
    "grader_id": "independent-grader",
    "model_calls_complete": True,
    "required_fact_maximum": 10,
    "required_fact_score": 9,
    "rubric_sha256": payload["identity"]["rubric_sha256"],
    "schema_version": "velgraphing-grader-output-v1",
    "unsupported_material_claims": 0,
    "usage": {
        "cached_input_tokens": 0,
        "cost_usd": 0.002,
        "input_tokens": 4,
        "model": "fixture-grader",
        "output_tokens": 1,
        "provenance": "fixture",
        "reasoning_output_tokens": 0
    }
}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
'''


class HostBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)

    def run_host(self, answer_code=ANSWER_CODE, *, answer_timeout_s=2,
                 wall_limit_ns=5_000_000_000, prepared=None):
        trial = Trial(identity(), Budget(0, wall_limit_ns), execution="fixture")
        return run_process_trial(
            trial,
            lambda *_: prepared or {"question": "frozen question", "evidence": ["opaque-source-pointer"]},
            answer_argv=[sys.executable, "-c", answer_code],
            grader_argv=[sys.executable, "-c", GRADER_CODE],
            cwd=self.cwd,
            answer_timeout_s=answer_timeout_s,
            grader_timeout_s=2,
        )

    def test_real_answer_and_independent_grader_subprocesses(self):
        result = self.run_host()
        self.assertEqual(result["terminal_reason"], "passed")
        self.assertEqual(result["attempts"][0]["grade"]["required_fact_recall"], 0.9)
        self.assertEqual(result["attempts"][0]["grade"]["grader_id"], "independent-grader")
        self.assertEqual(result["attempts"][0]["answer_sha256"], digest(b"observed subprocess answer"))
        self.assertEqual([row["kind"] for row in result["attempts"][0]["host_processes"]], ["answer", "grader"])
        self.assertTrue(all(row["status"] == "completed" for row in result["attempts"][0]["host_processes"]))
        self.assertEqual(result["total_input_tokens"], 14)
        self.assertEqual(result["total_output_tokens"], 3)
        self.assertTrue(result["usage_complete"])
        self.assertEqual(len(result["attempts"][0]["context_deliveries"]), 1)

    def test_process_timeout_is_callback_timeout_not_wall_deadline(self):
        result = self.run_host("import time; time.sleep(1)", answer_timeout_s=0.01)
        self.assertEqual(result["terminal_reason"], "callback_timeout")
        self.assertEqual(result["attempts"][0]["failure_stage"], "answer")
        self.assertEqual(result["attempts"][0]["failure_reason"], "callback_timeout")
        receipt = result["attempts"][0]["host_processes"][0]
        self.assertEqual(receipt["status"], "timeout")
        self.assertLessEqual(receipt["timeout_limit_ns"], result["budget"]["wall_limit_ns"])

    def test_process_timeout_clipped_by_wall_budget_is_deadline(self):
        result = self.run_host(
            "import time; time.sleep(1)",
            answer_timeout_s=2,
            wall_limit_ns=50_000_000,
        )
        self.assertEqual(result["terminal_reason"], "deadline_exceeded")
        self.assertEqual(result["attempts"][0]["failure_stage"], "controller")
        self.assertEqual(result["attempts"][0]["failure_reason"], "deadline_exceeded")
        receipt = result["attempts"][0]["host_processes"][0]
        self.assertEqual(receipt["status"], "timeout")
        self.assertLess(receipt["timeout_limit_ns"], 2_000_000_000)

    def test_unknown_usage_stays_unknown(self):
        result = self.run_host(ANSWER_UNKNOWN_USAGE_CODE)
        self.assertEqual(result["terminal_reason"], "passed")
        self.assertFalse(result["usage_complete"])
        self.assertIsNone(result["total_input_tokens"])
        self.assertIsNone(result["all_attempt_cost_usd"])

    def test_process_error_does_not_expose_stderr(self):
        result = self.run_host("import sys; sys.stderr.write('secret-value'); raise SystemExit(2)")
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(result["attempts"][0]["failure_reason"], "process_exit_nonzero")
        self.assertNotIn("secret-value", str(result))
        self.assertEqual(result["attempts"][0]["host_processes"][0]["status"], "failed")

    def test_shell_string_is_rejected(self):
        trial = Trial(identity(), Budget(0, 5_000_000_000), execution="fixture")
        with self.assertRaisesRegex(MeasurementError, "invalid_process_argv"):
            run_process_trial(
                trial, lambda *_: {}, answer_argv="python -c pass",
                grader_argv=[sys.executable, "-c", GRADER_CODE], cwd=self.cwd,
                answer_timeout_s=1, grader_timeout_s=1,
            )

    def test_v3_answer_requires_known_evidence_citation(self):
        prepared = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "frozen question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": [{"id": "c0"}],
        }
        missing = self.run_host(ANSWER_CODE, prepared=prepared)
        self.assertEqual(missing["attempts"][0]["failure_reason"],
                         "answer_evidence_citation_missing")
        invalid = self.run_host(
            ANSWER_CODE.replace("observed subprocess answer", "unsupported [c9]"),
            prepared=prepared)
        self.assertEqual(invalid["attempts"][0]["failure_reason"],
                         "answer_evidence_citation_invalid")
        valid = self.run_host(
            ANSWER_CODE.replace("observed subprocess answer", "supported [c0]"),
            prepared=prepared)
        self.assertEqual(valid["terminal_reason"], "passed")


if __name__ == "__main__":
    unittest.main()
