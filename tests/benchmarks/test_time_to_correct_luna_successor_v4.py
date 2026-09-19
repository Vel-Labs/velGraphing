"""Offline Luna successor freeze tests. No provider or model calls."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "time_to_correct_luna_successor_v4",
    ROOT / "scripts/benchmarks/time_to_correct_luna_successor_v4.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


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


if __name__ == "__main__":
    unittest.main()
