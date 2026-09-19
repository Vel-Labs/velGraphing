"""Offline Luna successor freeze tests. No provider or model calls."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "time_to_correct_luna_successor_v4",
    ROOT / "scripts/benchmarks/time_to_correct_luna_successor_v4.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def lane_entries():
    command = [sys.executable, "-c", "pass"]
    return [{
        "trial_id": trial_id,
        "role": role,
        "thread_id": f"thread-{role}-{trial_id}",
        "model": "gpt-5.6-luna",
        "reasoning": "medium",
        "argv": command,
        "argv_sha256": mod.digest(mod.canonical(command)),
    } for trial_id in mod.DISPATCH for role in mod.LANE_ROLES]


class LunaSuccessorTests(unittest.TestCase):
    def test_study_is_four_tasks_and_sixteen_balanced_trials(self) -> None:
        self.assertEqual(tuple(task for task, _ in mod.TASK_ARMS), (
            "S-01", "D-01", "L-01", "M-02",
        ))
        self.assertEqual(len(mod.DISPATCH), 16)
        self.assertEqual(set(mod.DISPATCH), {
            f"{arm}-{task}" for task, _ in mod.TASK_ARMS for arm in mod.ARMS
        })
        self.assertEqual(
            mod.preview._study(mod.STUDY_ID)["previews"],
            mod.preview.LUNA_SUCCESSOR_PREVIEWS,
        )

    def test_required_facts_map_to_prompt_asks(self) -> None:
        questions, registry_sha256 = mod.load_questions()
        rubrics, rubric_sha256 = mod.load_rubrics()
        self.assertEqual(registry_sha256, mod.evaluator.LUNA_SUCCESSOR_QUESTION_REGISTRY_SHA256)
        self.assertEqual(len(rubric_sha256), 64)
        self.assertEqual(set(questions), set(rubrics))
        for rubric in rubrics.values():
            ask_ids = {row["id"] for row in rubric["asks"]}
            self.assertTrue(all(row["ask_id"] in ask_ids for row in rubric["required_facts"]))
            self.assertFalse(
                set(row["fact"] for row in rubric["required_facts"])
                & set(rubric["diagnostic_facts"])
            )
        d_required = [row["fact"] for row in rubrics["D-01"]["required_facts"]]
        self.assertFalse(any("base case" in fact.lower() for fact in d_required))
        self.assertTrue(any("base case" in fact.lower() for fact in rubrics["D-01"]["diagnostic_facts"]))
        l_required = [row["fact"] for row in rubrics["L-01"]["required_facts"]]
        self.assertFalse(any("Kafka" in fact for fact in l_required))
        self.assertTrue(any("Kafka" in fact for fact in rubrics["L-01"]["diagnostic_facts"]))

    def test_blind_review_citation_and_attribution_repairs(self) -> None:
        questions, _ = mod.load_questions()
        rubrics, _ = mod.load_rubrics()

        s_asks = {row["id"] for row in rubrics["S-01"]["asks"]}
        s_facts = [row["fact"] for row in rubrics["S-01"]["required_facts"]]
        self.assertIn("citation", s_asks)
        self.assertTrue(any("sorts/quick_sort.py" in fact for fact in s_facts))
        input_effect = next(
            row["fact"] for row in rubrics["S-01"]["required_facts"]
            if row["ask_id"] == "input_effect"
        )
        self.assertIn("randomly selected pivot", input_effect)
        self.assertIn("not deterministic", input_effect)

        l_asks = {row["id"] for row in rubrics["L-01"]["asks"]}
        l_facts = {row["ask_id"]: row["fact"] for row in rubrics["L-01"]["required_facts"]}
        self.assertTrue({"citations", "attribution"}.issubset(l_asks))
        self.assertIn("00-url-shortener.md", l_facts["citations"])
        self.assertIn("00-scalability.md", l_facts["citations"])
        self.assertIn("case study", l_facts["attribution"])
        self.assertIn("scalability chapter", l_facts["attribution"])

        m_prompt = questions["M-02"]["prompt"]
        self.assertIn("one documented process-documentation choice", m_prompt)
        self.assertIn("one documented training choice", m_prompt)
        self.assertIn("Cite both the small-company playbook and FAQ", m_prompt)
        m_facts = {row["ask_id"]: row["fact"] for row in rubrics["M-02"]["required_facts"]}
        self.assertIn("reference training slides", m_facts["training"])
        self.assertIn("LFC193/LFC194", m_facts["training"])
        self.assertIn("Small Company Playbook", m_facts["citations"])
        self.assertIn("OpenChain-Processes-and-FAQ/faq.md", m_facts["citations"])

    def test_identity_pins_luna_for_answer_and_grader(self) -> None:
        questions, _ = mod.load_questions()
        rubrics, _ = mod.load_rubrics()
        identity = mod.trial_identity(
            "D-01", "D", questions["D-01"], rubrics["D-01"],
            "a" * 40, "b" * 64,
        )
        self.assertEqual(identity["answer_model"], "gpt-5.6-luna")
        self.assertEqual(identity["reasoning"], "medium")
        self.assertEqual(mod.GRADER_MODEL, "gpt-5.6-luna")

    def test_answer_and_grader_payloads_exclude_treatment(self) -> None:
        questions, _ = mod.load_questions()
        rubrics, _ = mod.load_rubrics()
        grader = mod.grader_rubric(rubrics["D-01"])
        self.assertEqual(set(grader), {"required_facts", "critical_facts", "acceptable_spans"})
        self.assertNotIn("arm", questions["D-01"])
        self.assertNotIn("jev", questions["D-01"])
        self.assertNotIn("diagnostic_facts", grader)

    def test_plan_pairs_arms_and_caps_only_effectful_jev_calls(self) -> None:
        plan = mod.load_plan(expected_live_authorized=True)
        rows = plan["arm_preflight"]
        self.assertEqual([row["trial_id"] for row in rows], list(mod.DISPATCH))
        self.assertEqual(sum(row["call_disposition"] == "planned" for row in rows), 8)
        self.assertEqual(plan["call_authorization"]["planned_calls"], 8)
        self.assertEqual(plan["call_authorization"]["completed_prior_calls"], 7)
        self.assertEqual(plan["call_authorization"]["aggregate_authorized_calls"], 15)
        self.assertEqual(plan["call_authorization"]["prior_authorization_envelope_usd"], 0.038535168)
        self.assertEqual(plan["call_authorization"]["aggregate_authorization_envelope_usd"], 0.08257536)
        self.assertEqual(plan["call_authorization"]["authorization_remaining_usd"], 0.91742464)
        self.assertEqual(plan["run_root"], ".velgraphing-local/retrievel-t030-luna-successor-r4")
        self.assertLessEqual(plan["call_authorization"]["planned_calls"], 8)
        by_task = {}
        for row in rows:
            by_task.setdefault(row["task_id"], {})[row["arm"]] = row
            if row["arm"] in {"A", "C"}:
                self.assertEqual(row["call_disposition"], "treatment_off")
                self.assertIsNone(row["request_sha256"])
            else:
                expected = (
                    "planned" if row["jev_call_could_affect_selection"]
                    else "skip_no_membership_effect"
                )
                self.assertEqual(row["call_disposition"], expected)
        for arms in by_task.values():
            self.assertEqual(arms["A"]["pool_sha256"], arms["B"]["pool_sha256"])
            self.assertEqual(arms["C"]["pool_sha256"], arms["D"]["pool_sha256"])

    def test_plan_is_source_free_and_live_authorized(self) -> None:
        plan = json.loads(mod.PLAN_PATH.read_text(encoding="utf-8"))
        self.assertTrue(plan["live_authorized"])
        self.assertEqual(plan["provider_calls_executed"], 0)
        self.assertEqual(
            plan["status"], "live_authorized_lane_manifest_pending"
        )
        self.assertNotIn("excerpt", json.dumps(plan))
        self.assertEqual(plan["models"]["answer"], "gpt-5.6-luna")
        self.assertEqual(plan["models"]["grader"], "gpt-5.6-luna")
        self.assertEqual(plan["lane_manifest_contract"], mod.LANE_MANIFEST_CONTRACT)

    def test_lane_manifest_requires_complete_unique_hashed_lanes(self) -> None:
        entries = lane_entries()
        lanes = mod._validate_lane_entries(entries)
        self.assertEqual(len(lanes), 32)
        self.assertEqual(
            set(lanes),
            {(trial_id, role) for trial_id in mod.DISPATCH for role in mod.LANE_ROLES},
        )
        invalid = {
            "missing": entries[:-1],
            "extra": [*entries, dict(entries[0])],
            "thread_reuse": [
                entries[0], {**entries[1], "thread_id": entries[0]["thread_id"]},
                *entries[2:],
            ],
            "model": [{**entries[0], "model": "gpt-5.6-sol"}, *entries[1:]],
            "reasoning": [{**entries[0], "reasoning": "high"}, *entries[1:]],
            "argv_hash": [{**entries[0], "argv_sha256": "0" * 64}, *entries[1:]],
        }
        for label, value in invalid.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    mod.SuccessorError, "successor_lane_manifest_invalid"
                ):
                    mod._validate_lane_entries(value)

    def test_selection_revalidates_source_and_preserves_required_evidence(self) -> None:
        from tests.core.test_ranked_context_selection import fixture

        graph, snapshot, reader, candidates = fixture()
        run = {
            "route": "direct",
            "candidates": [{
                "id": candidate.candidate_id,
                "path": candidate.source_path,
                "source_sha256": candidate.source_sha256,
                "byte_start": candidate.byte_start,
                "byte_end": candidate.byte_end,
                "required": candidate.required,
                "record_id": candidate.record_id,
                "relationship_parent_candidate_id": (
                    candidate.relationship_parent_candidate_id
                ),
            } for candidate in candidates],
        }
        lane = {
            "plain_graph": graph,
            "typed_graph": graph,
            "snapshot": snapshot,
            "reader": reader,
        }
        question = {"prompt": "find required and optional evidence"}
        selected = mod._selection("S-01", "A", run, lane, question, None)
        self.assertIn("c0", selected.projection.selected_candidate_ids)
        self.assertEqual(selected.projection.required_candidate_ids, ("c0",))
        reader.sources["src/context.py"] = b"changed source bytes"
        with self.assertRaisesRegex(mod.SuccessorError, "successor_selection_invalid"):
            mod._selection("S-01", "A", run, lane, question, None)

    def test_controller_dispatches_all_sixteen_trials_in_frozen_order(self) -> None:
        plan = json.loads(mod.PLAN_PATH.read_text(encoding="utf-8"))
        questions, _ = mod.load_questions()
        rubrics, _ = mod.load_rubrics()
        artifact = {"runs": [
            {"task_id": task, "route": route}
            for task, _ in mod.TASK_ARMS for route in ("direct", "typed_graph")
        ]}
        result = {
            "terminal_reason": "passed",
            "attempts": [{"coverage": {
                "model_calls": True,
                "context_deliveries": True,
            }}],
        }
        lanes = {
            (entry["trial_id"], entry["role"]): entry for entry in lane_entries()
        }
        with (
            mock.patch.object(mod, "preflight", return_value={
                "arm_preflight": plan["arm_preflight"],
            }),
            mock.patch.object(mod, "load_plan", return_value=plan),
            mock.patch.object(mod, "load_questions", return_value=(questions, "a" * 64)),
            mock.patch.object(mod, "load_rubrics", return_value=(rubrics, "b" * 64)),
            mock.patch.object(mod.preview, "_load_inputs", return_value=(artifact, questions)),
            mock.patch.object(mod, "run_trial", return_value=result) as run_trial,
        ):
            output = mod.run_successor(
                Path("candidates"), Path("questions"), Path("rubrics"),
                Path("manifests"), Path("lanes"), Path("preview"), Path("run"),
                lane_manifest=lanes,
            )
        self.assertEqual(len(output["results"]), 16)
        self.assertEqual(
            [f"{call.args[1]}-{call.args[0]}" for call in run_trial.call_args_list],
            list(mod.DISPATCH),
        )
        self.assertTrue(all(
            call.kwargs["ledger"].cap == 8 for call in run_trial.call_args_list
        ))
        self.assertTrue(all(
            call.kwargs["answer_lane"]["role"] == "answer"
            and call.kwargs["grader_lane"]["role"] == "grader"
            for call in run_trial.call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
