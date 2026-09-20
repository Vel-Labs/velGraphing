"""Offline Luna successor freeze tests. No provider or model calls."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
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
        self.assertFalse(mod.REQUIRE_ANSWER_EVIDENCE_CITATION)

    def test_plan_pairs_arms_and_caps_only_effectful_jev_calls(self) -> None:
        plan = mod.load_plan(expected_live_authorized=False)
        rows = plan["arm_preflight"]
        self.assertEqual([row["trial_id"] for row in rows], list(mod.DISPATCH))
        self.assertEqual(sum(row["call_disposition"] == "planned" for row in rows), 8)
        self.assertEqual(plan["call_authorization"]["planned_calls"], 8)
        self.assertEqual(plan["call_authorization"]["completed_prior_calls"], 34)
        self.assertEqual(plan["call_authorization"]["aggregate_authorized_calls"], 42)
        self.assertEqual(plan["call_authorization"]["prior_authorization_envelope_usd"], 0.187170816)
        self.assertEqual(plan["call_authorization"]["aggregate_authorization_envelope_usd"], 0.231211008)
        self.assertEqual(plan["call_authorization"]["authorization_remaining_usd"], 0.768788992)
        self.assertEqual(plan["run_root"], ".velgraphing-local/retrievel-t030-luna-successor-r13")
        self.assertLessEqual(plan["call_authorization"]["planned_calls"], 8)
        by_task = {}
        for row in rows:
            by_task.setdefault(row["task_id"], {})[row["arm"]] = row
            if row["arm"] in {"A", "C"}:
                self.assertEqual(row["call_disposition"], "treatment_off")
                self.assertIsNone(row["preview_sha256"])
                self.assertIsNone(row["request_sha256"])
            else:
                self.assertEqual(len(row["preview_sha256"]), 64)
                expected = (
                    "planned" if row["jev_call_could_affect_selection"]
                    else "skip_no_membership_effect"
                )
                self.assertEqual(row["call_disposition"], expected)
        for arms in by_task.values():
            self.assertEqual(arms["A"]["pool_sha256"], arms["B"]["pool_sha256"])
            self.assertEqual(arms["C"]["pool_sha256"], arms["D"]["pool_sha256"])

    def test_plan_is_source_free_and_fails_closed_pending_host_lanes(self) -> None:
        plan = json.loads(mod.PLAN_PATH.read_text(encoding="utf-8"))
        self.assertFalse(plan["live_authorized"])
        self.assertEqual(plan["provider_calls_executed"], 0)
        self.assertEqual(
            plan["status"], "frozen_lane_manifest_pending_live_authorization"
        )
        self.assertNotIn("excerpt", json.dumps(plan))
        self.assertEqual(plan["models"]["answer"], "gpt-5.6-luna")
        self.assertEqual(plan["models"]["grader"], "gpt-5.6-luna")
        self.assertEqual(plan["lane_manifest_contract"], mod.LANE_MANIFEST_CONTRACT)
        self.assertEqual(plan["lane_manifest"], mod.LANE_MANIFEST_BINDING)
        self.assertEqual(plan["controller"], mod.CONTROLLER)
        self.assertEqual(plan["telemetry_schema"], mod.TELEMETRY_SCHEMA)
        self.assertIsNone(plan["lane_manifest"]["sha256"])
        plan["live_authorized"] = True
        plan["status"] = "live_authorized_lane_manifest_frozen"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(mod.SuccessorError, "successor_plan_invalid"):
                mod.load_plan(path, expected_live_authorized=True)

    def test_frozen_lane_manifest_allows_live_plan_and_preflight(self) -> None:
        candidate_path = mod.PLAN_PATH.parent / mod.CANDIDATE_ARTIFACT["path"]
        artifact = json.loads(candidate_path.read_text(encoding="utf-8"))
        questions, _ = mod.load_questions()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / mod.RUN_ROOT
            run_root.mkdir(parents=True)
            manifest_path = run_root / "lane-manifest.json"
            manifest_raw = mod.canonical({
                "schema_version": mod.LANE_MANIFEST_SCHEMA,
                "entries": lane_entries(),
            })
            manifest_path.write_bytes(manifest_raw)

            plan = json.loads(mod.PLAN_PATH.read_text(encoding="utf-8"))
            plan["status"] = "live_authorized_lane_manifest_frozen"
            plan["live_authorized"] = True
            plan["lane_manifest"] = {
                **mod.LANE_MANIFEST_BINDING,
                "status": "frozen",
                "sha256": mod.digest(manifest_raw),
            }
            preview_value = {"index": [], "records": []}
            for row in plan["arm_preflight"]:
                record = {"arm": row["arm"], "task_id": row["task_id"]}
                preview_value["records"].append(record)
                preview_value["index"].append({
                    "arm": row["arm"],
                    "task_id": row["task_id"],
                    "request_sha256": row["request_sha256"],
                    "jev_call_could_affect_selection": row["jev_call_could_affect_selection"],
                })
                row["preview_sha256"] = (
                    mod.digest(mod.canonical(record)) if row["arm"] in {"B", "D"} else None
                )
            preview_path = root / "preview.json"
            preview_raw = mod.canonical(preview_value)
            preview_path.write_bytes(preview_raw)
            preview_binding = {**mod.PREVIEW_ARTIFACT, "sha256": mod.digest(preview_raw)}
            plan["preview_artifact"] = preview_binding
            plan_path = root / "plan.json"
            plan_path.write_bytes(mod.canonical(plan))

            with (
                mock.patch.object(mod, "ROOT", root),
                mock.patch.object(mod, "PREVIEW_ARTIFACT", preview_binding),
                mock.patch.object(mod.preview, "_load_inputs", return_value=(artifact, questions)),
                mock.patch.object(mod.preview, "validate_preview"),
                mock.patch.object(mod.generator, "generate", return_value=(artifact, {})),
            ):
                loaded = mod.load_plan(plan_path, expected_live_authorized=True)
                frozen = mod.preflight(
                    candidate_path, mod.QUESTIONS_PATH, mod.RUBRICS_PATH,
                    root, root, preview_path,
                    expected_live_authorized=True, plan_path=plan_path,
                )
                self.assertEqual(loaded["lane_manifest"]["status"], "frozen")
                self.assertTrue(frozen["live_authorized"])
                self.assertEqual(frozen["planned_jev_calls"], 8)

                plan["lane_manifest"]["sha256"] = "0" * 64
                plan_path.write_bytes(mod.canonical(plan))
                with self.assertRaisesRegex(
                    mod.SuccessorError, "successor_lane_manifest_invalid"
                ):
                    mod.load_plan(plan_path, expected_live_authorized=True)

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

    def test_completed_trials_persist_with_current_lane_bindings(self) -> None:
        lanes = {
            (entry["trial_id"], entry["role"]): entry for entry in lane_entries()
        }
        identities = {trial_id: {"trial_id": trial_id} for trial_id in mod.DISPATCH}
        candidate_sets = {trial_id: "d" * 64 for trial_id in mod.DISPATCH}
        trial_id = mod.DISPATCH[0]
        result = {
            "schema_version": "velgraphing-time-to-correct-v1",
            "terminal_reason": "passed",
            "identity": identities[trial_id],
            "attempts": [{
                "coverage": {"model_calls": True, "context_deliveries": True},
                "bindings": {"candidate_set_sha256": candidate_sets[trial_id]},
                "answer_boundary": {
                    "execution_identity": mod._lane_execution_identity(
                        lanes[(trial_id, "answer")]
                    ),
                },
                "grader_boundary": {
                    "execution_identity": mod._lane_execution_identity(
                        lanes[(trial_id, "grader")]
                    ),
                },
            }],
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            receipt_root = root / "completed"
            mod.save_completed_trial(receipt_root, result)
            loaded = mod._load_current_completed(
                receipt_root, identities, candidate_sets, lanes
            )
            self.assertEqual(set(loaded), {trial_id})
            conflict = {**result, "terminal_reason": "repair_budget_exhausted"}
            with self.assertRaisesRegex(
                mod.MeasurementError, "completed_trial_receipt_conflict"
            ):
                mod.save_completed_trial(receipt_root, conflict)
            wrong_root = root / "wrong"
            wrong = json.loads(json.dumps(result))
            wrong["attempts"][0]["bindings"]["candidate_set_sha256"] = "e" * 64
            mod.save_completed_trial(wrong_root, wrong)
            with self.assertRaisesRegex(
                mod.SuccessorError, "successor_completed_trial_conflict"
            ):
                mod._load_current_completed(
                    wrong_root, identities, candidate_sets, lanes
                )
            incomplete = mod.DISPATCH[1]
            (root / "trials" / incomplete).mkdir(parents=True)
            with self.assertRaisesRegex(
                mod.MeasurementError, "incomplete_trial_requires_parent_audit"
            ):
                mod.require_resumable(root, incomplete, set(loaded))

    def test_incorrect_trial_accepts_unavailable_usage_only_with_complete_calls(self) -> None:
        lanes = {
            (entry["trial_id"], entry["role"]): entry for entry in lane_entries()
        }
        trial_id = mod.DISPATCH[0]
        result = {
            "terminal_reason": "repair_budget_exhausted",
            "attempts": [{
                "coverage": {"model_calls": True, "context_deliveries": True},
                "answer_boundary": {
                    "model_calls_complete": True,
                    "context_deliveries_complete": True,
                    "execution_identity": mod._lane_execution_identity(
                        lanes[(trial_id, "answer")]
                    ),
                },
                "grader_boundary": {
                    "execution_identity": mod._lane_execution_identity(
                        lanes[(trial_id, "grader")]
                    ),
                },
                "model_calls": [{
                    "call_id": f"{role}-0",
                    "kind": role,
                    "model": "gpt-5.6-luna",
                    "provenance": "unavailable",
                    "input_tokens": None,
                    "output_tokens": None,
                    "cached_input_tokens": None,
                    "reasoning_output_tokens": None,
                    "cost_usd": None,
                } for role in mod.LANE_ROLES],
            }],
        }
        mod._require_accepted_trial(result)

        incomplete = json.loads(json.dumps(result))
        incomplete["attempts"][0]["coverage"]["model_calls"] = False
        systemic = json.loads(json.dumps(result))
        systemic["terminal_reason"] = "measurement_error"
        for label, invalid in {"incomplete": incomplete, "systemic": systemic}.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                mod.SuccessorError, "successor_systemic_trial_failure"
            ):
                mod._require_accepted_trial(invalid)

    def test_controller_skips_completed_trials_and_keeps_frozen_order(self) -> None:
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
        completed = {trial_id: result for trial_id in mod.DISPATCH[:2]}
        with (
            mock.patch.object(mod, "preflight", return_value={
                "arm_preflight": plan["arm_preflight"],
            }),
            mock.patch.object(mod, "load_plan", return_value=plan),
            mock.patch.object(mod, "load_questions", return_value=(questions, "a" * 64)),
            mock.patch.object(mod, "load_rubrics", return_value=(rubrics, "b" * 64)),
            mock.patch.object(mod.preview, "_load_inputs", return_value=(artifact, questions)),
            mock.patch.object(mod.dependency, "_packet", return_value={"candidates": []}),
            mock.patch.object(
                mod, "_current_trial_identity",
                side_effect=lambda task, arm, *_: (
                    {"trial_id": f"{arm}-{task}"}, Path("lane"), "c" * 64
                ),
            ),
            mock.patch.object(
                mod, "_load_current_completed", side_effect=lambda *_: dict(completed)
            ),
            mock.patch.object(mod, "require_resumable") as require_resumable,
            mock.patch.object(mod, "save_completed_trial") as save_completed,
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
                list(mod.DISPATCH[2:]),
            )
            self.assertEqual(save_completed.call_count, 14)
            self.assertEqual(require_resumable.call_count, 16)
            self.assertTrue(all(
                call.kwargs["ledger"].cap == 8 for call in run_trial.call_args_list
            ))
            self.assertTrue(all(
                call.kwargs["answer_lane"]["role"] == "answer"
                and call.kwargs["grader_lane"]["role"] == "grader"
                for call in run_trial.call_args_list
            ))

            run_trial.reset_mock()
            save_completed.reset_mock()
            run_trial.return_value = {
                "terminal_reason": "measurement_error",
                "attempts": [{"coverage": {
                    "model_calls": True,
                    "context_deliveries": True,
                }}],
            }
            with self.assertRaisesRegex(
                mod.SuccessorError, "successor_systemic_trial_failure"
            ):
                mod.run_successor(
                    Path("candidates"), Path("questions"), Path("rubrics"),
                    Path("manifests"), Path("lanes"), Path("preview"), Path("run"),
                    lane_manifest=lanes,
                )
            self.assertEqual(run_trial.call_count, 1)
            self.assertEqual(save_completed.call_count, 1)


if __name__ == "__main__":
    unittest.main()
