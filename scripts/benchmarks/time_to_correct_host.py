"""Frozen subprocess boundary for answer and independent grader commands.

Commands are argv arrays. The boundary never invokes a shell, reads credentials,
or invents answer, grade, context, usage, or success data.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping

try:
    from .time_to_correct import Answer, Grade, MeasurementError, Trial, canonical, digest
except ImportError:
    from time_to_correct import Answer, Grade, MeasurementError, Trial, canonical, digest


ANSWER_OUTPUT_VERSION = "velgraphing-answer-output-v1"
GRADER_OUTPUT_VERSION = "velgraphing-grader-output-v1"
USAGE_KEYS = {
    "model", "provenance", "input_tokens", "output_tokens",
    "cached_input_tokens", "reasoning_output_tokens", "cost_usd",
}


def _response_contract(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "velgraphing-response-contract-v1",
        "encoding": "canonical-json",
        "json_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": dict(properties),
        },
    }


ANSWER_RESPONSE_CONTRACT = _response_contract({
    "schema_version": {"const": ANSWER_OUTPUT_VERSION},
    "answer_text": {"type": "string"},
    "usage": {"type": ["object", "null"]},
    "model_calls_complete": {"type": "boolean"},
    "context_deliveries_complete": {"type": "boolean"},
})

GRADER_RESPONSE_CONTRACT = _response_contract({
    "schema_version": {"const": GRADER_OUTPUT_VERSION},
    "required_fact_score": {"type": "number"},
    "required_fact_maximum": {"type": "number", "exclusiveMinimum": 0},
    "critical_facts_exact": {"type": "boolean"},
    "unsupported_material_claims": {"type": "integer", "minimum": 0},
    "grader_id": {"type": "string"},
    "rubric_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "usage": {"type": ["object", "null"]},
    "model_calls_complete": {"type": "boolean"},
})


def _argv(value: Any) -> tuple[str, ...]:
    if type(value) is not list or not value or not all(type(part) is str and part for part in value):
        raise MeasurementError("invalid_process_argv")
    return tuple(value)


def _timeout(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise MeasurementError("invalid_process_timeout")
    return float(value)


def _decode_canonical(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise MeasurementError("process_output_invalid_json") from None
    if type(value) is not dict or raw != canonical(value):
        raise MeasurementError("process_output_not_canonical")
    return value


def _receipt(trial: Trial, kind: str, argv: tuple[str, ...], input_raw: bytes,
             output: bytes, error: bytes, exit_code: int | None,
             timeout_limit_ns: int, status: str) -> None:
    rows = trial._attempt().setdefault("host_processes", [])
    rows.append({
        "kind": kind,
        "argv_sha256": digest(canonical(list(argv))),
        "input_sha256": digest(input_raw),
        "stdout_sha256": digest(output),
        "stderr_sha256": digest(error),
        "exit_code": exit_code,
        "timeout_limit_ns": timeout_limit_ns,
        "status": status,
    })


def _invoke(trial: Trial, kind: str, argv_value: Any, payload: Mapping[str, Any],
            cwd: Path, call_timeout_s: float) -> dict[str, Any]:
    argv = _argv(argv_value)
    timeout_s = _timeout(call_timeout_s)
    trial._check_deadline()
    remaining_ns = trial.remaining_ns()
    configured_timeout_ns = int(timeout_s * 1_000_000_000)
    controller_limited = remaining_ns < configured_timeout_ns
    timeout_limit_ns = min(configured_timeout_ns, remaining_ns)
    raw = canonical(payload)
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env={},
            input=raw,
            capture_output=True,
            check=False,
            timeout=timeout_limit_ns / 1_000_000_000,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b""
        error = exc.stderr or b""
        _receipt(trial, kind, argv, raw, output, error, None, timeout_limit_ns, "timeout")
        if controller_limited:
            trial._check_deadline()
        raise TimeoutError from None
    except OSError:
        _receipt(trial, kind, argv, raw, b"", b"", None, timeout_limit_ns, "unavailable")
        raise MeasurementError("process_unavailable") from None
    status = "completed" if completed.returncode == 0 else "failed"
    _receipt(trial, kind, argv, raw, completed.stdout, completed.stderr,
             completed.returncode, timeout_limit_ns, status)
    if completed.returncode != 0:
        raise MeasurementError("process_exit_nonzero")
    return _decode_canonical(completed.stdout)


def _record_usage(trial: Trial, kind: str, payload: Any, attempt: int,
                  default_model: str) -> bool:
    call_id = f"{kind}-{attempt}"
    if payload is None:
        trial.usage(call_id, kind, provenance="unavailable", model=default_model)
        return False
    if type(payload) is not dict or set(payload) != USAGE_KEYS:
        raise MeasurementError("invalid_process_usage")
    trial.usage(call_id, kind, **payload)
    return True


def run_process_trial(
    trial: Trial,
    prepare: Callable[[Trial, int], Mapping[str, Any]],
    *,
    answer_argv: list[str],
    grader_argv: list[str],
    cwd: Path,
    answer_timeout_s: float,
    grader_timeout_s: float,
    grader_context: Mapping[str, Any] | None = None,
    answer_response_contract: Mapping[str, Any] | None = None,
    grader_response_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a trial through frozen answer and grader subprocess boundaries."""
    answer_command = list(_argv(answer_argv))
    grader_command = list(_argv(grader_argv))
    answer_timeout = _timeout(answer_timeout_s)
    grader_timeout = _timeout(grader_timeout_s)
    if grader_context is not None and type(grader_context) is not dict:
        raise MeasurementError("invalid_grader_context")
    if (answer_response_contract is not None and type(answer_response_contract) is not dict
            or grader_response_contract is not None and type(grader_response_contract) is not dict):
        raise MeasurementError("invalid_response_contract")

    def answer(t: Trial, prepared: Mapping[str, Any], attempt: int) -> Answer:
        if type(prepared) is not dict:
            raise MeasurementError("invalid_answer_input")
        payload = {
            "schema_version": "velgraphing-answer-input-v1",
            "attempt": attempt,
            "identity": {
                key: t.identity[key] for key in (
                    "run_id", "trial_id", "task_id", "arm", "repository_id",
                    "repository_commit", "source_snapshot_sha256", "answer_model",
                    "reasoning", "prompt_sha256",
                )
            },
            "payload": prepared,
        }
        if answer_response_contract is not None:
            payload["response_contract"] = dict(answer_response_contract)
        raw = canonical(payload)
        t.context(raw, kind="answer_request")
        output = _invoke(t, "answer", answer_command, payload, cwd, answer_timeout)
        if set(output) != {"schema_version", "answer_text", "usage", "model_calls_complete", "context_deliveries_complete"}:
            raise MeasurementError("invalid_answer_output")
        if output["schema_version"] != ANSWER_OUTPUT_VERSION or type(output["answer_text"]) is not str:
            raise MeasurementError("invalid_answer_output")
        if type(output["model_calls_complete"]) is not bool or type(output["context_deliveries_complete"]) is not bool:
            raise MeasurementError("invalid_answer_output")
        if prepared.get("schema_version") == "velgraphing-answer-evidence-v3":
            allowed = {row.get("id") for row in prepared.get("evidence", [])
                       if type(row) is dict and type(row.get("id")) is str}
            cited = re.findall(r"\[([A-Za-z0-9_-]+)\]", output["answer_text"])
            if not cited:
                raise MeasurementError("answer_evidence_citation_missing")
            if any(candidate_id not in allowed for candidate_id in cited):
                raise MeasurementError("answer_evidence_citation_invalid")
        if output["usage"] is not None:
            if type(output["usage"]) is not dict or set(output["usage"]) != USAGE_KEYS:
                raise MeasurementError("invalid_process_usage")
            if output["usage"]["model"] != t.identity["answer_model"]:
                raise MeasurementError("answer_model_mismatch")
        _record_usage(t, "answer", output["usage"], attempt, t.identity["answer_model"])
        t._attempt()["answer_boundary"] = {
            "model_calls_complete": output["model_calls_complete"],
            "context_deliveries_complete": output["context_deliveries_complete"],
        }
        return Answer(output["answer_text"])

    def grade(t: Trial, produced: Answer, attempt: int) -> Grade:
        payload = {
            "schema_version": "velgraphing-grader-input-v1",
            "attempt": attempt,
            "identity": {
                key: t.identity[key] for key in (
                    "run_id", "trial_id", "task_id", "arm", "rubric_sha256", "rubric_version",
                )
            },
            "answer_text": produced.content,
        }
        if grader_response_contract is not None:
            payload["response_contract"] = dict(grader_response_contract)
        if grader_context is not None:
            payload["grader_context"] = grader_context
            t.context(canonical(payload), kind="tool_message")
        output = _invoke(t, "grader", grader_command, payload, cwd, grader_timeout)
        expected = {
            "schema_version", "required_fact_score", "required_fact_maximum",
            "critical_facts_exact", "unsupported_material_claims", "grader_id",
            "rubric_sha256", "usage", "model_calls_complete",
        }
        if set(output) != expected or output["schema_version"] != GRADER_OUTPUT_VERSION:
            raise MeasurementError("invalid_grader_output")
        if type(output["model_calls_complete"]) is not bool:
            raise MeasurementError("invalid_grader_output")
        _record_usage(t, "grader", output["usage"], attempt, "unknown-grader")
        answer_boundary = t._attempt().get("answer_boundary", {})
        t.coverage(
            source_operations=bool(t._attempt()["coverage"]["source_operations"]),
            model_calls=bool(answer_boundary.get("model_calls_complete") and output["model_calls_complete"]),
            context_deliveries=bool(answer_boundary.get("context_deliveries_complete")),
        )
        required_score = output["required_fact_score"]
        required_maximum = output["required_fact_maximum"]
        if type(required_score) not in (int, float) or type(required_maximum) not in (int, float):
            raise MeasurementError("invalid_grader_output")
        recall = required_score / required_maximum if required_maximum else -1
        passed = (recall >= t.pass_recall_min and output["critical_facts_exact"] is True
                  and output["unsupported_material_claims"] == 0)
        return Grade(
            passed,
            required_score,
            required_maximum,
            output["critical_facts_exact"],
            output["unsupported_material_claims"],
            output["grader_id"],
            output["rubric_sha256"],
        )

    return trial.run(prepare, answer, grade)
