"""Convert serialized compiler candidates into ineligible graph candidates.

This module is a pure boundary adapter. It does not inspect compiler storage or
call compiler services. Human review remains evidence and never grants graph
eligibility.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any


COMPILER_SCHEMA = "CompilerCandidateRecordV1"
GRAPH_SCHEMA = "GraphCandidateV1"
REJECTION_SCHEMA = "GraphCandidateRejectionV1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = (
    "schema_version",
    "record_id",
    "source",
    "draft_status",
    "confidence",
    "agent_generated",
    "human_reviewed",
    "provenance",
    "candidate_type",
    "candidate_payload",
)


def _rejection(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    rejection: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        rejection["field"] = field
    return {
        "schema_version": REJECTION_SCHEMA,
        "accepted": False,
        "rejection": rejection,
    }


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return _rejection("invalid_record", "The serialized value must be a JSON object.")

    for field in _TOP_LEVEL_FIELDS:
        if field not in record:
            return _rejection("missing_field", f"Required field is absent: {field}.", field)

    if record["schema_version"] != COMPILER_SCHEMA:
        return _rejection(
            "unsupported_schema",
            f"schema_version must be {COMPILER_SCHEMA}.",
            "schema_version",
        )

    for field in ("record_id", "draft_status", "candidate_type"):
        if not _non_empty_string(record[field]):
            return _rejection("invalid_field", f"{field} must be a non-empty string.", field)

    source = record["source"]
    if not isinstance(source, dict):
        return _rejection("invalid_field", "source must be an object.", "source")
    for field in ("path", "sha256", "locator"):
        if field not in source:
            return _rejection(
                "missing_field", f"Required field is absent: source.{field}.", f"source.{field}"
            )
    if not _non_empty_string(source["path"]):
        return _rejection("invalid_field", "source.path must be a non-empty string.", "source.path")
    if not isinstance(source["sha256"], str) or not _SHA256.fullmatch(source["sha256"]):
        return _rejection(
            "invalid_digest",
            "source.sha256 must be a lowercase SHA-256 hexadecimal digest.",
            "source.sha256",
        )
    if not _non_empty_string(source["locator"]):
        return _rejection(
            "invalid_locator", "source.locator must be a non-empty string.", "source.locator"
        )

    confidence = record["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return _rejection("invalid_field", "confidence must be a number from 0 to 1.", "confidence")
    if not 0 <= confidence <= 1:
        return _rejection("invalid_field", "confidence must be a number from 0 to 1.", "confidence")

    for field in ("agent_generated", "human_reviewed"):
        if not isinstance(record[field], bool):
            return _rejection("invalid_field", f"{field} must be a boolean.", field)

    return None


def adapt_serialized_candidate(serialized: str | bytes | bytearray) -> dict[str, Any]:
    """Return a GraphCandidateV1 envelope or a typed rejection.

    The accepted envelope contains a deep copy of the complete compiler record.
    Eligibility is always false, including when ``human_reviewed`` is true.
    """

    if not isinstance(serialized, (str, bytes, bytearray)):
        return _rejection("invalid_serialization", "Input must be serialized JSON text or bytes.")

    try:
        record = json.loads(serialized)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _rejection("invalid_json", f"Input is not valid JSON: {exc.msg}.")

    rejected = _validate(record)
    if rejected is not None:
        return rejected

    return {
        "schema_version": GRAPH_SCHEMA,
        "accepted": True,
        "eligibility": False,
        "eligibility_basis": "candidate_requires_separate_policy_or_verifier_admission",
        "compiler_candidate": copy.deepcopy(record),
    }
