"""Offline timing integration with the REAL Jev evaluator in an isolated module.

No production module is patched. This bridge deliberately cannot make network
calls or access credentials. Fixture provider duration is local response-copy
work; replay has no provider stage. Neither is a live latency measurement.
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


def load_jev(repo: Path) -> Any:
    spec = importlib.util.spec_from_file_location("jev_benchmark_" + uuid.uuid4().hex,
                                                  repo / "packages/core/jev.py")
    if spec is None or spec.loader is None:
        raise MeasurementError("jev_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Defense in depth: even accidental fallthrough cannot invoke the real HTTP
    # function. Do not run status or inspect the environment in this bridge.
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise MeasurementError("live_provider_forbidden")
    module._http = forbidden
    return module


def evaluate_offline(trial: Trial, repo: Path, packet: dict[str, Any], root: Path, *,
                     envelope: dict[str, Any], mode: str = "rerank",
                     fixture_provider: bool = False) -> dict[str, Any]:
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
            return prepared
    def read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal source_calls
        raw = original_read(*args, **kwargs)
        source_calls += 1
        trial.source(digest(raw), 0, len(raw), access="file_read",
                     operation_id=f"jev-{trial.current['attempt_id']}-read{source_calls}")
        return raw
    def parse(*args: Any, **kwargs: Any) -> Any:
        with trial.phase("response_validation"):
            return original_parse(*args, **kwargs)
    module.prepare, module.parse_response, module._read_source = prepare, parse, read
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
    usage = result.get("usage") if fixture_provider else result.get("replayed_usage")
    trial.usage(f"jev-{trial.current['attempt_id']}", "jev", provenance="fixture" if usage else "unavailable",
                model=module.DEFAULT_MODEL,
                input_tokens=usage["input_tokens"] if usage else None,
                output_tokens=usage["output_tokens"] if usage else None)
    trial.current["jev_observation"] = {
        # Opaque IDs, hashes and scalar decisions only. Never retain request text.
        key: result.get(key) for key in ("status", "reason", "baseline_order", "order", "required_ids",
                    "candidate_set_sha256", "request_sha256", "source_revalidated", "resolved_model")
    }
    trial.current["jev_observation"]["measurement_execution"] = "fixture_provider" if fixture_provider else "replay"
    return result
