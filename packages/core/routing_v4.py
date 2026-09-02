"""Deterministic advisory routing over caller-supplied policy and source bytes.

This module verifies consistency only. Its recommendation is planning
metadata. It does not prove ownership, intent, admission, trust, freshness,
host containment, or task authority. It cannot activate a skill or authorize
a write.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Protocol

from .routing import (
    GRAPH_ENGINEERING_OPERATIONS,
    GRAPH_STEWARD_OPERATIONS,
    RouteFact,
    RouteOperation,
    RouteScope,
)

_SHA256_LENGTH = 64
_FROZEN_WHITE_SPACE_V4 = frozenset(
    {
        *range(0x0009, 0x000E),
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    }
)
_FORBIDDEN_PAYLOAD_KEYS = frozenset({
    "scope", "operation", "route", "recommendation", "fact", "trust",
    "freshness", "sensitivity", "admission", "eligible", "agent_generated",
    "verifier_promoted", "authority", "permission", "activate", "write_authority",
})


class AssertionKindV4(str, Enum):
    SCOPE = "scope"
    OPERATION = "operation"
    STRUCTURAL_FACT = "structural_fact"


class AssertionStatusV4(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    INELIGIBLE = "ineligible"


class RecommendationTargetV4(str, Enum):
    GRAPH_ENGINEERING = "graph_engineering"
    GRAPH_STEWARD = "graph_steward"
    NO_SKILL = "no_skill"
    DEFER = "defer"


class RecommendationReasonV4(str, Enum):
    PROJECT_STRUCTURAL_ROUTE = "project_structural_route"
    PROJECT_ASSESSMENT_ROUTE = "project_assessment_route"
    FEDERATION_ROUTE = "federation_route"
    DIRECT_BASELINE_ROUTE = "direct_baseline_route"
    NON_CURRENT_ASSERTION = "non_current_assertion"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    INCOMPLETE_EVIDENCE = "incomplete_evidence"


_ROUTES = frozenset(item.value for item in RecommendationTargetV4)
_REASONS = frozenset(item.value for item in RecommendationReasonV4)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_digest(value: object, label: str) -> None:
    if type(value) is not str or len(value) != _SHA256_LENGTH or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a full lowercase SHA-256")


def _require_portable_text_v4(value: object, label: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be PortableTextV4")
    has_non_whitespace = False
    for character in value:
        code_point = ord(character)
        if (
            code_point <= 0x001F
            or 0x007F <= code_point <= 0x009F
            or 0xD800 <= code_point <= 0xDFFF
        ):
            raise ValueError(f"{label} must be PortableTextV4")
        if code_point not in _FROZEN_WHITE_SPACE_V4:
            has_non_whitespace = True
    if not has_non_whitespace:
        raise ValueError(f"{label} must contain a non-White_Space code point")


def _require_relative_path(value: object) -> None:
    if type(value) is not str or not value or "\\" in value:
        raise ValueError("source path must be PortablePathV4")
    segments = value.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise ValueError("source path must be PortablePathV4")
    for segment in segments:
        _require_portable_text_v4(segment, "source path segment")


def _require_exact_keys(payload: Mapping[str, Any], keys: frozenset[str], label: str) -> None:
    if frozenset(payload) != keys:
        raise ValueError(f"{label} fields must match the closed contract")


@dataclass(frozen=True)
class SourceIdentityV4:
    path: str
    byte_length: int
    sha256: str

    def __post_init__(self) -> None:
        _require_relative_path(self.path)
        if type(self.byte_length) is not int or self.byte_length < 0:
            raise ValueError("byte_length must be a non-negative integer")
        _require_digest(self.sha256, "source sha256")

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "byte_length": self.byte_length, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SourceIdentityV4:
        _require_exact_keys(payload, frozenset({"path", "byte_length", "sha256"}), "source")
        return cls(payload["path"], payload["byte_length"], payload["sha256"])


@dataclass(frozen=True)
class SourceSnapshotV4:
    sources: tuple[SourceIdentityV4, ...]

    def __post_init__(self) -> None:
        if type(self.sources) is not tuple or not self.sources:
            raise ValueError("snapshot sources must be a non-empty tuple")
        if any(type(item) is not SourceIdentityV4 for item in self.sources):
            raise TypeError("snapshot sources must contain SourceIdentityV4 values")
        paths = tuple(item.path for item in self.sources)
        identities = tuple(item.sha256 for item in self.sources)
        if paths != tuple(sorted(paths)):
            raise ValueError("snapshot sources must use canonical path order")
        if len(paths) != len(set(paths)):
            raise ValueError("snapshot source paths must be unique")
        if len(identities) != len(set(identities)):
            raise ValueError("snapshot source identities must be unique")

    @property
    def snapshot_sha256(self) -> str:
        return _digest_bytes(_canonical_bytes({"sources": [item.to_dict() for item in self.sources]}))

    def to_dict(self) -> dict[str, object]:
        return {"snapshot_sha256": self.snapshot_sha256, "sources": [item.to_dict() for item in self.sources]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SourceSnapshotV4:
        _require_exact_keys(payload, frozenset({"snapshot_sha256", "sources"}), "snapshot")
        if type(payload["sources"]) is not list:
            raise TypeError("snapshot sources must be a list")
        snapshot = cls(tuple(SourceIdentityV4.from_dict(item) for item in payload["sources"]))
        if payload["snapshot_sha256"] != snapshot.snapshot_sha256:
            raise ValueError("snapshot_sha256 does not match snapshot contents")
        return snapshot


@dataclass(frozen=True)
class PolicyAssertionV4:
    assertion_id: str
    source_path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    excerpt_sha256: str
    kind: AssertionKindV4
    value: str
    status: AssertionStatusV4

    def __post_init__(self) -> None:
        _require_portable_text_v4(self.assertion_id, "assertion_id")
        _require_relative_path(self.source_path)
        _require_digest(self.source_sha256, "assertion source sha256")
        _require_digest(self.excerpt_sha256, "excerpt sha256")
        if type(self.byte_start) is not int or type(self.byte_end) is not int:
            raise ValueError("byte range must use exact integers")
        if self.byte_start < 0 or self.byte_end <= self.byte_start:
            raise ValueError("byte range must be non-empty and ordered")
        if type(self.kind) is not AssertionKindV4:
            raise TypeError("kind must be an AssertionKindV4")
        if type(self.status) is not AssertionStatusV4:
            raise TypeError("status must be an AssertionStatusV4")
        if type(self.value) is not str:
            raise TypeError("assertion value must be a string")
        if self.kind is AssertionKindV4.SCOPE:
            RouteScope(self.value)
        elif self.kind is AssertionKindV4.OPERATION:
            RouteOperation(self.value)
        else:
            RouteFact(self.value)

    def to_dict(self) -> dict[str, object]:
        return {
            "assertion_id": self.assertion_id, "source_path": self.source_path,
            "source_sha256": self.source_sha256, "byte_start": self.byte_start,
            "byte_end": self.byte_end, "excerpt_sha256": self.excerpt_sha256,
            "kind": self.kind.value, "value": self.value, "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PolicyAssertionV4:
        keys = frozenset({"assertion_id", "source_path", "source_sha256", "byte_start", "byte_end", "excerpt_sha256", "kind", "value", "status"})
        _require_exact_keys(payload, keys, "assertion")
        return cls(
            payload["assertion_id"], payload["source_path"], payload["source_sha256"],
            payload["byte_start"], payload["byte_end"], payload["excerpt_sha256"],
            AssertionKindV4(payload["kind"]), payload["value"], AssertionStatusV4(payload["status"]),
        )


@dataclass(frozen=True)
class RoutingPolicyV4:
    policy_id: str
    source_set_sha256: str
    assertions: tuple[PolicyAssertionV4, ...]

    def __post_init__(self) -> None:
        _require_portable_text_v4(self.policy_id, "policy_id")
        _require_digest(self.source_set_sha256, "source_set_sha256")
        if type(self.assertions) is not tuple or not self.assertions:
            raise ValueError("policy assertions must be a non-empty tuple")
        if any(type(item) is not PolicyAssertionV4 for item in self.assertions):
            raise TypeError("policy assertions must contain PolicyAssertionV4 values")
        assertion_ids = tuple(item.assertion_id for item in self.assertions)
        if assertion_ids != tuple(sorted(assertion_ids)):
            raise ValueError("policy assertions must use canonical assertion ID order")
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("policy assertion IDs must be unique")

    def _identity_dict(self) -> dict[str, object]:
        return {"policy_id": self.policy_id, "source_set_sha256": self.source_set_sha256, "assertions": [item.to_dict() for item in self.assertions]}

    @property
    def policy_sha256(self) -> str:
        return _digest_bytes(_canonical_bytes(self._identity_dict()))

    def to_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "policy_sha256": self.policy_sha256}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RoutingPolicyV4:
        _require_exact_keys(payload, frozenset({"policy_id", "source_set_sha256", "assertions", "policy_sha256"}), "policy")
        if type(payload["assertions"]) is not list:
            raise TypeError("policy assertions must be a list")
        policy = cls(payload["policy_id"], payload["source_set_sha256"], tuple(PolicyAssertionV4.from_dict(item) for item in payload["assertions"]))
        if payload["policy_sha256"] != policy.policy_sha256:
            raise ValueError("policy_sha256 does not match policy contents")
        return policy


@dataclass(frozen=True)
class RoutingRecommendationV4:
    recommendation: str
    scope: str | None
    operation: str | None
    used_assertion_ids: tuple[str, ...]
    rejected_assertion_ids: tuple[str, ...]
    policy_sha256: str
    snapshot_sha256: str
    reason: str
    contract_kind: str = "advisory"
    grants_authority: bool = False
    may_activate_skill: bool = False
    write_authority: str = "none"
    requires_separate_host_task_authority: bool = True

    def __post_init__(self) -> None:
        if self.recommendation not in _ROUTES:
            raise ValueError("recommendation is not supported")
        if self.scope is not None:
            RouteScope(self.scope)
        if self.operation is not None:
            RouteOperation(self.operation)
        for label, values in (("used", self.used_assertion_ids), ("rejected", self.rejected_assertion_ids)):
            if type(values) is not tuple:
                raise ValueError(f"{label} assertion IDs must be a tuple")
            for item in values:
                _require_portable_text_v4(item, f"{label} assertion ID")
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"{label} assertion IDs must be unique and sorted")
        if set(self.used_assertion_ids) & set(self.rejected_assertion_ids):
            raise ValueError("used and rejected assertion IDs must be disjoint")
        _require_digest(self.policy_sha256, "policy_sha256")
        _require_digest(self.snapshot_sha256, "snapshot_sha256")
        if self.reason not in _REASONS:
            raise ValueError("reason is not supported")
        expected_reasons = {
            "graph_engineering": {"project_structural_route", "project_assessment_route"},
            "graph_steward": {"federation_route"},
            "no_skill": {"direct_baseline_route"},
            "defer": {"non_current_assertion", "conflicting_evidence", "incomplete_evidence"},
        }
        if self.reason not in expected_reasons[self.recommendation]:
            raise ValueError("recommendation and reason must agree")
        if self.recommendation == "graph_engineering":
            if self.scope != RouteScope.PROJECT.value:
                raise ValueError("graph_engineering requires project scope")
            if self.operation not in {item.value for item in GRAPH_ENGINEERING_OPERATIONS}:
                raise ValueError("graph_engineering requires a Graph Engineering operation")
            if self.reason == "project_assessment_route" and self.operation != RouteOperation.ASSESS.value:
                raise ValueError("project_assessment_route requires assess")
        elif self.recommendation == "graph_steward":
            if self.scope != RouteScope.FEDERATION.value:
                raise ValueError("graph_steward requires federation scope")
            if self.operation not in {item.value for item in GRAPH_STEWARD_OPERATIONS}:
                raise ValueError("graph_steward requires a Graph Steward operation")
        elif self.recommendation == "no_skill" and self.scope != RouteScope.PROJECT.value:
            raise ValueError("no_skill requires project scope")
        if self.recommendation != "defer" and (
            self.scope is None or self.operation is None or self.rejected_assertion_ids
        ):
            raise ValueError("a non-defer recommendation requires complete current advisory inputs")
        if self.reason == "non_current_assertion" and not self.rejected_assertion_ids:
            raise ValueError("non_current_assertion requires rejected assertion IDs")
        if self.rejected_assertion_ids and self.reason != "non_current_assertion":
            raise ValueError("rejected assertion IDs require non_current_assertion")
        if self.contract_kind != "advisory":
            raise ValueError("contract_kind must be advisory")
        if type(self.grants_authority) is not bool or self.grants_authority:
            raise ValueError("grants_authority must be the exact boolean false")
        if type(self.may_activate_skill) is not bool or self.may_activate_skill:
            raise ValueError("may_activate_skill must be the exact boolean false")
        if self.write_authority != "none":
            raise ValueError("write_authority must be none")
        if type(self.requires_separate_host_task_authority) is not bool or not self.requires_separate_host_task_authority:
            raise ValueError("requires_separate_host_task_authority must be the exact boolean true")

    def to_dict(self) -> dict[str, object]:
        return {
            "recommendation": self.recommendation, "scope": self.scope,
            "operation": self.operation, "used_assertion_ids": list(self.used_assertion_ids),
            "rejected_assertion_ids": list(self.rejected_assertion_ids),
            "policy_sha256": self.policy_sha256, "snapshot_sha256": self.snapshot_sha256,
            "reason": self.reason, "contract_kind": self.contract_kind,
            "grants_authority": self.grants_authority,
            "may_activate_skill": self.may_activate_skill,
            "write_authority": self.write_authority,
            "requires_separate_host_task_authority": self.requires_separate_host_task_authority,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RoutingRecommendationV4:
        keys = frozenset({"recommendation", "scope", "operation", "used_assertion_ids", "rejected_assertion_ids", "policy_sha256", "snapshot_sha256", "reason", "contract_kind", "grants_authority", "may_activate_skill", "write_authority", "requires_separate_host_task_authority"})
        _require_exact_keys(payload, keys, "recommendation")
        if type(payload["used_assertion_ids"]) is not list or type(payload["rejected_assertion_ids"]) is not list:
            raise TypeError("serialized assertion IDs must be lists")
        return cls(
            payload["recommendation"], payload["scope"], payload["operation"],
            tuple(payload["used_assertion_ids"]), tuple(payload["rejected_assertion_ids"]),
            payload["policy_sha256"], payload["snapshot_sha256"], payload["reason"],
            payload["contract_kind"], payload["grants_authority"], payload["may_activate_skill"],
            payload["write_authority"], payload["requires_separate_host_task_authority"],
        )


class SourceReaderV4(Protocol):
    def read_bytes(self, project_relative_path: str) -> bytes: ...
    def is_symlink(self, project_relative_path: str) -> bool: ...


@dataclass(frozen=True)
class _VerifiedRecommendationInputV4:
    scope: RouteScope | None
    operation: RouteOperation | None
    facts: frozenset[RouteFact]
    used_assertion_ids: tuple[str, ...]
    rejected_assertion_ids: tuple[str, ...]


def _source_set_sha256(snapshot: SourceSnapshotV4) -> str:
    return _digest_bytes(_canonical_bytes({"source_identities": [item.sha256 for item in snapshot.sources]}))


def _read_verified_source_bytes(
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
) -> dict[str, bytes]:
    if type(snapshot) is not SourceSnapshotV4:
        raise TypeError("snapshot must be an exact SourceSnapshotV4")
    if not callable(getattr(reader, "read_bytes", None)) or not callable(getattr(reader, "is_symlink", None)):
        raise TypeError("reader must implement the read-only V4 reader protocol")
    source_bytes: dict[str, bytes] = {}
    for source in snapshot.sources:
        if reader.is_symlink(source.path):
            raise ValueError("source paths must not be symlinks")
        raw = reader.read_bytes(source.path)
        if type(raw) is not bytes:
            raise TypeError("reader must return exact bytes")
        if len(raw) != source.byte_length or _digest_bytes(raw) != source.sha256:
            raise ValueError("source bytes do not match snapshot identity")
        source_bytes[source.path] = raw
    return source_bytes


def _verify(policy: RoutingPolicyV4, snapshot: SourceSnapshotV4, reader: SourceReaderV4) -> _VerifiedRecommendationInputV4:
    if type(policy) is not RoutingPolicyV4:
        raise TypeError("V4 requires an exact RoutingPolicyV4 input")
    if type(snapshot) is not SourceSnapshotV4:
        raise TypeError("V4 requires an exact SourceSnapshotV4 input")
    if policy.source_set_sha256 != _source_set_sha256(snapshot):
        raise ValueError("policy source set does not match snapshot")
    source_bytes = _read_verified_source_bytes(snapshot, reader)
    sources = {item.path: item for item in snapshot.sources}
    scopes: list[tuple[str, RouteScope]] = []
    operations: list[tuple[str, RouteOperation]] = []
    facts: list[tuple[str, RouteFact]] = []
    rejected: list[str] = []
    for assertion in policy.assertions:
        source = sources.get(assertion.source_path)
        if source is None or assertion.source_sha256 != source.sha256:
            raise ValueError("assertion source identity does not match snapshot")
        raw = source_bytes[assertion.source_path]
        if assertion.byte_end > len(raw):
            raise ValueError("assertion byte range exceeds source")
        if _digest_bytes(raw[assertion.byte_start:assertion.byte_end]) != assertion.excerpt_sha256:
            raise ValueError("assertion excerpt does not match source bytes")
        if assertion.status is not AssertionStatusV4.CURRENT:
            rejected.append(assertion.assertion_id)
            continue
        if assertion.kind is AssertionKindV4.SCOPE:
            scopes.append((assertion.assertion_id, RouteScope(assertion.value)))
        elif assertion.kind is AssertionKindV4.OPERATION:
            operations.append((assertion.assertion_id, RouteOperation(assertion.value)))
        else:
            facts.append((assertion.assertion_id, RouteFact(assertion.value)))
    scope = scopes[0][1] if len(scopes) == 1 else None
    operation = operations[0][1] if len(operations) == 1 else None
    used = sorted(identifier for identifier, _ in (*scopes, *operations, *facts))
    return _VerifiedRecommendationInputV4(scope, operation, frozenset(item for _, item in facts), tuple(used), tuple(sorted(rejected)))


def recommend_route_v4(policy: RoutingPolicyV4, snapshot: SourceSnapshotV4, reader: SourceReaderV4) -> RoutingRecommendationV4:
    """Verify supplied bytes and return advisory planning metadata only."""
    verified = _verify(policy, snapshot, reader)
    scope, operation, facts = verified.scope, verified.operation, verified.facts
    recommendation, reason = "defer", "incomplete_evidence"
    if verified.rejected_assertion_ids:
        reason = "non_current_assertion"
    elif scope is None or operation is None:
        reason = "incomplete_evidence"
    elif RouteFact.STRUCTURAL_NEED in facts and RouteFact.DIRECT_BASELINE_SUFFICIENT in facts:
        reason = "conflicting_evidence"
    elif RouteFact.PROJECT_SCOPE in facts and RouteFact.FEDERATION_SCOPE in facts:
        reason = "conflicting_evidence"
    elif scope is RouteScope.PROJECT and RouteFact.FEDERATION_SCOPE in facts:
        reason = "conflicting_evidence"
    elif scope is RouteScope.FEDERATION and RouteFact.PROJECT_SCOPE in facts:
        reason = "conflicting_evidence"
    elif scope is RouteScope.PROJECT and operation in GRAPH_ENGINEERING_OPERATIONS and RouteFact.STRUCTURAL_NEED in facts:
        recommendation, reason = "graph_engineering", "project_structural_route"
    elif scope is RouteScope.PROJECT and operation is RouteOperation.ASSESS and RouteFact.GRAPH_WORTHY in facts:
        recommendation, reason = "graph_engineering", "project_assessment_route"
    elif scope is RouteScope.FEDERATION and operation in GRAPH_STEWARD_OPERATIONS and RouteFact.REGISTRY_REFERENCE in facts and RouteFact.CROSS_PROJECT_ACTION in facts:
        recommendation, reason = "graph_steward", "federation_route"
    elif scope is RouteScope.PROJECT and RouteFact.DIRECT_BASELINE_SUFFICIENT in facts and not ({RouteFact.STRUCTURAL_NEED, RouteFact.GRAPH_WORTHY, RouteFact.FEDERATION_SCOPE, RouteFact.REGISTRY_REFERENCE, RouteFact.CROSS_PROJECT_ACTION} & facts):
        recommendation, reason = "no_skill", "direct_baseline_route"
    return RoutingRecommendationV4(
        recommendation, scope.value if scope else None, operation.value if operation else None,
        verified.used_assertion_ids, verified.rejected_assertion_ids,
        policy.policy_sha256, snapshot.snapshot_sha256, reason,
    )


def reject_untrusted_routing_payload_v4(payload: object) -> None:
    """Reject consequential keys, cycles, callables, and unsupported containers."""
    active: set[int] = set()

    def inspect(value: object) -> None:
        if isinstance(value, (Mapping, list, tuple)):
            identity = id(value)
            if identity in active:
                raise ValueError("routing payload must not contain a cycle")
            active.add(identity)
            try:
                if isinstance(value, Mapping):
                    for key, nested in value.items():
                        if type(key) is not str:
                            raise TypeError("routing payload keys must be strings")
                        if key in _FORBIDDEN_PAYLOAD_KEYS:
                            raise ValueError(f"routing payload field is forbidden: {key}")
                        inspect(nested)
                else:
                    for nested in value:
                        inspect(nested)
            finally:
                active.remove(identity)
            return
        if value is None or type(value) in (str, bool, int, float):
            return
        raise TypeError("routing payload contains an unsupported value or container")

    inspect(payload)


__all__ = [
    "AssertionKindV4", "AssertionStatusV4", "PolicyAssertionV4", "RoutingPolicyV4",
    "RecommendationReasonV4", "RecommendationTargetV4", "RoutingRecommendationV4",
    "SourceIdentityV4", "SourceReaderV4", "SourceSnapshotV4",
    "recommend_route_v4", "reject_untrusted_routing_payload_v4",
]
