"""Offline qualification for the 24-trial calibration coordinator."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))
from time_to_correct import (Budget, MeasurementError, Trial, canonical, digest,
                             save_completed_trial, summarize)
from time_to_correct_calibration import (HANDOFF_PATH, LiveJevBudget, bind_controller,
                                         calibration_run_root, controller_identity,
                                         finish_workers, fixture_identity,
                                         handoff_argv, jev_answer_payload, load_calibration, load_pilot,
                                         qualify,
                                         PREPARATION_RESPONSE_CONTRACT,
                                         request_candidates, require_resumable, revalidate_lane,
                                         run_calibration, start_fixture_worker,
                                         summarize_calibration, trial_identity,
                                         validate_live_authority, verify_lane,
                                         V3_CANDIDATE_POLICY, V3_MEASUREMENT_CONTRACT)
from time_to_correct_handoff import (
    CAPTURE_RECEIPT,
    COMPLETION_ATTESTATION,
    HandoffError,
    MAX_BYTES,
    RAW_ASSISTANT_RESPONSE,
    attest_draft,
    capture_host_response,
    normalize_json_object,
    read_attested_draft,
    read_canonical,
)
from time_to_correct_host import (ANSWER_RESPONSE_CONTRACT, GRADER_RESPONSE_CONTRACT,
                                  run_process_trial)
from time_to_correct_jev import evaluate_live


def write_lane_manifest(
    root: Path, trial_id: str, role: str, thread_id: str,
    model: str = "gpt-5.6-luna", reasoning: str = "medium",
) -> str:
    root.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-c", "pass"]
    raw = canonical({
        "schema_version": "velgraphing-v4-luna-lane-manifest-v1",
        "entries": [{
            "trial_id": trial_id,
            "role": role,
            "thread_id": thread_id,
            "model": model,
            "reasoning": reasoning,
            "argv": command,
            "argv_sha256": digest(canonical(command)),
        }],
    })
    (root / "lane-manifest.json").write_bytes(raw)
    return digest(raw)


def write_lane_request(root: Path, identity: dict[str, str]) -> None:
    contract = deepcopy(ANSWER_RESPONSE_CONTRACT)
    schema = contract["json_schema"]
    schema["required"].append("execution_identity")
    schema["properties"]["execution_identity"] = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(identity),
        "properties": {key: {"const": value} for key, value in identity.items()},
    }
    lane = (
        root / "trials" / identity["trial_id"] / "attempt-0" / identity["role"]
    )
    lane.mkdir(parents=True, exist_ok=True)
    (lane / "request.json").write_bytes(canonical({"response_contract": contract}))


T310_RAW_RESPONSE = (
    b'{"schema_version":"velgraphing-answer-output-v1","answer_text":"'
    b'`quick_sort([3, 1, 2])` removes one randomly chosen pivot from the original '
    b'input list using `pop`, so the input is left with the other two elements. It '
    b'returns `[1, 2, 3]`. For each recursive partition, it puts remaining items '
    b'`<= pivot` into a `lesser` list and items `> pivot` into a `greater` list, '
    b'recursively sorts both, then combines them around the pivot. When a collection '
    b'has fewer than two elements, it returns that collection unchanged. Source: '
    b'`sorts/quick_sort.py` [c1]","usage":null,"model_calls_complete":true,'
    b'"context_deliveries_complete":true,"execution_identity":{"model":'
    b'"gpt-5.6-luna","reasoning":"medium","role":"answer","thread_id":'
    b'"01a0c3b9-3309-7500-a3ad-6cc713dcf659","trial_id":"INLINE-CANARY"}}'
)


def capture_test_response(
    root: Path, trial_id: str, role: str, thread_id: str,
    model: str = "gpt-5.6-luna", reasoning: str = "medium",
) -> tuple[Path, str, bytes]:
    identity = {
        "trial_id": trial_id, "role": role, "thread_id": thread_id,
        "model": model, "reasoning": reasoning,
    }
    manifest_sha256 = write_lane_manifest(
        root, trial_id, role, thread_id, model, reasoning
    )
    write_lane_request(root, identity)
    value = json.loads(T310_RAW_RESPONSE)
    value["execution_identity"] = identity
    raw = json.dumps(value, indent=2).encode()
    draft, _, _ = capture_host_response(
        root, trial_id, 0, role, raw,
        thread_id=thread_id, model=model, reasoning=reasoning,
        lane_manifest_sha256=manifest_sha256,
    )
    return draft, manifest_sha256, canonical(value)


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

    def test_v2_freeze_is_explicit_and_cannot_accept_v1_results(self):
        v1 = load_calibration(ROOT)
        v2 = load_calibration(ROOT, "velgraphing-ttc-calibration-v2")
        self.assertEqual(v2["registered_trials"], v1["registered_trials"])
        self.assertEqual(v2["source_pilot"], v1["source_pilot"])
        self.assertEqual((v2["answer_model"], v2["reasoning"], v2["provider_retries"],
                          v2["max_live_jev_calls"]), ("gpt-5.6-sol", "medium", 0, 12))
        self.assertEqual(v2["timeouts_seconds"], {
            "preparation": 180, "jev_approval": 60, "answer": 180, "grader": 120})
        self.assertEqual(v2["repair_budget"], {
            "max_repairs": 0, "wall_limit_ns": 600_000_000_000})
        changed = deepcopy(v2)
        changed["timeouts_seconds"]["grader"] = 60
        with patch("time_to_correct_calibration.read_json", return_value=changed):
            with self.assertRaisesRegex(MeasurementError, "calibration_freeze_invalid"):
                load_calibration(ROOT, "velgraphing-ttc-calibration-v2")
        copied_v1 = {"identity": {"run_id": v1["calibration_id"],
                                  "trial_id": "A-C-01", "arm": "A"}}
        with self.assertRaisesRegex(MeasurementError, "calibration_result_mismatch"):
            summarize_calibration(v2, [copied_v1], {})

    def test_v3_freeze_reuses_v2_inputs_and_pins_measurement_contract(self):
        v2 = load_calibration(ROOT, "velgraphing-ttc-calibration-v2")
        v3 = load_calibration(ROOT, "velgraphing-ttc-calibration-v3")
        self.assertEqual(v3["registered_trials"], v2["registered_trials"])
        self.assertEqual(v3["source_pilot"], v2["source_pilot"])
        self.assertEqual(v3["base_commit"], "031a8390ae3accce7fe4b3756f01f98f2c606ee6")
        self.assertEqual(v3["measurement_contract"], V3_MEASUREMENT_CONTRACT)
        self.assertEqual(v3["candidate_policy"], V3_CANDIDATE_POLICY)
        self.assertEqual(v3["measurement_contract"]["primary_provider_budget"],
                         {"calls": 12, "retries": 0})
        self.assertEqual(v3["measurement_contract"]["sensitivity_ablation"]["status"],
                         "future_companion_not_authorized")
        changed = deepcopy(v3)
        changed["measurement_contract"]["unknown_boundaries"]["shared_state_tokens"] = "estimated"
        with patch("time_to_correct_calibration.read_json", return_value=changed):
            with self.assertRaisesRegex(MeasurementError, "calibration_freeze_invalid"):
                load_calibration(ROOT, "velgraphing-ttc-calibration-v3")

    def test_v1_and_v2_require_separate_canonical_run_roots(self):
        v1 = load_calibration(ROOT)
        v2 = load_calibration(ROOT, "velgraphing-ttc-calibration-v2")
        v1_root = ROOT / ".velgraphing-local" / v1["calibration_id"]
        v2_root = ROOT / ".velgraphing-local" / v2["calibration_id"]
        self.assertEqual(calibration_run_root(ROOT, v1, str(v1_root)), v1_root)
        self.assertEqual(calibration_run_root(ROOT, v2, str(v2_root)), v2_root)
        with self.assertRaisesRegex(MeasurementError, "calibration_run_root_mismatch"):
            calibration_run_root(ROOT, v2, str(v1_root))

    def test_v1_completed_receipt_in_v2_root_refuses_before_dispatch(self):
        v1 = load_calibration(ROOT)
        packets, corpora, oracle = load_pilot(ROOT, v1)
        registration = v1["registered_trials"][0]
        packet = packets[registration["packet_id"]]
        corpus = corpora[packet["corpus"]["id"]]
        identity = trial_identity(
            v1, registration, packet, corpus, oracle[registration["task_id"]], "a" * 64)
        receipt = {
            "schema_version": "velgraphing-time-to-correct-v1",
            "identity": identity,
            "budget": v1["repair_budget"],
            "pass_recall_min": 0.9,
            "execution": "observed",
            "terminal_reason": "cancelled",
        }
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            run_root = Path(raw) / "velgraphing-ttc-calibration-v2"
            save_completed_trial(run_root / "completed", receipt)
            args = SimpleNamespace(
                repo_root=str(ROOT), calibration_id="velgraphing-ttc-calibration-v2",
                allow_live_jev=True, approved_max_live_jev_calls=12,
                run_root=str(run_root),
                lane_root=str(ROOT / "benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/fixture"),
            )
            with (patch("time_to_correct_calibration.controller_identity", return_value={}),
                  patch("time_to_correct_calibration.bind_controller", return_value={}),
                  patch("time_to_correct_calibration.calibration_run_root", return_value=run_root),
                  patch("time_to_correct_calibration.run_registered_trial") as dispatch,
                  patch("time_to_correct_calibration.evaluate_live") as provider):
                with self.assertRaisesRegex(MeasurementError, "calibration_result_mismatch"):
                    run_calibration(args)
        dispatch.assert_not_called()
        provider.assert_not_called()

    def test_native_requests_embed_exact_response_contracts(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            workers = [start_fixture_worker(root, "contracts", lane)
                       for lane in ("preparation", "answer", "grader")]
            trial = Trial(fixture_identity("contracts", "B", "a" * 64),
                          Budget(0, 3_000_000_000), execution="fixture")
            packet = {"schema_version": "velgraphing-jev-candidates-v1",
                      "query": "fixture query", "candidates": []}

            def prepare(current, _):
                request_candidates(current, ROOT, root,
                                   {"fixture_candidate_packet": packet}, 1,
                                   PREPARATION_RESPONSE_CONTRACT)
                return {"question": "contract fixture question", "evidence": []}

            with patch("time_to_correct_calibration.load_jev", return_value=SimpleNamespace(
                    validate_packet=lambda value: value)):
                result = run_process_trial(
                    trial, prepare,
                    answer_argv=[sys.executable, str(HANDOFF_PATH), "wait", "--run-root",
                                 str(root), "--trial-id", "contracts", "--attempt", "0",
                                 "--lane", "answer", "--wait-seconds", "1"],
                    grader_argv=[sys.executable, str(HANDOFF_PATH), "wait", "--run-root",
                                 str(root), "--trial-id", "contracts", "--attempt", "0",
                                 "--lane", "grader", "--wait-seconds", "1"],
                    cwd=ROOT, answer_timeout_s=1.5, grader_timeout_s=1.5,
                    answer_response_contract=ANSWER_RESPONSE_CONTRACT,
                    grader_response_contract=GRADER_RESPONSE_CONTRACT,
                )
            finish_workers(workers)
            preparation = read_canonical(
                root / "trials/contracts/attempt-0/preparation/request.json")[1]
            answer = read_canonical(root / "trials/contracts/attempt-0/answer/request.json")[1]
            grader = read_canonical(root / "trials/contracts/attempt-0/grader/request.json")[1]
        self.assertEqual(result["terminal_reason"], "passed")
        self.assertEqual(preparation["response_contract"]["encoding"], "canonical-json")
        self.assertEqual(answer["response_contract"], ANSWER_RESPONSE_CONTRACT)
        self.assertEqual(grader["response_contract"], GRADER_RESPONSE_CONTRACT)

    def test_handoff_argv_binds_optional_absolute_python(self):
        root = self.local_root / "transport-contract"
        executable = Path(sys.executable).resolve()
        self.assertEqual(handoff_argv(root, "trial", "answer", 1)[0], sys.executable)
        self.assertEqual(
            handoff_argv(root, "trial", "answer", 1, executable)[0], str(executable)
        )
        with self.assertRaisesRegex(MeasurementError, "python_executable_invalid"):
            handoff_argv(root, "trial", "answer", 1, Path("python3"))
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            inert = Path(raw) / "python"
            inert.write_text("not executable", encoding="utf-8")
            with self.assertRaisesRegex(MeasurementError, "python_executable_invalid"):
                handoff_argv(root, "trial", "answer", 1, inert)

    def test_fixture_worker_executes_with_fixed_credential_free_environment(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            executable = Path(sys.executable).resolve()
            with (
                patch.dict(os.environ, {"TYPESAFE_API_KEY": "must-not-cross-boundary"}),
                patch("time_to_correct_calibration.subprocess.Popen", wraps=subprocess.Popen) as launch,
            ):
                worker = start_fixture_worker(root, "safe-env", "answer", python_executable=executable)
                completed = subprocess.run(
                    handoff_argv(root, "safe-env", "answer", 1, executable),
                    cwd=ROOT, env={}, input=canonical({"identity": {"answer_model": "fixture-model"}}),
                    capture_output=True, check=False,
                )
                finish_workers([worker])
            child_env = launch.call_args_list[0].kwargs["env"]
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(child_env, {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"})
        self.assertNotIn("TYPESAFE_API_KEY", child_env)

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
            draft, manifest_sha256, response = capture_test_response(
                root, "publish", "answer", "thread-publish"
            )
            identity = [
                "--thread-id", "thread-publish", "--model", "gpt-5.6-luna",
                "--reasoning", "medium", "--lane-manifest-sha256", manifest_sha256,
            ]
            attested = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "attest", "--run-root", str(root),
                 "--trial-id", "publish", "--attempt", "0", "--lane", "answer",
                 "--draft-file", str(draft), *identity,
                 "--thread-status", "completed", "--draft-status", "stable-final"],
                cwd=ROOT, env={}, capture_output=True, check=False,
            )
            completed = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "respond", "--run-root", str(root),
                 "--trial-id", "publish", "--attempt", "0", "--lane", "answer",
                 "--response-file", str(draft), *identity],
                cwd=ROOT, env={}, capture_output=True, check=False,
            )
            published = (lane / "response.json").read_bytes()
            draft_value = read_canonical(draft)[1]
        self.assertEqual((attested.returncode, attested.stderr), (0, b""))
        self.assertEqual((completed.returncode, completed.stderr), (0, b""))
        self.assertEqual(published, response)
        self.assertEqual(draft_value["answer_text"], json.loads(response)["answer_text"])

    def test_host_response_capture_preserves_bytes_and_attestation_is_immutable(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            trial_id = "INLINE-CANARY"
            thread_id = "01a0c3b9-3309-7500-a3ad-6cc713dcf659"
            lane = root / f"trials/{trial_id}/attempt-0/answer"
            manifest_sha256 = write_lane_manifest(
                root, trial_id, "answer", thread_id
            )
            identity = {
                "trial_id": trial_id, "role": "answer",
                "thread_id": thread_id, "model": "gpt-5.6-luna",
                "reasoning": "medium",
            }
            write_lane_request(root, identity)
            response = T310_RAW_RESPONSE
            self.assertEqual(len(response), 786)
            self.assertEqual(
                digest(response),
                "591f2d3ee65167f5f260b26084014b5374a5b52259ef6c3733449d808057ffc6",
            )
            command = [
                sys.executable, str(HANDOFF_PATH), "capture",
                "--run-root", str(root), "--trial-id", trial_id,
                "--attempt", "0", "--lane", "answer",
                "--thread-id", thread_id, "--model", "gpt-5.6-luna",
                "--reasoning", "medium", "--lane-manifest-sha256", manifest_sha256,
                "--thread-status", "completed",
            ]
            captured = subprocess.run(
                command, cwd=ROOT, env={}, input=response,
                capture_output=True, check=False,
            )
            draft = lane / "draft.json"
            captured_value = json.loads(captured.stdout)
            canonical_response = canonical(json.loads(response))
            raw_artifact = lane / RAW_ASSISTANT_RESPONSE
            self.assertEqual(raw_artifact.read_bytes(), response)
            self.assertEqual(draft.read_bytes(), canonical_response)
            self.assertEqual(json.loads(draft.read_bytes()), json.loads(response))
            attested = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "attest",
                 "--run-root", str(root), "--trial-id", trial_id,
                 "--attempt", "0", "--lane", "answer", "--draft-file", str(draft),
                 "--thread-id", thread_id, "--model", "gpt-5.6-luna",
                 "--reasoning", "medium", "--lane-manifest-sha256", manifest_sha256,
                 "--thread-status", "completed", "--draft-status", "stable-final"],
                cwd=ROOT, env={}, capture_output=True, check=False,
            )
            changed = {**json.loads(response), "answer_text": "changed"}
            draft.write_bytes(canonical(changed))
            rejected = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "respond",
                 "--run-root", str(root), "--trial-id", trial_id,
                 "--attempt", "0", "--lane", "answer", "--response-file", str(draft),
                 "--thread-id", thread_id, "--model", "gpt-5.6-luna",
                 "--reasoning", "medium", "--lane-manifest-sha256", manifest_sha256],
                cwd=ROOT, env={}, capture_output=True, check=False,
            )
        self.assertEqual((captured.returncode, captured.stderr), (0, b""))
        self.assertEqual(captured_value["raw_sha256"], digest(response))
        self.assertEqual(captured_value["draft_sha256"], digest(canonical_response))
        self.assertEqual(
            captured_value["draft_sha256"],
            "1a455f9f43b064fe555edafb0da12f137865b35b5f7919ae57a2840204635866",
        )
        self.assertEqual((attested.returncode, attested.stderr), (0, b""))
        self.assertEqual(rejected.returncode, 3)
        self.assertIn(b"capture_receipt_invalid", rejected.stderr)

    def test_host_response_capture_rejects_invalid_content_boundaries(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            cases = (
                ("empty", b"", b"host_response_empty"),
                ("oversize", b"{" + b" " * MAX_BYTES, b"handoff_file_invalid"),
                ("invalid", b"{", b"invalid_json_object"),
                ("prose", b'{} trailing', b"invalid_json_object"),
                ("array", b"[]", b"invalid_json_object"),
                ("string", b'"{}"', b"invalid_json_object"),
            )
            for trial_id, response, reason in cases:
                lane = root / "trials" / trial_id / "attempt-0" / "answer"
                lane.mkdir(parents=True)
                manifest_sha256 = write_lane_manifest(
                    root, trial_id, "answer", f"thread-{trial_id}"
                )
                completed = subprocess.run(
                    [sys.executable, str(HANDOFF_PATH), "capture",
                     "--run-root", str(root), "--trial-id", trial_id,
                     "--attempt", "0", "--lane", "answer",
                     "--thread-id", f"thread-{trial_id}",
                     "--model", "gpt-5.6-luna", "--reasoning", "medium",
                     "--lane-manifest-sha256", manifest_sha256,
                     "--thread-status", "completed"],
                    cwd=ROOT, env={}, input=response,
                    capture_output=True, check=False,
                )
                self.assertEqual(completed.returncode, 3)
                self.assertIn(reason, completed.stderr)
                self.assertFalse((lane / "draft.json").exists())
                self.assertEqual(
                    (lane / RAW_ASSISTANT_RESPONSE).exists(),
                    trial_id not in {"empty", "oversize"},
                )

    def test_manually_created_draft_cannot_be_attested(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            lane = root / "trials/manual/attempt-0/answer"
            lane.mkdir(parents=True)
            draft = lane / "draft.json"
            draft.write_bytes(canonical({"answer": "manual"}))
            manifest_sha256 = write_lane_manifest(
                root, "manual", "answer", "thread-manual"
            )
            with self.assertRaisesRegex(HandoffError, "capture_receipt_invalid"):
                attest_draft(
                    root, "manual", 0, "answer", draft,
                    thread_id="thread-manual", model="gpt-5.6-luna",
                    reasoning="medium", lane_manifest_sha256=manifest_sha256,
                )

    def test_missing_or_invalid_capture_receipt_cannot_be_attested(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            for state in ("missing", "invalid"):
                with self.subTest(state=state):
                    trial_id = f"receipt-{state}"
                    thread_id = f"thread-{state}"
                    manifest_sha256 = write_lane_manifest(
                        root, trial_id, "answer", thread_id
                    )
                    lane = root / f"trials/{trial_id}/attempt-0/answer"
                    lane.mkdir(parents=True)
                    draft = lane / "draft.json"
                    draft.write_bytes(canonical({"answer": state}))
                    (lane / RAW_ASSISTANT_RESPONSE).write_bytes(draft.read_bytes())
                    if state == "invalid":
                        (lane / CAPTURE_RECEIPT).write_bytes(canonical({}))
                    with self.assertRaisesRegex(
                        HandoffError, "capture_receipt_invalid"
                    ):
                        attest_draft(
                            root, trial_id, 0, "answer", draft,
                            thread_id=thread_id, model="gpt-5.6-luna",
                            reasoning="medium",
                            lane_manifest_sha256=manifest_sha256,
                        )

    def test_host_response_capture_rejects_contract_identity_and_existing_artifacts(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            base = json.loads(T310_RAW_RESPONSE)
            for trial_id, change in (
                ("missing", lambda value: value.pop("usage")),
                ("extra", lambda value: value.update({"extra": True})),
                ("identity", lambda value: value["execution_identity"].update(
                    {"thread_id": "wrong-thread"}
                )),
            ):
                thread_id = f"thread-{trial_id}"
                identity = {
                    "trial_id": trial_id, "role": "answer", "thread_id": thread_id,
                    "model": "gpt-5.6-luna", "reasoning": "medium",
                }
                value = deepcopy(base)
                value["execution_identity"] = dict(identity)
                change(value)
                manifest_sha256 = write_lane_manifest(
                    root, trial_id, "answer", thread_id
                )
                write_lane_request(root, identity)
                lane = root / "trials" / trial_id / "attempt-0" / "answer"
                completed = subprocess.run(
                    [sys.executable, str(HANDOFF_PATH), "capture",
                     "--run-root", str(root), "--trial-id", trial_id,
                     "--attempt", "0", "--lane", "answer",
                     "--thread-id", thread_id, "--model", "gpt-5.6-luna",
                     "--reasoning", "medium",
                     "--lane-manifest-sha256", manifest_sha256,
                     "--thread-status", "completed"],
                    cwd=ROOT, env={}, input=json.dumps(value).encode(),
                    capture_output=True, check=False,
                )
                self.assertEqual(completed.returncode, 3)
                self.assertIn(b"host_response_contract_invalid", completed.stderr)
                self.assertTrue((lane / RAW_ASSISTANT_RESPONSE).is_file())
                self.assertFalse((lane / "draft.json").exists())

            for existing in (RAW_ASSISTANT_RESPONSE, "draft.json"):
                trial_id = f"existing-{existing.split('.')[0]}"
                thread_id = f"thread-{trial_id}"
                identity = {
                    "trial_id": trial_id, "role": "answer", "thread_id": thread_id,
                    "model": "gpt-5.6-luna", "reasoning": "medium",
                }
                manifest_sha256 = write_lane_manifest(
                    root, trial_id, "answer", thread_id
                )
                write_lane_request(root, identity)
                lane = root / "trials" / trial_id / "attempt-0" / "answer"
                (lane / existing).write_bytes(b"existing")
                value = deepcopy(base)
                value["execution_identity"] = identity
                completed = subprocess.run(
                    [sys.executable, str(HANDOFF_PATH), "capture",
                     "--run-root", str(root), "--trial-id", trial_id,
                     "--attempt", "0", "--lane", "answer",
                     "--thread-id", thread_id, "--model", "gpt-5.6-luna",
                     "--reasoning", "medium",
                     "--lane-manifest-sha256", manifest_sha256,
                     "--thread-status", "completed"],
                    cwd=ROOT, env={}, input=canonical(value),
                    capture_output=True, check=False,
                )
                self.assertEqual(completed.returncode, 3)
                self.assertIn(b"handoff_file_exists", completed.stderr)

    def test_response_normalization_canonicalizes_nested_keys_from_stdin_and_draft(self):
        raw = (
            b'{"schema_version":"fixture-response-v1","execution_identity":'
            b'{"thread_id":"thread-1","trial_id":"A-S-01","role":"grader",'
            b'"reasoning":"medium","model":"gpt-5.6-luna"}}'
        )
        expected = canonical(json.loads(raw))
        with tempfile.TemporaryDirectory(dir=self.local_root) as temporary:
            root = Path(temporary) / "run"
            for source in ("stdin", "draft"):
                trial_id = f"normalize-{source}"
                lane = root / "trials" / trial_id / "attempt-0" / "grader"
                lane.mkdir(parents=True)
                command = [
                    sys.executable, str(HANDOFF_PATH), "respond",
                    "--run-root", str(root), "--trial-id", trial_id,
                    "--attempt", "0", "--lane", "grader", "--normalize-json",
                ]
                input_raw = raw
                if source == "draft":
                    draft, manifest_sha256, expected = capture_test_response(
                        root, trial_id, "grader", "thread-1"
                    )
                    attest_draft(
                        root, trial_id, 0, "grader", draft,
                        thread_id="thread-1", model="gpt-5.6-luna", reasoning="medium",
                        lane_manifest_sha256=manifest_sha256,
                    )
                    command.extend([
                        "--response-file", str(draft), "--thread-id", "thread-1",
                        "--model", "gpt-5.6-luna", "--reasoning", "medium",
                        "--lane-manifest-sha256", manifest_sha256,
                    ])
                    input_raw = None
                completed = subprocess.run(
                    command, cwd=ROOT, env={}, input=input_raw,
                    capture_output=True, check=False,
                )
                self.assertEqual((completed.returncode, completed.stderr), (0, b""))
                self.assertEqual((lane / "response.json").read_bytes(), expected)

    def test_draft_observed_before_completion_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            lane = root / "trials/pending/attempt-0/answer"
            lane.mkdir(parents=True)
            draft = lane / "draft.json"
            draft.write_bytes(canonical({"answer": "partial"}))
            with self.assertRaisesRegex(HandoffError, "completion_attestation_invalid"):
                read_attested_draft(
                    root, "pending", 0, "answer", draft,
                    thread_id="thread-pending", model="gpt-5.6-luna", reasoning="medium",
                    lane_manifest_sha256="a" * 64,
                )

    def test_completed_mutated_draft_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            draft, manifest_sha256, _ = capture_test_response(
                root, "mutated", "answer", "thread-mutated"
            )
            attest_draft(
                root, "mutated", 0, "answer", draft,
                thread_id="thread-mutated", model="gpt-5.6-luna", reasoning="medium",
                lane_manifest_sha256=manifest_sha256,
            )
            draft.write_bytes(canonical({"answer": "changed"}))
            with self.assertRaisesRegex(
                HandoffError, "capture_receipt_invalid"
            ):
                read_attested_draft(
                    root, "mutated", 0, "answer", draft,
                    thread_id="thread-mutated", model="gpt-5.6-luna", reasoning="medium",
                    lane_manifest_sha256=manifest_sha256,
                )

    def test_completed_stable_matching_draft_succeeds(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            draft, manifest_sha256, expected = capture_test_response(
                root, "stable", "grader", "thread-stable"
            )
            attest_draft(
                root, "stable", 0, "grader", draft,
                thread_id="thread-stable", model="gpt-5.6-luna", reasoning="medium",
                lane_manifest_sha256=manifest_sha256,
            )
            self.assertEqual(
                read_attested_draft(
                    root, "stable", 0, "grader", draft,
                    thread_id="thread-stable", model="gpt-5.6-luna", reasoning="medium",
                    lane_manifest_sha256=manifest_sha256,
                ),
                expected,
            )

    def test_completion_attestation_rejects_wrong_lane_or_thread_identity(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            root = Path(raw) / "run"
            lane = root / "trials/identity/attempt-0/answer"
            draft, manifest_sha256, _ = capture_test_response(
                root, "identity", "answer", "thread-correct"
            )
            rejected = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "attest", "--run-root", str(root),
                 "--trial-id", "identity", "--attempt", "0", "--lane", "answer",
                 "--draft-file", str(draft), "--thread-id", "thread-wrong",
                 "--model", "gpt-5.6-luna", "--reasoning", "medium",
                 "--lane-manifest-sha256", manifest_sha256,
                 "--thread-status", "completed", "--draft-status", "stable-final"],
                cwd=ROOT, env={}, capture_output=True, check=False,
            )
            self.assertEqual(rejected.returncode, 3)
            self.assertIn(b"lane_manifest_identity_invalid", rejected.stderr)
            attest_draft(
                root, "identity", 0, "answer", draft,
                thread_id="thread-correct", model="gpt-5.6-luna", reasoning="medium",
                lane_manifest_sha256=manifest_sha256,
            )
            with self.assertRaisesRegex(HandoffError, "completion_attestation_invalid"):
                read_attested_draft(
                    root, "identity", 0, "answer", draft,
                    thread_id="thread-wrong", model="gpt-5.6-luna", reasoning="medium",
                    lane_manifest_sha256=manifest_sha256,
                )
            wrong_lane = root / "trials/identity/attempt-0/grader"
            wrong_lane.mkdir()
            wrong_draft = wrong_lane / "draft.json"
            wrong_draft.write_bytes(draft.read_bytes())
            (wrong_lane / COMPLETION_ATTESTATION).write_bytes(
                (lane / COMPLETION_ATTESTATION).read_bytes()
            )
            with self.assertRaisesRegex(HandoffError, "completion_attestation_invalid"):
                read_attested_draft(
                    root, "identity", 0, "grader", wrong_draft,
                    thread_id="thread-correct", model="gpt-5.6-luna", reasoning="medium",
                    lane_manifest_sha256=manifest_sha256,
                )

    def test_response_cli_strict_default_rejects_noncanonical_nested_keys(self):
        raw = b'{"z":0,"execution_identity":{"thread_id":"t","model":"m"}}'
        with tempfile.TemporaryDirectory(dir=self.local_root) as temporary:
            root = Path(temporary) / "run"
            lane = root / "trials/strict/attempt-0/grader"
            lane.mkdir(parents=True)
            completed = subprocess.run(
                [sys.executable, str(HANDOFF_PATH), "respond", "--run-root", str(root),
                 "--trial-id", "strict", "--attempt", "0", "--lane", "grader"],
                cwd=ROOT, env={}, input=raw, capture_output=True, check=False,
            )
            published = (lane / "response.json").exists()
        self.assertEqual(completed.returncode, 3)
        self.assertIn(b"invalid_canonical_json", completed.stderr)
        self.assertFalse(published)

    def test_response_normalization_rejects_unsafe_json(self):
        for raw in (b"[]", b"{", b'{"value":NaN}', b'{"value":1e400}', b"{" + b" " * MAX_BYTES):
            with self.subTest(raw=raw[:24]):
                with self.assertRaises(HandoffError):
                    normalize_json_object(raw)

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

    def test_v3_aggregation_retains_arm_metrics_contrasts_and_unknowns(self):
        config = load_calibration(ROOT, "velgraphing-ttc-calibration-v3")
        results = []
        arm_value = {"A": 1, "B": 2, "C": 3, "D": 4}
        for registration in config["registered_trials"]:
            arm = registration["arm"]
            jev_on = arm in {"B", "D"}
            failed = registration["trial_id"] == "B-C-01"
            phase = lambda status, duration: {
                "status": status, "inclusive_union_ns": duration,
            }
            model_calls = [{
                "call_id": f"answer-{registration['trial_id']}", "kind": "answer",
                "model": config["answer_model"], "provenance": "provider_reported",
                "input_tokens": 100 + arm_value[arm], "output_tokens": 10,
            }, {
                "call_id": f"grader-{registration['trial_id']}", "kind": "grader",
                "model": "grader", "provenance": "provider_reported",
                "input_tokens": 50, "output_tokens": 5,
            }]
            jev_observation = None
            if jev_on:
                model_calls.append({
                    "call_id": f"jev-{registration['trial_id']}", "kind": "jev",
                    "model": "jev-1.13.0", "provenance": "provider_reported",
                    "input_tokens": 30, "output_tokens": 2,
                })
                jev_observation = {
                    "request_bytes": 900, "shared_state_bytes": 500,
                    "questions_bytes": 300, "candidate_count": 3,
                    "question_count": 3, "rubric_version": "evidence-usefulness-v1",
                    "shared_state_tokens": None, "question_suffix_tokens": None,
                    "source_bytes_verified": 700, "elapsed_ms": 4.5,
                    "attempted_calls": 1,
                    "scores": [{"id": "c0", "score": 2.0,
                                "probabilities": {"0": 0.0, "1": 0.1, "2": 0.9},
                                "distribution_confidence": 0.9}],
                }
            attempt = {
                "coverage": {"model_calls": True, "source_operations": True,
                             "context_deliveries": True},
                "phase_status": {"answer_generation": "observed"},
                "answer_boundary": {"model_calls_complete": True,
                                    "context_deliveries_complete": True},
                "context_deliveries": [{"kind": "answer_request",
                                        "bytes": 1000 + arm_value[arm], "sha256": "a" * 64}],
                "source_operations": [{"operation_id": "read-1", "source_sha256": "b" * 64,
                                       "byte_start": 5, "byte_end": 25, "access": "file_read"}],
                "model_calls": model_calls,
                "terminal_reason": "repair_budget_exhausted" if failed else "passed",
            }
            if jev_observation is not None:
                attempt["jev_observation"] = jev_observation
            graph_on = arm in {"C", "D"}
            attempt["candidate_observation"] = {
                "route": "graph_find_tag_index" if graph_on else "direct_flat",
                "candidate_packet_sha256": digest(
                    f"{registration['task_id']}:{'graph' if graph_on else 'direct'}".encode()),
                "baseline_order_sha256": digest(
                    f"{registration['task_id']}:{'graph' if graph_on else 'direct'}:order".encode()),
                "record_count": 10 if graph_on else None,
                "edge_count": 0 if graph_on else None,
                "edge_expansion_status": "not_available" if graph_on else "not_applicable",
            }
            result = {
                "identity": {
                    "run_id": config["calibration_id"], "trial_id": registration["trial_id"],
                    "arm": arm, "answer_model": config["answer_model"],
                    "reasoning": config["reasoning"], "rubric_version": "task-rubric-v1",
                    "rubric_sha256": digest(registration["task_id"].encode("utf-8")),
                },
                "budget": config["repair_budget"], "pass_recall_min": 0.9,
                "execution": "observed",
                "terminal_reason": "repair_budget_exhausted" if failed else "passed",
                "first_pass_correct": not failed,
                "user_visible_wall_ns": 1000 + arm_value[arm],
                "confirmed_time_to_correct_ns": None if failed else 900 + arm_value[arm],
                "all_attempt_cost_usd": None,
                "observed_active_execution_ns": 700,
                "observed_wait_union_ns": 100 if jev_on else 0,
                "unattributed_ns": 200,
                "attempts": [attempt],
                "phases": {
                    "source_capture": phase("observed", 10),
                    "candidate_discovery": phase("observed", 11),
                    "context_composition": phase("observed", 12),
                    "answer_generation": phase("observed", 13),
                    "grading": phase("observed", 14),
                    "cold_graph_build": phase("observed", 30) if graph_on else phase("not_applicable", 0),
                    "warm_graph_load": phase("not_applicable", 0),
                    "retrieval": phase("observed", 20) if graph_on else phase("missing", None),
                    "fallback": phase("missing", None),
                    "provider": phase("observed", 40) if jev_on else phase("not_applicable", 0),
                    "operator_approval": phase("observed", 5) if jev_on else phase("not_applicable", 0),
                },
            }
            results.append(result)
        output = summarize_calibration(config, results, {})
        self.assertEqual(output["schema_version"], "velgraphing-ttc-calibration-result-v3")
        self.assertEqual(set(output["paired_contrasts"]), {"B-A", "D-C", "C-A", "D-B"})
        self.assertEqual(output["measurement_summaries"]["D"]["metrics"]["jev_request_bytes"],
                         {"observed_trials": 6, "missing_trials": 0, "mean": 900.0})
        self.assertEqual(output["measurement_summaries"]["D"]["metrics"]["grader_input_tokens"]["mean"], 50.0)
        self.assertEqual(len(output["measurement_summaries"]["D"]["jev_score_observations"]), 6)
        b_failure = output["measurement_summaries"]["B"]["confidence_linked_task_failures"]
        self.assertEqual(b_failure[0]["trial_id"], "B-C-01")
        self.assertEqual(b_failure[0]["interpretation"], "descriptive_not_candidate_calibration")
        direct = output["measurement_summaries"]["A"]["trials"][0]
        self.assertIsNone(direct["shared_state_tokens"])
        self.assertIsNone(direct["question_suffix_tokens"])
        self.assertEqual(direct["warm_graph_load"]["status"], "not_applicable")
        graph = output["measurement_summaries"]["C"]["trials"][0]
        self.assertEqual((graph["discovery_route"], graph["graph_edge_count"],
                          graph["edge_expansion_status"]),
                         ("graph_find_tag_index", 0, "not_available"))
        self.assertEqual(output["candidate_calibration"], {
            "status": "unscored", "reason": "no_candidate_level_oracle_exists",
            "confidence_linked_failures_are": "descriptive_only",
        })
        self.assertEqual(output["paired_contrasts"]["B-A"]["metrics"]["user_visible_wall_ns"], {
            "paired_tasks": 6, "missing_pairs": 0, "mean_delta_left_minus_right": 1.0})
        self.assertEqual(output["paired_contrasts"]["B-A"]["metrics"]["operator_approval_ns"], {
            "paired_tasks": 6, "missing_pairs": 0, "mean_delta_left_minus_right": 5.0})

    def test_v1_v2_summary_shape_is_unchanged_by_v3_aggregation(self):
        for calibration_id in ("velgraphing-ttc-calibration-v1",
                               "velgraphing-ttc-calibration-v2"):
            config = load_calibration(ROOT, calibration_id)
            output = summarize_calibration(config, [], {})
            self.assertEqual(output["schema_version"], "velgraphing-ttc-calibration-result-v1")
            self.assertNotIn("measurement_summaries", output)
            self.assertNotIn("paired_contrasts", output)

    def test_v3_missing_trials_remain_missing_and_numeric_values_stay_null(self):
        config = load_calibration(ROOT, "velgraphing-ttc-calibration-v3")
        output = summarize_calibration(config, [], {})
        row = output["measurement_summaries"]["A"]["trials"][0]
        self.assertEqual(row["terminal_reason"], "missing")
        self.assertIsNone(row["user_visible_wall_ns"])
        self.assertIsNone(row["source_operation_count"])
        self.assertIsNone(row["provider_calls"])
        self.assertEqual(row["warm_graph_load"], {"status": "missing", "duration_ns": None})
        self.assertEqual(output["paired_contrasts"]["B-A"]["metrics"]["provider_calls"], {
            "paired_tasks": 0, "missing_pairs": 6, "mean_delta_left_minus_right": None})

    def test_offline_qualification_exercises_required_lifecycle(self):
        result = qualify(ROOT)
        self.assertEqual(result["provider_calls_made"], 0)
        self.assertEqual(result["direct_off"]["terminal_reason"], "passed")
        self.assertEqual(result["graph_on_replay"], {
            "terminal_reason": "passed", "graph_records": 2, "jev_execution": "replay"})
        self.assertEqual(result["missing_response"], {
            "terminal_reason": "measurement_error", "handoff_status": "response_timeout"})
        self.assertEqual(result["live_refusal"], "live_jev_not_approved")

    def test_v3_qualification_proves_fixed_pairs_without_provider_calls(self):
        result = qualify(ROOT, "velgraphing-ttc-calibration-v3")
        self.assertEqual(result["provider_calls_made"], 0)
        self.assertEqual(result["direct_off"]["terminal_reason"], "passed")
        self.assertEqual(result["graph_on_replay"]["terminal_reason"], "passed")
        self.assertTrue(result["pair_proof"]["direct"]["a_b_match"])
        self.assertTrue(result["pair_proof"]["graph"]["c_d_match"])
        self.assertEqual(result["pair_proof"]["answer_evidence_budget_bytes"], 16384)

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

    def test_restricted_index_passes_and_lane_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.local_root) as raw:
            repo = Path(raw) / "controller"
            corpus_root = Path(raw) / "corpus"
            corpus_root.mkdir()
            source = corpus_root / "source.py"
            omitted = corpus_root / "omitted.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            omitted.write_text("OMITTED = True\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(corpus_root)], check=True)
            subprocess.run(["git", "-C", str(corpus_root), "add", "source.py", "omitted.py"],
                           check=True)
            subprocess.run(["git", "-C", str(corpus_root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                            "fixture"], check=True)
            commit = subprocess.run(["git", "-C", str(corpus_root), "rev-parse", "HEAD"],
                                    capture_output=True, check=True, text=True).stdout.strip()
            subprocess.run(["git", "-C", str(corpus_root), "read-tree", "--empty"], check=True)
            subprocess.run(["git", "-C", str(corpus_root), "add", "source.py"], check=True)
            omitted.unlink()
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
            self.assertEqual(before["index_entry_count"], 1)
            status = subprocess.run(
                ["git", "-C", str(corpus_root), "status", "--porcelain=v1", "-z"],
                capture_output=True, check=True).stdout
            self.assertTrue(status)  # Intentional full-tree omission is not lane dirtiness.
            source.write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(MeasurementError, "corpus_changed_during_trial"):
                revalidate_lane(repo, corpus, corpus_root, before)
            source.write_bytes(raw_source)
            source.chmod(0o755)
            subprocess.run(["git", "-C", str(corpus_root), "update-index", "--chmod=+x",
                            "source.py"], check=True)
            with self.assertRaisesRegex(MeasurementError, "corpus_changed_during_trial"):
                revalidate_lane(repo, corpus, corpus_root, before)
            source.chmod(0o644)
            subprocess.run(["git", "-C", str(corpus_root), "update-index", "--chmod=-x",
                            "source.py"], check=True)
            extra = corpus_root / "extra.py"
            extra.write_text("EXTRA = True\n", encoding="utf-8")
            with self.assertRaisesRegex(MeasurementError, "corpus_changed_during_trial"):
                revalidate_lane(repo, corpus, corpus_root, before)
            extra.unlink()
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
