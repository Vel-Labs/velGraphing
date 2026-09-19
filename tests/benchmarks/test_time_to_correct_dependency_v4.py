"""Offline D-01 four-arm controller tests. No provider or model calls."""

from __future__ import annotations

import copy
from contextlib import nullcontext, redirect_stderr
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from packages.core import Graph
from packages.core import jev
from tests.core.test_ranked_context_selection import (
    fixture,
    graph_with_relationship_edge,
    source_record,
)


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "time_to_correct_dependency_v4",
    ROOT / "scripts/benchmarks/time_to_correct_dependency_v4.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


ANSWER_CODE = r'''
import json, sys
request = json.load(sys.stdin)
if set(request) != {"schema_version", "question", "instructions", "evidence", "response_contract"}: raise SystemExit(7)
if any(key in json.dumps(request) for key in ("arm", "route", "jev_status", "request_sha256", "score", "relationship_parent")): raise SystemExit(8)
candidate = request["evidence"][0]["id"]
result = {"schema_version":"velgraphing-answer-output-v1","answer_text":f"fixture [{candidate}]","usage":None,"model_calls_complete":True,"context_deliveries_complete":True}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
'''

GRADER_CODE = r'''
import json, sys
request = json.load(sys.stdin)
if set(request) != {"schema_version", "answer_text", "rubric", "response_contract"}: raise SystemExit(7)
if set(request["rubric"]) != {"required_facts", "critical_facts", "acceptable_spans"}: raise SystemExit(8)
result = {"schema_version":"velgraphing-grader-output-v1","required_fact_score":3,"required_fact_maximum":3,"critical_facts_exact":True,"unsupported_material_claims":0,"grader_id":"fixture-grader","usage":None,"model_calls_complete":True}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
'''


class DependencyControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=local)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        graph, snapshot, reader, candidates = fixture()
        self.source = self.root / candidates[0].source_path
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(reader.sources[candidates[0].source_path])
        displaced = replace(candidates[2], candidate_id="c3", record_id="record-c3")
        child = replace(candidates[2], relationship_parent_candidate_id="c1")
        graph = Graph((*graph.records, source_record(
            displaced.record_id,
            displaced.source_path,
            displaced.source_sha256,
            "optional-b",
        )))
        graph = graph_with_relationship_edge(graph, snapshot, reader, candidates[1], child)
        pool = (candidates[0], displaced, candidates[1], child)
        rows = []
        for candidate in pool:
            rows.append({
                "id": candidate.candidate_id,
                "path": candidate.source_path,
                "source_sha256": candidate.source_sha256,
                "byte_start": candidate.byte_start,
                "byte_end": candidate.byte_end,
                "required": candidate.required,
                "record_id": candidate.record_id,
                "relationship_parent_candidate_id": candidate.relationship_parent_candidate_id,
            })
        self.run = {
            "task_id": mod.TASK_ID,
            "corpus": "thealgorithms-python",
            "prompt_sha256": mod.digest(b"fixture dependency question"),
            "route": "typed_graph",
            "source_snapshot_sha256": snapshot.snapshot_sha256,
            "sources": [{
                "path": candidates[0].source_path,
                "source_sha256": candidates[0].source_sha256,
                "byte_length": len(self.source.read_bytes()),
            }],
            "candidates": rows,
            "controls": {"fixture": True},
        }
        self.lane = {
            "lane": self.root,
            "plain_graph": graph,
            "typed_graph": graph,
            "snapshot": snapshot,
            "reader": reader,
        }
        self.question = {
            "id": mod.TASK_ID,
            "corpus": "thealgorithms-python",
            "prompt": "fixture dependency question",
        }

    def regenerate(self, trial, route):
        audit = mod.SourceReadAudit(trial, 2)
        with trial.phase("cold_graph_build"):
            for _ in range(2):
                raw = self.lane["reader"].read_bytes(self.run["sources"][0]["path"])
                audit.record("scanner", self.run["sources"][0]["path"], raw)
        with trial.phase("candidate_discovery"):
            pass
        with trial.phase("retrieval"):
            pass
        run = copy.deepcopy(self.run)
        run["route"] = route
        return run, {
            **self.lane,
            "reader": mod.AuditedReader(self.lane["reader"], audit),
            "source_audit": audit,
        }

    @staticmethod
    def evaluator(packet, root, **kwargs):
        prepared = jev.prepare(packet, root, kwargs["model"])
        scores = {"c1": 2, "c2": 2, "c3": 0, "c0": 0}
        response = {
            "model": kwargs["model"],
            "answers": {
                f"candidate_{index}": {
                    "type": "score",
                    "score": scores[row["id"]],
                    "confidence": 1.0,
                    "probabilities": {
                        str(value): float(value == scores[row["id"]])
                        for value in range(3)
                    },
                    "legend": jev._rubric_legend(),
                }
                for index, row in enumerate(packet["candidates"])
            },
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }
        return jev.evaluate(
            packet,
            root,
            mode="rerank",
            allow_network=True,
            approved_request_sha256=prepared["request_sha256"],
            model=kwargs["model"],
            transport=lambda *_: response,
        )

    @staticmethod
    def fallback(packet, root, **kwargs):
        prepared = jev.prepare(packet, root, kwargs["model"])
        return jev.evaluate(
            packet,
            root,
            mode="rerank",
            allow_network=True,
            approved_request_sha256=prepared["request_sha256"],
            model=kwargs["model"],
            transport=lambda *_: (_ for _ in ()).throw(OSError()),
        )

    def run_arm(self, arm: str, evaluator=None):
        ledger_root = self.root / f"ledger-{arm}"
        ledger_root.mkdir(mode=0o700)
        ledger = mod.LiveJevBudget(ledger_root, 2)
        with mock.patch.object(mod, "FINAL_ANSWER_BYTES", 1250):
            return mod.run_arm(
                arm,
                "a" * 40,
                "d" * 64,
                self.question,
                {**self.run, "route": mod.ARMS[arm]},
                self.regenerate,
                answer_argv=[sys.executable, "-c", ANSWER_CODE],
                grader_argv=[sys.executable, "-c", GRADER_CODE],
                cwd=self.root,
                ledger=ledger,
                evaluate=evaluator or self.evaluator,
                live_authorized=True,
                execution="fixture",
            )

    def test_plan_is_exact_and_non_authorizing(self) -> None:
        plan = mod.validate_plan()
        self.assertFalse(plan["live_authorized"])
        self.assertEqual(plan["limits"]["maximum_jev_calls"], 2)
        self.assertEqual(plan["limits"]["retries"], 0)
        self.assertEqual(plan["answer_rubric_sha256"], mod.digest(mod.canonical(mod.RUBRIC)))

    def test_c_omits_child_d_can_select_it_and_required_survives(self) -> None:
        c = self.run_arm("C")
        d = self.run_arm("D")
        c_observation = c["attempts"][0]["candidate_observation"]
        d_observation = d["attempts"][0]["candidate_observation"]
        self.assertNotIn("c2", c_observation["selected_candidate_ids"])
        self.assertIn("c2", d_observation["selected_candidate_ids"])
        self.assertEqual(c_observation["required_candidate_ids"], ["c0"])
        self.assertEqual(d_observation["required_candidate_ids"], ["c0"])
        self.assertEqual(c["budget"]["max_repairs"], 0)
        self.assertEqual(d["budget"]["max_repairs"], 0)

    def test_provider_fallback_keeps_verified_baseline(self) -> None:
        result = self.run_arm("D", self.fallback)
        attempt = result["attempts"][0]
        self.assertEqual(attempt["phase_status"]["fallback"], "observed")
        self.assertEqual(attempt["candidate_observation"]["order_source"], "baseline")
        self.assertEqual(result["terminal_reason"], "passed")

    def test_phase_accounting_and_arm_blind_subprocesses_are_complete(self) -> None:
        result = self.run_arm("D")
        status = result["attempts"][0]["phase_status"]
        self.assertNotIn("missing", status.values())
        for phase in (
            "cold_graph_build", "candidate_discovery", "retrieval", "jev_preparation",
            "provider", "source_revalidation", "response_validation",
            "source_capture", "context_composition", "answer_generation", "grading",
        ):
            self.assertEqual(status[phase], "observed")
        self.assertTrue(result["attempts"][0]["context_deliveries"])
        self.assertTrue(result["attempts"][0]["coverage"]["source_operations"])
        self.assertGreater(
            result["attempts"][0]["candidate_observation"]["source_operation_count"],
            0,
        )

    def test_live_gate_and_call_ledger_stop_conditions(self) -> None:
        ledger_root = self.root / "cap-ledger"
        ledger_root.mkdir(mode=0o700)
        ledger = mod.LiveJevBudget(ledger_root, 2)
        with self.assertRaisesRegex(mod.ControllerError, "dependency_live_not_authorized"):
            mod.run_arm(
                "A", "a" * 40, "d" * 64, self.question, self.run, self.regenerate,
                answer_argv=[sys.executable, "-c", ANSWER_CODE],
                grader_argv=[sys.executable, "-c", GRADER_CODE],
                cwd=self.root, ledger=ledger,
            )
        with self.assertRaisesRegex(mod.ControllerError, "dependency_live_not_authorized"):
            mod.run_arm(
                "A", "a" * 40, "d" * 64, self.question, self.run, self.regenerate,
                answer_argv=[sys.executable, "-c", ANSWER_CODE],
                grader_argv=[sys.executable, "-c", GRADER_CODE],
                cwd=self.root, ledger=ledger, live_authorized=True,
            )
        ledger.reserve("B-D-01", "a" * 64)
        ledger.reserve("D-D-01", "b" * 64)
        with self.assertRaisesRegex(mod.MeasurementError, "jev_call_cap_exhausted"):
            ledger.reserve("extra-D-01", "c" * 64)

    def test_run_command_cannot_execute_while_plan_is_off(self) -> None:
        inputs = []
        for name in ("candidates.json", "questions.json", "preview.json"):
            path = self.root / name
            path.write_text("{}", encoding="utf-8")
            inputs.append(path)
        output = self.root / "result.json"
        with redirect_stderr(io.StringIO()):
            status = mod.main([
                "run",
                "--candidates", str(inputs[0]),
                "--questions", str(inputs[1]),
                "--manifests-root", str(self.root),
                "--lanes-root", str(self.root),
                "--preview", str(inputs[2]),
                "--run-root", str(self.root),
                "--answer-argv-json", str(self.root / "answer.json"),
                "--grader-argv-json", str(self.root / "grader.json"),
                "--output", str(output),
            ])
        self.assertEqual(status, 2)
        self.assertFalse(output.exists())

    def test_run_root_is_checkout_local_and_private(self) -> None:
        self.assertEqual(mod._validated_run_root(self.root), self.root)
        foreign = self.root / ".velgraphing-local" / "run"
        foreign.mkdir(parents=True, mode=0o700)
        with self.assertRaisesRegex(mod.ControllerError, "dependency_run_root_invalid"):
            mod._validated_run_root(foreign)
        with tempfile.TemporaryDirectory(dir=self.root.parent) as raw:
            public = Path(raw)
            public.chmod(0o755)
            with self.assertRaisesRegex(mod.ControllerError, "dependency_run_root_invalid"):
                mod._validated_run_root(public)

    def test_actual_source_read_bypasses_fail_coverage(self) -> None:
        def run(regenerate, arm="A", evaluator=None):
            root = self.root / f"bypass-{arm}-{run.calls}"
            run.calls += 1
            root.mkdir(mode=0o700)
            return mod.run_arm(
                arm, "a" * 40, "d" * 64, self.question,
                {**self.run, "route": mod.ARMS[arm]}, regenerate,
                answer_argv=[sys.executable, "-c", ANSWER_CODE],
                grader_argv=[sys.executable, "-c", GRADER_CODE],
                cwd=self.root, ledger=mod.LiveJevBudget(root, 2),
                evaluate=evaluator or self.evaluator,
                live_authorized=True, execution="fixture",
            )
        run.calls = 0

        def scanner_bypass(trial, route):
            frozen, lane = self.regenerate(trial, route)
            lane["source_audit"].scanner_expected += 1
            return frozen, lane

        def selection_bypass(trial, route):
            frozen, lane = self.regenerate(trial, route)
            lane["reader"] = self.lane["reader"]
            return frozen, lane

        for regenerate in (scanner_bypass, selection_bypass):
            with self.subTest(regenerate=regenerate.__name__):
                result = run(regenerate)
                self.assertEqual(result["terminal_reason"], "measurement_error")
                self.assertEqual(
                    result["attempts"][0]["failure_reason"],
                    "dependency_source_coverage_incomplete",
                )

        with mock.patch.object(mod, "_observe_jev_reads", return_value=nullcontext()):
            result = run(self.regenerate, arm="B")
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(
            result["attempts"][0]["failure_reason"],
            "dependency_source_coverage_incomplete",
        )

    def test_run_four_arm_pairs_calls_and_stops_on_systemic_b_failure(self) -> None:
        run_root = self.root / "four-arm"
        run_root.mkdir(mode=0o700)
        (self.root / self.question["corpus"]).mkdir()
        artifact = {
            "runs": [
                {**copy.deepcopy(self.run), "route": "direct"},
                {**copy.deepcopy(self.run), "route": "typed_graph"},
            ]
        }
        commands = {
            arm: [sys.executable, "-c", ANSWER_CODE] for arm in mod.ARMS
        }
        graders = {
            arm: [sys.executable, "-c", GRADER_CODE] for arm in mod.ARMS
        }
        calls = []

        def regenerate(route, question, manifests, lanes, trial):
            calls.append(route)
            return self.regenerate(trial, route)

        patches = (
            mock.patch.object(mod, "preflight", return_value={"live_authorized": True}),
            mock.patch.object(mod.preview, "_load_inputs", return_value=(artifact, {mod.TASK_ID: self.question})),
            mock.patch.object(mod.generator, "_manifest", return_value={"commit": "a" * 40}),
            mock.patch.object(mod, "lane_state_sha256", return_value="d" * 64),
            mock.patch.object(mod, "regenerate_pool", side_effect=regenerate),
            mock.patch.object(mod, "FINAL_ANSWER_BYTES", 1250),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = mod.run_four_arm(
                self.root / "candidates.json",
                self.root / "questions.json",
                self.root,
                self.root,
                self.root / "preview.json",
                run_root,
                answer_argv=commands,
                grader_argv=graders,
                live_authorized=True,
                evaluate=self.evaluator,
                execution="fixture",
            )
        self.assertEqual(
            [row["identity"]["arm"] for row in result["results"]],
            ["A", "B", "C", "D"],
        )
        self.assertEqual(
            result["controller_preflight"]["ttc_allocation"],
            "separate_not_in_arm_ttc",
        )
        self.assertGreaterEqual(result["controller_preflight"]["elapsed_ns"], 0)
        self.assertEqual(calls, ["direct", "direct", "typed_graph", "typed_graph"])
        self.assertEqual(
            result["results"][0]["attempts"][0]["candidate_observation"]["pool_sha256"],
            result["results"][1]["attempts"][0]["candidate_observation"]["pool_sha256"],
        )
        self.assertEqual(
            result["results"][2]["attempts"][0]["candidate_observation"]["pool_sha256"],
            result["results"][3]["attempts"][0]["candidate_observation"]["pool_sha256"],
        )
        receipts = list((run_root / "jev-calls").glob("*.json"))
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(row["budget"]["max_repairs"] == 0 for row in result["results"]))

        failed_root = self.root / "four-arm-failure"
        failed_root.mkdir(mode=0o700)
        calls.clear()
        failed_commands = dict(commands)
        failed_commands["B"] = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('{}')",
        ]
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            mod, "regenerate_pool", side_effect=regenerate
        ), patches[5], self.assertRaisesRegex(
            mod.ControllerError, "dependency_systemic_trial_failure"
        ):
            mod.run_four_arm(
                self.root / "candidates.json",
                self.root / "questions.json",
                self.root,
                self.root,
                self.root / "preview.json",
                failed_root,
                answer_argv=failed_commands,
                grader_argv=graders,
                live_authorized=True,
                evaluate=self.evaluator,
                execution="fixture",
            )
        self.assertEqual(calls, ["direct", "direct"])

        incomplete_cases = {
            "answer-model": (
                ANSWER_CODE.replace(
                    '"model_calls_complete":True', '"model_calls_complete":False'
                ),
                GRADER_CODE,
            ),
            "answer-context": (
                ANSWER_CODE.replace(
                    '"context_deliveries_complete":True',
                    '"context_deliveries_complete":False',
                ),
                GRADER_CODE,
            ),
            "grader-model": (
                ANSWER_CODE,
                GRADER_CODE.replace(
                    '"model_calls_complete":True', '"model_calls_complete":False'
                ),
            ),
        }
        for name, (answer_code, grader_code) in incomplete_cases.items():
            with self.subTest(coverage=name):
                incomplete_root = self.root / f"four-arm-incomplete-{name}"
                incomplete_root.mkdir(mode=0o700)
                calls.clear()
                incomplete_commands = dict(commands)
                incomplete_graders = dict(graders)
                incomplete_commands["B"] = [sys.executable, "-c", answer_code]
                incomplete_graders["B"] = [sys.executable, "-c", grader_code]
                with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
                    mod, "regenerate_pool", side_effect=regenerate
                ), patches[5], self.assertRaisesRegex(
                    mod.ControllerError, "dependency_systemic_trial_failure"
                ):
                    mod.run_four_arm(
                        self.root / "candidates.json",
                        self.root / "questions.json",
                        self.root,
                        self.root,
                        self.root / "preview.json",
                        incomplete_root,
                        answer_argv=incomplete_commands,
                        grader_argv=incomplete_graders,
                        live_authorized=True,
                        evaluate=self.evaluator,
                        execution="fixture",
                    )
                self.assertEqual(calls, ["direct", "direct"])


if __name__ == "__main__":
    unittest.main()
