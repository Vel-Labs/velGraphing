"""Offline D-01 four-arm controller tests. No provider or model calls."""

from __future__ import annotations

import copy
from contextlib import nullcontext, redirect_stderr
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from packages.core import Graph, SourceIdentityV4, SourceSnapshotV4
from packages.core import jev
from scripts.benchmarks import time_to_correct_host as host
from tests.core.test_ranked_context_selection import (
    SourceReader,
    candidate,
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
if any(key in json.dumps(request) for key in ("arm", "route", "jev_status", "request_sha256", "score")): raise SystemExit(8)
if request["instructions"] != ["Evidence list order is not source order. Determine source adjacency only from matching path values and byte_start and byte_end coordinates.", "Cite each supporting evidence ID exactly as shown, enclosed in brackets."]: raise SystemExit(9)
if any(set(row) != {"id", "path", "source_sha256", "byte_start", "byte_end", "relationship_parent_candidate_id", "excerpt"} for row in request["evidence"]): raise SystemExit(10)
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
        with mock.patch.object(mod, "FINAL_ANSWER_BYTES", 1400):
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

    def test_successor_plan_is_exact_and_authorized(self) -> None:
        plan = mod.validate_plan(expected_live_authorized=True)
        self.assertTrue(plan["live_authorized"])
        self.assertEqual(plan["provider_calls_executed"], 2)
        self.assertEqual(plan["successor_provider_calls_executed"], 2)
        self.assertEqual(plan["repair_provider_calls_executed"], 0)
        self.assertEqual(plan["repair_jev_calls_authorized"], 1)
        self.assertEqual(plan["aggregate_authorized_call_total"], 6)
        self.assertEqual(plan["aggregate_completed_call_total"], 5)
        self.assertEqual(plan["repaired_candidate_commit"], mod.REPAIRED_CANDIDATE_COMMIT)
        self.assertEqual(plan["package_candidate_sha256"], mod.PACKAGE_CANDIDATE_SHA256)
        self.assertEqual(plan["successor_run_root"], mod.SUCCESSOR_RUN_ROOT)
        self.assertEqual(plan["repair_run_root"], mod.REPAIR_RUN_ROOT)
        self.assertEqual(plan["private_result_sha256"], mod.PRIVATE_RESULT_SHA256)
        self.assertEqual(plan["successor_result_sha256"], mod.SUCCESSOR_RESULT_SHA256)
        self.assertEqual(plan["limits"]["maximum_jev_calls"], 2)
        self.assertEqual(plan["limits"]["retries"], 0)
        self.assertEqual(plan["answer_rubric_sha256"], mod.digest(mod.canonical(mod.RUBRIC)))

    def test_handoff_timeouts_fit_serial_trial_deadline(self) -> None:
        self.assertGreater(
            mod.HANDOFF_PROCESS_TIMEOUT_SECONDS,
            mod.HANDOFF_WAIT_SECONDS,
        )
        required_seconds = (
            mod.PROVIDER_TIMEOUT_SECONDS
            + 2 * mod.HANDOFF_PROCESS_TIMEOUT_SECONDS
        )
        self.assertGreaterEqual(
            mod.REPAIR_TRIAL_WALL_LIMIT_SECONDS,
            required_seconds,
        )

    def test_repair_lane_commands_bind_root_lane_and_wait(self) -> None:
        for lane in ("answer", "grader"):
            command = [
                sys.executable,
                "scripts/benchmarks/time_to_correct_handoff.py", "wait",
                "--run-root", str(self.root), "--trial-id", "D-D-01",
                "--attempt", "0", "--lane", lane,
                "--wait-seconds", str(mod.HANDOFF_WAIT_SECONDS),
            ]
            path = self.root / f"{lane}-repair-argv.json"
            path.write_bytes(mod.canonical({"D": command}))
            self.assertEqual(mod._repair_argv(path, self.root, lane), command)
            command[-1] = "599"
            path.write_bytes(mod.canonical({"D": command}))
            with self.assertRaisesRegex(
                mod.ControllerError, "dependency_lane_commands_invalid"
            ):
                mod._repair_argv(path, self.root, lane)

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

    def test_d01_context_preserves_frozen_import_order_and_relationship_child(self) -> None:
        merge_import = b"from sorts.merge_sort import merge_sort"
        quick_import = b"from sorts.quick_sort import quick_sort"
        benchmark_raw = b"\n".join((merge_import, quick_import, b""))
        quick_prefix = b"from random import randrange\n\n\n"
        quick_implementation = (
            b"def quick_sort(collection: list) -> list:\n"
            b"    \"\"\"A pure Python implementation of quicksort algorithm.\n\n"
            b"    :param collection: a mutable collection of comparable items\n"
            b"    :return: the same collection ordered in ascending order\n\n"
            b"    Examples:\n"
            b"    >>> quick_sort([0, 5, 3, 2, 2])\n"
            b"    [0, 2, 2, 3, 5]\n"
            b"    >>> quick_sort([])\n"
            b"    []\n"
            b"    >>> quick_sort([-2, 5, 0, -45])\n"
            b"    [-45, -2, 0, 5]\n"
            b"    \"\"\"\n"
            b"    # Base case: if the collection has 0 or 1 elements, it is already sorted\n"
            b"    if len(collection) < 2:\n"
            b"        return collection\n\n"
            b"    # Randomly select a pivot index and remove the pivot element from the collection\n"
            b"    pivot_index = randrange(len(collection))\n"
            b"    pivot = collection.pop(pivot_index)\n\n"
            b"    # Partition the remaining elements into two groups: lesser or equal, and greater\n"
            b"    lesser = [item for item in collection if item <= pivot]\n"
            b"    greater = [item for item in collection if item > pivot]\n\n"
            b"    # Recursively sort the lesser and greater groups, and combine with the pivot\n"
            b"    return [*quick_sort(lesser), pivot, *quick_sort(greater)]\n\n\n"
        )
        quick_raw = quick_prefix + quick_implementation
        benchmark_path = "sorts/benchmark_sorts.py"
        quick_path = "sorts/quick_sort.py"
        benchmark_sha = hashlib.sha256(benchmark_raw).hexdigest()
        quick_sha = hashlib.sha256(quick_raw).hexdigest()
        merge = candidate(
            "merge-import", benchmark_path, benchmark_sha, 0, len(merge_import),
            required=True,
        )
        quick_parent = candidate(
            "quick-import",
            benchmark_path,
            benchmark_sha,
            len(merge_import) + 1,
            len(merge_import) + 1 + len(quick_import),
            required=False,
        )
        quick_child = candidate(
            "quick-implementation",
            quick_path,
            quick_sha,
            len(quick_prefix),
            len(quick_raw),
            required=False,
            relationship_parent_candidate_id=quick_parent.candidate_id,
        )
        candidates = (merge, quick_parent, quick_child)
        reader = SourceReader({benchmark_path: benchmark_raw, quick_path: quick_raw})
        snapshot = SourceSnapshotV4((
            SourceIdentityV4(benchmark_path, len(benchmark_raw), benchmark_sha),
            SourceIdentityV4(quick_path, len(quick_raw), quick_sha),
        ))
        graph = graph_with_relationship_edge(
            Graph(tuple(source_record(
                item.record_id,
                item.source_path,
                item.source_sha256,
                reader.sources[item.source_path][item.byte_start:item.byte_end].decode(),
            ) for item in candidates)),
            snapshot,
            reader,
            quick_parent,
            quick_child,
        )
        run = {
            "route": "typed_graph",
            "candidates": [{
                "id": item.candidate_id,
                "path": item.source_path,
                "source_sha256": item.source_sha256,
                "byte_start": item.byte_start,
                "byte_end": item.byte_end,
                "required": item.required,
                "record_id": item.record_id,
                "relationship_parent_candidate_id": (
                    item.relationship_parent_candidate_id
                ),
            } for item in candidates],
        }
        lane = {
            "plain_graph": graph,
            "typed_graph": graph,
            "snapshot": snapshot,
            "reader": reader,
        }

        selection = mod._selection(run, lane, self.question, "C", None)
        model_input = host._answer_input(
            mod._answer_evidence(self.question["prompt"], selection)
        )
        evidence = model_input["evidence"]

        self.assertEqual(
            [row["excerpt"] for row in evidence[:2]],
            [merge_import.decode(), quick_import.decode()],
        )
        self.assertLess(evidence[0]["byte_start"], evidence[1]["byte_start"])
        self.assertEqual(evidence[2]["excerpt"], quick_implementation.decode())
        self.assertEqual(
            evidence[2]["relationship_parent_candidate_id"],
            quick_parent.candidate_id,
        )
        self.assertEqual(
            model_input["instructions"][0],
            "Evidence list order is not source order. Determine source adjacency "
            "only from matching path values and byte_start and byte_end coordinates.",
        )

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
        with mock.patch.object(
            mod,
            "validate_plan",
            side_effect=mod.ControllerError("dependency_plan_mismatch"),
        ), self.assertRaisesRegex(mod.ControllerError, "dependency_live_not_authorized"):
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

    def test_run_command_requires_complete_preconditions(self) -> None:
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

        with tempfile.TemporaryDirectory(dir=self.root) as raw:
            sandbox = Path(raw)
            checkout = sandbox / "checkout"
            outside = sandbox / "outside"
            checkout.mkdir(mode=0o700)
            outside.mkdir(mode=0o700)
            run = outside / "run"
            run.mkdir(mode=0o700)
            (checkout / ".velgraphing-local").symlink_to(outside, target_is_directory=True)
            with mock.patch.object(mod, "ROOT", checkout), self.assertRaisesRegex(
                mod.ControllerError, "dependency_run_root_invalid"
            ):
                mod._validated_run_root(checkout / ".velgraphing-local" / "run")

    def test_lane_commands_require_absolute_executables(self) -> None:
        commands = {
            arm: [sys.executable, "-c", "pass"] for arm in mod.ARMS
        }
        valid = self.root / "valid-argv.json"
        valid.write_bytes(mod.canonical(commands))
        self.assertEqual(mod._argv_map(valid, self.root), commands)

        commands["A"][0] = "python3"
        relative = self.root / "relative-argv.json"
        relative.write_bytes(mod.canonical(commands))
        with self.assertRaisesRegex(
            mod.ControllerError, "dependency_lane_commands_invalid"
        ):
            mod._argv_map(relative, self.root)

        d_only = {"D": [sys.executable, "-c", "pass"]}
        d_only_path = self.root / "d-only-argv.json"
        d_only_path.write_bytes(mod.canonical(d_only))
        self.assertEqual(mod._argv_map(d_only_path, self.root, {"D"}), d_only)
        with self.assertRaisesRegex(
            mod.ControllerError, "dependency_lane_commands_invalid"
        ):
            mod._argv_map(valid, self.root, {"D"})

    def test_repair_observation_loader_rejects_each_wrong_hash(self) -> None:
        result_raw = mod.canonical({"result": "fixture"})
        observation = {"observation": "fixture"}
        observation_raw = mod.canonical(observation)
        (self.root / "result.json").write_bytes(result_raw)
        observations = self.root / "jev-observations"
        observations.mkdir()
        (observations / "B.json").write_bytes(observation_raw)
        result_sha = mod.digest(result_raw)
        observation_sha = mod.digest(observation_raw)

        with mock.patch.object(mod, "SUCCESSOR_RESULT_SHA256", result_sha), mock.patch.object(
            mod, "SUCCESSOR_B_OBSERVATION_SHA256", observation_sha
        ):
            self.assertEqual(mod._load_repair_b_observation(self.root), observation)
        for result_identity, observation_identity in (
            ("0" * 64, observation_sha),
            (result_sha, "0" * 64),
        ):
            with self.subTest(
                result_identity=result_identity,
                observation_identity=observation_identity,
            ), mock.patch.object(
                mod, "SUCCESSOR_RESULT_SHA256", result_identity
            ), mock.patch.object(
                mod, "SUCCESSOR_B_OBSERVATION_SHA256", observation_identity
            ), self.assertRaisesRegex(
                mod.ControllerError, "dependency_repair_replay_identity_mismatch"
            ):
                mod._load_repair_b_observation(self.root)

    def test_confirm_d_cli_rejects_nonplanned_run_root(self) -> None:
        arguments = [
            "confirm-d",
            "--candidates", str(self.root),
            "--questions", str(self.root),
            "--manifests-root", str(self.root),
            "--lanes-root", str(self.root),
            "--preview", str(self.root),
            "--run-root", str(self.root),
            "--answer-argv-json", str(self.root / "answer.json"),
            "--grader-argv-json", str(self.root / "grader.json"),
            "--replay-observations-root", str(self.root),
            "--output", str(self.root / "result.json"),
        ]
        error = io.StringIO()
        with mock.patch.object(mod, "validate_plan"), redirect_stderr(error):
            self.assertEqual(mod.main(arguments), 2)
        self.assertIn("dependency_run_root_plan_mismatch", error.getvalue())

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
        with mock.patch.object(mod, "_validated_run_root", return_value=run_root):
            observations = mod._load_preserved_observations(run_root)
        self.assertEqual(set(observations), {"B", "D"})

        replay_root = self.root / "four-arm-replay"
        replay_root.mkdir(mode=0o700)
        calls.clear()
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            mod, "regenerate_pool", side_effect=regenerate
        ), patches[5]:
            replay = mod.run_four_arm(
                self.root / "candidates.json",
                self.root / "questions.json",
                self.root,
                self.root,
                self.root / "preview.json",
                replay_root,
                answer_argv=commands,
                grader_argv=graders,
                live_authorized=True,
                evaluate=lambda *args, **kwargs: self.fail("provider called"),
                jev_observations=observations,
                execution="fixture",
            )
        self.assertEqual(replay["controller_preflight"]["jev_execution"], "replay")
        self.assertFalse((replay_root / "jev-calls").exists())
        self.assertEqual(
            [
                row["attempts"][0]["candidate_observation"]["jev_execution"]
                for row in replay["results"]
            ],
            ["off", "replay", "off", "replay"],
        )

        invalid_observations = copy.deepcopy(observations)
        invalid_observations["B"]["request_sha256"] = "0" * 64
        invalid_root = self.root / "four-arm-invalid-replay"
        invalid_root.mkdir(mode=0o700)
        calls.clear()
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
                invalid_root,
                answer_argv=commands,
                grader_argv=graders,
                live_authorized=True,
                evaluate=lambda *args, **kwargs: self.fail("provider called"),
                jev_observations=invalid_observations,
                execution="fixture",
            )
        self.assertEqual(calls, ["direct", "direct"])
        self.assertFalse((invalid_root / "jev-calls").exists())

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

    def test_d_confirmation_replays_b_and_runs_only_one_live_d_call(self) -> None:
        b_result = self.run_arm("B")
        b_observation = b_result["attempts"][0]["jev_observation"]
        run_root = self.root / "d-confirmation"
        run_root.mkdir(mode=0o700)
        (self.root / self.question["corpus"]).mkdir()
        artifact = {
            "runs": [
                {**copy.deepcopy(self.run), "route": "direct"},
                {**copy.deepcopy(self.run), "route": "typed_graph"},
            ]
        }
        calls = []

        def regenerate(route, question, manifests, lanes, trial=None):
            calls.append((route, trial is not None))
            if trial is None:
                return {**copy.deepcopy(self.run), "route": route}, self.lane
            return self.regenerate(trial, route)

        patches = (
            mock.patch.object(mod, "preflight", return_value={"live_authorized": True}),
            mock.patch.object(mod.preview, "_load_inputs", return_value=(artifact, {mod.TASK_ID: self.question})),
            mock.patch.object(mod.generator, "_manifest", return_value={"commit": "a" * 40}),
            mock.patch.object(mod, "lane_state_sha256", return_value="d" * 64),
            mock.patch.object(mod, "regenerate_pool", side_effect=regenerate),
            mock.patch.object(mod, "FINAL_ANSWER_BYTES", 1400),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            evaluate = mock.Mock(side_effect=self.evaluator)
            result = mod.run_d_confirmation(
                self.root / "candidates.json",
                self.root / "questions.json",
                self.root,
                self.root,
                self.root / "preview.json",
                run_root,
                answer_argv=[sys.executable, "-c", ANSWER_CODE],
                grader_argv=[sys.executable, "-c", GRADER_CODE],
                b_observation=b_observation,
                live_authorized=True,
                evaluate=evaluate,
                execution="fixture",
            )
        self.assertEqual(result["schema_version"], "velgraphing-d01-d-repair-result-v1")
        self.assertEqual(result["b_replay"]["order_source"], "reranked")
        self.assertEqual(
            result["result"]["attempts"][0]["candidate_observation"]["jev_execution"],
            "live",
        )
        self.assertEqual(calls, [("direct", False), ("typed_graph", True)])
        self.assertEqual(len(list((run_root / "jev-calls").glob("*.json"))), 1)
        evaluate.assert_called_once()
        self.assertEqual(
            result["result"]["budget"]["wall_limit_ns"],
            mod.REPAIR_TRIAL_WALL_LIMIT_SECONDS * 1_000_000_000,
        )


if __name__ == "__main__":
    unittest.main()
