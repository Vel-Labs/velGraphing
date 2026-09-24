"""Closed, source-bound packet contract for packet-only review."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Literal, Mapping, Sequence

from .instructions import InstructionPlan
from .routing_v4 import SourceReaderV4, SourceSnapshotV4, _require_relative_path
from .selection import RankedContextPlan


SCHEMA_VERSION = "review-packet-v1"
ReviewPacketStatus = Literal["eligible", "stale_snapshot", "source_mismatch"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ADVISORY_POLICY = {"contract_kind": "advisory", "grants_authority": False, "tools_activated": False, "host_interception_claimed": False, "network": "none", "external_effects": []}
_SKILL_FIELDS = {"skill_id", "source", "metadata", "command", "purpose", "applicability", "required_context", "tools", "external_effects", "permission_needs", "expected_output", "validation", "overlaps", "incompatibilities", "invocation"}
_SKILL_EFFECTS = {"none", "host_worker_execution", "local_write_after_explicit_approval", "network_provider_source_excerpts_when_evaluate"}


class ReviewPacketError(ValueError):
    """Raised when a review packet is not closed, canonical, or source-bound."""


def _json(value: object, *, context: bool = False) -> bytes:
    try:
        text = json.dumps(value, allow_nan=False, ensure_ascii=not context, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ReviewPacketError(f"value is not canonical JSON: {error}") from error
    return (text + ("" if context else "\n")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object, label: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ReviewPacketError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ReviewPacketError(f"{label} must be a non-empty string")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise ReviewPacketError(f"{label} contains a control character")
    return value


def _path(value: object, label: str) -> str:
    value = _text(value, label)
    try:
        _require_relative_path(value)
    except ValueError as error:
        raise ReviewPacketError(f"{label} must be a normalized relative POSIX path") from error
    return value


def _ordered(value: object, label: str, *, paths: bool = False) -> tuple[str, ...]:
    if type(value) not in {list, tuple}:
        raise ReviewPacketError(f"{label} must be a list or tuple")
    result = tuple(_path(item, f"{label} item") if paths else _text(item, f"{label} item") for item in value)
    if result != tuple(sorted(result)) or len(result) != len(set(result)):
        raise ReviewPacketError(f"{label} must be sorted and unique")
    return result


def _require_snapshot_membership(paths: Sequence[str], snapshot: SourceSnapshotV4) -> None:
    snapshot_paths = {item.path for item in snapshot.sources}
    if any(path not in snapshot_paths for path in paths):
        raise ReviewPacketError("changed_paths must be present in the source snapshot")


def _keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise ReviewPacketError(f"{label} has an invalid shape")
    return value


def _manifest(value: object) -> tuple[dict[str, Any], str, frozenset[str]]:
    if type(value) is not dict or set(value) != {"schema_version", "skills"} or value["schema_version"] != "retrievel-skill-manifest-v1" or type(value["skills"]) is not list or not value["skills"]:
        raise ReviewPacketError("skill_manifest has an invalid shape")
    ids: list[str] = []
    for index, skill in enumerate(value["skills"]):
        if type(skill) is not dict or set(skill) != _SKILL_FIELDS:
            raise ReviewPacketError(f"skill_manifest.skills[{index}] has an invalid closed shape")
        ids.append(_text(skill["skill_id"], f"skill_manifest.skills[{index}].skill_id"))
        _path(skill["source"], f"skill_manifest.skills[{index}].source")
        for key in ("metadata", "command"):
            if skill[key] is not None:
                _path(skill[key], f"skill_manifest.skills[{index}].{key}")
        _text(skill["purpose"], f"skill_manifest.skills[{index}].purpose")
        for key in ("applicability", "required_context", "tools", "external_effects", "permission_needs", "expected_output", "validation", "overlaps", "incompatibilities"):
            items = skill[key]
            if type(items) is not list or any(type(item) is not str or not item for item in items):
                raise ReviewPacketError(f"skill_manifest.skills[{index}].{key} must be a string list")
        if not set(skill["external_effects"]).issubset(_SKILL_EFFECTS):
            raise ReviewPacketError(f"skill_manifest.skills[{index}].external_effects has an unsupported value")
        invocation = skill.get("invocation")
        if type(invocation) is not dict or set(invocation) != {"recommendation_only", "implicit"} or invocation["recommendation_only"] is not True or invocation["implicit"] is not False:
            raise ReviewPacketError(f"skill_manifest.skills[{index}] is not recommendation-only")
    if len(ids) != len(set(ids)):
        raise ReviewPacketError("skill_manifest skill IDs must be unique")
    normalized = json.loads(_json(value).decode())
    return normalized, _sha(_json(normalized)), frozenset(ids)


def _manifest_input(value: bytes | Mapping[str, Any]) -> tuple[dict[str, Any], str, frozenset[str]]:
    if type(value) is bytes:
        try:
            value = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReviewPacketError(f"skill_manifest bytes are not UTF-8 JSON: {error}") from error
    return _manifest(value)


def _policy(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    policy = _keys(value, {"policy_id", "policy_sha256", "blocking_finding_codes"}, "blocking_policy")
    _text(policy["policy_id"], "blocking_policy.policy_id")
    _digest(policy["policy_sha256"], "blocking_policy.policy_sha256")
    _ordered(policy["blocking_finding_codes"], "blocking_policy.blocking_finding_codes")
    return json.loads(_json(policy).decode())


def _context_plan(value: object, snapshot_sha256: str) -> dict[str, Any]:
    required = {"baseline_fail_closed", "candidate_count", "candidate_set_sha256", "jev_decision", "reason", "route", "schema_version"}
    optional = {"task_facets", "context_fidelity"}
    if type(value) is not dict or not required.issubset(value) or set(value) - required - optional:
        raise ReviewPacketError("context_plan has an invalid shape")
    if value["schema_version"] != "graph-ranked-context-plan-v1" or type(value["baseline_fail_closed"]) is not bool or type(value["candidate_count"]) is not int or value["candidate_count"] < 0:
        raise ReviewPacketError("context_plan has invalid schema fields")
    _digest(value["candidate_set_sha256"], "context_plan.candidate_set_sha256")
    _text(value["route"], "context_plan.route")
    _text(value["reason"], "context_plan.reason")
    jev = _keys(value["jev_decision"], {"baseline_omitted_candidate_count", "baseline_omitted_excerpt_bytes", "baseline_selected_candidate_count", "baseline_selected_excerpt_bytes", "classification_observation_applied", "classification_source", "jev_call_could_affect_selection", "jev_enabled", "jev_observation_applied", "reason", "relationship_candidate_signal", "schema_version"}, "context_plan.jev_decision")
    if jev["schema_version"] != "graph-ranked-context-jev-decision-v1":
        raise ReviewPacketError("unsupported context decision schema")
    for key in ("classification_observation_applied", "jev_call_could_affect_selection", "jev_enabled", "jev_observation_applied", "relationship_candidate_signal"):
        if type(jev[key]) is not bool:
            raise ReviewPacketError(f"context_plan.jev_decision.{key} must be boolean")
    for key in ("baseline_omitted_candidate_count", "baseline_omitted_excerpt_bytes", "baseline_selected_candidate_count", "baseline_selected_excerpt_bytes"):
        if type(jev[key]) is not int or jev[key] < 0:
            raise ReviewPacketError(f"context_plan.jev_decision.{key} must be non-negative")
    _text(jev["classification_source"], "context_plan.jev_decision.classification_source")
    _text(jev["reason"], "context_plan.jev_decision.reason")
    if "task_facets" in value and (type(value["task_facets"]) is not list or any(type(item) is not str or not item for item in value["task_facets"]) or len(value["task_facets"]) != len(set(value["task_facets"]))):
        raise ReviewPacketError("context_plan.task_facets must be unique strings")
    if "context_fidelity" not in value:
        raise ReviewPacketError("context_plan must carry source fidelity")
    fidelity = _keys(value["context_fidelity"], {"schema_version", "query_sha256", "source_snapshot_sha256", "candidate_set_sha256", "byte_budget", "reuse_state", "remaining_byte_budget", "requested_task_facets", "decisions"}, "context_plan.context_fidelity")
    if fidelity["schema_version"] != "graph-ranked-context-fidelity-v1" or fidelity["source_snapshot_sha256"] != snapshot_sha256 or fidelity["candidate_set_sha256"] != value["candidate_set_sha256"]:
        raise ReviewPacketError("context_plan source fidelity does not match snapshot")
    for key in ("query_sha256", "source_snapshot_sha256", "candidate_set_sha256"):
        _digest(fidelity[key], f"context_plan.context_fidelity.{key}")
    for key in ("byte_budget", "remaining_byte_budget"):
        if type(fidelity[key]) is not int or fidelity[key] < 0:
            raise ReviewPacketError(f"context_plan.context_fidelity.{key} must be non-negative")
    if fidelity["reuse_state"] not in {"rebuild", "refresh", "reuse", "widen"} or type(fidelity["requested_task_facets"]) is not list:
        raise ReviewPacketError("context_plan fidelity has invalid reuse or facet data")
    if "task_facets" in value and fidelity["requested_task_facets"] != value["task_facets"]:
        raise ReviewPacketError("context_plan task facets are not bound")
    if type(fidelity["decisions"]) is not list or len(fidelity["decisions"]) != value["candidate_count"]:
        raise ReviewPacketError("context_plan candidate decisions are incomplete")
    seen: set[str] = set()
    for index, raw in enumerate(fidelity["decisions"]):
        item = _keys(raw, {"candidate_id", "included", "mode", "reason", "source_path", "source_sha256", "byte_start", "byte_end", "source_unit_complete"}, f"context decision {index}")
        identifier = _text(item["candidate_id"], "context decision candidate_id")
        if identifier in seen or type(item["included"]) is not bool or type(item["source_unit_complete"]) is not bool:
            raise ReviewPacketError("context decision IDs must be unique")
        seen.add(identifier)
        _text(item["mode"], "context decision mode")
        _text(item["reason"], "context decision reason")
        _path(item["source_path"], "context decision source_path")
        _digest(item["source_sha256"], "context decision source_sha256")
        if type(item["byte_start"]) is not int or type(item["byte_end"]) is not int or item["byte_start"] < 0 or item["byte_end"] <= item["byte_start"]:
            raise ReviewPacketError("context decision byte range is invalid")
    return json.loads(_json(value, context=True).decode())


def _selected_context(value: object, selected_ids: tuple[str, ...], context_plan: dict[str, Any], snapshot: SourceSnapshotV4) -> None:
    if type(value) is not list or tuple(item.get("candidate_id") for item in value if type(item) is dict) != selected_ids:
        raise ReviewPacketError("selected_context does not match selected_candidate_ids")
    decisions = {item["candidate_id"]: item for item in context_plan["context_fidelity"]["decisions"]}
    sources = {item.path: item for item in snapshot.sources}
    for index, raw in enumerate(value):
        item = _keys(raw, {"candidate_id", "record_id", "source_path", "source_sha256", "byte_start", "byte_end", "excerpt_sha256", "required"}, f"selected_context {index}")
        decision = decisions.get(_text(item["candidate_id"], "selected_context.candidate_id"))
        if decision is None or not decision["included"]:
            raise ReviewPacketError("selected context is not included by the context plan")
        _text(item["record_id"], "selected_context.record_id")
        _path(item["source_path"], "selected_context.source_path")
        _digest(item["source_sha256"], "selected_context.source_sha256")
        _digest(item["excerpt_sha256"], "selected_context.excerpt_sha256")
        if type(item["byte_start"]) is not int or type(item["byte_end"]) is not int or item["byte_start"] < 0 or item["byte_end"] <= item["byte_start"] or type(item["required"]) is not bool:
            raise ReviewPacketError("selected context has invalid coordinates")
        source = sources.get(item["source_path"])
        if source is None or item["source_sha256"] != source.sha256 or any(item[key] != decision[key] for key in ("source_path", "source_sha256", "byte_start", "byte_end")):
            raise ReviewPacketError("selected context is not bound to source and plan identities")


def _validate(value: object) -> bytes:
    expected = {"schema_version", "mode", "task_id", "task_summary", "review_question", "changed_paths", "source_snapshot", "source_snapshot_sha256", "context_plan", "context_plan_sha256", "selected_candidate_ids", "selected_context", "instruction_plan", "instruction_plan_sha256", "skill_manifest", "skill_manifest_sha256", "applicable_skill_ids", "known_risks", "blocking_policy", "advisory_policy"}
    packet = _keys(value, expected, "review packet")
    if packet["schema_version"] != SCHEMA_VERSION or packet["mode"] != "packet_only":
        raise ReviewPacketError("unsupported review packet schema or mode")
    for key in ("task_id", "task_summary", "review_question"):
        _text(packet[key], key)
    changed = _ordered(packet["changed_paths"], "changed_paths", paths=True)
    if list(changed) != packet["changed_paths"]:
        raise ReviewPacketError("changed_paths must be canonical")
    snapshot = SourceSnapshotV4.from_dict(packet["source_snapshot"])
    _require_snapshot_membership(changed, snapshot)
    _digest(packet["source_snapshot_sha256"], "source_snapshot_sha256")
    if packet["source_snapshot_sha256"] != snapshot.snapshot_sha256:
        raise ReviewPacketError("source snapshot identity is not bound")
    context = _context_plan(packet["context_plan"], snapshot.snapshot_sha256)
    _digest(packet["context_plan_sha256"], "context_plan_sha256")
    if packet["context_plan_sha256"] != _sha(_json(context, context=True)):
        raise ReviewPacketError("context_plan_sha256 does not match context_plan")
    if type(packet["selected_candidate_ids"]) is not list:
        raise ReviewPacketError("selected_candidate_ids must be a list")
    selected_ids = tuple(_text(item, "selected_candidate_ids item") for item in packet["selected_candidate_ids"])
    if len(selected_ids) != len(set(selected_ids)):
        raise ReviewPacketError("selected_candidate_ids must be unique")
    included_ids = tuple(item["candidate_id"] for item in context["context_fidelity"]["decisions"] if item["included"])
    if selected_ids != included_ids:
        raise ReviewPacketError("selected_candidate_ids must equal included context decisions")
    _selected_context(packet["selected_context"], selected_ids, context, snapshot)
    instruction = InstructionPlan.from_dict(packet["instruction_plan"])
    _digest(packet["instruction_plan_sha256"], "instruction_plan_sha256")
    if packet["instruction_plan_sha256"] != _sha(instruction.to_json().encode()):
        raise ReviewPacketError("instruction_plan_sha256 does not match instruction_plan")
    _, manifest_sha256, skill_ids = _manifest(packet["skill_manifest"])
    _digest(packet["skill_manifest_sha256"], "skill_manifest_sha256")
    if packet["skill_manifest_sha256"] != manifest_sha256:
        raise ReviewPacketError("skill_manifest_sha256 does not match skill_manifest")
    applicable = _ordered(packet["applicable_skill_ids"], "applicable_skill_ids")
    if not set(applicable).issubset(skill_ids):
        raise ReviewPacketError("applicable skill ID is not in skill_manifest")
    _ordered(packet["known_risks"], "known_risks")
    _policy(packet["blocking_policy"])
    if _keys(packet["advisory_policy"], set(_ADVISORY_POLICY), "advisory_policy") != _ADVISORY_POLICY:
        raise ReviewPacketError("review policy must remain advisory")
    return _json(packet)


def _read_selected(packet: "ReviewPacket", snapshot: SourceSnapshotV4, reader: SourceReaderV4) -> None:
    _require_reader(reader)
    identities = {item.path: item for item in snapshot.sources}
    for item in packet.to_dict()["selected_context"]:
        source = identities.get(item["source_path"])
        if source is None or source.sha256 != item["source_sha256"] or reader.is_symlink(item["source_path"]):
            raise ReviewPacketError("selected context source identity is not current")
        raw = reader.read_bytes(item["source_path"])
        if type(raw) is not bytes or len(raw) != source.byte_length or _sha(raw) != source.sha256 or item["byte_end"] > len(raw) or _sha(raw[item["byte_start"]:item["byte_end"]]) != item["excerpt_sha256"]:
            raise ReviewPacketError("selected context bytes do not match")


def _require_reader(reader: object) -> SourceReaderV4:
    if not callable(getattr(reader, "read_bytes", None)) or not callable(getattr(reader, "is_symlink", None)):
        raise ReviewPacketError("reader does not implement the read-only V4 protocol")
    return reader  # type: ignore[return-value]


@dataclass(frozen=True)
class ReviewPacket:
    """Canonical review packet whose hash excludes no envelope field."""

    _canonical: bytes

    @classmethod
    def from_dict(cls, value: object) -> "ReviewPacket":
        return cls(_validate(value))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._canonical.decode())

    @property
    def packet_sha256(self) -> str:
        return _sha(self._canonical)


def prepare_review_packet(task_id: str, task_summary: str, review_question: str, changed_paths: Sequence[str], snapshot: SourceSnapshotV4, reader: SourceReaderV4, context_plan: RankedContextPlan, instruction_plan: InstructionPlan, skill_manifest: bytes | Mapping[str, Any], applicable_skill_ids: Sequence[str], known_risks: Sequence[str], blocking_policy: Mapping[str, Any] | None = None) -> ReviewPacket:
    """Prepare a packet from accepted caller-owned plans and exact source bytes."""
    if type(snapshot) is not SourceSnapshotV4 or type(context_plan) is not RankedContextPlan or type(instruction_plan) is not InstructionPlan:
        raise TypeError("snapshot, context_plan, and instruction_plan must use exact existing contract types")
    changed = _ordered(changed_paths, "changed_paths", paths=True)
    _require_snapshot_membership(changed, snapshot)
    applicable = _ordered(applicable_skill_ids, "applicable_skill_ids")
    risks = _ordered(known_risks, "known_risks")
    manifest, manifest_sha256, skill_ids = _manifest_input(skill_manifest)
    if not set(applicable).issubset(skill_ids):
        raise ReviewPacketError("applicable skill ID is not in skill_manifest")
    _require_reader(reader)
    policy = _policy(blocking_policy)
    selected_ids = tuple(context_plan.baseline.projection.selected_candidate_ids)
    candidates = {candidate.candidate_id: candidate for candidate in context_plan.candidates}
    if len(candidates) != len(context_plan.candidates) or any(identifier not in candidates for identifier in selected_ids):
        raise ReviewPacketError("context plan selected IDs are not bound to candidates")
    context = context_plan.to_dict()
    if context.get("context_fidelity", {}).get("source_snapshot_sha256") != snapshot.snapshot_sha256:
        raise ReviewPacketError("context plan source snapshot does not match packet snapshot")
    identities = {item.path: item for item in snapshot.sources}
    selected: list[dict[str, Any]] = []
    for identifier in selected_ids:
        candidate = candidates[identifier]
        source = identities.get(candidate.source_path)
        if source is None or source.sha256 != candidate.source_sha256 or reader.is_symlink(candidate.source_path):
            raise ReviewPacketError("selected candidate source identity is not current")
        raw = reader.read_bytes(candidate.source_path)
        if type(raw) is not bytes or len(raw) != source.byte_length or _sha(raw) != source.sha256 or candidate.byte_end > len(raw):
            raise ReviewPacketError("selected candidate bytes do not match snapshot")
        selected.append({"candidate_id": candidate.candidate_id, "record_id": candidate.record_id, "source_path": candidate.source_path, "source_sha256": candidate.source_sha256, "byte_start": candidate.byte_start, "byte_end": candidate.byte_end, "excerpt_sha256": _sha(raw[candidate.byte_start:candidate.byte_end]), "required": candidate.required})
    return ReviewPacket.from_dict({"schema_version": SCHEMA_VERSION, "mode": "packet_only", "task_id": _text(task_id, "task_id"), "task_summary": _text(task_summary, "task_summary"), "review_question": _text(review_question, "review_question"), "changed_paths": list(changed), "source_snapshot": snapshot.to_dict(), "source_snapshot_sha256": snapshot.snapshot_sha256, "context_plan": context, "context_plan_sha256": _sha(_json(context, context=True)), "selected_candidate_ids": list(selected_ids), "selected_context": selected, "instruction_plan": instruction_plan.to_dict(), "instruction_plan_sha256": _sha(instruction_plan.to_json().encode()), "skill_manifest": manifest, "skill_manifest_sha256": manifest_sha256, "applicable_skill_ids": list(applicable), "known_risks": list(risks), "blocking_policy": policy, "advisory_policy": dict(_ADVISORY_POLICY)})


def check_review_packet(packet: ReviewPacket, current_snapshot: SourceSnapshotV4, reader: SourceReaderV4) -> ReviewPacketStatus:
    """Return closed eligibility status without discovery, fallback, or invalidation."""
    if type(packet) is not ReviewPacket or type(current_snapshot) is not SourceSnapshotV4:
        raise TypeError("packet and current_snapshot must use exact contract types")
    if current_snapshot.snapshot_sha256 != packet.to_dict()["source_snapshot_sha256"]:
        return "stale_snapshot"
    _require_reader(reader)
    try:
        _read_selected(packet, current_snapshot, reader)
    except (ReviewPacketError, OSError, TypeError, ValueError, KeyError):
        return "source_mismatch"
    return "eligible"
