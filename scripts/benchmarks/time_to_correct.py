"""Benchmark-owned, single-controller timing and accounting. No model client.

A host supplies real execution and independent grading callbacks. This module
never launches an agent, reads credentials, or converts source bytes to tokens.
Only the owning process/thread stamps events. Nanoseconds are units, not an
assertion of clock precision. Controlled tests may inject a clock.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping, Sequence
import uuid

PHASES = (
    "cold_graph_build", "warm_graph_load", "candidate_discovery", "retrieval",
    "fallback", "source_capture", "jev_preparation", "provider",
    "source_revalidation", "response_validation", "context_composition",
    "answer_generation", "grading", "host_queue", "operator_approval", "repair",
)
WAITS = {"host_queue", "operator_approval"}
WORK = set(PHASES) - WAITS - {"repair"}
HASH = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[A-Za-z0-9_.:@+-]{1,128}\Z")
IDENTITY = {
    "run_id", "trial_id", "task_id", "arm", "repository_id", "repository_commit",
    "source_snapshot_sha256", "dirty_state_sha256", "answer_model", "reasoning",
    "prompt_sha256", "rubric_sha256", "rubric_version", "answer_lane_id",
}
BINDINGS = {
    "candidate_set_sha256", "request_sha256", "model_visible_context_sha256",
    "source_snapshot_sha256", "graph_artifact_sha256", "fallback_allowlist_sha256",
}
RECEIPT_KINDS = {"answer", "jev", "grader", "other_model"}
PROVENANCES = {"provider_reported", "host_observed", "fixture", "unavailable"}


class MeasurementError(ValueError):
    """Closed reason codes only; never attach source or arbitrary exceptions."""

    def __init__(self, reason: str) -> None:
        if type(reason) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason):
            reason = "measurement_error"
        self.reason = reason
        super().__init__(reason)


class _ControllerDeadline(Exception):
    """Private signal for the controller-owned wall deadline."""


TRANSIENT_MODEL_ERRORS = frozenset({
    "process_unavailable", "process_response_timeout",
    "process_response_malformed", "process_output_invalid_json",
    "process_output_not_canonical", "invalid_answer_output",
    "invalid_grader_output", "grader_required_fact_decisions_mismatch",
    "answer_evidence_citation_missing",
})


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise MeasurementError("invalid_integer")
    return value


def identifier(value: Any) -> str:
    if type(value) is not str or not ID.fullmatch(value):
        raise MeasurementError("invalid_opaque_identifier")
    return value


def fingerprint(value: Any) -> str:
    if type(value) is not str or not HASH.fullmatch(value):
        raise MeasurementError("invalid_sha256")
    return value


def union_ns(intervals: Sequence[tuple[int, int]]) -> int:
    """Length of an interval union, never a sum of overlapping durations."""
    total = 0
    end = -1
    for left, right in sorted(intervals):
        integer(left)
        integer(right)
        if right < left:
            raise MeasurementError("reversed_interval")
        total += max(0, right - max(left, end))
        end = max(end, right)
    return total


@dataclass(frozen=True)
class Budget:
    max_repairs: int = 2
    wall_limit_ns: int = 300_000_000_000

    def __post_init__(self) -> None:
        integer(self.max_repairs)
        integer(self.wall_limit_ns, 1)
        if self.max_repairs > 10:
            raise MeasurementError("repair_limit_too_large")


@dataclass(frozen=True)
class Answer:
    content: str
    # Usage must be recorded separately at EACH actual model call, not once
    # on a whole agent turn that might contain hidden internal model calls.


@dataclass(frozen=True)
class Grade:
    passed: bool
    required_fact_score: float
    required_fact_maximum: float
    critical_facts_exact: bool
    unsupported_material_claims: int
    grader_id: str
    rubric_sha256: str

    @property
    def required_fact_recall(self) -> float:
        return self.required_fact_score / self.required_fact_maximum

    def validate(self, identity: Mapping[str, Any]) -> None:
        if type(self.passed) is not bool or type(self.critical_facts_exact) is not bool:
            raise MeasurementError("invalid_grade")
        for value in (self.required_fact_score, self.required_fact_maximum):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise MeasurementError("invalid_grade")
        if (self.required_fact_maximum <= 0 or not 0 <= self.required_fact_score
                <= self.required_fact_maximum):
            raise MeasurementError("invalid_grade")
        integer(self.unsupported_material_claims)
        identifier(self.grader_id)
        fingerprint(self.rubric_sha256)
        if self.grader_id == identity["answer_lane_id"]:
            raise MeasurementError("grader_is_answer_lane")
        if self.rubric_sha256 != identity["rubric_sha256"]:
            raise MeasurementError("rubric_changed")
        if self.passed and (not self.critical_facts_exact or self.unsupported_material_claims):
            raise MeasurementError("pass_contradicts_safety_grade")


class Trial:
    """One task/arm/repetition, stamped only by its benchmark controller.

    Host code is trusted instrumentation, not an adversarial security boundary.
    No API accepts worker-supplied timestamps. Mark an unobservable phase missing.
    A different host/process needs its own clock domain and duration receipt;
    never subtract its timestamp from this controller's clock.
    """

    def __init__(self, identity: Mapping[str, Any], budget: Budget = Budget(), *,
                 clock: Callable[[], int] = time.monotonic_ns,
                 execution: str = "observed", pass_recall_min: float = 0.9,
                 retry_transient: bool = False) -> None:
        if set(identity) != IDENTITY or identity["arm"] not in {"A", "B", "C", "D"}:
            raise MeasurementError("invalid_trial_identity")
        for key, value in identity.items():
            if key.endswith("sha256"):
                fingerprint(value)
            else:
                identifier(value)
        if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", identity["repository_commit"]):
            raise MeasurementError("invalid_commit")
        if execution not in {"observed", "fixture", "replay"}:
            raise MeasurementError("invalid_execution_kind")
        if type(pass_recall_min) not in (int, float) or not math.isfinite(pass_recall_min) or not 0 <= pass_recall_min <= 1:
            raise MeasurementError("invalid_pass_threshold")
        if type(retry_transient) is not bool:
            raise MeasurementError("invalid_retry_policy")
        self.retry_transient = retry_transient
        self.pass_recall_min = float(pass_recall_min)
        self.identity = MappingProxyType(dict(identity))
        self.budget = budget
        self.execution = execution
        self.clock_domain = uuid.uuid4().hex
        self._clock = clock
        self._owner = (os.getpid(), threading.get_ident())
        self._origin = integer(clock())
        self._last = self._origin
        self.events: list[dict[str, Any]] = []
        self.intervals: list[dict[str, Any]] = []
        self._stack: list[tuple[int, str]] = []
        self.attempts: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.terminal_reason: str | None = None
        self.stamp("task_accepted")
        # Anchor the domain and deadline to acceptance, not constructor setup.
        self._origin = self._last
        self.events[0]["t_ns"] = 0

    def now(self) -> int:
        if self._owner != (os.getpid(), threading.get_ident()):
            raise MeasurementError("clock_owner_mismatch")
        value = integer(self._clock())
        if value < self._last:
            raise MeasurementError("clock_moved_backward")
        self._last = value
        return value - self._origin

    def stamp(self, event: str, **metadata: Any) -> int:
        if self.terminal_reason is not None:
            raise MeasurementError("trial_already_terminal")
        allowed_events = {"task_accepted", "task_terminal", "attempt_started", "attempt_completed",
                          "answer_dispatch", "answer_completed", "independent_grade_completed", "first_passing_answer"}
        allowed_events |= {p + suffix for p in PHASES for suffix in ("_started", "_finished")}
        if event not in allowed_events:
            raise MeasurementError("invalid_event")
        # Only internal closed event attributes are accepted, no arbitrary data.
        if set(metadata) - {"span_id", "parent_span_id", "outcome"}:
            raise MeasurementError("invalid_event_metadata")
        if "outcome" in metadata and metadata["outcome"] not in {"completed", "error"}:
            raise MeasurementError("invalid_event_outcome")
        for key in ("span_id", "parent_span_id"):
            if metadata.get(key) is not None:
                integer(metadata[key])
        timestamp = self.now()
        self.events.append({"sequence": len(self.events), "event": event,
                            "t_ns": timestamp, "attempt_id": self.current["attempt_id"] if self.current else None,
                            **metadata})
        return timestamp

    def remaining_ns(self) -> int:
        return max(0, self.budget.wall_limit_ns - self.now())

    def _check_deadline(self) -> None:
        if self.remaining_ns() == 0:
            raise _ControllerDeadline

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        if name not in PHASES:
            raise MeasurementError("invalid_phase")
        if self.current and self.current["phase_status"].get(name) == "not_applicable":
            raise MeasurementError("phase_marked_not_applicable")
        span_id = len(self.events)
        parent = self._stack[-1][0] if self._stack else None
        begin = self.stamp(name + "_started", span_id=span_id, parent_span_id=parent)
        self._stack.append((span_id, name))
        outcome = "completed"
        try:
            yield
        except BaseException:
            outcome = "error"
            raise
        finally:
            self._stack.pop()
            finish = self.stamp(name + "_finished", span_id=span_id, outcome=outcome)
            self.intervals.append({"phase": name, "start_ns": begin, "end_ns": finish,
                                   "attempt_id": self.current["attempt_id"] if self.current else None,
                                   "outcome": outcome})
            if self.current:
                self.current["phase_status"][name] = "observed"

    def not_applicable(self, *names: str) -> None:
        attempt = self._attempt()
        for name in names:
            if name not in PHASES or attempt["phase_status"][name] == "observed":
                raise MeasurementError("invalid_phase_status")
            if any(active == name for _, active in self._stack):
                raise MeasurementError("phase_is_active")
            attempt["phase_status"][name] = "not_applicable"

    def _attempt(self) -> dict[str, Any]:
        if self.current is None or self.terminal_reason is not None:
            raise MeasurementError("no_active_attempt")
        return self.current

    def bind(self, **hashes: str) -> None:
        attempt = self._attempt()
        if set(hashes) - BINDINGS:
            raise MeasurementError("invalid_binding")
        for key, value in hashes.items():
            fingerprint(value)
            old = attempt["bindings"][key]
            if old is not None and old != value:
                raise MeasurementError("attempt_binding_changed")
            if key == "source_snapshot_sha256" and value != self.identity[key]:
                raise MeasurementError("snapshot_changed")
            attempt["bindings"][key] = value

    def context(self, raw: bytes, *, kind: str = "answer_request") -> None:
        """Account actual delivered content bytes, not disk reads or tokens.

        Call at the host boundary for EVERY model-visible message/request.
        request bytes and tool-message bytes are separate overlapping views:
        do not sum them to estimate total context or model tokens.
        """
        if type(raw) is not bytes or kind not in {"answer_request", "tool_message"}:
            raise MeasurementError("invalid_context")
        self._attempt()["context_deliveries"].append(
            {"kind": kind, "bytes": len(raw), "sha256": digest(raw)})
        if kind == "answer_request":
            # May change across multiple model calls, so the attempt binding is
            # a digest of the ordered delivery receipts, not only the last call.
            rows = [r for r in self.current["context_deliveries"] if r["kind"] == kind]
            self.current["bindings"]["model_visible_context_sha256"] = digest(canonical(rows))

    def source(self, source_sha256: str, byte_start: int, byte_end: int, *,
               access: str = "file_read", operation_id: str) -> None:
        fingerprint(source_sha256)
        identifier(operation_id)
        integer(byte_start)
        integer(byte_end)
        if byte_end < byte_start or access not in {"file_read", "memory_read", "tool_read"}:
            raise MeasurementError("invalid_source_operation")
        rows = self._attempt()["source_operations"]
        if any(row["operation_id"] == operation_id for row in rows):
            raise MeasurementError("duplicate_source_operation")
        rows.append({"operation_id": operation_id, "source_sha256": source_sha256,
                     "byte_start": byte_start, "byte_end": byte_end, "access": access})

    def usage(self, call_id: str, kind: str, *, provenance: str,
              input_tokens: int | None = None, output_tokens: int | None = None,
              cached_input_tokens: int | None = None,
              reasoning_output_tokens: int | None = None,
              cost_usd: float | None = None, model: str) -> None:
        identifier(call_id)
        identifier(model)
        if provenance == "fixture" and self.execution == "observed":
            raise MeasurementError("fixture_usage_in_observed_trial")
        if kind not in RECEIPT_KINDS or provenance not in PROVENANCES:
            raise MeasurementError("invalid_usage_kind")
        for value in (input_tokens, output_tokens, cached_input_tokens, reasoning_output_tokens):
            if value is not None:
                integer(value)
        if cached_input_tokens is not None and (input_tokens is None or cached_input_tokens > input_tokens):
            raise MeasurementError("invalid_cached_subset")
        if reasoning_output_tokens is not None and (output_tokens is None or reasoning_output_tokens > output_tokens):
            raise MeasurementError("invalid_reasoning_subset")
        if provenance == "unavailable" and any(v is not None for v in
                (input_tokens, output_tokens, cached_input_tokens, reasoning_output_tokens, cost_usd)):
            raise MeasurementError("unavailable_usage_has_values")
        if cost_usd is not None and (type(cost_usd) not in (int, float) or not math.isfinite(cost_usd) or cost_usd < 0):
            raise MeasurementError("invalid_cost")
        rows = self._attempt()["model_calls"]
        if any(r["call_id"] == call_id for a in self.attempts for r in a["model_calls"]):
            raise MeasurementError("duplicate_model_call")
        rows.append(dict(call_id=call_id, kind=kind, model=model, provenance=provenance,
                         input_tokens=input_tokens, output_tokens=output_tokens,
                         cached_input_tokens=cached_input_tokens,
                         reasoning_output_tokens=reasoning_output_tokens, cost_usd=cost_usd))

    def coverage(self, *, source_operations: bool = False,
                 model_calls: bool = False, context_deliveries: bool = False) -> None:
        """Host attests complete capture; defaults remain incomplete/unknown."""
        values = locals().copy()
        values.pop("self")
        if any(type(v) is not bool for v in values.values()):
            raise MeasurementError("invalid_coverage")
        self._attempt()["coverage"].update(values)

    def run(self, prepare: Callable[["Trial", int], Any],
            answer: Callable[["Trial", Any, int], Answer],
            grade: Callable[["Trial", Answer, int], Grade]) -> dict[str, Any]:
        """Execute bounded attempts. Callbacks must honor host cancellation.

        Deadline enforcement is cooperative at callback boundaries, NOT a hard
        kill of arbitrary code. Late work is retained and not credited as success.
        The grader's hidden rubric is never passed to the answer callback.
        """
        if self.attempts or self.terminal_reason:
            raise MeasurementError("trial_already_run")
        reason = "repair_budget_exhausted"
        for number in range(self.budget.max_repairs + 1):
            if self.remaining_ns() == 0:
                reason = "deadline_exceeded"
                break
            self.current = {
                "attempt_id": f"a{number}", "number": number,
                "bindings": {k: None for k in BINDINGS},
                "phase_status": {p: "missing" for p in PHASES},
                "context_deliveries": [], "source_operations": [], "model_calls": [],
                "coverage": {"source_operations": False, "model_calls": False, "context_deliveries": False},
                "grade": None, "answer_sha256": None, "answer_completed_ns": None,
                "grade_completed_ns": None, "terminal_reason": None,
                "failure_stage": None, "failure_reason": None,
            }
            self.current["bindings"]["source_snapshot_sha256"] = self.identity["source_snapshot_sha256"]
            self.attempts.append(self.current)
            self.stamp("attempt_started")
            repair = self.phase("repair") if number else None
            if repair:
                repair.__enter__()
            else:
                self.not_applicable("repair")
            try:
                stage = "prepare"
                prepared = prepare(self, number)
                self._check_deadline()
                self.stamp("answer_dispatch")
                stage = "answer"
                with self.phase("answer_generation"):
                    produced = answer(self, prepared, number)
                if not isinstance(produced, Answer) or type(produced.content) is not str:
                    raise MeasurementError("invalid_answer")
                self.current["answer_sha256"] = digest(produced.content.encode("utf-8"))
                self.current["answer_completed_ns"] = self.stamp("answer_completed")
                self._check_deadline()
                stage = "grader"
                with self.phase("grading"):
                    scored = grade(self, produced, number)
                    if not isinstance(scored, Grade):
                        raise MeasurementError("invalid_grade")
                    scored.validate(self.identity)
                    expected_pass = (scored.required_fact_recall >= self.pass_recall_min
                                     and scored.critical_facts_exact and scored.unsupported_material_claims == 0)
                    if scored.passed != expected_pass:
                        raise MeasurementError("grade_disagrees_with_frozen_gate")
                self.current["grade_completed_ns"] = self.stamp("independent_grade_completed")
                self.current["grade"] = {**vars(scored), "required_fact_recall": scored.required_fact_recall}
                self._check_deadline()
                if scored.passed:
                    self.stamp("first_passing_answer")
                    reason = "passed"
                else:
                    reason = ("repair_budget_exhausted" if self.retry_transient
                              or number == self.budget.max_repairs else "needs_repair")
            except _ControllerDeadline:
                reason = "deadline_exceeded"
                self.current["failure_stage"] = "controller"
                self.current["failure_reason"] = reason
            except TimeoutError:
                reason = ("needs_repair" if self.retry_transient
                          and stage in {"answer", "grader"}
                          and number < self.budget.max_repairs else "callback_timeout")
                self.current["failure_stage"] = stage
                self.current["failure_reason"] = "callback_timeout"
            except (KeyboardInterrupt, InterruptedError):
                reason = "cancelled"
            except MeasurementError as exc:
                reason = ("needs_repair" if self.retry_transient
                          and stage in {"answer", "grader"}
                          and exc.reason in TRANSIENT_MODEL_ERRORS
                          and number < self.budget.max_repairs else "measurement_error")
                self.current["failure_stage"] = stage
                self.current["failure_reason"] = exc.reason
            except (Exception, SystemExit):
                reason = "callback_error"
                self.current["failure_stage"] = stage
                self.current["failure_reason"] = reason
            finally:
                if repair:
                    repair.__exit__(None, None, None)
                self.current["terminal_reason"] = reason
                self.stamp("attempt_completed")
            if reason != "needs_repair":
                break
        self.stamp("task_terminal")
        self.terminal_reason = reason
        return self.result()

    def result(self) -> dict[str, Any]:
        if self.terminal_reason is None:
            raise MeasurementError("trial_not_terminal")
        elapsed = self.events[-1]["t_ns"] - self.events[0]["t_ns"]
        waits = [(r["start_ns"], r["end_ns"]) for r in self.intervals if r["phase"] in WAITS]
        work = [(r["start_ns"], r["end_ns"]) for r in self.intervals if r["phase"] in WORK]
        occupied = union_ns(work + waits)
        phase_totals: dict[str, Any] = {}
        for phase in PHASES:
            intervals = [(r["start_ns"], r["end_ns"]) for r in self.intervals if r["phase"] == phase]
            statuses = [attempt["phase_status"][phase] for attempt in self.attempts]
            observed = statuses.count("observed")
            missing = statuses.count("missing")
            not_applicable = statuses.count("not_applicable")
            if statuses and observed == len(statuses):
                status = "observed"
            elif statuses and not_applicable == len(statuses):
                status = "not_applicable"
            elif statuses and missing == len(statuses):
                status = "missing"
            else:
                status = "partial"
            phase_totals[phase] = {
                "status": status,
                "complete": bool(statuses) and missing == 0,
                "attempts_total": len(statuses),
                "observed_attempts": observed,
                "missing_attempts": missing,
                "not_applicable_attempts": not_applicable,
                "inclusive_union_ns": union_ns(intervals) if intervals else (0 if status == "not_applicable" else None),
            }
        first = self.attempts[0] if self.attempts else None
        passing = next((a for a in self.attempts if a["terminal_reason"] == "passed"), None)
        receipts = [r for a in self.attempts for r in a["model_calls"]]
        usage_complete = bool(self.attempts) and all(
            a["coverage"]["model_calls"] and
            (a["answer_completed_ns"] is None or any(r["kind"] == "answer" for r in a["model_calls"]))
            for a in self.attempts)
        def token_total(key: str) -> int | None:
            if not usage_complete or any(r[key] is None or r["provenance"] == "unavailable" for r in receipts):
                return None
            return sum(r[key] for r in receipts)
        cost = sum(r["cost_usd"] for r in receipts) if usage_complete and all(r["cost_usd"] is not None for r in receipts) else None
        zero = self.events[0]["t_ns"]
        payload = {
            "schema_version": "velgraphing-time-to-correct-v1", "identity": dict(self.identity),
            "execution": self.execution, "clock": {"name": "monotonic_ns", "domain": self.clock_domain,
                "owner": "benchmark_controller", "timestamps": "domain_relative_ns", "cross_domain_subtraction": False},
            "budget": dict(vars(self.budget)), "pass_recall_min": self.pass_recall_min, "deadline_enforcement": "cooperative_callback_boundaries",
            "terminal_reason": self.terminal_reason, "events": self.events, "intervals": self.intervals,
            "attempts": self.attempts, "phases": phase_totals,
            "first_pass_correct": first["grade"]["passed"] if first and first["grade"] else None,
            "first_answer_ns": first["answer_completed_ns"] - zero if first and first["answer_completed_ns"] is not None else None,
            "first_correct_answer_ns": passing["answer_completed_ns"] - zero if passing else None,
            "confirmed_time_to_correct_ns": passing["grade_completed_ns"] - zero if passing else None,
            "user_visible_wall_ns": elapsed,
            "observed_wait_union_ns": union_ns(waits),
            "observed_active_execution_ns": occupied - union_ns(waits),
            "unattributed_ns": elapsed - occupied,
            "usage_complete": usage_complete, "total_input_tokens": token_total("input_tokens"),
            "total_output_tokens": token_total("output_tokens"), "successful_task_cost_usd": cost if passing else None,
            "all_attempt_cost_usd": cost,
        }
        return json.loads(canonical(payload))


def summarize(expected_trial_ids: Sequence[str], results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep registered missing, failed, censored and successful trials visible.

    No success-only latency average, and no fake finite TTC for a failed task.
    Missing trials count in denominators. Compare one arm/protocol at a time.
    """
    expected = [identifier(i) for i in expected_trial_ids]
    if len(set(expected)) != len(expected) or not expected:
        raise MeasurementError("invalid_registration")
    by_id: dict[str, Mapping[str, Any]] = {}
    protocol_keys = ("run_id", "arm", "answer_model", "reasoning", "rubric_version", "rubric_sha256")
    protocol = None
    for result in results:
        trial_id = result["identity"]["trial_id"]
        if trial_id not in expected or trial_id in by_id:
            raise MeasurementError("unregistered_or_duplicate_trial")
        key = tuple(result["identity"][p] for p in protocol_keys) + (canonical(result["budget"]), result["pass_recall_min"], result["execution"])
        if protocol is not None and key != protocol:
            raise MeasurementError("incomparable_trials")
        protocol = key
        by_id[trial_id] = result
    rows = []
    for trial_id in expected:
        result = by_id.get(trial_id)
        rows.append({"trial_id": trial_id, "terminal_reason": result["terminal_reason"] if result else "missing",
                     "first_pass_correct": result["first_pass_correct"] if result else None,
                     "user_visible_wall_ns": result["user_visible_wall_ns"] if result else None,
                     "confirmed_time_to_correct_ns": result["confirmed_time_to_correct_ns"] if result else None})
    passing = sum(r["terminal_reason"] == "passed" for r in rows)
    first_pass = sum(r["first_pass_correct"] is True for r in rows)
    return {"registered_trials": len(expected), "reported_trials": len(results),
            "passed_within_budget": passing, "pass_rate_registered": passing / len(expected),
            "first_pass_correct_registered": first_pass / len(expected),
            "ungraded_or_missing_trials": sum(r["first_pass_correct"] is None for r in rows),
            "mean_observed_terminal_wall_ns": sum(r["user_visible_wall_ns"] for r in rows) / len(rows)
                if all(r["user_visible_wall_ns"] is not None for r in rows) else None,
            "mean_time_to_correct_ns": sum(r["confirmed_time_to_correct_ns"] for r in rows) / len(rows)
                if passing == len(rows) else None,
            "ttc_mean_policy": "all_registered_trials_must_pass",
            "coverage_complete": len(results) == len(expected),
            "rates_are_lower_bounds": len(results) != len(expected) or any(r["first_pass_correct"] is None for r in rows),
            "cost_per_success_usd": sum(r["all_attempt_cost_usd"] for r in results) / passing
                if passing and len(results) == len(expected) and all(r["all_attempt_cost_usd"] is not None for r in results) else None,
            "trials": rows}


def save_completed_trial(directory: Path, result: Mapping[str, Any]) -> Path:
    """Atomically retain one terminal trial for interrupted-run recovery."""
    if result.get("schema_version") != "velgraphing-time-to-correct-v1" or not result.get("terminal_reason"):
        raise MeasurementError("invalid_completed_trial")
    trial_id = identifier(result.get("identity", {}).get("trial_id"))
    raw = canonical(result)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{trial_id}.json"
    if destination.exists():
        if destination.read_bytes() != raw:
            raise MeasurementError("completed_trial_receipt_conflict")
        return destination
    temporary = directory / f".{trial_id}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def load_completed_trials(directory: Path, expected_trial_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Load only preregistered completed receipts. Missing IDs remain missing."""
    results = []
    for trial_id in expected_trial_ids:
        trial_id = identifier(trial_id)
        path = directory / f"{trial_id}.json"
        if not path.exists():
            continue
        raw = path.read_bytes()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            raise MeasurementError("invalid_completed_trial") from None
        if raw != canonical(result) or result.get("schema_version") != "velgraphing-time-to-correct-v1":
            raise MeasurementError("invalid_completed_trial")
        if result.get("identity", {}).get("trial_id") != trial_id or not result.get("terminal_reason"):
            raise MeasurementError("invalid_completed_trial")
        results.append(result)
    return results
