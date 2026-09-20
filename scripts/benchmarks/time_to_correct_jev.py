"""Timing integration with the real Jev evaluator in an isolated module.

No production module is patched. Offline evaluation cannot make network calls or
access credentials. Live evaluation requires explicit runtime authority and cap
binding before the canonical evaluator can read its credential.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any
import uuid

try:
    from .time_to_correct import MeasurementError, Trial, digest
except ImportError:
    from time_to_correct import MeasurementError, Trial, digest


def _load_jev(repo: Path, *, forbid_live: bool) -> Any:
    spec = importlib.util.spec_from_file_location("jev_benchmark_" + uuid.uuid4().hex,
                                                  repo / "packages/core/jev.py")
    if spec is None or spec.loader is None:
        raise MeasurementError("jev_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if forbid_live:
        # Defense in depth: offline fallthrough cannot invoke the real HTTP function.
        def forbidden(*args: Any, **kwargs: Any) -> None:
            raise MeasurementError("live_provider_forbidden")
        module._http = forbidden
    return module


def load_jev(repo: Path) -> Any:
    """Load a credential-blind evaluator for replay and fixture use."""
    return _load_jev(repo, forbid_live=True)


def _instrument(module: Any, trial: Trial, *, operation_prefix: str = "jev") -> None:
    original_prepare, original_parse, original_read = module.prepare, module.parse_response, module._read_source
    preparation_calls = 0
    source_calls = 0
    def prepare(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal preparation_calls
        phase = "jev_preparation" if preparation_calls == 0 else "source_revalidation"
        preparation_calls += 1
        with trial.phase(phase):
            prepared = original_prepare(*args, **kwargs)
            if preparation_calls == 1:
                trial.bind(candidate_set_sha256=prepared["candidate_set_sha256"],
                           request_sha256=prepared["request_sha256"])
                request = prepared["request"]
                trial.current["_jev_packet_telemetry"] = {
                    "request_bytes": prepared["request_bytes"],
                    "shared_state_bytes": len(module.canonical(request["state"])),
                    "questions_bytes": len(module.canonical(request["questions"])),
                    "candidate_count": len(request["state"]["candidates"]),
                    "question_count": len(request["questions"]),
                    "rubric_version": prepared["rubric_version"],
                    # TypeSafe reports request-level usage, not this split.
                    "shared_state_tokens": None,
                    "question_suffix_tokens": None,
                }
            return prepared
    def read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal source_calls
        raw = original_read(*args, **kwargs)
        source_calls += 1
        trial.source(digest(raw), 0, len(raw), access="file_read",
                     operation_id=f"{operation_prefix}-{trial.current['attempt_id']}-read{source_calls}")
        return raw
    def parse(*args: Any, **kwargs: Any) -> Any:
        with trial.phase("response_validation"):
            return original_parse(*args, **kwargs)
    module.prepare, module.parse_response, module._read_source = prepare, parse, read


def prepare_preview(trial: Trial, repo: Path, packet: dict[str, Any], root: Path) -> dict[str, Any]:
    """Prepare the exact request hash for caller-owned approval, without network."""
    module = load_jev(repo)
    _instrument(module, trial, operation_prefix="jev-preview")
    return module.prepare(packet, root, module.DEFAULT_MODEL)


def _record(trial: Trial, module: Any, result: dict[str, Any], *, execution: str,
            provenance: str, retain_packet_telemetry: bool) -> None:
    usage = result.get("usage") if execution in {"live", "fixture_provider"} else result.get("replayed_usage")
    trial.usage(f"jev-{trial.current['attempt_id']}", "jev",
                provenance=provenance if usage else "unavailable",
                model=result.get("resolved_model") or module.DEFAULT_MODEL,
                input_tokens=usage["input_tokens"] if usage else None,
                output_tokens=usage["output_tokens"] if usage else None)
    packet_telemetry = {
        "request_bytes": None,
        "shared_state_bytes": None,
        "questions_bytes": None,
        "candidate_count": None,
        "question_count": None,
        "rubric_version": module.RUBRIC_VERSION,
        "shared_state_tokens": None,
        "question_suffix_tokens": None,
        **trial.current.pop("_jev_packet_telemetry", {}),
    }
    trial.current["jev_observation"] = {
        key: result.get(key) for key in (
            "status", "reason", "baseline_order", "order", "required_ids",
            "candidate_set_sha256", "request_sha256", "source_revalidated", "resolved_model",
        )
    }
    if retain_packet_telemetry:
        trial.current["jev_observation"].update({
            **packet_telemetry,
            "source_bytes_verified": result.get("source_bytes_verified"),
            "scores": copy.deepcopy(result.get("scores", [])),
            "elapsed_ms": result.get("elapsed_ms"),
            "attempted_calls": result.get("attempted_calls"),
        })
    trial.current["jev_observation"]["measurement_execution"] = execution


def evaluate_offline(trial: Trial, repo: Path, packet: dict[str, Any], root: Path, *,
                     envelope: dict[str, Any], mode: str = "rerank",
                     fixture_provider: bool = False,
                     retain_packet_telemetry: bool = False) -> dict[str, Any]:
    """Instrument existing prepare/parse/revalidation without changing ranking.

    envelope must be a request-bound replay envelope, including in fixture mode.
    Use this only in a single-owner benchmark controller. A live-host adapter
    needs its own explicit provider authorization and complete call ledger.
    """
    if trial.execution not in {"fixture", "replay"}:
        raise MeasurementError("offline_bridge_requires_fixture_or_replay")
    if type(fixture_provider) is not bool or mode not in {"off", "shadow", "rerank"}:
        raise MeasurementError("invalid_offline_options")
    module = load_jev(repo)
    _instrument(module, trial)
    def transport(payload: Any, timeout: float) -> Any:
        if (set(envelope) != {"schema_version", "request_sha256", "response"}
                or envelope["schema_version"] != "velgraphing-jev-replay-v1"
                or module.sha256(module.canonical(payload)) != envelope["request_sha256"]):
            raise MeasurementError("fixture_request_mismatch")
        with trial.phase("provider"):
            return copy.deepcopy(envelope["response"])
    if mode == "off":
        trial.not_applicable("jev_preparation", "provider", "source_revalidation", "response_validation")
        return module.evaluate(packet, root, mode="off")
    if fixture_provider:
        result = module.evaluate(packet, root, mode=mode, allow_network=True,
                                 approved_request_sha256=envelope.get("request_sha256"), transport=transport)
        # allow_network is required by the production interface, but this isolated
        # copy has no functional HTTP transport and only copies the supplied JSON.
    else:
        trial.not_applicable("provider")
        result = module.evaluate(packet, root, mode=mode, replay=envelope)
    _record(trial, module, result,
            execution="fixture_provider" if fixture_provider else "replay",
            provenance="fixture", retain_packet_telemetry=retain_packet_telemetry)
    return result


def evaluate_live(trial: Trial, repo: Path, packet: dict[str, Any], root: Path, *,
                  approved_request_sha256: str, runtime_approved: bool,
                  max_live_calls: int, call_number: int, timeout_s: float = 10,
                  retain_packet_telemetry: bool = False) -> dict[str, Any]:
    """Run one canonical live evaluation after caller-owned approval and cap checks."""
    if trial.execution != "observed" or runtime_approved is not True:
        raise MeasurementError("live_jev_not_approved")
    if (type(max_live_calls) is not int or type(call_number) is not int
            or max_live_calls < 1 or not 1 <= call_number <= max_live_calls):
        raise MeasurementError("live_jev_cap_not_bound")
    module = _load_jev(repo, forbid_live=False)
    original_http = module._http
    _instrument(module, trial, operation_prefix="jev-live")
    def observed_http(payload: Any, timeout: float) -> Any:
        with trial.phase("provider"):
            return original_http(payload, timeout)
    module._http = observed_http
    result = module.evaluate(
        packet, root, mode="rerank", allow_network=True,
        approved_request_sha256=approved_request_sha256,
        model=module.DEFAULT_MODEL, timeout_s=timeout_s,
    )
    _record(trial, module, result, execution="live", provenance="provider_reported",
            retain_packet_telemetry=retain_packet_telemetry)
    return result
