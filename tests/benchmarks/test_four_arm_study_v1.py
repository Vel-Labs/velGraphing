"""Offline contract tests for the successor four-arm study."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import re
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks/velgraphing-four-arm-study-v1"
LANES = Path(os.environ.get(
    "VELGRAPHING_CORPUS_LANE_ROOT",
    ROOT / "benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4",
))
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))

import four_arm_study_v1 as study  # noqa: E402
from time_to_correct_calibration import _v3_trial_measurement  # noqa: E402
from time_to_correct_host import (  # noqa: E402
    _answer_input, _grader_input, run_process_trial,
)

CUSTODY = ROOT / study.SUCCESSOR_WITNESS_CUSTODY


class FourArmPublicBoundaryTests(unittest.TestCase):
    def test_installed_graph_find_trial_transports_complete_nonprovider_measurement(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="t050-canary-", dir=local) as raw:
            root = Path(raw)
            lane = root / "lane"
            (lane / "src").mkdir(parents=True)
            (lane / "tests").mkdir()
            (lane / "src/cancel.py").write_text(
                "def cancel_task(task):\n    return task.cancel()\n",
                encoding="utf-8",
            )
            (lane / "tests/test_cancel.py").write_text(
                "def test_cancel_task(task):\n    assert cancel_task(task)\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q", str(lane)], check=True)
            subprocess.run(
                ["git", "-C", str(lane), "add", "src/cancel.py", "tests/test_cancel.py"],
                check=True,
            )
            sources = [
                {"path": path.relative_to(lane).as_posix(),
                 "byte_length": len(path.read_bytes()),
                 "sha256": study.digest(path.read_bytes())}
                for path in sorted(lane.rglob("*.py"))
            ]
            source_manifest = {
                "sources": sources,
                "snapshot_sha256": study._sha256({"sources": sources}),
            }
            run_root = root / "run"
            run_root.mkdir()
            installed = study._install_graph_find(run_root)
            prompt = "Find cancel_task implementation and test behavior."
            rubric = {
                "required_facts": ["cancel_task"],
                "critical_facts": ["cancel_task"],
                "acceptable_spans": ["cancel_task"],
            }
            identity = {
                "run_id": "t050-fixture", "trial_id": "C-S-01",
                "task_id": "S-01", "arm": "C", "repository_id": "fixture",
                "repository_commit": "a" * 40,
                "source_snapshot_sha256": source_manifest["snapshot_sha256"],
                "dirty_state_sha256": study.digest(b""),
                "answer_model": "fixture-answer", "reasoning": "none",
                "prompt_sha256": study.digest(prompt.encode()),
                "rubric_sha256": study.digest(study.canonical(rubric)),
                "rubric_version": "t050-fixture-v1", "answer_lane_id": "answer-C-S-01",
            }
            answer_code = (
                "import json,sys; x=json.load(sys.stdin); e=x['evidence']; "
                "a=' '.join(r['excerpt'] for r in e)+' '+' '.join('['+r['id']+']' for r in e); "
                "sys.stdout.write(json.dumps({'schema_version':'velgraphing-answer-output-v1',"
                "'answer_text':a,'usage':None,'model_calls_complete':False,"
                "'context_deliveries_complete':True},sort_keys=True,separators=(',',':')))"
            )
            grader_code = (
                "import json,sys; x=json.load(sys.stdin); fs=x['rubric']['required_facts']; "
                "a=x['answer_text'].casefold(); d=[f.casefold() in a for f in fs]; n=len(fs); s=sum(d); "
                "sys.stdout.write(json.dumps({'schema_version':'velgraphing-grader-output-v1',"
                "'required_fact_score':s,'required_fact_maximum':n,"
                "'critical_facts_exact':all(f.casefold() in a for f in x['rubric']['critical_facts']),"
                "'unsupported_material_claims':0,'grader_id':'fixture-grader','usage':None,"
                "'model_calls_complete':False},sort_keys=True,separators=(',',':')))"
            )
            trial = study.Trial(identity, study.Budget(0, 60_000_000_000), execution="fixture")

            def prepare(current: study.Trial, _attempt: int) -> dict[str, object]:
                current.not_applicable(
                    "jev_preparation", "provider", "source_revalidation",
                    "response_validation", "operator_approval", "fallback",
                )
                payload = study._installed_graph_payload(
                    current, task_id="S-01", prompt=prompt, lane=lane,
                    source_manifest=source_manifest, installed=installed,
                )
                current.coverage(source_operations=True)
                return payload

            result = run_process_trial(
                trial, prepare,
                answer_argv=[sys.executable, "-c", answer_code],
                grader_argv=[sys.executable, "-c", grader_code],
                cwd=ROOT, answer_timeout_s=10, grader_timeout_s=10,
                grader_context=rubric, grader_model="fixture-grader",
            )

            self.assertEqual("passed", result["terminal_reason"], result["attempts"])
            attempt = result["attempts"][0]
            process_kinds = [row["kind"] for row in attempt["host_processes"]]
            self.assertEqual(1, process_kinds.count("graph_find"))
            self.assertEqual(1, process_kinds.count("answer"))
            self.assertEqual(1, process_kinds.count("grader"))
            self.assertTrue(attempt["coverage"]["source_operations"])
            self.assertFalse(attempt["coverage"]["model_calls"])
            self.assertFalse(result["usage_complete"])
            self.assertGreater(len(attempt["source_operations"]), 0)
            self.assertEqual("observed", result["phases"]["candidate_discovery"]["status"])
            self.assertEqual("observed", result["phases"]["context_composition"]["status"])
            self.assertEqual(
                attempt["bindings"]["candidate_set_sha256"],
                attempt["candidate_observation"]["candidate_set_sha256"],
            )
            self.assertEqual(
                installed[1], attempt["bindings"]["graph_artifact_sha256"],
            )
            self.assertEqual(
                "installed_graph_find_process",
                attempt["candidate_observation"]["stage_clock"]["domain"],
            )
            self.assertLessEqual(
                result["confirmed_time_to_correct_ns"], result["user_visible_wall_ns"],
            )

            changed_manifest = dict(source_manifest)
            changed_manifest["snapshot_sha256"] = "0" * 64
            mismatch_trial = study.Trial(
                {**identity, "trial_id": "C-S-02", "task_id": "S-02",
                 "answer_lane_id": "answer-C-S-02"},
                study.Budget(0, 60_000_000_000), execution="fixture",
            )
            mismatch = mismatch_trial.run(
                lambda current, _number: study._installed_graph_payload(
                    current, task_id="S-02", prompt=prompt, lane=lane,
                    source_manifest=changed_manifest, installed=installed,
                ),
                lambda *_args: None, lambda *_args: None,
            )
            self.assertEqual("measurement_error", mismatch["terminal_reason"])
            self.assertEqual(
                "installed_graph_find_binding_mismatch",
                mismatch["attempts"][0]["failure_reason"],
            )

    def test_tracked_historical_bundle_validates_without_private_custody(self) -> None:
        freeze, questions, rubrics = study.load_bundle()
        current_release = json.loads(
            (ROOT / "plugins/graph-engineering/.codex-plugin/release-manifest.json")
            .read_text(encoding="utf-8")
        )
        self.assertNotEqual(
            freeze["product"]["package_candidate_sha256"],
            current_release["candidate_sha256"],
        )
        self.assertEqual(tuple(freeze["tasks"]), study.TASKS)
        self.assertEqual(len(questions["questions"]), 4)
        self.assertEqual(len(rubrics["tasks"]), 4)

    def test_tampered_historical_product_bindings_fail_closed(self) -> None:
        freeze, _, _ = study.load_bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("questions", "rubrics", "preflight"):
                shutil.copy(BENCHMARK / f"{name}.json", root / f"{name}.json")
            for field, value in (
                ("commit", "0" * 40),
                ("package_candidate_sha256", "0" * 64),
                ("package_name", "renamed-package"),
                ("package_version", "0.2.0"),
            ):
                with self.subTest(field=field):
                    changed = deepcopy(freeze)
                    changed["product"][field] = value
                    (root / "freeze.json").write_text(
                        json.dumps(changed), encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        study.StudyError, "package_binding_invalid",
                    ):
                        study.load_bundle(root, ROOT)

    def test_successor_overlay_fails_closed_without_private_custody(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(
            study.StudyError, "successor_witness_custody_path_invalid",
        ):
            study.load_successor_ttc_contract(
                custody_path=Path(directory) / "missing.json",
            )


class FourArmStudyTests(unittest.TestCase):
    def setUp(self) -> None:
        if not CUSTODY.is_file():
            self.skipTest("private successor witness custody is unavailable")
        self.freeze, self.questions, self.rubrics = study.load_bundle()
        self.successor = study.load_successor_rubrics()
        self.ttc, self.custody = study.load_successor_ttc_contract(
            custody_path=CUSTODY,
        )
        self.frozen_preflight = json.loads(
            (BENCHMARK / "preflight.json").read_text(encoding="utf-8")
        )

    def test_freeze_identity_has_exact_four_by_four_matrix(self) -> None:
        self.assertEqual(tuple(self.freeze["tasks"]), study.TASKS)
        self.assertNotIn("C-02", self.freeze["tasks"])
        self.assertEqual(len(self.freeze["dispatch_order"]), 16)
        self.assertEqual(set(self.freeze["arms"]), {"A", "B", "C", "D"})
        self.assertEqual(
            self.freeze["controller"]["argv"],
            [
                "/usr/bin/env", "python3", "-B",
                "scripts/benchmarks/four_arm_study_v1.py", "validate", "--root",
                "benchmarks/velgraphing-four-arm-study-v1",
            ],
        )
        self.assertEqual(
            self.freeze["controller"]["prepare_argv_template"],
            study.PREPARE_ARGV_TEMPLATE,
        )
        self.assertEqual(
            self.freeze["controller"]["execution_argv_template"],
            study.EXECUTION_ARGV_TEMPLATE,
        )
        self.assertEqual(self.freeze["controller"]["provider_answer_and_grader_calls"], 0)
        self.assertEqual(
            self.freeze["controller"]["sha256"],
            study.HISTORICAL_CONTROLLER_SHA256,
        )
        self.assertEqual(
            self.successor["implementation_bindings"]["controller"]["sha256"],
            study.SUCCESSOR_RUBRICS_CONTROLLER_SHA256,
        )
        self.assertEqual(
            self.ttc["bindings"]["controller"]["sha256"],
            study.digest((ROOT / self.freeze["controller"]["path"]).read_bytes()),
        )
        self.assertEqual(
            study._bound_grader_contract(self.freeze),
            study.GRADER_RESPONSE_CONTRACT,
        )
        self.assertNotEqual(
            study.digest(study.canonical(study.GRADER_RESPONSE_CONTRACT)),
            study.digest(study.canonical(study.SUCCESSOR_GRADER_RESPONSE_CONTRACT)),
        )

    def test_successor_rubrics_correct_scoring_and_arm_meanings(self) -> None:
        d01 = self.successor["tasks"]["D-01"]
        l01 = self.successor["tasks"]["L-01"]
        m02 = self.successor["tasks"]["M-02"]
        self.assertTrue(any(
            "retained" in row["fact"] for row in d01["required_facts"]
        ))
        self.assertFalse(any("random" in row["fact"].lower()
                             for row in d01["required_facts"]))
        documentation = next(
            row["fact"] for row in m02["required_facts"]
            if row["ask_id"] == "documentation"
        )
        self.assertIn("any process-documentation choice supported", documentation)
        for rubric in (l01, m02):
            citation = next(row["fact"] for row in rubric["required_facts"]
                            if row["ask_id"] == "citations")
            self.assertIn("evidence IDs that map", citation)
        self.assertEqual(self.successor["arm_labels"], study.SUCCESSOR_ARM_LABELS)

    def test_host_payloads_keep_answer_and_grader_blind(self) -> None:
        answer = _answer_input({
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "public question",
            "instructions": ["cite evidence"],
            "evidence": [{
                "id": "a" * 64, "path": "source.py", "excerpt": "evidence",
                "arm": "D", "route": "graph", "jev": "on", "score": 1,
            }],
            "arm": "D", "route": "graph", "treatment": "on",
            "rubric": {"oracle": True},
        })
        grader = _grader_input(
            "answer",
            {
                "required_facts": ["required"],
                "critical_facts": ["critical"],
                "acceptable_spans": ["source.py"],
                "arm": "D", "route": "graph", "jev": "on", "question": "hidden",
            },
            {"c1": "source.py"},
        )
        self.assertEqual(set(answer), {"schema_version", "question", "instructions", "evidence"})
        self.assertEqual(set(answer["evidence"][0]), {"id", "path", "excerpt"})
        self.assertEqual(answer["evidence"][0]["id"], "c1")
        self.assertEqual(
            set(grader),
            {"schema_version", "answer_text", "rubric", "evidence_sources"},
        )
        self.assertEqual(grader["schema_version"], "velgraphing-grader-model-input-v2")
        self.assertEqual(grader["evidence_sources"], {"c1": "source.py"})
        self.assertEqual(
            set(grader["rubric"]),
            {"required_facts", "critical_facts", "acceptable_spans"},
        )
        self.assertIn(
            "required_fact_decisions",
            study.SUCCESSOR_GRADER_RESPONSE_CONTRACT["json_schema"]["required"],
        )

    def test_tracked_contract_is_source_free_and_custody_bound(self) -> None:
        tracked = (BENCHMARK / study.SUCCESSOR_TTC_CONTRACT).read_text(encoding="utf-8")
        for forbidden in (
            '"fact_witness_map"', '"fallback_allowlist"', '"byte_start"',
            '"byte_end"', '"candidate_id"', '"source_text"',
        ):
            self.assertNotIn(forbidden, tracked)
        for rows in self.custody["fallback_allowlist"].values():
            for row in rows:
                self.assertNotIn(row["id"], tracked)
                self.assertNotIn(row["path"], tracked)
        self.assertEqual(
            self.ttc["witness_custody_sha256"],
            study.digest(study.canonical(self.custody)),
        )

    def test_documented_successor_commands_bind_custody_without_oracle_paths(self) -> None:
        readme = (BENCHMARK / "README.md").read_text(encoding="utf-8")
        protocol = (BENCHMARK / "PROTOCOL.md").read_text(encoding="utf-8")
        tracked = readme + protocol
        binding = (
            'WITNESS_CUSTODY="$PWD/.velgraphing-local/velgraphing-four-arm-study-v1/'
            'successor-ttc-witness-custody.json"'
        )
        self.assertEqual(tracked.count("WITNESS_CUSTODY="), 1)
        self.assertIn(binding, readme)
        command_blocks = re.findall(r"```sh\n(.*?)```", readme, flags=re.DOTALL)
        for command in (
            "validate-successor-overlay", "freeze-lanes",
            "four_arm_study_v1.py run",
        ):
            block = next((row for row in command_blocks if command in row), None)
            self.assertIsNotNone(block, command)
            self.assertIn('--witness-custody "$WITNESS_CUSTODY"', block)
        oracle_paths = {
            row["path"]
            for rows in self.custody["fallback_allowlist"].values()
            for row in rows
        }
        self.assertFalse(oracle_paths.intersection(tracked.split()))
        for path in oracle_paths:
            self.assertNotIn(path, tracked)

    def test_custody_path_and_canonical_bytes_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            study.StudyError, "successor_witness_custody_path_invalid"
        ):
            study._load_successor_witness_custody(CUSTODY.with_name("wrong.json"), ROOT)
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(
                study.StudyError, "successor_witness_custody_path_invalid"
            ):
                study._load_successor_witness_custody(CUSTODY, ROOT)
        with patch.object(Path, "read_bytes", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(
                study.StudyError, "successor_witness_custody_invalid"
            ):
                study._load_successor_witness_custody(CUSTODY, ROOT)
        noncanonical = json.dumps(self.custody, indent=2).encode("utf-8")
        with patch.object(Path, "read_bytes", return_value=noncanonical):
            with self.assertRaisesRegex(
                study.StudyError, "successor_witness_custody_noncanonical"
            ):
                study._load_successor_witness_custody(CUSTODY, ROOT)

    def test_custody_hash_binds_witness_map_and_fallback_allowlist(self) -> None:
        for key in ("fact_witness_map", "fallback_allowlist"):
            custody = deepcopy(self.custody)
            custody[key].pop("S-01")
            with self.subTest(key=key), self.assertRaisesRegex(
                study.StudyError, "successor_witness_custody_invalid"
            ):
                study._validate_successor_ttc_contract(
                    self.ttc, self.freeze, self.successor, BENCHMARK, ROOT, custody,
                )

    def test_verifier_runs_inside_observed_fallback_with_zero_append(self) -> None:
        events: list[str] = []

        class FakeTrial:
            @contextmanager
            def phase(self, name: str):
                events.append(f"{name}:start")
                try:
                    yield
                finally:
                    events.append(f"{name}:finish")

        candidate = {**self.custody["fallback_allowlist"]["S-01"][0], "required": False}
        packet = {
            "schema_version": "fixture", "query": "question", "candidates": [candidate],
        }
        actual = study.apply_verified_fallback

        def observed(*args):
            self.assertEqual(events, ["fallback:start"])
            return actual(*args)

        with patch.object(study, "apply_verified_fallback", side_effect=observed):
            _, _, receipt = study._apply_verified_fallback_measured(
                FakeTrial(), "S-01", packet, [candidate["id"]],
                self.ttc, self.custody,
            )
        self.assertEqual(events, ["fallback:start", "fallback:finish"])
        self.assertEqual(receipt["fallback_invocations"], 0)

    def test_sealed_result_requires_oracle_assisted_claim_boundary(self) -> None:
        result = {
            "identity": {"trial_id": "A-S-01"},
            "terminal_reason": "passed",
            "user_visible_wall_ns": 10,
            "confirmed_time_to_correct_ns": 9,
            "phases": {},
            "attempts": [{
                "coverage": {"model_calls": True, "source_operations": True},
                "answer_boundary": {"model_calls_complete": True},
                "model_calls": [
                    {"kind": "answer", "provenance": "fixture", "input_tokens": 1,
                     "output_tokens": 1},
                    {"kind": "grader", "provenance": "fixture", "input_tokens": 1,
                     "output_tokens": 1},
                ],
                "source_operations": [], "context_deliveries": [],
                "verified_fallback": {"fallback_invocations": 0},
            }],
        }
        local = ROOT / ".velgraphing-local"
        with tempfile.TemporaryDirectory(dir=local) as directory:
            sealed = study._seal(
                Path(directory), self.freeze,
                {"A-S-01": {"trial_id": "A-S-01", "task_id": "S-01"}},
                [result], "0" * 64, "fixture",
                successor_ttc_contract=self.ttc, successor_rubrics=self.successor,
            )
        self.assertEqual(sealed["classification"], "oracle_assisted_fallback_ttc")
        self.assertEqual(
            set(sealed["claim_boundary"]["prohibited"]),
            {
                "direct_retrieval_performance", "graph_retrieval_performance",
                "jev_retrieval_performance",
                "direct_graph_or_jev_comparative_retrieval_performance",
            },
        )

    def test_verified_fallback_policy_is_arm_invariant_and_bounded(self) -> None:
        candidate = {
            "id": "0" * 64, "path": "irrelevant.py", "source_sha256": "1" * 64,
            "byte_start": 0, "byte_end": 100, "required": False,
        }
        packet = {"schema_version": "fixture", "query": "question", "candidates": [candidate]}
        receipts = []
        for arm in study.ARMS:
            with self.subTest(arm=arm):
                updated, order, receipt = study.apply_verified_fallback(
                    "D-01", packet, [candidate["id"]], self.ttc, self.custody,
                )
                self.assertEqual(receipt["fallback_invocations"], 1)
                self.assertEqual(len(receipt["exact_fallback_candidates"]), 2)
                self.assertLessEqual(receipt["final_context_bytes"], 16_384)
                self.assertEqual(len(updated["candidates"]), 3)
                self.assertEqual(len(order), 3)
                receipts.append(receipt)
        self.assertTrue(all(receipt == receipts[0] for receipt in receipts))
        self.assertEqual(self.ttc["verifier_policy"]["scope"], "all_arms")

    def test_verified_fallback_refuses_unresolved_or_oversize_before_answer(self) -> None:
        candidate = {
            "id": "0" * 64, "path": "irrelevant.py", "source_sha256": "1" * 64,
            "byte_start": 0, "byte_end": 100, "required": False,
        }
        packet = {"schema_version": "fixture", "query": "question", "candidates": [candidate]}
        unresolved = deepcopy(self.custody)
        unresolved["fallback_allowlist"]["D-01"] = unresolved[
            "fallback_allowlist"
        ]["D-01"][:1]
        with self.assertRaisesRegex(study.MeasurementError, "source_witness_unresolved"):
            study.apply_verified_fallback(
                "D-01", packet, [candidate["id"]], self.ttc, unresolved,
            )
        oversize = deepcopy(packet)
        oversize["candidates"][0]["byte_end"] = 16_000
        with self.assertRaisesRegex(
            study.MeasurementError, "verified_fallback_context_exceeded"
        ):
            study.apply_verified_fallback(
                "D-01", oversize, [candidate["id"]], self.ttc,
                self.custody,
            )

    def test_successor_contract_refuses_stale_bindings_and_pending_manifest(self) -> None:
        self.assertEqual(
            self.ttc["status"], "pending_lane_manifest_and_final_user_reack",
        )
        with self.assertRaisesRegex(study.StudyError, "successor_lane_manifest_not_ready"):
            study.validate_successor_execution_bindings(self.ttc, self.freeze)
        mutations = {
            "controller": lambda value: value["bindings"]["controller"].update(sha256="0" * 64),
            "host": lambda value: value["bindings"]["host"].update(sha256="0" * 64),
            "rubric": lambda value: value["bindings"]["successor_rubric"].update(sha256="0" * 64),
            "grader_contract": lambda value: value["bindings"].update(
                successor_grader_response_contract_sha256="0" * 64
            ),
            "pool": lambda value: value["bindings"]["pool_bindings"].update(
                {"direct:S-01": "0" * 64}
            ),
            "verifier": lambda value: value.update(verifier_policy_sha256="0" * 64),
            "request_set": lambda value: value["bindings"].update(
                request_byte_set_sha256="0" * 64
            ),
            "manifest": lambda value: value["bindings"]["lane_manifest"].update(
                sha256="0" * 64
            ),
            "custody": lambda value: value.update(witness_custody_sha256="0" * 64),
        }
        for name, mutate in mutations.items():
            candidate = deepcopy(self.ttc)
            mutate(candidate)
            with self.subTest(binding=name), self.assertRaises(study.StudyError):
                study._validate_successor_ttc_contract(
                    candidate, self.freeze, self.successor, BENCHMARK, ROOT,
                    self.custody,
                )

    def test_provider_fallback_accounts_one_call_without_answer_retry(self) -> None:
        result = {
            "terminal_reason": "passed",
            "user_visible_wall_ns": 10,
            "confirmed_time_to_correct_ns": 9,
            "phases": {
                "provider": {"status": "observed", "inclusive_union_ns": 1},
                "operator_approval": {"status": "not_applicable", "inclusive_union_ns": 0},
                "fallback": {"status": "observed", "inclusive_union_ns": 1},
            },
            "attempts": [{
                "coverage": {"model_calls": True, "source_operations": True},
                "answer_boundary": {"model_calls_complete": True},
                "model_calls": [
                    {"kind": "jev", "provenance": "unavailable", "input_tokens": None,
                     "output_tokens": None},
                    {"kind": "answer", "provenance": "fixture", "input_tokens": 1,
                     "output_tokens": 1},
                    {"kind": "grader", "provenance": "fixture", "input_tokens": 1,
                     "output_tokens": 1},
                ],
                "source_operations": [], "context_deliveries": [],
                "jev_observation": {"status": "fallback", "attempted_calls": 1},
            }],
        }
        measurement = _v3_trial_measurement(
            {"trial_id": "D-S-01", "task_id": "S-01"}, result,
        )
        self.assertEqual(measurement["provider_calls"], 1)
        self.assertEqual(measurement["attempt_count"], 1)
        self.assertEqual(measurement["answer_call_count"], 1)
        self.assertEqual(measurement["grader_call_count"], 1)
        self.assertEqual(measurement["task_retries"], 0)

    def lane_manifest(self) -> dict[str, object]:
        entries = []
        for trial_id in study.DISPATCH:
            for role in ("answer", "grader"):
                binding = self.freeze["lane_identity_contract"][role]
                argv = study.lane_argv(trial_id, role)
                entries.append({
                    "trial_id": trial_id,
                    "role": role,
                    "thread_id": f"thread-{role}-{trial_id}",
                    "model": binding["model"],
                    "reasoning": binding["reasoning"],
                    "argv": argv,
                    "argv_sha256": study._sha256(argv),
                })
        return {
            "schema_version": self.freeze["lane_identity_contract"]["handoff_schema"],
            "entries": entries,
        }

    def test_lane_manifest_binds_models_reasoning_and_unique_threads(self) -> None:
        manifest = self.lane_manifest()
        study.validate_lane_manifest(manifest, self.freeze)
        grader = next(row for row in manifest["entries"] if row["role"] == "grader")
        grader["model"] = "gpt-5.6-luna"
        with self.assertRaisesRegex(study.StudyError, "lane_manifest_invalid"):
            study.validate_lane_manifest(manifest, self.freeze)

    def test_validate_cli_accepts_frozen_manifest_runtime_binding(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local) as directory:
            root = Path(directory)
            bindings = {
                "schema_version": "velgraphing-four-arm-lane-bindings-v1",
                "bindings": [{
                    "trial_id": trial_id,
                    "answer_thread_id": f"answer-{trial_id}",
                    "grader_thread_id": f"grader-{trial_id}",
                } for trial_id in study.DISPATCH],
            }
            manifest = root / "lane-manifest.json"
            study.freeze_lane_manifest(bindings, self.freeze, manifest, sys.executable)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(study.main([
                    "validate", "--root", str(BENCHMARK),
                    "--lane-manifest", str(manifest),
                ]), 0)
            self.assertEqual(
                json.loads(output.getvalue())["validation_scope"],
                "historical_bundle",
            )
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(study.main([
                "validate-successor-overlay", "--root", str(BENCHMARK),
                "--witness-custody", str(CUSTODY),
            ]), 0)
        successor = json.loads(output.getvalue())
        self.assertEqual(successor["validation_scope"], "successor_overlay")
        self.assertEqual(
            successor["successor_rubric_sha256"],
            study.digest(study.canonical(self.successor)),
        )
        self.assertEqual(
            successor["grader_contract_sha256"],
            study.digest(study.canonical(study.SUCCESSOR_GRADER_RESPONSE_CONTRACT)),
        )
        self.assertEqual(
            successor["successor_ttc_contract_sha256"],
            study.digest(study.canonical(self.ttc)),
        )

    def test_historical_validation_is_independent_of_successor_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "freeze", "questions", "rubrics", "preflight", "successor-rubrics",
                "successor-ttc-contract",
            ):
                shutil.copy(BENCHMARK / f"{name}.json", root / f"{name}.json")
            successor_path = root / "successor-rubrics.json"
            successor = json.loads(successor_path.read_text(encoding="utf-8"))
            successor["arm_labels"]["A"] = "corrupt"
            successor_path.write_text(json.dumps(successor), encoding="utf-8")

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(study.main(["validate", "--root", str(root)]), 0)
            self.assertEqual(
                json.loads(output.getvalue())["validation_scope"],
                "historical_bundle",
            )

            error = StringIO()
            with redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
                study.main([
                    "validate-successor-overlay", "--root", str(root),
                    "--witness-custody", str(CUSTODY),
                ])
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn("successor_rubrics_invalid", error.getvalue())

    def test_historical_execution_commands_fail_closed(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        pool = local / "velgraphing-four-arm-study-v1/phase-2-pools.json"
        run_root = local / "historical-execution-refused"
        commands = (
            [
                "prepare", "--root", str(BENCHMARK), "--lanes-root", str(LANES),
                "--local-output", str(pool), "--preflight-output",
                str(BENCHMARK / "preflight.json"),
            ],
            [
                "qualify", "--root", str(BENCHMARK), "--pool-artifact", str(pool),
                "--lane-root", str(LANES), "--run-root", str(run_root),
                "--python-executable", sys.executable,
            ],
        )
        for argv in commands:
            error = StringIO()
            with self.subTest(command=argv[0]), redirect_stderr(error):
                with self.assertRaises(SystemExit) as stopped:
                    study.main(argv)
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn("execution_binding_stale", error.getvalue())
        manifest = self.lane_manifest()
        manifest["entries"][1]["thread_id"] = manifest["entries"][0]["thread_id"]
        with self.assertRaisesRegex(study.StudyError, "lane_manifest_invalid"):
            study.validate_lane_manifest(manifest, self.freeze)
        manifest = self.lane_manifest()
        manifest["entries"][0]["argv"] = ["arbitrary-command"]
        manifest["entries"][0]["argv_sha256"] = study._sha256(["arbitrary-command"])
        with self.assertRaisesRegex(study.StudyError, "lane_manifest_invalid"):
            study.validate_lane_manifest(manifest, self.freeze)

    def preflight(self) -> dict[str, object]:
        return deepcopy(self.frozen_preflight)

    def test_eight_call_ceiling_zero_retry_and_membership_skip(self) -> None:
        preflight = self.preflight()
        self.assertEqual(study.validate_preflight(preflight, self.freeze), 8)
        b_row = next(row for row in preflight["trials"] if row["trial_id"] == "B-S-01")
        b_row["jev_call_could_affect_selection"] = False
        b_row["call_disposition"] = "skip_no_membership_effect"
        b_row["selection_decision_reason"] = "all_optional_candidates_fit"
        with self.assertRaisesRegex(study.StudyError, "preflight_invalid"):
            study.validate_preflight(preflight, self.freeze)
        preflight = self.preflight()
        preflight["retries"] = 1
        with self.assertRaisesRegex(study.StudyError, "preflight_invalid"):
            study.validate_preflight(preflight, self.freeze)
        too_small = deepcopy(self.freeze)
        too_small["jev"]["max_calls"] = 7
        with self.assertRaisesRegex(study.StudyError, "preflight_invalid"):
            study.validate_preflight(self.preflight(), too_small)

    def test_frozen_pools_preserve_real_graph_delta_and_source_free_tracking(self) -> None:
        pools = {row["pool_id"]: row for row in self.frozen_preflight["pools"]}
        self.assertEqual(len(pools), 8)
        self.assertEqual(len({row["pool_sha256"] for row in pools.values()}), 8)
        self.assertNotEqual(
            pools["direct:D-01"]["candidate_set_sha256"],
            pools["graph:D-01"]["candidate_set_sha256"],
        )
        self.assertNotEqual(
            pools["direct:D-01"]["request_sha256"],
            pools["graph:D-01"]["request_sha256"],
        )
        self.assertFalse(pools["direct:D-01"]["relationship_delta_present"])
        self.assertTrue(pools["graph:D-01"]["relationship_delta_present"])
        self.assertGreater(pools["graph:D-01"]["relationship_candidate_count"], 0)
        self.assertNotEqual(
            pools["direct:L-01"]["candidate_set_sha256"],
            pools["graph:L-01"]["candidate_set_sha256"],
        )
        self.assertTrue(pools["graph:L-01"]["relationship_delta_present"])
        for task_id in ("S-01", "M-02"):
            self.assertEqual(
                pools[f"direct:{task_id}"]["candidate_set_sha256"],
                pools[f"graph:{task_id}"]["candidate_set_sha256"],
            )
            self.assertFalse(pools[f"graph:{task_id}"]["relationship_delta_present"])
        tracked = (BENCHMARK / "preflight.json").read_text(encoding="utf-8")
        self.assertNotIn('"source_path"', tracked)
        self.assertNotIn('"candidates"', tracked)
        self.assertNotIn('"excerpt"', tracked)
        self.assertTrue(all(
            row["candidate_count"] <= study.CANDIDATE_LIMIT
            and row["aggregate_excerpt_bytes"]
            <= study.CANDIDATE_AGGREGATE_BYTE_BUDGET
            and row["eligibility"]["source_revalidated"] is True
            and row["eligibility"]["fail_closed"] is False
            for row in pools.values()
        ))
        self.assertEqual(self.frozen_preflight["provider_calls_executed"], 0)

    @unittest.skipUnless(LANES.is_dir(), "frozen v4 corpus lanes are unavailable")
    def test_real_frozen_lanes_reproduce_phase_two_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = study.prepare_study(
                self.freeze,
                self.questions,
                BENCHMARK,
                LANES,
                root / "pools.json",
                root / "preflight.json",
                ROOT,
            )
            self.assertEqual(
                result["preflight_sha256"],
                self.freeze["artifacts"]["preflight"]["sha256"],
            )
            self.assertEqual(result["planned_jev_calls"], 8)
            self.assertEqual(result["skipped_jev_calls"], 0)
            reproduced = json.loads((root / "preflight.json").read_text(encoding="utf-8"))
            self.assertEqual(reproduced, self.frozen_preflight)
            local = json.loads((root / "pools.json").read_text(encoding="utf-8"))
            self.assertEqual(local["provider_calls_executed"], 0)
            self.assertEqual(len(local["pools"]), 8)

    def test_stale_pool_identity_fails_closed(self) -> None:
        changed = self.preflight()
        changed["pools"][0]["pool_sha256"] = "0" * 64
        with self.assertRaisesRegex(study.StudyError, "preflight_pool_invalid"):
            study.validate_preflight(changed, self.freeze)

    @unittest.skipUnless(LANES.is_dir(), "frozen v4 corpus lanes are unavailable")
    def test_lane_symlink_alias_fails_closed(self) -> None:
        manifest = study._load_manifest(
            ROOT / self.freeze["corpora"]["thealgorithms-python"]["manifest"]
        )
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / "lane"
            os.symlink(LANES / "thealgorithms-python", alias)
            with self.assertRaisesRegex(study.StudyError, "lane_identity_invalid"):
                study._scan_lane(alias, manifest, derive_edges=True)

    def write_bundle(self, root: Path, freeze: object) -> None:
        for name in ("questions", "rubrics", "preflight"):
            shutil.copy(BENCHMARK / f"{name}.json", root / f"{name}.json")
        (root / "freeze.json").write_text(json.dumps(freeze), encoding="utf-8")

    def test_source_and_package_bindings_fail_closed(self) -> None:
        for field, value, reason in (
            ("commit", "0" * 40, "package_binding_invalid"),
            ("package_candidate_sha256", "0" * 64, "package_binding_invalid"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                changed = deepcopy(self.freeze)
                changed["product"][field] = value
                self.write_bundle(root, changed)
                with self.assertRaisesRegex(study.StudyError, reason):
                    study.load_bundle(root, ROOT)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = deepcopy(self.freeze)
            changed["implementation_bindings"]["jev"] = {
                "path": "packages/core/retrieval.py",
                "sha256": study.digest((ROOT / "packages/core/retrieval.py").read_bytes()),
            }
            self.write_bundle(root, changed)
            with self.assertRaisesRegex(study.StudyError, "implementation_binding_invalid"):
                study.load_bundle(root, ROOT)

        for field, value in (("commit", "0" * 40), ("snapshot_sha256", "0" * 64)):
            with self.subTest(corpus_field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                changed = deepcopy(self.freeze)
                changed["corpora"]["engineering-handbook"][field] = value
                self.write_bundle(root, changed)
                with self.assertRaisesRegex(study.StudyError, "source_binding_invalid"):
                    study.load_bundle(root, ROOT)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = deepcopy(self.freeze)
            manifest = changed["corpora"]["engineering-handbook"]["manifest"]
            changed["corpora"]["engineering-handbook"]["manifest"] = f"./{manifest}"
            self.write_bundle(root, changed)
            with self.assertRaisesRegex(study.StudyError, "source_binding_invalid"):
                study.load_bundle(root, ROOT)

    def test_telemetry_schema_covers_end_to_end_time_usage_and_missingness(self) -> None:
        telemetry = self.freeze["telemetry_schema"]
        self.assertEqual(set(telemetry["time_ms"]), study.TIME_METRICS)
        self.assertEqual(set(telemetry["usage"]), study.USAGE_METRICS)
        self.assertEqual(
            set(telemetry["quality"]),
            {"accepted_correctness", "first_pass_correctness"},
        )
        self.assertEqual(set(telemetry["failure"]), {"failure_class", "missingness"})


if __name__ == "__main__":
    unittest.main()
