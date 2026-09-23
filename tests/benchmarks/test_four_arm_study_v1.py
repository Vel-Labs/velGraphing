"""Offline contract tests for the successor four-arm study."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from copy import deepcopy
from decimal import Decimal
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
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks/velgraphing-four-arm-study-v1"
LANES = Path(os.environ.get(
    "VELGRAPHING_CORPUS_LANE_ROOT",
    ROOT / "benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4",
))
PINNED_LANES = ROOT.parent.parent / "benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4"
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))

import four_arm_study_v1 as study  # noqa: E402
from time_to_correct import Answer, Budget, Grade, Trial  # noqa: E402
from time_to_correct_calibration import _v3_trial_measurement  # noqa: E402
from time_to_correct_host import (  # noqa: E402
    _answer_input, _grader_input,
)

CUSTODY = ROOT / study.SUCCESSOR_WITNESS_CUSTODY


class FourArmPublicBoundaryTests(unittest.TestCase):
    def test_fresh_comparison_can_disable_oracle_append_without_changing_legacy_mode(self) -> None:
        selection = SimpleNamespace(
            route="ranked",
            projection=SimpleNamespace(
                fail_closed=False,
                selected_candidate_ids=["selected"],
                required_candidate_ids=["selected"],
            ),
            reason="verified_ranked_context_selected",
            order_source="baseline",
        )
        discovery = {
            "graph": object(), "task": SimpleNamespace(task_id="S-01"),
            "snapshot": object(), "reader": object(), "packet": {"query": "q"},
            "candidates": (),
        }
        trial = SimpleNamespace(
            current={"candidate_observation": {}},
            phase=lambda _name: nullcontext(),
        )
        contract = {"fixture": True}
        custody = {"fixture": True}
        with (
            patch.object(study, "select_ranked_context", return_value=selection),
            patch.object(study, "compose_answer_payload", return_value={"answer": "ok"}),
            patch.object(study, "_apply_verified_fallback_measured") as append,
        ):
            payload = study._select_direct_payload(
                trial, discovery, Path("."), None, None, contract, custody,
                oracle_source_append_enabled=False,
            )
        append.assert_not_called()
        self.assertEqual({"answer": "ok"}, payload)
        self.assertEqual(
            {"policy": "oracle_source_append_disabled", "fallback_invocations": 0},
            trial.current["verified_fallback"],
        )

        legacy_trial = SimpleNamespace(
            current={"candidate_observation": {}},
            phase=lambda _name: nullcontext(),
        )
        with (
            patch.object(study, "select_ranked_context", return_value=selection),
            patch.object(study, "compose_answer_payload", return_value={"answer": "ok"}),
            patch.object(
                study, "_apply_verified_fallback_measured",
                return_value=({"query": "q"}, ["selected"], {"fallback_invocations": 1}),
            ) as append,
        ):
            study._select_direct_payload(
                legacy_trial, discovery, Path("."), None, None, contract, custody,
            )
        append.assert_called_once()
        self.assertEqual({"fallback_invocations": 1}, legacy_trial.current["verified_fallback"])

    def test_graph_plan_fallback_is_rejected_only_for_strict_ac_route(self) -> None:
        direct_plan = {"route": "direct"}
        with self.assertRaisesRegex(
            study.MeasurementError, "installed_graph_find_plan_fell_back_to_direct",
        ):
            study._require_graph_plan(direct_plan, required=True)
        self.assertIsNone(study._require_graph_plan(direct_plan, required=False))
        self.assertIsNone(
            study._require_graph_plan({"route": "graph"}, required=True)
        )

    def test_successor_public_asks_become_answer_facets_only(self) -> None:
        asks = [{"id": "traffic", "text": "Explain the public traffic assumptions."}]
        self.assertEqual(study._public_task_facets({
            "asks": asks,
            "required_facts": [{"fact": "hidden grader-only fact"}],
        }), ["Explain the public traffic assumptions."])
        with self.assertRaisesRegex(
            study.MeasurementError, "successor_public_asks_invalid",
        ):
            study._public_task_facets({"asks": [{"fact": "hidden"}]})

    def test_direct_candidate_binding_matches_real_jev_evaluator(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="direct-jev-hash-", dir=local) as raw:
            lane = Path(raw)
            source = lane / "evidence.py"
            source.write_text(
                "def cancel_task(task):\n    return task.cancel()\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q", str(lane)], check=True)
            subprocess.run(["git", "-C", str(lane), "add", "evidence.py"], check=True)
            subprocess.run([
                "git", "-C", str(lane), "-c", "user.name=Fixture",
                "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
            ], check=True)
            commit = subprocess.check_output(
                ["git", "-C", str(lane), "rev-parse", "HEAD"], text=True,
            ).strip()
            source_row = {
                "path": "evidence.py", "byte_length": len(source.read_bytes()),
                "sha256": study.digest(source.read_bytes()),
            }
            manifest = {
                "schema_version": "velgraphing-corpus-source-manifest-v1",
                "repository": "fixture", "commit": commit,
                "includes": ["**"], "excludes": [], "sources": [source_row],
                "source_count": 1, "source_bytes": source_row["byte_length"],
                "snapshot_sha256": study._sha256({"sources": [source_row]}),
                "skipped": [],
            }
            identity = {
                "run_id": "fixture", "trial_id": "B-S-01", "task_id": "S-01",
                "arm": "B", "repository_id": "fixture", "repository_commit": commit,
                "source_snapshot_sha256": manifest["snapshot_sha256"],
                "dirty_state_sha256": "b" * 64, "answer_model": "fixture",
                "reasoning": "none", "prompt_sha256": "c" * 64,
                "rubric_sha256": "d" * 64, "rubric_version": "fixture-v1",
                "answer_lane_id": "answer-fixture",
            }
            trial = Trial(identity, Budget(0, 5_000_000_000), execution="fixture")
            observations = []

            def prepare(current, _attempt):
                discovery = study._discover_direct(
                    current, "S-01", "Find cancel_task.", lane, manifest,
                )
                preview = study.jev.prepare(discovery["packet"], lane)
                legend = {
                    str(index): value
                    for index, value in enumerate(study.jev._rubric_criteria())
                }
                envelope = {
                    "schema_version": "velgraphing-jev-replay-v1",
                    "request_sha256": preview["request_sha256"],
                    "response": {
                        "model": study.jev.DEFAULT_MODEL,
                        "answers": {
                            f"candidate_{index}": {
                                "type": "score", "score": 2, "confidence": 1.0,
                                "probabilities": {str(value): float(value == 2)
                                                  for value in range(3)},
                                "legend": legend,
                            }
                            for index, _ in enumerate(discovery["packet"]["candidates"])
                        },
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                }
                observation = study.evaluate_offline(
                    current, ROOT, discovery["packet"], lane, envelope=envelope,
                    fixture_provider=True, retain_packet_telemetry=True,
                )
                observations.append(observation)
                return observation

            result = trial.run(
                prepare,
                lambda _trial, observation, _attempt: Answer(" ".join(observation["order"])),
                lambda _trial, _answer, _attempt: Grade(
                    True, 1, 1, True, 0, "grader-fixture", "d" * 64,
                ),
            )
            attempt = result["attempts"][0]
            self.assertEqual("passed", result["terminal_reason"], result["attempts"])
            self.assertEqual("reranked", observations[0]["status"])
            self.assertEqual(1, observations[0]["attempted_calls"])
            self.assertEqual(
                attempt["candidate_observation"]["candidate_set_sha256"],
                attempt["bindings"]["candidate_set_sha256"],
            )
            self.assertEqual(observations[0]["request_sha256"], attempt["bindings"]["request_sha256"])

    def test_installed_graph_find_rejects_unmanifested_files(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="manifest-extra-", dir=local) as raw:
            run_root = Path(raw)
            study._install_graph_find(run_root)
            extra = run_root / "installed-plugin/graph-engineering/packages/core/__init__.py"
            extra.parent.mkdir(parents=True)
            extra.write_text("raise RuntimeError('unmanifested module')\n", encoding="utf-8")
            with self.assertRaisesRegex(study.StudyError, "installed_adapter_invalid"):
                study._install_graph_find(run_root)

    def test_installed_graph_find_timeout_records_redacted_process_receipt(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        identity = {
            "run_id": "fixture-run", "trial_id": "B-S-01", "task_id": "S-01",
            "arm": "B", "repository_id": "fixture", "repository_commit": "a" * 40,
            "source_snapshot_sha256": "b" * 64, "dirty_state_sha256": "c" * 64,
            "answer_model": "fixture-answer", "reasoning": "none",
            "prompt_sha256": "d" * 64, "rubric_sha256": "e" * 64,
            "rubric_version": "fixture-v1", "answer_lane_id": "answer-fixture",
        }
        with tempfile.TemporaryDirectory(prefix="graph-find-timeout-", dir=local) as raw:
            run_root = Path(raw)
            installed = study._install_graph_find(run_root)
            trial = Trial(identity, Budget(0, 5_000_000_000), execution="fixture")

            def prepare(current: Trial, _attempt: int) -> dict[str, object]:
                return study._installed_graph_payload(
                    current, task_id="S-01", prompt="Find the fixture evidence.",
                    lane=run_root, source_manifest={"snapshot_sha256": "b" * 64},
                    installed=installed, run_root=run_root,
                )

            def timed_out(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
                raise subprocess.TimeoutExpired(
                    argv, kwargs["timeout"], output=b"partial stdout", stderr=b"partial stderr",
                )

            with patch.object(study.subprocess, "run", side_effect=timed_out):
                result = trial.run(
                    prepare,
                    lambda *_: Answer("unreachable"),
                    lambda *_: Grade(False, 0, 1, False, 0, "fixture-grader", "e" * 64),
                )

        attempt = result["attempts"][0]
        self.assertEqual("callback_timeout", result["terminal_reason"])
        self.assertEqual("prepare", attempt["failure_stage"])
        self.assertEqual("callback_timeout", attempt["failure_reason"])
        self.assertEqual("observed", attempt["phase_status"]["candidate_discovery"])
        self.assertEqual([{
            "kind": "graph_find",
            "argv_sha256": study.digest(study.canonical([
                sys.executable, str(installed[0]), "--root", str(run_root),
                "--prompt", "Find the fixture evidence.", "--maximum-results",
                str(study.RETRIEVAL_NODE_LIMIT), "--byte-budget",
                str(study.CANDIDATE_AGGREGATE_BYTE_BUDGET), "--context-byte-budget",
                str(study.FINAL_CONTEXT_BYTE_BUDGET), "--ranked-context", "plan",
                "--diagnostics",
            ])),
            "input_sha256": study.digest(b""),
            "stdout_sha256": study.digest(b"partial stdout"),
            "stderr_sha256": study.digest(b"partial stderr"),
            "exit_code": None,
            "timeout_limit_ns": 120_000_000_000,
            "status": "timeout",
        }], attempt["host_processes"])
        self.assertNotIn("partial stdout", json.dumps(result))
        self.assertNotIn("partial stderr", json.dumps(result))

    def test_installed_graph_find_trial_supports_graph_off_and_d_on_replay(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="t050-canary-", dir=local) as raw:
            root = Path(raw)
            corpus_id = "fixture-corpus"
            lane_root = root / "lanes"
            lane = lane_root / corpus_id
            (lane / "src").mkdir(parents=True)
            fixture_source = (
                'FRESH_GRAPH_MARKER = "fresh-source-evidence"\n'
                "def cancel_task(task):\n    return task.cancel()\n"
            )
            (lane / "src/cancel.py").write_text(fixture_source, encoding="utf-8")
            (lane / "src/evidence.py").write_text("\n".join(
                f"def alpha_evidence_{index:02d}():\n"
                f"    return 'FRESH_GRAPH_MARKER rerank candidate {index} {'x' * 1900}'"
                for index in range(14)
            ) + "\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(lane)], check=True)
            subprocess.run(
                ["git", "-C", str(lane), "add", "src"],
                check=True,
            )
            sources = [
                {"path": path.relative_to(lane).as_posix(),
                 "byte_length": len(path.read_bytes()),
                 "sha256": study.digest(path.read_bytes())}
                for path in sorted(lane.rglob("*.py"))
            ]
            source_manifest = {
                "schema_version": "velgraphing-corpus-source-manifest-v1",
                "repository": corpus_id,
                "commit": "a" * 40,
                "includes": ["**"],
                "excludes": [],
                "sources": sources,
                "source_count": len(sources),
                "source_bytes": sum(row["byte_length"] for row in sources),
                "snapshot_sha256": study._sha256({"sources": sources}),
                "skipped": [],
            }
            run_root = root / "run"
            run_root.mkdir()
            prompt = "Find FRESH_GRAPH_MARKER and the cancel_task implementation."
            rubric = {
                "rubric_version": "t050-fixture-v2",
                "required_facts": [{"ask_id": "fresh", "fact": "FRESH_GRAPH_MARKER"}],
                "critical_facts": ["FRESH_GRAPH_MARKER"],
                "acceptable_spans": ["FRESH_GRAPH_MARKER"],
            }
            answer_code = (
                "import json,sys; x=json.load(sys.stdin); raw=json.dumps(x); "
                "assert 'task_facets' not in x; "
                "assert 'FRESH_GRAPH_MARKER' in raw; "
                "assert 'PRECOMPUTED_POOL_LEAK_SENTINEL' not in raw; e=x['evidence']; "
                "a=' '.join(r['excerpt'] for r in e)+' '+' '.join('['+r['id']+']' for r in e); "
                "sys.stdout.write(json.dumps({'schema_version':'velgraphing-answer-output-v1',"
                "'answer_text':a,'usage':None,'model_calls_complete':False,"
                "'context_deliveries_complete':True},sort_keys=True,separators=(',',':')))"
            )
            grader_code = (
                "import json,sys; x=json.load(sys.stdin); "
                "fs=x['rubric']['required_facts']; a=x['answer_text'].casefold(); "
                "d=[f.casefold() in a for f in fs]; n=len(fs); s=sum(d); "
                "sys.stdout.write(json.dumps({'schema_version':'velgraphing-grader-output-v1',"
                "'required_fact_score':s,'required_fact_maximum':n,"
                "'critical_facts_exact':all(f.casefold() in a for f in x['rubric']['critical_facts']),"
                "'unsupported_material_claims':0,'grader_id':'fixture-grader','usage':None,"
                "'model_calls_complete':False},sort_keys=True,separators=(',',':')))"
            )
            trial_id = "C-S-01"
            freeze = {
                "study_id": "t050-fixture",
                "corpora": {corpus_id: {
                    "commit": "a" * 40,
                    "snapshot_sha256": source_manifest["snapshot_sha256"],
                    "manifest": "benchmarks/velgraphing-corpus-pilot-v1/fixture.json",
                }},
                "lane_identity_contract": {
                    "answer": {"model": "fixture-answer", "reasoning": "none"},
                },
                "implementation_bindings": {
                    "grader_response_contract_sha256": study.digest(
                        study.canonical(study.GRADER_RESPONSE_CONTRACT),
                    ),
                },
            }
            registration = {
                "trial_id": trial_id, "task_id": "S-01", "arm": "C",
                "call_disposition": "skip_no_membership_effect",
                "selection_decision_sha256": study.digest(b"fixture-decision"),
            }
            pool = {
                "corpus": corpus_id,
                "pool_sha256": study.digest(b"fixture-pool"),
                "identity": {"route": "graph", "task_id": "S-01"},
                "candidate_packet": {
                    "query": prompt,
                    "candidates": [{"id": "stale", "excerpt": "PRECOMPUTED_POOL_LEAK_SENTINEL"}],
                },
            }
            process_manifest = {"entries": [
                {"trial_id": trial_id, "role": "answer", "thread_id": "answer_fixture",
                 "model": "fixture-answer", "reasoning": "none",
                 "argv": [sys.executable, "-c", answer_code]},
                {"trial_id": trial_id, "role": "grader", "thread_id": "grader_fixture",
                 "model": "fixture-grader", "reasoning": "none",
                 "argv": [sys.executable, "-c", grader_code]},
            ]}
            successor_grader_code = grader_code.replace(
                "'schema_version':'velgraphing-grader-output-v1',",
                "'schema_version':'velgraphing-grader-output-v2',",
            ).replace(
                "'required_fact_score':s,'required_fact_maximum':n,",
                "'required_fact_score':s,'required_fact_maximum':n,'required_fact_decisions':d,",
            )
            successor_manifest = deepcopy(process_manifest)
            successor_manifest["entries"][1]["argv"] = [
                sys.executable, "-c", successor_grader_code,
            ]
            before = {"restricted_state_sha256": "c" * 64}
            with (
                patch.object(study, "verify_lane", return_value=([], before)) as verify,
                patch.object(study, "revalidate_lane") as revalidate,
                patch.object(study, "_load_manifest", return_value=source_manifest),
                patch.object(study, "_question_prompt", return_value=prompt),
            ):
                result = study.execute_trial(
                    freeze, registration, pool, rubric, lane_root, run_root,
                    successor_manifest, study.digest(study.canonical(successor_manifest)),
                    execution="fixture",
                    successor_ttc_contract={"fixture_contract": True},
                    oracle_source_append_enabled=False,
                    use_public_task_facets=False,
                )
                strict_result = study.execute_trial(
                    freeze, registration, pool, rubric, lane_root, run_root,
                    process_manifest, study.digest(study.canonical(process_manifest)),
                    execution="fixture", require_graph_selection=True,
                )
                self.assertEqual(2, verify.call_count)
                self.assertEqual(2, revalidate.call_count)

            self.assertEqual("passed", result["terminal_reason"], result["attempts"])
            attempt = result["attempts"][0]
            self.assertEqual("direct", attempt["candidate_observation"]["selection_route"])
            process_kinds = [row["kind"] for row in attempt["host_processes"]]
            self.assertEqual(1, process_kinds.count("graph_find"))
            self.assertEqual(1, process_kinds.count("answer"))
            self.assertEqual(1, process_kinds.count("grader"))
            self.assertTrue(attempt["coverage"]["source_operations"])
            self.assertFalse(attempt["coverage"]["model_calls"])
            self.assertFalse(result["usage_complete"])
            self.assertGreater(len(attempt["source_operations"]), 0)
            self.assertEqual("installed_graph_find", attempt["candidate_observation"]["route"])
            strict_attempt = strict_result["attempts"][0]
            self.assertNotEqual("passed", strict_result["terminal_reason"])
            self.assertEqual(
                "direct", strict_attempt["candidate_observation"]["selection_route"]
            )
            self.assertEqual(
                "fallback_before_answer",
                strict_attempt["candidate_observation"]["route_disposition"],
            )
            strict_kinds = [row["kind"] for row in strict_attempt["host_processes"]]
            self.assertEqual(["graph_find"], strict_kinds)
            self.assertTrue(attempt["candidate_observation"]["selection_reason"])
            self.assertEqual("observed", result["phases"]["candidate_discovery"]["status"])
            self.assertEqual("observed", result["phases"]["context_composition"]["status"])
            self.assertEqual("missing", result["phases"]["cold_graph_build"]["status"])
            self.assertEqual(
                attempt["bindings"]["candidate_set_sha256"],
                attempt["candidate_observation"]["candidate_set_sha256"],
            )
            installed = study._install_graph_find(run_root)
            self.assertEqual(
                installed[1], attempt["bindings"]["graph_artifact_sha256"],
            )
            self.assertEqual(
                "installed_graph_find_process",
                attempt["candidate_observation"]["stage_clock"]["domain"],
            )
            self.assertGreater(attempt["candidate_observation"]["stage_ns"]["graph_build"], 0)
            self.assertTrue(attempt["grade"]["passed"])
            self.assertLessEqual(
                result["confirmed_time_to_correct_ns"], result["user_visible_wall_ns"],
            )

            # Preview the installed adapter outside the measured execute_trial.
            preview_command = [
                sys.executable, str(installed[0]), "--root", str(lane), "--prompt",
                "alpha_evidence_00",
                "--maximum-results", str(study.RETRIEVAL_NODE_LIMIT), "--byte-budget",
                str(study.CANDIDATE_AGGREGATE_BYTE_BUDGET),
                "--context-byte-budget", str(study.FINAL_CONTEXT_BYTE_BUDGET),
                "--ranked-context", "preview", "--diagnostics",
            ]
            preview_env = {
                "PATH": os.environ.get("PATH", os.defpath),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            preview_result = subprocess.run(
                preview_command, cwd=str(study.ROOT), env=preview_env,
                capture_output=True, check=False, timeout=120,
            )
            self.assertEqual(0, preview_result.returncode, preview_result.stderr)
            preview_payload = json.loads(preview_result.stdout.decode("utf-8"))[
                "ranked_context"
            ]
            preview = preview_payload["jev_preview"]
            self.assertIsNotNone(preview, preview_payload)
            required_ids = preview_payload["selection"]["context"][
                "required_candidate_ids"
            ]
            self.assertTrue(required_ids)
            request = preview["request"]
            optional_ids = [
                candidate["id"] for candidate in request["state"]["candidates"]
                if candidate["id"] not in required_ids
            ]
            preferred_id = optional_ids[-1] if optional_ids else None
            answers = {}
            for index, candidate in enumerate(request["state"]["candidates"]):
                name = f"candidate_{index}"
                criteria = request["questions"][name]["criteria"]
                preferred = candidate["id"] == preferred_id
                answers[name] = {
                    "type": "score",
                    "probabilities": {
                        "0": 0.0 if preferred else 1.0,
                        "1": 0.0,
                        "2": 1.0 if preferred else 0.0,
                    },
                    "legend": {str(i): value for i, value in enumerate(criteria)},
                    "score": 2.0 if preferred else 0.0,
                    "confidence": 1.0,
                }
            replay = {
                "schema_version": "velgraphing-jev-replay-v1",
                "request_sha256": preview["request_sha256"],
                "response": {
                    "model": request["model"],
                    "answers": answers,
                    "usage": {"input_tokens": 123, "output_tokens": 17},
                },
            }
            d_trial_id = "D-S-01"
            d_registration = {
                **registration, "trial_id": d_trial_id, "arm": "D",
            }
            d_pool = {
                **pool,
                "identity": {"route": "graph", "task_id": "S-01"},
                "jev_preview": {"request_sha256": preview["request_sha256"]},
            }
            d_manifest = {"entries": [
                {**row, "trial_id": d_trial_id}
                for row in process_manifest["entries"]
            ]}
            d_manifest["entries"][0]["thread_id"] = "answer_d_fixture"
            d_manifest["entries"][1]["thread_id"] = "grader_d_fixture"
            graph_calls = []
            replay_child_output = []
            original_run = subprocess.run

            def record_graph_run(*args, **kwargs):
                command = args[0]
                if len(command) > 1 and Path(command[1]) == installed[0]:
                    graph_calls.append((list(command), dict(kwargs.get("env", {}))))
                completed = original_run(*args, **kwargs)
                if len(command) > 1 and Path(command[1]) == installed[0]:
                    replay_child_output.append(completed.stdout)
                return completed

            with (
                patch.object(study, "verify_lane", return_value=([], before)) as d_verify,
                patch.object(study, "revalidate_lane") as d_revalidate,
                patch.object(study, "_load_manifest", return_value=source_manifest),
                patch.object(study, "_question_prompt", return_value="alpha_evidence_00"),
                patch.object(study.subprocess, "run", side_effect=record_graph_run),
            ):
                d_result = study.execute_trial(
                    freeze, d_registration, d_pool, rubric, lane_root, run_root,
                    d_manifest, study.digest(study.canonical(d_manifest)),
                    execution="fixture", replay=replay,
                )
                d_verify.assert_called_once()
                d_revalidate.assert_called_once()
                with self.assertRaisesRegex(
                    study.MeasurementError, "fixture_request_mismatch",
                ):
                    study.execute_trial(
                        freeze, d_registration, d_pool, rubric, lane_root, run_root,
                        d_manifest, study.digest(study.canonical(d_manifest)),
                        execution="fixture",
                        replay={**replay, "request_sha256": "0" * 64},
                    )

            self.assertEqual(1, len(graph_calls))
            graph_argv, graph_env = graph_calls[0]
            self.assertNotIn("--allow-network", graph_argv)
            self.assertNotIn("--approve-request-sha256", graph_argv)
            self.assertIn("--ranked-context", graph_argv)
            self.assertEqual("replay", graph_argv[graph_argv.index("--ranked-context") + 1])
            self.assertIn("--jev-mode", graph_argv)
            self.assertEqual("rerank", graph_argv[graph_argv.index("--jev-mode") + 1])
            self.assertIn("--jev-response", graph_argv)
            self.assertIn("--diagnostics", graph_argv)
            self.assertNotIn("TYPESAFE_API_KEY", graph_env)
            self.assertEqual("passed", d_result["terminal_reason"], d_result["attempts"])
            d_attempt = d_result["attempts"][0]
            d_process_kinds = [row["kind"] for row in d_attempt["host_processes"]]
            self.assertEqual(1, d_process_kinds.count("graph_find"))
            self.assertEqual(1, d_process_kinds.count("answer"))
            self.assertEqual(1, d_process_kinds.count("grader"))
            d_observation = d_attempt["jev_observation"]
            self.assertEqual("replay", d_observation["execution"])
            self.assertEqual("reranked", d_observation["status"])
            self.assertEqual(preview["request_sha256"], d_observation["request_sha256"])
            self.assertEqual(0, d_observation["attempted_calls"])
            self.assertTrue(d_observation["source_revalidated"])
            self.assertEqual("reranked", d_observation["order_source"])
            self.assertTrue(d_observation["jev_source_revalidated"])
            self.assertEqual(preview["request_bytes"], d_observation["request_bytes"])
            self.assertEqual(
                {"input_tokens": 123, "output_tokens": 17},
                d_observation["replayed_usage"],
            )
            self.assertTrue(
                set(required_ids).issubset(
                    d_attempt["candidate_observation"]["selected_candidate_ids"],
                ),
            )
            self.assertNotIn(
                "fresh-source-evidence", json.dumps(d_observation, sort_keys=True),
            )
            jev_usage = [row for row in d_attempt["model_calls"] if row["kind"] == "jev"]
            self.assertEqual([], jev_usage)
            self.assertFalse(d_attempt["coverage"]["model_calls"])
            self.assertFalse(d_result["usage_complete"])
            d_measurement = _v3_trial_measurement(d_registration, d_result)
            self.assertEqual(preview["request_bytes"], d_measurement["jev_request_bytes"])
            self.assertEqual(0, d_measurement["provider_calls"])
            self.assertIsNone(d_measurement["provider_input_tokens"])
            self.assertIsNone(d_measurement["provider_output_tokens"])

            # This is a controller/subprocess-contract simulation, not live
            # adapter or transport coverage. It shapes a replay result as a live
            # observation and intercepts the installed child. No provider call occurs.
            live_id = "D-S-02"
            live_registration = {
                **d_registration, "trial_id": live_id,
                "call_disposition": "planned",
            }
            live_pool = {
                **d_pool,
                "jev_preview": {
                    "request_sha256": preview["request_sha256"],
                    "request_bytes": preview["request_bytes"],
                },
            }
            live_payload = json.loads(replay_child_output[0].decode("utf-8"))
            live_ranked = live_payload["ranked_context"]
            live_observation = live_ranked["jev_observation"]
            live_ranked["mode"] = "evaluate"
            live_ranked["network_called"] = True
            live_observation["execution"] = "live"
            live_observation["attempted_calls"] = 1
            live_observation["usage"] = live_observation["replayed_usage"]
            live_observation["replayed_usage"] = None

            answer_identity = {
                "trial_id": live_id, "role": "answer", "thread_id": "answer_d_live",
                "model": "fixture-answer", "reasoning": "none",
            }
            grader_identity = {
                "trial_id": live_id, "role": "grader", "thread_id": "grader_d_live",
                "model": "fixture-grader", "reasoning": "none",
            }
            observed_answer_code = answer_code.replace(
                "'context_deliveries_complete':True}",
                "'context_deliveries_complete':True,'execution_identity':"
                f"{json.dumps(answer_identity, sort_keys=True)}}}",
            )
            observed_grader_code = grader_code.replace(
                "'model_calls_complete':False}",
                "'model_calls_complete':False,'execution_identity':"
                f"{json.dumps(grader_identity, sort_keys=True)}}}",
            ).replace("'grader_id':'fixture-grader'", f"'grader_id':'grader-{live_id}'")
            live_manifest = {"entries": [
                {**d_manifest["entries"][0], **answer_identity,
                 "argv": [sys.executable, "-c", observed_answer_code]},
                {**d_manifest["entries"][1], **grader_identity,
                 "argv": [sys.executable, "-c", observed_grader_code]},
            ]}
            live_run_root = root / "live-run"
            live_run_root.mkdir()
            live_installed = study._install_graph_find(live_run_root)
            fake_api_key = "test-only-graph-find-key"
            observed_graph_calls = []
            child_key_presence = []
            expected_live_children = {
                tuple(row["argv"]): row["role"] for row in live_manifest["entries"]
            }

            def simulate_live_graph(*args, **kwargs):
                command = list(args[0])
                environment = kwargs.get("env", {})
                if len(command) > 1 and Path(command[1]) == live_installed[0]:
                    child_key_presence.append(("graph_find", "TYPESAFE_API_KEY" in environment))
                    observed_graph_calls.append((
                        list(command), set(environment),
                        environment.get("TYPESAFE_API_KEY") == fake_api_key,
                    ))
                    return subprocess.CompletedProcess(
                        command, 0,
                        json.dumps(live_payload, sort_keys=True, separators=(",", ":")).encode(),
                        b"",
                    )
                if "--allow-network" in command:
                    raise AssertionError("unhandled network-enabled child process")
                role = expected_live_children.get(tuple(command))
                if role is None:
                    raise AssertionError(f"unexpected child process: {command!r}")
                child_key_presence.append((role, "TYPESAFE_API_KEY" in environment))
                return original_run(*args, **kwargs)

            live_budget = study.LiveJevBudget(live_run_root, 1)
            with (
                patch.object(study.os, "environ", {
                    "PATH": os.defpath, "TYPESAFE_API_KEY": fake_api_key,
                }),
                patch.object(study, "verify_lane", return_value=([], before)),
                patch.object(study, "revalidate_lane") as live_revalidate,
                patch.object(study, "_load_manifest", return_value=source_manifest),
                patch.object(study, "_question_prompt", return_value="alpha_evidence_00"),
                patch.object(study.subprocess, "run", side_effect=simulate_live_graph),
            ):
                live_result = study.execute_trial(
                    freeze, live_registration, live_pool, rubric, lane_root,
                    live_run_root, live_manifest,
                    study.digest(study.canonical(live_manifest)),
                    execution="observed", budget=live_budget,
                )
                live_revalidate.assert_called_once()

            self.assertEqual(1, len(observed_graph_calls))
            live_argv, live_env_keys, key_matched = observed_graph_calls[0]
            self.assertEqual({
                "PATH", "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE",
                "TYPESAFE_API_KEY",
            }, live_env_keys)
            self.assertTrue(key_matched)
            self.assertNotIn(fake_api_key, live_argv)
            self.assertIn("--ranked-context", live_argv)
            self.assertEqual("evaluate", live_argv[live_argv.index("--ranked-context") + 1])
            self.assertIn("--jev-mode", live_argv)
            self.assertEqual("rerank", live_argv[live_argv.index("--jev-mode") + 1])
            self.assertIn("--allow-network", live_argv)
            self.assertIn("--approve-request-sha256", live_argv)
            self.assertEqual(
                preview["request_sha256"],
                live_argv[live_argv.index("--approve-request-sha256") + 1],
            )
            self.assertIn("--diagnostics", live_argv)
            self.assertNotIn("--jev-response", live_argv)
            self.assertEqual(
                [("graph_find", True), ("answer", False), ("grader", False)],
                child_key_presence,
            )
            self.assertEqual("passed", live_result["terminal_reason"])
            live_attempt = live_result["attempts"][0]
            live_process_kinds = [row["kind"] for row in live_attempt["host_processes"]]
            self.assertEqual(1, live_process_kinds.count("graph_find"))
            self.assertEqual(1, live_process_kinds.count("answer"))
            self.assertEqual(1, live_process_kinds.count("grader"))
            self.assertEqual("live", live_attempt["jev_observation"]["execution"])
            self.assertEqual("reranked", live_attempt["jev_observation"]["status"])
            self.assertEqual(
                preview["request_sha256"], live_attempt["bindings"]["request_sha256"],
            )
            self.assertEqual(1, live_attempt["jev_observation"]["attempted_calls"])
            self.assertTrue(live_attempt["jev_observation"]["source_revalidated"])
            self.assertEqual(
                "installed_graph_find_entire_process_including_jev",
                live_attempt["candidate_observation"]["process_scope"],
            )
            self.assertEqual("reranked", live_attempt["jev_observation"]["order_source"])
            self.assertTrue(live_attempt["jev_observation"]["jev_source_revalidated"])
            self.assertEqual(
                preview["request_bytes"], live_attempt["jev_observation"]["request_bytes"],
            )
            self.assertTrue(set(required_ids).issubset(
                live_attempt["candidate_observation"]["selected_candidate_ids"],
            ))
            live_jev_calls = [
                call for call in live_attempt["model_calls"] if call["kind"] == "jev"
            ]
            self.assertEqual(1, len(live_jev_calls))
            self.assertEqual("provider_reported", live_jev_calls[0]["provenance"])
            self.assertEqual(123, live_jev_calls[0]["input_tokens"])
            self.assertEqual(17, live_jev_calls[0]["output_tokens"])
            self.assertFalse(live_attempt["coverage"]["model_calls"])
            self.assertEqual("missing", live_result["phases"]["provider"]["status"])
            self.assertFalse(live_result["usage_complete"])
            live_measurement = _v3_trial_measurement(live_registration, live_result)
            self.assertIsNone(live_measurement["provider_input_tokens"])
            self.assertIsNone(live_measurement["provider_output_tokens"])
            self.assertEqual(1, live_measurement["provider_calls"])
            live_receipt_path = live_run_root / "jev-calls" / f"{live_id}.json"
            live_receipt = json.loads(live_receipt_path.read_text(encoding="utf-8"))
            self.assertEqual("consumed", live_receipt["status"])
            self.assertEqual(1, live_receipt["attempted_calls"])
            self.assertEqual("reranked", live_receipt["provider_status"])
            self.assertNotIn(fake_api_key, json.dumps(live_result, sort_keys=True))
            self.assertNotIn(fake_api_key, live_receipt_path.read_text(encoding="utf-8"))

            # A failed child cannot consume the reservation as a confirmed call.
            failed_id = "D-S-03"
            failed_registration = {**live_registration, "trial_id": failed_id}
            failed_manifest = {"entries": [
                {**row, "trial_id": failed_id,
                 "thread_id": f"{row['role']}_d_failed"}
                for row in live_manifest["entries"]
            ]}
            failed_run_root = root / "failed-run"
            failed_run_root.mkdir()
            failed_installed = study._install_graph_find(failed_run_root)
            failed_graph_calls = []
            expected_failed_children = {
                tuple(row["argv"]): row["role"] for row in failed_manifest["entries"]
            }

            def fail_live_graph(*args, **kwargs):
                command = list(args[0])
                if len(command) > 1 and Path(command[1]) == failed_installed[0]:
                    failed_graph_calls.append(list(command))
                    return subprocess.CompletedProcess(command, 1, b"", b"child failed")
                if "--allow-network" in command:
                    raise AssertionError("unhandled network-enabled child process")
                if tuple(command) not in expected_failed_children:
                    raise AssertionError(f"unexpected child process: {command!r}")
                return original_run(*args, **kwargs)

            failed_budget = study.LiveJevBudget(failed_run_root, 1)
            with (
                patch.object(study.os, "environ", {
                    "PATH": os.defpath, "TYPESAFE_API_KEY": fake_api_key,
                }),
                patch.object(study, "verify_lane", return_value=([], before)),
                patch.object(study, "revalidate_lane"),
                patch.object(study, "_load_manifest", return_value=source_manifest),
                patch.object(study, "_question_prompt", return_value="alpha_evidence_00"),
                patch.object(study.subprocess, "run", side_effect=fail_live_graph),
            ):
                failed_result = study.execute_trial(
                    freeze, failed_registration, live_pool, rubric, lane_root,
                    failed_run_root, failed_manifest,
                    study.digest(study.canonical(failed_manifest)),
                    execution="observed", budget=failed_budget,
                )
            self.assertEqual("measurement_error", failed_result["terminal_reason"])
            self.assertEqual(
                "installed_graph_find_failed",
                failed_result["attempts"][0]["failure_reason"],
            )
            self.assertEqual(1, len(failed_graph_calls))
            failed_receipt_path = failed_run_root / "jev-calls" / f"{failed_id}.json"
            failed_receipt = json.loads(failed_receipt_path.read_text(encoding="utf-8"))
            self.assertEqual("reserved_unknown_if_consumed", failed_receipt["status"])
            self.assertIsNone(failed_receipt["attempted_calls"])
            self.assertNotIn(fake_api_key, failed_receipt_path.read_text(encoding="utf-8"))

            # A live response must report the preview's exact request size.
            mismatch_id = "D-S-04"
            mismatch_run_root = root / "mismatch-run"
            mismatch_run_root.mkdir()
            mismatch_installed = study._install_graph_find(mismatch_run_root)
            mismatched_live_payload = deepcopy(live_payload)
            mismatched_live_payload["ranked_context"]["jev_observation"]["request_bytes"] += 1
            mismatch_graph_calls = []

            def mismatch_live_graph(*args, **kwargs):
                command = list(args[0])
                if len(command) > 1 and Path(command[1]) == mismatch_installed[0]:
                    mismatch_graph_calls.append(command)
                    return subprocess.CompletedProcess(
                        command, 0,
                        json.dumps(mismatched_live_payload, sort_keys=True,
                                   separators=(",", ":")).encode(),
                        b"",
                    )
                raise AssertionError(f"unexpected child after request-size mismatch: {command!r}")

            mismatch_registration = {**live_registration, "trial_id": mismatch_id}
            mismatch_manifest = {"entries": [
                {**row, "trial_id": mismatch_id}
                for row in live_manifest["entries"]
            ]}
            mismatch_budget = study.LiveJevBudget(mismatch_run_root, 1)
            with (
                patch.object(study.os, "environ", {
                    "PATH": os.defpath, "TYPESAFE_API_KEY": fake_api_key,
                }),
                patch.object(study, "verify_lane", return_value=([], before)),
                patch.object(study, "revalidate_lane"),
                patch.object(study, "_load_manifest", return_value=source_manifest),
                patch.object(study, "_question_prompt", return_value="alpha_evidence_00"),
                patch.object(study.subprocess, "run", side_effect=mismatch_live_graph),
            ):
                mismatch_result = study.execute_trial(
                    freeze, mismatch_registration, live_pool, rubric, lane_root,
                    mismatch_run_root, mismatch_manifest,
                    study.digest(study.canonical(mismatch_manifest)),
                    execution="observed", budget=mismatch_budget,
                )
            self.assertEqual("measurement_error", mismatch_result["terminal_reason"])
            self.assertEqual(1, len(mismatch_graph_calls))
            mismatch_receipt = json.loads(
                (mismatch_run_root / "jev-calls" / f"{mismatch_id}.json")
                .read_text(encoding="utf-8"),
            )
            self.assertEqual("reserved_unknown_if_consumed", mismatch_receipt["status"])

            changed_manifest = dict(source_manifest)
            changed_manifest["snapshot_sha256"] = "0" * 64
            mismatch_trial = study.Trial(
                {**result["identity"], "trial_id": "C-S-02", "task_id": "S-02",
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

    def test_historical_implementation_bindings_ignore_worktree_drift(self) -> None:
        freeze, _, _ = study.load_bundle()
        for name in ("retrieval", "selection"):
            path = freeze["implementation_bindings"][name]["path"]
            current = study.digest((ROOT / path).read_bytes())
            bound = study._bound_blob_sha256(
                ROOT, freeze["product"]["commit"], path,
                "implementation_binding_invalid",
            )
            self.assertNotEqual(current, freeze["implementation_bindings"][name]["sha256"])
            self.assertEqual(bound, freeze["implementation_bindings"][name]["sha256"])

    def test_refresh_rebinds_stale_successor_and_clears_prior_authority(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        names = (
            "freeze", "questions", "rubrics", "preflight", "successor-rubrics",
            "successor-ttc-contract", "successor-freeze", "successor-preflight",
        )
        with tempfile.TemporaryDirectory(prefix="successor-refresh-", dir=local) as raw:
            root = Path(raw)
            for name in names:
                shutil.copy(BENCHMARK / f"{name}.json", root / f"{name}.json")
            successor_path = root / "successor-rubrics.json"
            successor = json.loads(successor_path.read_text(encoding="utf-8"))
            successor["implementation_bindings"]["controller"]["sha256"] = "0" * 64
            successor["implementation_bindings"]["host"]["sha256"] = "0" * 64
            successor_path.write_text(json.dumps(successor), encoding="utf-8")
            contract_path = root / "successor-ttc-contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["status"] = "ready_after_final_user_reack"
            contract["bindings"]["controller"]["sha256"] = "0" * 64
            contract["bindings"]["host"]["sha256"] = "0" * 64
            contract["bindings"]["calibration"]["sha256"] = "0" * 64
            contract["bindings"]["successor_rubric"]["sha256"] = "0" * 64
            contract["bindings"]["lane_manifest"]["sha256"] = "1" * 64
            contract["bindings"]["lane_manifest"]["status"] = "frozen"
            contract["remaining_authority"]["absolute_python_executable"] = sys.executable
            contract["remaining_authority"]["lane_manifest_sha256"] = "1" * 64
            contract["remaining_authority"]["final_user_reack"] = []
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            successor_freeze_path = root / "successor-freeze.json"
            successor_freeze = json.loads(
                successor_freeze_path.read_text(encoding="utf-8")
            )
            successor_freeze["bindings"]["package_candidate"]["candidate_sha256"] = (
                "0" * 64
            )
            successor_freeze_path.write_text(
                json.dumps(successor_freeze), encoding="utf-8",
            )
            result = study.freeze_successor(
                root, PINNED_LANES, CUSTODY, ROOT, refresh=True,
            )
            contract = json.loads(
                (root / "successor-ttc-contract.json").read_text(encoding="utf-8")
            )
            successor_freeze = json.loads(
                (root / "successor-freeze.json").read_text(encoding="utf-8")
            )
            successor_preflight = json.loads(
                (root / "successor-preflight.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                result["successor_freeze_sha256"],
                study.digest((root / "successor-freeze.json").read_bytes()),
            )
            self.assertNotEqual(
                successor_preflight["pool_artifact_sha256"], study.LOCAL_POOL_SHA256,
            )
            self.assertEqual(
                successor_preflight["source_preflight_sha256"],
                study.digest(study._json_bytes(
                    successor_preflight["source_free_preflight"]
                )),
            )
            self.assertEqual(
                contract["status"], "pending_lane_manifest_and_final_user_reack",
            )
            self.assertIsNone(contract["bindings"]["lane_manifest"]["sha256"])
            self.assertNotEqual(contract["remaining_authority"]["final_user_reack"], [])
            self.assertFalse(successor_freeze["execution_policy"]["execution_ready"])
            self.assertFalse(
                successor_freeze["execution_policy"]["provider_spend_authorized"]
            )
            current_release = json.loads(
                (ROOT / "plugins/graph-engineering/.codex-plugin/release-manifest.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(
                successor_freeze["bindings"]["package_candidate"]["candidate_sha256"],
                current_release["candidate_sha256"],
            )

        with tempfile.TemporaryDirectory(prefix="successor-refresh-tamper-", dir=local) as raw:
            root = Path(raw)
            for name in names:
                shutil.copy(BENCHMARK / f"{name}.json", root / f"{name}.json")
            successor_path = root / "successor-rubrics.json"
            successor = json.loads(successor_path.read_text(encoding="utf-8"))
            successor["arm_labels"]["A"] = "tampered"
            successor_path.write_text(json.dumps(successor), encoding="utf-8")
            with self.assertRaisesRegex(study.StudyError, "successor_rubrics_invalid"):
                study.freeze_successor(root, LANES, CUSTODY, ROOT, refresh=True)

    def test_bind_successor_lanes_enables_offline_approval(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        names = (
            "freeze", "questions", "rubrics", "preflight", "successor-rubrics",
            "successor-ttc-contract", "successor-freeze", "successor-preflight",
        )
        with tempfile.TemporaryDirectory(prefix="successor-bind-", dir=local) as raw:
            root = Path(raw)
            for name in names:
                shutil.copy(BENCHMARK / f"{name}.json", root / f"{name}.json")
            study.freeze_successor(root, PINNED_LANES, CUSTODY, ROOT, refresh=True)
            freeze = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
            bindings = {
                "schema_version": "velgraphing-four-arm-lane-bindings-v1",
                "bindings": [{
                    "trial_id": trial_id,
                    "answer_thread_id": (
                        f"m09_bind_r1_luna_answer_"
                        f"{trial_id.lower().replace('-', '_')}"
                    ),
                    "answer_task_path": (
                        f"/root/m09_bind_r1_luna_answer_"
                        f"{trial_id.lower().replace('-', '_')}"
                    ),
                    "grader_thread_id": (
                        f"m09_bind_r1_astra_grader_"
                        f"{trial_id.lower().replace('-', '_')}"
                    ),
                    "grader_task_path": (
                        f"/root/m09_bind_r1_astra_grader_"
                        f"{trial_id.lower().replace('-', '_')}"
                    ),
                } for trial_id in study.DISPATCH],
            }
            manifest_path = root / "lane-manifest.json"
            manifest_sha = study.freeze_lane_manifest(
                bindings, freeze, manifest_path, sys.executable,
            )
            result = study.bind_successor_lane_manifest(
                root, root, CUSTODY, sys.executable, ROOT,
            )
            contract = json.loads(
                (root / "successor-ttc-contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                contract["status"], "frozen_pending_final_user_reack",
            )
            self.assertEqual(
                contract["bindings"]["lane_manifest"]["sha256"], manifest_sha,
            )
            self.assertEqual(
                contract["remaining_authority"]["absolute_python_executable"],
                sys.executable,
            )
            self.assertFalse(result["execution_ready"])
            approved = study.approve_successor(
                root, CUSTODY,
                approved_max_live_jev_calls=8,
                approved_request_set=study.REQUEST_BYTE_SET_SHA256,
                approved_max_additional_provider_spend_usd="0.9031",
                approved_manifest=manifest_sha,
                approved_python=sys.executable,
            )
            self.assertTrue(approved["execution_ready"])

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
        self.successor_freeze, self.successor_preflight = study.load_successor_freeze(
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
            study.digest((ROOT / "scripts/benchmarks/four_arm_study_v1.py").read_bytes()),
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

    def test_successor_freeze_binds_current_candidate_and_pending_authority(self) -> None:
        generated = study._build_successor_freeze(
            self.freeze, self.successor, self.ttc, 8, BENCHMARK, ROOT,
        )
        self.assertEqual(generated, self.successor_freeze)
        bindings = self.successor_freeze["bindings"]
        policy = self.successor_freeze["execution_policy"]
        self.assertEqual(
            self.successor_freeze["status"],
            "pending_lane_manifest_and_final_user_reack",
        )
        self.assertEqual(
            bindings["package_candidate"]["candidate_sha256"],
            json.loads((ROOT / "plugins/graph-engineering/.codex-plugin/release-manifest.json")
                       .read_text(encoding="utf-8"))["candidate_sha256"],
        )
        self.assertEqual(bindings["pool_bindings"], self.ttc["bindings"]["pool_bindings"])
        self.assertEqual(policy["fresh_answer_lanes"], 16)
        self.assertEqual(policy["fresh_grader_lanes"], 16)
        self.assertEqual(policy["exact_host_argv_arrays"], 32)
        self.assertEqual(policy["planned_jev_calls"], 8)
        self.assertEqual(policy["jev_max_calls"], 8)
        self.assertEqual(policy["jev_retries"], 0)
        self.assertEqual(policy["task_retries"], 0)
        self.assertEqual(policy["answer_tasks_created"], 0)
        self.assertEqual(policy["grader_tasks_created"], 0)
        self.assertEqual(policy["live_lanes_created"], 0)
        self.assertFalse(policy["execution_ready"])
        self.assertEqual(policy["max_additional_provider_spend_usd"], "0.9031")
        self.assertEqual(
            policy["provider_budget_authority"],
            self.ttc["provider_budget_authority"],
        )
        self.assertFalse(policy["provider_spend_authorized"])
        self.assertTrue(policy["final_user_reack_required"])
        self.assertEqual(
            set(self.ttc["remaining_authority"]["final_user_reack"]),
            {
                "request_byte_set_sha256", "eight_call_cap",
                "total_authorized_provider_budget_usd",
                "operator_reported_spend_to_date_usd",
                "max_additional_provider_spend_usd",
                "lane_manifest_sha256", "absolute_python_executable",
            },
        )
        self.assertEqual(self.successor_preflight["executed_calls"], {
            "answer": 0, "grader": 0, "jev": 0, "provider": 0,
        })
        self.assertEqual(self.successor_preflight["retries"], 0)
        self.assertEqual(self.successor_preflight["planned_jev_calls"], 8)

        invalid = deepcopy(self.successor_freeze)
        invalid["execution_policy"]["jev_max_calls"] = 9
        with self.assertRaisesRegex(study.StudyError, "successor_freeze_invalid"):
            study._validate_successor_freeze(
                invalid, self.freeze, self.successor, self.ttc, 8, BENCHMARK, ROOT,
            )

        invalid_preflight = deepcopy(self.successor_preflight)
        invalid_preflight["executed_calls"]["provider"] = 1
        with self.assertRaisesRegex(study.StudyError, "successor_preflight_invalid"):
            study._validate_successor_preflight(
                invalid_preflight, self.successor_freeze,
                study.digest((BENCHMARK / study.SUCCESSOR_FREEZE).read_bytes()),
                self.freeze, BENCHMARK,
            )

    def _copy_successor_bundle(self, root: Path) -> None:
        for name in (
            "freeze", "questions", "rubrics", "preflight", "successor-rubrics",
            "successor-ttc-contract", "successor-freeze", "successor-preflight",
        ):
            shutil.copy(BENCHMARK / f"{name}.json", root / f"{name}.json")
        lane_bindings = {
            "schema_version": "velgraphing-four-arm-lane-bindings-v1",
            "bindings": [{
                "trial_id": trial_id,
                "answer_thread_id": f"answer_{trial_id.lower().replace('-', '_')}",
                "answer_task_path": f"/root/answer_{trial_id.lower().replace('-', '_')}",
                "grader_thread_id": f"grader_{trial_id.lower().replace('-', '_')}",
                "grader_task_path": f"/root/grader_{trial_id.lower().replace('-', '_')}",
            } for trial_id in study.DISPATCH],
        }
        lane_manifest = root / "lane-manifest.json"
        lane_sha = study.freeze_lane_manifest(
            lane_bindings, self.freeze, lane_manifest, sys.executable,
        )
        pending = deepcopy(self.ttc)
        pending["status"] = "frozen_pending_final_user_reack"
        pending["bindings"]["lane_manifest"] = {
            "schema_version": self.freeze["lane_identity_contract"]["handoff_schema"],
            "entry_count": 32,
            "sha256": lane_sha,
            "status": "frozen",
            "thread_id_semantics": study.THREAD_ID_SEMANTICS,
            "task_path_semantics": study.TASK_PATH_SEMANTICS,
        }
        pending["remaining_authority"]["absolute_python_executable"] = sys.executable
        pending["remaining_authority"]["lane_manifest_sha256"] = lane_sha
        pending["remaining_authority"]["final_user_reack"] = [
            "request_byte_set_sha256", "eight_call_cap",
            "total_authorized_provider_budget_usd",
            "operator_reported_spend_to_date_usd",
            "max_additional_provider_spend_usd", "lane_manifest_sha256",
            "absolute_python_executable",
        ]
        pending_freeze = study._build_successor_freeze(
            self.freeze, self.successor, pending, 8, root, ROOT,
        )
        pending_freeze_sha = study.digest(study._json_bytes(pending_freeze))
        pending_preflight = study._build_successor_preflight(
            pending_freeze_sha,
            self.successor_preflight["source_free_preflight"],
            self.successor_preflight["source_preflight_sha256"],
            self.successor_preflight["pool_artifact_sha256"],
            pending_freeze,
        )
        (root / "successor-ttc-contract.json").write_bytes(
            study._json_bytes(pending)
        )
        (root / "successor-freeze.json").write_bytes(
            study._json_bytes(pending_freeze)
        )
        (root / "successor-preflight.json").write_bytes(
            study._json_bytes(pending_preflight)
        )

    def test_approve_successor_materializes_ready_state_without_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_successor_bundle(root)
            result = study.approve_successor(
                root, CUSTODY,
                approved_max_live_jev_calls=8,
                approved_request_set=study.REQUEST_BYTE_SET_SHA256,
                approved_max_additional_provider_spend_usd="0.9031",
                approved_manifest=json.loads(
                    (root / "successor-ttc-contract.json").read_text(encoding="utf-8")
                )["bindings"]["lane_manifest"]["sha256"],
                approved_python=json.loads(
                    (root / "successor-ttc-contract.json").read_text(encoding="utf-8")
                )["remaining_authority"][
                    "absolute_python_executable"
                ],
            )
            contract, _ = study.load_successor_ttc_contract(
                root, ROOT, custody_path=CUSTODY,
            )
            successor_freeze, successor_preflight = study.load_successor_freeze(
                root, ROOT, custody_path=CUSTODY,
            )
            self.assertTrue(result["execution_ready"])
            self.assertEqual(contract["status"], "ready_after_final_user_reack")
            self.assertEqual(contract["remaining_authority"]["final_user_reack"], [])
            self.assertTrue(successor_freeze["execution_policy"]["execution_ready"])
            self.assertFalse(successor_freeze["execution_policy"]["final_user_reack_required"])
            self.assertTrue(successor_freeze["execution_policy"]["provider_spend_authorized"])
            self.assertEqual(successor_preflight["executed_calls"], {
                "answer": 0, "grader": 0, "jev": 0, "provider": 0,
            })
            self.assertEqual(successor_preflight["retries"], 0)

    def test_approve_successor_rejects_mismatch_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_successor_bundle(root)
            before = {
                name: (root / f"{name}.json").read_bytes()
                for name in (
                    "successor-ttc-contract", "successor-freeze", "successor-preflight",
                )
            }
            with self.assertRaisesRegex(
                study.StudyError, "approval_request_byte_set_mismatch",
            ):
                study.approve_successor(
                    root, CUSTODY,
                    approved_max_live_jev_calls=8,
                    approved_request_set="0" * 64,
                    approved_max_additional_provider_spend_usd="0.9031",
                    approved_manifest=json.loads(
                        (root / "successor-ttc-contract.json").read_text(encoding="utf-8")
                    )["bindings"]["lane_manifest"]["sha256"],
                    approved_python=json.loads(
                        (root / "successor-ttc-contract.json").read_text(encoding="utf-8")
                    )["remaining_authority"][
                        "absolute_python_executable"
                    ],
                )
            for name, raw in before.items():
                self.assertEqual(raw, (root / f"{name}.json").read_bytes())

    def test_additional_provider_spend_uses_unverified_operator_account_truth(self) -> None:
        authority = self.ttc["provider_budget_authority"]
        self.assertEqual(study.MAX_ADDITIONAL_PROVIDER_SPEND_USD, Decimal("0.9031"))
        self.assertEqual(authority["total_authorized_usd"], "1.0000")
        self.assertEqual(authority["operator_reported_spend_to_date_usd"], "0.0969")
        self.assertEqual(authority["operator_reported_calls_to_date"], 108)
        self.assertEqual(authority["operator_reported_tokens_to_date"], 2_371_440)
        self.assertEqual(authority["remaining_authorized_usd"], "0.9031")
        self.assertEqual(authority["source"], "operator_provided_typesafe_account_truth")
        self.assertFalse(authority["provider_verified"])
        self.assertEqual(authority["historical_reservation_reconciliation"], {
            "amount_usd": "0.359789241",
            "basis": "historical_request_byte_based_total_reservation",
            "status": "retired_historical_only",
            "counts_as_spend": False,
            "charged": False,
            "subtract_again_from_remaining_budget": False,
            "attributable_to_operator_reported_account_level_spend": False,
        })
        self.assertEqual(
            Decimal(authority["operator_reported_spend_to_date_usd"])
            + Decimal(authority["remaining_authorized_usd"]),
            Decimal(authority["total_authorized_usd"]),
        )
        with self.assertRaisesRegex(
            study.MeasurementError, "max_additional_provider_spend_not_approved",
        ):
            study._validate_approved_additional_provider_spend("1.00")
        study._validate_approved_additional_provider_spend("0.9031")

    def test_pool_hash_mismatch_blocks_preparation_and_lane_creation(self) -> None:
        expected = study.digest(b"frozen-source-bound-pools")
        self.assertEqual(
            study._require_successor_pool_hash(b"frozen-source-bound-pools", {
                "pool_artifact_sha256": expected,
            }),
            expected,
        )
        with self.assertRaisesRegex(
            study.StudyError, "successor_pool_artifact_hash_invalid",
        ):
            study._require_successor_pool_hash(b"stale-pools", {
                "pool_artifact_sha256": expected,
            })

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            pool_path = Path(directory) / "phase-2-pools.json"
            pool_path.write_bytes(b"stale-pools")
            relative_path = pool_path.relative_to(ROOT).as_posix()
            with patch.object(study, "LOCAL_POOL_ARTIFACT", relative_path):
                with self.assertRaisesRegex(
                    study.StudyError, "successor_pool_artifact_hash_invalid",
                ):
                    study.load_prepared_successor_pool(
                        BENCHMARK, pool_path, CUSTODY, ROOT,
                    )
                with patch.object(study, "execute_trial") as execute_trial:
                    with self.assertRaisesRegex(
                        study.StudyError, "successor_pool_artifact_hash_invalid",
                    ):
                        study.run_study(
                            BENCHMARK, pool_path, Path(directory),
                            Path(directory) / "run", Path(directory) / "lane-manifest.json",
                            CUSTODY, allow_live_jev=True, approved_cap=8,
                            approved_request_set=study.REQUEST_BYTE_SET_SHA256,
                            approved_max_additional_provider_spend_usd="0.9031",
                            approved_manifest="0" * 64,
                            approved_python=sys.executable,
                        )
                    execute_trial.assert_not_called()

        error = StringIO()
        with (
            patch.object(
                study, "load_prepared_successor_pool",
                side_effect=study.StudyError("successor_pool_artifact_hash_invalid"),
            ),
            patch.object(study, "freeze_lane_manifest") as create_lanes,
            redirect_stderr(error),
        ):
            with self.assertRaises(SystemExit) as stopped:
                study.main([
                    "freeze-lanes", "--root", str(BENCHMARK),
                    "--bindings", str(BENCHMARK / "not-read-before-pool-check.json"),
                    "--run-root", str(ROOT / ".velgraphing-local/t060-no-lanes"),
                    "--python-executable", sys.executable,
                    "--witness-custody", str(CUSTODY),
                ])
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("successor_pool_artifact_hash_invalid", error.getvalue())
        create_lanes.assert_not_called()

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
            sealed["budget"]["max_additional_provider_spend_usd"], "0.9031",
        )
        self.assertEqual(
            sealed["budget"]["provider_budget_authority"][
                "operator_reported_spend_to_date_usd"
            ],
            "0.0969",
        )
        self.assertNotIn("total_reservation_usd", sealed["budget"])
        self.assertEqual(
            sealed["budget"]["budget_semantics"],
            "operator_reported_remaining_authority_not_provider_verified",
        )
        with tempfile.TemporaryDirectory(dir=local) as directory:
            historical = study._seal(
                Path(directory), self.freeze,
                {"A-S-01": {"trial_id": "A-S-01", "task_id": "S-01"}},
                [result], "0" * 64, "fixture",
            )
        self.assertEqual(
            historical["budget"]["total_reservation_usd"],
            str(study.TOTAL_RESERVATION),
        )
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
        unselected = {
            "id": "f" * 64, "path": "unselected.py", "source_sha256": "2" * 64,
            "byte_start": 0, "byte_end": 100, "required": False,
        }
        packet = {
            "schema_version": "fixture", "query": "question",
            "candidates": [candidate, unselected],
        }
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
                self.assertEqual(
                    [row["id"] for row in updated["candidates"]], order,
                )
                self.assertNotIn(unselected["id"], order)
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
        self.assertEqual(
            self.ttc["bindings"]["lane_manifest"]["thread_id_semantics"],
            study.THREAD_ID_SEMANTICS,
        )
        self.assertEqual(self.ttc["remaining_authority"]["answer_task_names"], 16)
        self.assertEqual(self.ttc["remaining_authority"]["grader_task_names"], 16)
        self.assertEqual(self.ttc["remaining_authority"]["live_lanes_created"], 0)
        self.assertEqual(
            set(self.ttc["remaining_authority"]["final_user_reack"]),
            {
                "request_byte_set_sha256", "eight_call_cap",
                "total_authorized_provider_budget_usd",
                "operator_reported_spend_to_date_usd",
                "max_additional_provider_spend_usd",
                "lane_manifest_sha256", "absolute_python_executable",
            },
        )
        self.assertIsNone(self.ttc["remaining_authority"]["absolute_python_executable"])
        self.assertIsNone(self.ttc["remaining_authority"]["lane_manifest_sha256"])
        self.assertIsNone(self.ttc["bindings"]["lane_manifest"]["sha256"])
        self.assertFalse(self.successor_freeze["execution_policy"]["execution_ready"])
        self.assertFalse(
            self.successor_freeze["execution_policy"]["provider_spend_authorized"]
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
            "provider_budget_authority": lambda value: value[
                "provider_budget_authority"
            ].update(max_additional_spend_usd="1.0000"),
            "manifest": lambda value: value["bindings"]["lane_manifest"].update(
                sha256="0" * 64
            ),
            "manifest_thread_id_semantics": lambda value: value[
                "bindings"]["lane_manifest"].update(
                    thread_id_semantics="opaque_host_id",
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
                    "thread_id": f"thread_{role}_{trial_id.lower().replace('-', '_')}",
                    "canonical_task_path": (
                        f"/root/thread_{role}_{trial_id.lower().replace('-', '_')}"
                    ),
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
        self.assertTrue(all(
            row["argv"][row["argv"].index("--wait-seconds") + 1] == "600"
            for row in manifest["entries"]
        ))
        grader = next(row for row in manifest["entries"] if row["role"] == "grader")
        grader["model"] = "gpt-5.6-luna"
        with self.assertRaisesRegex(study.StudyError, "lane_manifest_invalid"):
            study.validate_lane_manifest(manifest, self.freeze)
        wrong_path = self.lane_manifest()
        wrong_path["entries"][0]["canonical_task_path"] = "/root/other_task"
        with self.assertRaisesRegex(study.StudyError, "lane_manifest_invalid"):
            study.validate_lane_manifest(wrong_path, self.freeze)
        for invalid_name in ("T070_r1_luna_answer_a_s_01", "t070-r1-luna-answer-a-s-01"):
            invalid = self.lane_manifest()
            invalid["entries"][0]["thread_id"] = invalid_name
            with self.subTest(thread_id=invalid_name), self.assertRaisesRegex(
                study.StudyError, "lane_manifest_invalid",
            ):
                study.validate_lane_manifest(invalid, self.freeze)

    def test_validate_cli_accepts_frozen_manifest_runtime_binding(self) -> None:
        local = ROOT / ".velgraphing-local"
        local.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local) as directory:
            root = Path(directory)
            bindings = {
                "schema_version": "velgraphing-four-arm-lane-bindings-v1",
                "bindings": [{
                    "trial_id": trial_id,
                    "answer_thread_id": f"answer_{trial_id.lower().replace('-', '_')}",
                    "answer_task_path": f"/root/answer_{trial_id.lower().replace('-', '_')}",
                    "grader_thread_id": f"grader_{trial_id.lower().replace('-', '_')}",
                    "grader_task_path": f"/root/grader_{trial_id.lower().replace('-', '_')}",
                } for trial_id in study.DISPATCH],
            }
            invalid_bindings = deepcopy(bindings)
            invalid_bindings["bindings"][0]["answer_thread_id"] = "T070-r1-answer-A-S-01"
            invalid_manifest = root / "invalid-lane-manifest.json"
            with self.assertRaisesRegex(study.StudyError, "lane_bindings_invalid"):
                study.freeze_lane_manifest(
                    invalid_bindings, self.freeze, invalid_manifest, sys.executable,
                )
            self.assertFalse(invalid_manifest.exists())
            manifest = root / "lane-manifest.json"
            manifest.write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(study.StudyError, "handoff_file_exists"):
                study.freeze_lane_manifest(bindings, self.freeze, manifest, sys.executable)
            self.assertEqual(manifest.read_text(encoding="utf-8"), "stale")
            study.freeze_lane_manifest(
                bindings, self.freeze, manifest, sys.executable,
                replace_existing=True,
            )
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
