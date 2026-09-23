"""Check the new M09 route, Jev, and independent-lane boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))
import m09_four_arm_repeated_v1 as study  # noqa: E402


class M09FourArmContractTests(unittest.TestCase):
    def test_two_manifests_bind_64_distinct_lane_identities(self) -> None:
        freeze = json.loads((study.BENCHMARK / "freeze.json").read_text())
        root = ROOT / ".velgraphing-local/m09-four-arm-repeated-20260923-r9"
        first = study._manifest(study._study_freeze(freeze), root, 1,
                                Path(sys.executable))
        second = study._manifest(study._study_freeze(freeze), root, 2,
                                 Path(sys.executable))
        entries = first["entries"] + second["entries"]
        self.assertEqual(64, len(entries))
        self.assertEqual(64, len({row["thread_id"] for row in entries}))
        self.assertEqual(32, len({row["trial_id"] for row in entries}))
        self.assertTrue(all(
            row["model"] == study.ANSWER_MODEL
            and row["reasoning"] == study.ANSWER_REASONING
            for row in entries if row["role"] == "answer"
        ))
        self.assertEqual({"A", "B", "C", "D"}, {
            row["trial_id"][0] for row in entries
        })
        self.assertTrue(all(
            row["canonical_task_path"] == f"/root/{row['thread_id']}"
            for row in entries
        ))
        self.assertTrue(all(row["thread_id"].startswith("m09_r9_") for row in entries))
        with self.assertRaisesRegex(study.StudyError, "run_tag_invalid"):
            study._manifest(study._study_freeze(freeze), root.parent / "invalid", 1,
                            Path(sys.executable))

    def test_answer_receipt_requires_actual_route_and_real_jev_call(self) -> None:
        contract = {"lanes": {"R1": "a" * 64}}
        registration = {
            "trial_id": "D-S-01-R1", "arm": "D", "task_id": "S-01",
            "selection_decision_sha256": "b" * 64,
        }
        pool = {"pool_sha256": "c" * 64}
        rubric = {"rubric_version": "fixture"}
        receipt = {
            "identity": {
                "run_id": study.STUDY_ID, "trial_id": "D-S-01-R1",
                "arm": "D", "task_id": "S-01",
            },
            "execution": "observed",
            "budget": {"max_repairs": 0, "wall_limit_ns": 600_000_000_000},
            "terminal_reason": "passed",
            "attempts": [{
                "model_calls": [
                    {"kind": "jev"}, {"kind": "answer"}, {"kind": "grader"},
                ],
                "candidate_observation": {
                    "selection_route": "direct",
                    "selection_reason": "graph_selection_would_displace_direct_baseline",
                },
                "jev_observation": {"attempted_calls": 1, "status": "reranked"},
                "grade": {"passed": True},
            }],
        }
        receipt["study_binding_sha256"] = study._receipt_binding(
            contract, registration, pool, rubric, contract["lanes"]["R1"],
        )
        study._validate_receipt(
            receipt, "D-S-01-R1", contract, registration, pool, rubric,
        )
        receipt["attempts"][0]["jev_observation"]["attempted_calls"] = 0
        with self.assertRaisesRegex(study.StudyError, "jev_execution_missing"):
            study._validate_receipt(
                receipt, "D-S-01-R1", contract, registration, pool, rubric,
            )
        receipt["attempts"][0]["jev_observation"]["attempted_calls"] = 1
        receipt["attempts"][0]["candidate_observation"]["selection_reason"] = ""
        with self.assertRaisesRegex(study.StudyError, "actual_route_missing"):
            study._validate_receipt(
                receipt, "D-S-01-R1", contract, registration, pool, rubric,
            )
        receipt["attempts"][0]["candidate_observation"]["selection_reason"] = (
            "graph_selection_would_displace_direct_baseline"
        )
        receipt["attempts"][0]["jev_observation"] = {
            "attempted_calls": 0, "status": "fallback",
            "reason": "source_changed_before_request",
        }
        receipt["attempts"][0]["model_calls"] = [
            {"kind": "answer"}, {"kind": "grader"},
        ]
        study._validate_receipt(
            receipt, "D-S-01-R1", contract, registration, pool, rubric,
        )

    def test_scored_negative_continues_to_next_frozen_trial(self) -> None:
        def receipt(passed: bool) -> dict:
            return {
                "terminal_reason": (
                    "passed" if passed else "repair_budget_exhausted"
                ),
                "attempts": [{
                    "grade": {"passed": passed},
                    "failure_stage": None, "failure_reason": None,
                    "model_calls": [{"kind": "answer"}, {"kind": "grader"}],
                }],
            }

        contract = {
            "policy": {"dispatch_order": ["A-S-01-R1", "B-S-01-R1"]},
            "inputs": {"lane_root": str(ROOT / ".velgraphing-local")},
            "lanes": {"R1": "a" * 64},
        }
        freeze = {"study_id": "fixture"}
        rubrics = {"tasks": {"S-01": {"rubric_version": "fixture"}}}
        pools = {"direct:S-01": {"pool_sha256": "b" * 64}}
        registrations = {
            f"{arm}-S-01": {
                "arm": arm, "task_id": "S-01", "pool_id": "direct:S-01",
            } for arm in ("A", "B")
        }
        first, second = receipt(False), receipt(True)
        with (
            patch.object(study, "load_frozen", return_value=(
                contract, freeze, rubrics, pools, registrations,
                {"R1": {"entries": []}},
            )),
            patch.object(study, "bind_controller"),
            patch.object(study, "controller_identity", return_value={}),
            patch.object(study, "load_completed_trials", return_value=[]),
            patch.object(study, "require_resumable"),
            patch.object(study, "_validate_receipt"),
            patch.object(study, "save_completed_trial") as save,
            patch.object(study.base, "execute_trial", side_effect=[first, second]) as execute,
            patch.object(study, "_result", return_value={"status": "closed"}),
            patch.object(study, "_write_once"),
            patch.dict(study.os.environ, {"TYPESAFE_API_KEY": "fixture-presence"}),
        ):
            result = study.run(
                ROOT / ".velgraphing-local/m09-test",
                study.base.digest(study.base.canonical(contract)),
                str(study.MAX_ADDITIONAL_USD),
            )
        self.assertEqual("closed", result["status"])
        self.assertEqual(str(study.MAX_ADDITIONAL_USD),
                         result["parent_approved_provider_spend_ceiling_usd"])
        self.assertEqual(2, execute.call_count)
        self.assertEqual(2, save.call_count)

    def test_aggregate_counts_scored_negative_route_and_jev_abstention(self) -> None:
        freeze = json.loads((study.BENCHMARK / "freeze.json").read_text())
        registrations = {}
        pools = {}
        for arm in study.ARMS:
            for task in study.TASKS:
                base_id = f"{arm}-{task}"
                route = freeze["arms"][arm]["route"]
                pool_id = f"{route}:{task}"
                registrations[base_id] = {
                    "arm": arm, "task_id": task, "pool_id": pool_id,
                }
                pools[pool_id] = {
                    "corpus": study.base.TASK_CORPORA[task],
                    "identity": {"route": route},
                }
        rubrics = {"tasks": {task: {} for task in study.TASKS}}
        receipts = {}
        for repeat in study.REPEATS:
            for trial_id in study._round_ids(freeze, repeat):
                arm = trial_id[0]
                negative = trial_id == "C-L-01-R1"
                abstain = trial_id == "D-D-01-R1"
                jev_on = arm in {"B", "D"}
                jev_calls = 0 if abstain else int(jev_on)
                receipts[trial_id] = {
                    "terminal_reason": (
                        "repair_budget_exhausted" if negative else "passed"
                    ),
                    "attempts": [{
                        "candidate_observation": {
                            "selection_route": "direct",
                            "selection_reason": "safe_fallback",
                        },
                        "jev_observation": {
                            "attempted_calls": jev_calls,
                            "status": "fallback" if abstain else (
                                "reranked" if jev_on else None
                            ),
                            "reason": "pre_call_abstention" if abstain else None,
                            "source_revalidated": bool(jev_calls),
                        },
                        "model_calls": [
                            {"kind": "answer", "input_tokens": None,
                             "output_tokens": None, "cost_usd": None},
                            {"kind": "grader", "input_tokens": None,
                             "output_tokens": None, "cost_usd": None},
                        ] + ([{
                            "kind": "jev", "input_tokens": 10,
                            "output_tokens": 2, "cost_usd": None,
                        }] if jev_calls else []),
                    }],
                }
        with (
            patch.object(study, "_validate_receipt"),
            patch.object(study.base, "_v3_trial_measurement", return_value={
                "user_visible_wall_ns": 100,
                "answer_request_bytes": 20,
            }),
        ):
            result = study._result(
                {"schema_version": study.SCHEMA}, freeze, registrations,
                pools, rubrics, receipts,
            )
        self.assertEqual(32, len(result["trials"]))
        self.assertEqual(1, result["by_corpus_arm"]["L-01:C"]["passes"])
        self.assertEqual(
            2, result["by_corpus_arm"]["L-01:C"]["selector_direct_fallbacks"]
        )
        self.assertEqual(1, result["by_corpus_arm"]["D-01:D"]["jev_executions"])
        self.assertEqual(1, result["by_corpus_arm"]["D-01:D"]["jev_reranks"])
        self.assertEqual(
            0, result["by_corpus_arm"]["D-01:D"]["model_usage"]["jev"]["cost_usd"][
                "reported_calls"
            ],
        )


if __name__ == "__main__":
    unittest.main()
