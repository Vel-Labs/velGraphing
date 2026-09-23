"""Real subprocess boundary tests. No shell, provider, credential, or Codex CLI."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))
from time_to_correct import Budget, MeasurementError, Trial, digest
from time_to_correct_host import (
    ANSWER_RESPONSE_CONTRACT,
    GRADER_RESPONSE_CONTRACT,
    SUCCESSOR_GRADER_RESPONSE_CONTRACT,
    TASK_FACET_CHECKLIST_PREFIX,
    V3_COMPLETENESS_INSTRUCTION,
    _answer_input,
    _grader_input,
    run_process_trial,
)


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
if set(payload) != {"schema_version", "question", "instructions", "evidence"}:
    raise SystemExit(9)
if payload["schema_version"] != "velgraphing-answer-model-input-v1":
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
if set(payload) != {"schema_version", "answer_text", "rubric"}:
    raise SystemExit(9)
if payload["schema_version"] != "velgraphing-grader-model-input-v1":
    raise SystemExit(9)
if "response_contract" in payload:
    raise SystemExit(8)
result = {
    "critical_facts_exact": True,
    "grader_id": "independent-grader",
    "model_calls_complete": True,
    "required_fact_maximum": 10,
    "required_fact_score": 9,
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


def identified_code(role, identity=None, grader_id=None):
    result = ({
        "answer_text": "strict answer",
        "context_deliveries_complete": True,
        "model_calls_complete": True,
        "schema_version": "velgraphing-answer-output-v1",
        "usage": None,
    } if role == "answer" else {
        "critical_facts_exact": True,
        "grader_id": grader_id or (
            f"grader-{identity['trial_id']}" if identity else "strict-grader"
        ),
        "model_calls_complete": True,
        "required_fact_maximum": 1,
        "required_fact_score": 1,
        "schema_version": "velgraphing-grader-output-v1",
        "unsupported_material_claims": 0,
        "usage": None,
    })
    if identity is not None:
        result["execution_identity"] = identity
    return (
        "import json,sys\n"
        "payload=json.load(sys.stdin)\n"
        "contract=payload.get('response_contract',{})\n"
        "assert 'execution_identity' in contract.get('json_schema',{}).get('required',[])\n"
        f"result={result!r}\n"
        "sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'),"
        "ensure_ascii=True,allow_nan=False))\n"
    )


def successor_grader_code(decisions, score, maximum=2):
    result = {
        "critical_facts_exact": True,
        "grader_id": "successor-grader",
        "model_calls_complete": True,
        "required_fact_decisions": decisions,
        "required_fact_maximum": maximum,
        "required_fact_score": score,
        "schema_version": "velgraphing-grader-output-v2",
        "unsupported_material_claims": 0,
        "usage": None,
    }
    return (
        "import json,sys\n"
        "payload=json.load(sys.stdin)\n"
        "assert payload['schema_version']=='velgraphing-grader-model-input-v2'\n"
        "assert payload['evidence_sources']=={'c1':'source.py'}\n"
        "properties=payload['response_contract']['json_schema']['properties']\n"
        "assert properties['required_fact_decisions']['minItems']==2\n"
        "assert properties['required_fact_decisions']['maxItems']==2\n"
        f"result={result!r}\n"
        "sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'),"
        "ensure_ascii=True,allow_nan=False))\n"
    )


class HostBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)

    def test_v3_answer_boundary_adds_only_public_completeness_instruction(self):
        evidence = [{"id": "candidate", "path": "source.py", "excerpt": "public evidence"}]
        v2 = _answer_input({"schema_version": "other", "question": "public question", "evidence": evidence})
        v3 = _answer_input({
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "public question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": evidence,
        })

        self.assertNotIn(V3_COMPLETENESS_INSTRUCTION, v2["instructions"])
        self.assertIn(V3_COMPLETENESS_INSTRUCTION, v3["instructions"])
        self.assertEqual(set(v3), {"schema_version", "question", "instructions", "evidence"})
        self.assertNotIn("rubric", json.dumps(v3, sort_keys=True))

    def test_public_task_facets_render_as_deterministic_numbered_checklist(self):
        payload = _answer_input({
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "public question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "task_facets": ("implementation", "ordering consequence"),
            "evidence": [],
        })

        self.assertEqual(payload["instructions"][1], (
            f"{TASK_FACET_CHECKLIST_PREFIX}\n"
            "1. implementation\n"
            "2. ordering consequence"
        ))
        self.assertNotIn("task_facets", payload)
        self.assertNotIn("rubric", json.dumps(payload, sort_keys=True))

    def test_absent_or_empty_task_facets_preserve_v3_behavior(self):
        base = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "public question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": [],
        }

        self.assertEqual(_answer_input(base), _answer_input({**base, "task_facets": []}))

    def test_invalid_task_facets_fail_closed(self):
        base = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "public question",
            "evidence": [],
        }
        invalid = ("facet", {"facet"}, [""], [" leading"], ["a", "a"], ["a\nb"], [1])
        for facets in invalid:
            with self.subTest(facets=facets), self.assertRaisesRegex(
                MeasurementError, "invalid_task_facets",
            ):
                _answer_input({**base, "task_facets": facets})

    def run_host(self, answer_code=ANSWER_CODE, *, grader_code=GRADER_CODE,
                 answer_timeout_s=2, wall_limit_ns=5_000_000_000,
                 prepared=None, grader_context=None, grader_model=None,
                 answer_execution_identity=None, grader_execution_identity=None,
                 strict_contracts=False, successor_grader=False,
                 require_answer_evidence_citation=True):
        trial = Trial(identity(), Budget(0, wall_limit_ns), execution="fixture")
        return run_process_trial(
            trial,
            lambda *_: prepared or {"question": "frozen question", "evidence": []},
            answer_argv=[sys.executable, "-c", answer_code],
            grader_argv=[sys.executable, "-c", grader_code],
            cwd=self.cwd,
            answer_timeout_s=answer_timeout_s,
            grader_timeout_s=2,
            grader_context=grader_context,
            grader_model=grader_model,
            answer_response_contract=(ANSWER_RESPONSE_CONTRACT if strict_contracts else None),
            grader_response_contract=(
                SUCCESSOR_GRADER_RESPONSE_CONTRACT if successor_grader
                else GRADER_RESPONSE_CONTRACT if strict_contracts else None
            ),
            answer_execution_identity=answer_execution_identity,
            grader_execution_identity=grader_execution_identity,
            require_answer_evidence_citation=require_answer_evidence_citation,
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

    def test_actual_d01_subprocess_inputs_are_allowlisted(self):
        evidence_id = "d" * 64
        answer_code = ANSWER_CODE.replace(
            'if "response_contract" in payload:',
            '''
if payload["question"] != "Which implementation is imported immediately after merge_sort, and how does it choose and place its pivot?": raise SystemExit(7)
if payload["instructions"] != ["Cite supporting evidence IDs as [cN].", "Answer every explicit part of the question. State each requested rule, behavior, comparison, distinction, and consequence directly; do not rely on examples or implications. Cite the supporting evidence for each statement."]: raise SystemExit(7)
if payload["evidence"] != [{"id":"c1","path":"sorts/quick_sort.py","excerpt":"pivot = collection.pop(randint(0, len(collection) - 1))","source_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","byte_start":253,"byte_end":1299,"relationship_parent_candidate_id":"parent"}]: raise SystemExit(7)
if "response_contract" in payload:''').replace(
                "observed subprocess answer", "observed subprocess answer [c1]"
            )
        grader_code = GRADER_CODE.replace(
            'if "response_contract" in payload:',
            '''
if payload["answer_text"] != "observed subprocess answer [c1]": raise SystemExit(7)
if payload["rubric"] != {"required_facts":["Names the imported implementation."],"critical_facts":["Explains pivot selection and placement."],"acceptable_spans":["sorts/quick_sort.py"]}: raise SystemExit(7)
if "response_contract" in payload:''').replace(
            '"required_fact_maximum": 10,', '"required_fact_maximum": 1,'
        ).replace('"required_fact_score": 9,', '"required_fact_score": 1,')
        prohibited = {
            "run_id": "run", "trial_id": "trial", "arm": "D", "route": "typed_graph",
            "jev_status": "reranked", "treatment": "on", "request_sha256": "a" * 64,
            "response_sha256": "b" * 64, "score": 0.9, "probability": 0.8,
            "confidence": 0.7,
            "call_ledger": {"calls": 1}, "provider": "typesafe",
            "controller_receipt": {"status": "kept outside"},
        }
        prepared = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "Which implementation is imported immediately after merge_sort, and how does it choose and place its pivot?",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": [{
                "id": evidence_id, "path": "sorts/quick_sort.py",
                "excerpt": "pivot = collection.pop(randint(0, len(collection) - 1))",
                "source_sha256": "c" * 64, "byte_start": 253, "byte_end": 1299,
                "relationship_parent_candidate_id": "parent",
                **prohibited,
            }],
            **prohibited,
        }
        grader_context = {
            "required_facts": ["Names the imported implementation."],
            "critical_facts": ["Explains pivot selection and placement."],
            "acceptable_spans": ["sorts/quick_sort.py"],
            **prohibited,
        }
        result = self.run_host(
            answer_code,
            grader_code=grader_code,
            prepared=prepared,
            grader_context=grader_context,
        )
        self.assertEqual(result["terminal_reason"], "passed")

    def test_successor_grader_receives_evidence_mapping_and_fact_decisions(self):
        prepared = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "frozen question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": [{"id": "a" * 64, "path": "source.py", "excerpt": "evidence"}],
        }
        answer_code = ANSWER_CODE.replace(
            "observed subprocess answer", "observed subprocess answer [c1]",
        )
        result = self.run_host(
            answer_code,
            grader_code=successor_grader_code([True, True], 2),
            prepared=prepared,
            grader_context={
                "required_facts": ["one", "two"],
                "critical_facts": [],
                "acceptable_spans": ["source.py"],
            },
            successor_grader=True,
        )
        self.assertEqual(result["terminal_reason"], "passed")
        self.assertEqual(
            result["attempts"][0]["grader_boundary"]["required_fact_decisions"],
            [True, True],
        )

    def test_successor_grader_mapping_and_fact_counts_fail_closed(self):
        for mapping in ({"bad": "source.py"}, {"c0": ""}, {"c0": 1}):
            with self.subTest(mapping=mapping), self.assertRaisesRegex(
                MeasurementError, "invalid_grader_evidence_sources",
            ):
                _grader_input("answer", {}, mapping)

        prepared = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "frozen question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": [{"id": "a" * 64, "path": "source.py", "excerpt": "evidence"}],
        }
        answer_code = ANSWER_CODE.replace(
            "observed subprocess answer", "observed subprocess answer [c1]",
        )
        for label, decisions, score in (
            ("count", [True], 1),
            ("satisfied", [True, False], 2),
        ):
            with self.subTest(label=label):
                result = self.run_host(
                    answer_code,
                    grader_code=successor_grader_code(decisions, score),
                    prepared=prepared,
                    grader_context={
                        "required_facts": ["one", "two"],
                        "critical_facts": [],
                        "acceptable_spans": ["source.py"],
                    },
                    successor_grader=True,
                )
                self.assertEqual(result["terminal_reason"], "measurement_error")
                self.assertEqual(
                    result["attempts"][0]["failure_reason"],
                    "grader_required_fact_decisions_mismatch",
                )

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

    def test_pinned_grader_model_rejects_substitution(self):
        result = self.run_host(grader_model="different-grader")
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(result["attempts"][0]["failure_reason"], "grader_model_mismatch")

    def test_strict_identity_accepts_null_usage_without_inventing_telemetry(self):
        answer_identity = {
            "model": "fixture-model", "reasoning": "none", "role": "answer",
            "trial_id": "trial1", "thread_id": "answer-thread",
        }
        grader_identity = {
            "model": "fixture-grader", "reasoning": "none", "role": "grader",
            "trial_id": "trial1", "thread_id": "grader-thread",
        }
        result = self.run_host(
            identified_code("answer", answer_identity).replace(
                "result=",
                "assert contract['json_schema']['properties']['usage']['const'] is None\n"
                "result=",
                1,
            ),
            grader_code=identified_code("grader", grader_identity),
            grader_model="fixture-grader",
            answer_execution_identity=answer_identity,
            grader_execution_identity=grader_identity,
            strict_contracts=True,
        )
        self.assertEqual(result["terminal_reason"], "passed")
        self.assertIsNone(result["total_input_tokens"])
        self.assertIsNone(result["total_output_tokens"])
        self.assertIsNone(result["all_attempt_cost_usd"])
        self.assertTrue(all(
            row["provenance"] == "unavailable"
            for row in result["attempts"][0]["model_calls"]
        ))
        self.assertEqual(
            result["attempts"][0]["answer_boundary"]["execution_identity"],
            answer_identity,
        )
        self.assertEqual(
            result["attempts"][0]["grader_boundary"]["execution_identity"],
            grader_identity,
        )

    def test_transient_answer_retry_uses_fresh_bound_lane(self):
        def lane(role, attempt):
            return {
                "model": "fixture-model" if role == "answer" else "fixture-grader",
                "reasoning": "none", "role": role, "trial_id": "trial1",
                "thread_id": f"{role}-thread-{attempt}",
            }
        answer_lanes = [
            {"argv": [sys.executable, "-c", (
                'import sys; sys.stdout.write("{}")' if attempt == 0
                else identified_code("answer", lane("answer", attempt))
            )], "identity": lane("answer", attempt)} for attempt in range(3)
        ]
        grader_lanes = [
            {"argv": [sys.executable, "-c", identified_code("grader", lane("grader", attempt))],
             "identity": lane("grader", attempt)} for attempt in range(3)
        ]
        trial = Trial(identity(), Budget(2, 10_000_000_000),
                      execution="fixture", retry_transient=True)
        result = run_process_trial(
            trial, lambda *_: {"question": "frozen question", "evidence": []},
            answer_argv=answer_lanes[0]["argv"], grader_argv=grader_lanes[0]["argv"],
            cwd=self.cwd, answer_timeout_s=2, grader_timeout_s=2,
            answer_response_contract=ANSWER_RESPONSE_CONTRACT,
            grader_response_contract=GRADER_RESPONSE_CONTRACT,
            answer_execution_identity=answer_lanes[0]["identity"],
            grader_execution_identity=grader_lanes[0]["identity"],
            answer_retry_lanes=answer_lanes, grader_retry_lanes=grader_lanes,
        )
        self.assertEqual("passed", result["terminal_reason"])
        self.assertEqual(2, len(result["attempts"]))
        self.assertEqual("invalid_answer_output", result["attempts"][0]["failure_reason"])
        self.assertEqual(lane("answer", 1), result["attempts"][1]["answer_boundary"]["execution_identity"])
        self.assertEqual(lane("grader", 1), result["attempts"][1]["grader_boundary"]["execution_identity"])

    def test_grader_maximum_must_match_frozen_required_facts(self):
        answer_identity = {
            "model": "fixture-model", "reasoning": "none", "role": "answer",
            "trial_id": "trial1", "thread_id": "answer-thread",
        }
        grader_identity = {
            "model": "fixture-grader", "reasoning": "none", "role": "grader",
            "trial_id": "trial1", "thread_id": "grader-thread",
        }
        grader_code = identified_code("grader", grader_identity).replace(
            "result=",
            "properties=contract['json_schema']['properties']\n"
            "assert properties['required_fact_score']['type'] == 'integer'\n"
            "assert properties['required_fact_score']['maximum'] == 2\n"
            "assert properties['required_fact_maximum']['const'] == 2\n"
            "result=",
            1,
        )
        result = self.run_host(
            identified_code("answer", answer_identity),
            grader_code=grader_code,
            grader_context={
                "required_facts": ["one", "two"],
                "critical_facts": [],
                "acceptable_spans": [],
            },
            grader_model="fixture-grader",
            answer_execution_identity=answer_identity,
            grader_execution_identity=grader_identity,
            strict_contracts=True,
        )
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(
            result["attempts"][0]["failure_reason"],
            "grader_required_fact_maximum_mismatch",
        )

    def test_grader_id_must_match_generated_const(self):
        answer_identity = {
            "model": "fixture-model", "reasoning": "none", "role": "answer",
            "trial_id": "trial1", "thread_id": "answer-thread",
        }
        grader_identity = {
            "model": "fixture-grader", "reasoning": "none", "role": "grader",
            "trial_id": "trial1", "thread_id": "grader-thread",
        }
        grader_code = identified_code(
            "grader", grader_identity, "fixture-grader/trial1"
        ).replace(
            "result=",
            "assert contract['json_schema']['properties']['grader_id']['const'] "
            "== 'grader-trial1'\n"
            "assert contract['json_schema']['properties']['usage']['const'] is None\n"
            "result=",
            1,
        )
        result = self.run_host(
            identified_code("answer", answer_identity),
            grader_code=grader_code,
            grader_context={
                "required_facts": ["one"],
                "critical_facts": [],
                "acceptable_spans": [],
            },
            grader_model="fixture-grader",
            answer_execution_identity=answer_identity,
            grader_execution_identity=grader_identity,
            strict_contracts=True,
        )
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(result["attempts"][0]["failure_reason"], "grader_id_mismatch")

    def test_strict_answer_identity_rejects_absent_or_substituted_fields(self):
        expected = {
            "model": "fixture-model", "reasoning": "none", "role": "answer",
            "trial_id": "trial1", "thread_id": "answer-thread",
        }
        grader_identity = {
            "model": "fixture-grader", "reasoning": "none", "role": "grader",
            "trial_id": "trial1", "thread_id": "grader-thread",
        }
        cases = [("absent", None)]
        for field, value in (
            ("model", "substitute-model"), ("reasoning", "high"),
            ("role", "grader"), ("trial_id", "other-trial"),
            ("thread_id", "other-thread"),
        ):
            cases.append((field, {**expected, field: value}))
        for label, observed in cases:
            with self.subTest(label=label):
                result = self.run_host(
                    identified_code("answer", observed),
                    grader_code=identified_code("grader", grader_identity),
                    grader_model="fixture-grader",
                    answer_execution_identity=expected,
                    grader_execution_identity=grader_identity,
                    strict_contracts=True,
                )
                self.assertEqual(result["terminal_reason"], "measurement_error")

    def test_strict_grader_identity_rejects_absence_or_substitution(self):
        answer_identity = {
            "model": "fixture-model", "reasoning": "none", "role": "answer",
            "trial_id": "trial1", "thread_id": "answer-thread",
        }
        expected = {
            "model": "fixture-grader", "reasoning": "none", "role": "grader",
            "trial_id": "trial1", "thread_id": "grader-thread",
        }
        for label, observed in (
            ("absent", None), ("wrong_role", {**expected, "role": "answer"}),
        ):
            with self.subTest(label=label):
                result = self.run_host(
                    identified_code("answer", answer_identity),
                    grader_code=identified_code("grader", observed),
                    grader_model="fixture-grader",
                    answer_execution_identity=answer_identity,
                    grader_execution_identity=expected,
                    strict_contracts=True,
                )
                self.assertEqual(result["terminal_reason"], "measurement_error")

    def test_process_error_does_not_expose_stderr(self):
        result = self.run_host("import sys; sys.stderr.write('secret-value'); raise SystemExit(2)")
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(result["attempts"][0]["failure_reason"], "process_exit_nonzero")
        self.assertNotIn("secret-value", str(result))
        self.assertEqual(result["attempts"][0]["host_processes"][0]["status"], "failed")

    def test_contract_invalid_answer_still_records_the_completed_model_call(self):
        invalid = ANSWER_UNKNOWN_USAGE_CODE.replace(
            "velgraphing-answer-output-v1", "velgraphing-response-contract-v1",
        )
        result = self.run_host(invalid)
        attempt = result["attempts"][0]
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(attempt["failure_stage"], "answer")
        self.assertEqual(attempt["failure_reason"], "invalid_answer_output")
        self.assertEqual([row["kind"] for row in attempt["model_calls"]], ["answer"])

    def test_malformed_usage_still_records_the_completed_model_call(self):
        malformed = ANSWER_CODE.replace('"input_tokens": 10', '"input_tokens": -1')
        result = self.run_host(malformed)
        attempt = result["attempts"][0]
        self.assertEqual(result["terminal_reason"], "measurement_error")
        self.assertEqual(attempt["failure_reason"], "invalid_integer")
        self.assertEqual(len(attempt["model_calls"]), 1)
        self.assertEqual(attempt["model_calls"][0]["kind"], "answer")
        self.assertEqual(attempt["model_calls"][0]["provenance"], "unavailable")

    def test_shell_string_is_rejected(self):
        trial = Trial(identity(), Budget(0, 5_000_000_000), execution="fixture")
        with self.assertRaisesRegex(MeasurementError, "invalid_process_argv"):
            run_process_trial(
                trial, lambda *_: {}, answer_argv="python -c pass",
                grader_argv=[sys.executable, "-c", GRADER_CODE], cwd=self.cwd,
                answer_timeout_s=1, grader_timeout_s=1,
            )

    def test_v3_answer_requires_known_evidence_citation(self):
        evidence_id = "a" * 64
        prepared = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "frozen question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": [{"id": evidence_id, "path": "source.py", "excerpt": "evidence"}],
        }
        missing = self.run_host(ANSWER_CODE, prepared=prepared)
        self.assertEqual(missing["attempts"][0]["failure_reason"],
                         "answer_evidence_citation_missing")
        invalid = self.run_host(
            ANSWER_CODE.replace("observed subprocess answer", "unsupported [c2]"),
            prepared=prepared)
        self.assertEqual(invalid["attempts"][0]["failure_reason"],
                         "answer_evidence_citation_invalid")
        valid = self.run_host(
            ANSWER_CODE.replace(
                "observed subprocess answer", "supported [c1] with [pivot]"
            ),
            prepared=prepared)
        self.assertEqual(valid["terminal_reason"], "passed")

    def test_missing_citation_can_reach_grader_but_invalid_id_still_fails(self):
        evidence_id = "a" * 64
        prepared = {
            "schema_version": "velgraphing-answer-evidence-v3",
            "question": "frozen question",
            "citation_instruction": "Cite supporting evidence IDs as [cN].",
            "evidence": [{"id": evidence_id, "path": "source.py", "excerpt": "evidence"}],
        }
        missing = self.run_host(
            ANSWER_CODE,
            prepared=prepared,
            require_answer_evidence_citation=False,
        )
        self.assertEqual(missing["terminal_reason"], "passed")
        invalid = self.run_host(
            ANSWER_CODE.replace("observed subprocess answer", "unsupported [c2]"),
            prepared=prepared,
            require_answer_evidence_citation=False,
        )
        self.assertEqual(invalid["terminal_reason"], "measurement_error")
        self.assertEqual(
            invalid["attempts"][0]["failure_reason"],
            "answer_evidence_citation_invalid",
        )


if __name__ == "__main__":
    unittest.main()
