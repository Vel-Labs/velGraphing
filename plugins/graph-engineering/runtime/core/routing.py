"""Deterministic authenticated structural routing for portable graph skills."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .models import Admission, Freshness, Provenance, Sensitivity, TrustClass


class RouteScope(str, Enum):
    PROJECT = "project"
    FEDERATION = "federation"
    UNKNOWN = "unknown"


class RouteOperation(str, Enum):
    ASSESS = "assess"
    DESIGN = "design"
    INITIALIZE = "initialize"
    VALIDATE = "validate"
    EVALUATE = "evaluate"
    REPAIR = "repair"
    EVOLVE = "evolve"
    INSPECT = "inspect"
    PLAN = "plan"
    VERIFY = "verify"
    ADMIT = "admit"
    RECONCILE = "reconcile"
    IMPACT = "impact"
    RETIRE = "retire"


class RouteFact(str, Enum):
    PROJECT_SCOPE = "project_scope"
    FEDERATION_SCOPE = "federation_scope"
    STRUCTURAL_NEED = "structural_need"
    GRAPH_WORTHY = "graph_worthy"
    REGISTRY_REFERENCE = "registry_reference"
    CROSS_PROJECT_ACTION = "cross_project_action"
    DIRECT_BASELINE_SUFFICIENT = "direct_baseline_sufficient"


GRAPH_ENGINEERING_OPERATIONS = frozenset(
    {
        RouteOperation.ASSESS,
        RouteOperation.DESIGN,
        RouteOperation.INITIALIZE,
        RouteOperation.VALIDATE,
        RouteOperation.EVALUATE,
        RouteOperation.REPAIR,
        RouteOperation.EVOLVE,
    }
)
GRAPH_STEWARD_OPERATIONS = frozenset(
    {
        RouteOperation.INSPECT,
        RouteOperation.PLAN,
        RouteOperation.VERIFY,
        RouteOperation.ADMIT,
        RouteOperation.RECONCILE,
        RouteOperation.IMPACT,
        RouteOperation.RETIRE,
    }
)
ROUTES = frozenset({"graph_engineering", "graph_steward", "no_skill", "defer"})
REASONS = frozenset(
    {
        "project_structural_route",
        "project_assessment_route",
        "federation_structural_route",
        "direct_baseline_route",
        "unknown_scope",
        "incomplete_evidence",
        "conflicting_evidence",
        "operation_scope_mismatch",
        "authenticated_route_divergence",
    }
)


@dataclass(frozen=True)
class RoutingEvidence:
    evidence_id: str
    fact: RouteFact
    provenance: Provenance
    trust: TrustClass
    freshness: Freshness
    sensitivity: Sensitivity
    admission: Admission
    eligible: bool
    agent_generated: bool
    verifier_promoted: bool

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id is required")

    def is_authenticated(
        self, allowed_sensitivities: tuple[Sensitivity, ...]
    ) -> bool:
        agent_origin_admitted = not self.agent_generated or (
            self.verifier_promoted
            and self.trust is TrustClass.POLICY_ADMITTED
            and self.admission is Admission.VERIFIER
        )
        return (
            self.eligible
            and agent_origin_admitted
            and self.provenance.is_verified()
            and self.trust
            in {TrustClass.VERIFIED_SOURCE, TrustClass.POLICY_ADMITTED}
            and self.freshness is Freshness.CURRENT
            and self.sensitivity in allowed_sensitivities
            and self.admission in {Admission.POLICY, Admission.VERIFIER}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "fact": self.fact.value,
            "provenance": {
                "path": self.provenance.path,
                "sha256": self.provenance.sha256,
                "locator": self.provenance.locator,
                "verified": self.provenance.verified,
            },
            "trust": self.trust.value,
            "freshness": self.freshness.value,
            "sensitivity": self.sensitivity.value,
            "admission": self.admission.value,
            "eligible": self.eligible,
            "agent_generated": self.agent_generated,
            "verifier_promoted": self.verifier_promoted,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RoutingEvidence":
        _require_exact_keys(
            payload,
            {
                "evidence_id",
                "fact",
                "provenance",
                "trust",
                "freshness",
                "sensitivity",
                "admission",
                "eligible",
                "agent_generated",
                "verifier_promoted",
            },
            "routing evidence",
        )
        provenance = payload["provenance"]
        if not isinstance(provenance, Mapping):
            raise ValueError("provenance must be an object")
        _require_exact_keys(
            provenance,
            {"path", "sha256", "locator", "verified"},
            "provenance",
        )
        return cls(
            evidence_id=_string(payload["evidence_id"], "evidence_id"),
            fact=RouteFact(payload["fact"]),
            provenance=Provenance(
                path=_string(provenance["path"], "provenance.path"),
                sha256=_string(provenance["sha256"], "provenance.sha256"),
                locator=_string(provenance["locator"], "provenance.locator"),
                verified=_boolean(provenance["verified"], "provenance.verified"),
            ),
            trust=TrustClass(payload["trust"]),
            freshness=Freshness(payload["freshness"]),
            sensitivity=Sensitivity(payload["sensitivity"]),
            admission=Admission(payload["admission"]),
            eligible=_boolean(payload["eligible"], "eligible"),
            agent_generated=_boolean(payload["agent_generated"], "agent_generated"),
            verifier_promoted=_boolean(
                payload["verifier_promoted"], "verifier_promoted"
            ),
        )


@dataclass(frozen=True)
class RoutingRequest:
    request_id: str
    scope: RouteScope
    operation: RouteOperation
    evidence: tuple[RoutingEvidence, ...]
    allowed_sensitivities: tuple[Sensitivity, ...] = (Sensitivity.PUBLIC,)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        if not self.allowed_sensitivities:
            raise ValueError("allowed_sensitivities must not be empty")
        if len(self.allowed_sensitivities) != len(set(self.allowed_sensitivities)):
            raise ValueError("allowed_sensitivities must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "scope": self.scope.value,
            "operation": self.operation.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "allowed_sensitivities": [
                sensitivity.value for sensitivity in self.allowed_sensitivities
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RoutingRequest":
        _require_exact_keys(
            payload,
            {"request_id", "scope", "operation", "evidence", "allowed_sensitivities"},
            "routing request",
        )
        evidence = payload["evidence"]
        sensitivities = payload["allowed_sensitivities"]
        if not isinstance(evidence, list):
            raise ValueError("evidence must be an array")
        if not isinstance(sensitivities, list):
            raise ValueError("allowed_sensitivities must be an array")
        return cls(
            request_id=_string(payload["request_id"], "request_id"),
            scope=RouteScope(payload["scope"]),
            operation=RouteOperation(payload["operation"]),
            evidence=tuple(
                RoutingEvidence.from_dict(item)
                if isinstance(item, Mapping)
                else _raise_value("evidence items must be objects")
                for item in evidence
            ),
            allowed_sensitivities=tuple(Sensitivity(item) for item in sensitivities),
        )


@dataclass(frozen=True)
class RouteDecision:
    route: str
    full_route: str
    authenticated_route: str
    used_evidence_ids: tuple[str, ...]
    divergent_evidence_ids: tuple[str, ...]
    fail_closed: bool
    reason: str

    def __post_init__(self) -> None:
        if self.route not in ROUTES or self.full_route not in ROUTES:
            raise ValueError("invalid route")
        if self.authenticated_route not in ROUTES:
            raise ValueError("invalid authenticated_route")
        if self.reason not in REASONS:
            raise ValueError("invalid route reason")
        projections_diverge = self.full_route != self.authenticated_route
        if projections_diverge:
            if not (
                self.route == "defer"
                and self.fail_closed
                and self.reason == "authenticated_route_divergence"
            ):
                raise ValueError(
                    "route divergence must return fail-closed defer with the "
                    "authenticated_route_divergence reason"
                )
        elif (
            self.route != self.full_route
            or self.reason == "authenticated_route_divergence"
        ):
            raise ValueError(
                "matching projections require the same route and a non-divergence reason"
            )
        if tuple(sorted(set(self.used_evidence_ids))) != self.used_evidence_ids:
            raise ValueError("used_evidence_ids must be sorted and unique")
        if tuple(sorted(set(self.divergent_evidence_ids))) != self.divergent_evidence_ids:
            raise ValueError("divergent_evidence_ids must be sorted and unique")
        if any(not evidence_id.strip() for evidence_id in self.used_evidence_ids):
            raise ValueError("used_evidence_ids must not contain blank IDs")
        if any(not evidence_id.strip() for evidence_id in self.divergent_evidence_ids):
            raise ValueError("divergent_evidence_ids must not contain blank IDs")
        if self.fail_closed != (self.route == "defer"):
            raise ValueError("defer must be fail closed and only defer may fail closed")

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "full_route": self.full_route,
            "authenticated_route": self.authenticated_route,
            "used_evidence_ids": list(self.used_evidence_ids),
            "divergent_evidence_ids": list(self.divergent_evidence_ids),
            "fail_closed": self.fail_closed,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteDecision":
        _require_exact_keys(
            payload,
            {
                "route",
                "full_route",
                "authenticated_route",
                "used_evidence_ids",
                "divergent_evidence_ids",
                "fail_closed",
                "reason",
            },
            "route decision",
        )
        used = _string_array(payload["used_evidence_ids"], "used_evidence_ids")
        divergent = _string_array(
            payload["divergent_evidence_ids"], "divergent_evidence_ids"
        )
        return cls(
            route=_string(payload["route"], "route"),
            full_route=_string(payload["full_route"], "full_route"),
            authenticated_route=_string(
                payload["authenticated_route"], "authenticated_route"
            ),
            used_evidence_ids=tuple(used),
            divergent_evidence_ids=tuple(divergent),
            fail_closed=_boolean(payload["fail_closed"], "fail_closed"),
            reason=_string(payload["reason"], "reason"),
        )


@dataclass(frozen=True)
class _Projection:
    route: str
    used_ids: tuple[str, ...]
    reason: str


def resolve_route(request: RoutingRequest) -> RouteDecision:
    """Resolve a route from typed facts and fail closed on trust divergence."""

    ordered = tuple(sorted(request.evidence, key=lambda item: item.evidence_id))
    authenticated = tuple(
        item
        for item in ordered
        if item.is_authenticated(request.allowed_sensitivities)
    )
    full = _resolve_projection(request, ordered)
    trusted = _resolve_projection(request, authenticated)
    if full.route != trusted.route:
        trusted_ids = {item.evidence_id for item in authenticated}
        divergent = tuple(
            sorted(item_id for item_id in full.used_ids if item_id not in trusted_ids)
        )
        return RouteDecision(
            route="defer",
            full_route=full.route,
            authenticated_route=trusted.route,
            used_evidence_ids=trusted.used_ids,
            divergent_evidence_ids=divergent,
            fail_closed=True,
            reason="authenticated_route_divergence",
        )
    return RouteDecision(
        route=trusted.route,
        full_route=full.route,
        authenticated_route=trusted.route,
        used_evidence_ids=trusted.used_ids,
        divergent_evidence_ids=(),
        fail_closed=trusted.route == "defer",
        reason=trusted.reason,
    )


def _resolve_projection(
    request: RoutingRequest, evidence: tuple[RoutingEvidence, ...]
) -> _Projection:
    by_fact: dict[RouteFact, tuple[str, ...]] = {}
    for fact in RouteFact:
        by_fact[fact] = tuple(
            item.evidence_id for item in evidence if item.fact is fact
        )

    project = by_fact[RouteFact.PROJECT_SCOPE]
    federation = by_fact[RouteFact.FEDERATION_SCOPE]
    structural = by_fact[RouteFact.STRUCTURAL_NEED]
    worthy = by_fact[RouteFact.GRAPH_WORTHY]
    registry = by_fact[RouteFact.REGISTRY_REFERENCE]
    cross_project = by_fact[RouteFact.CROSS_PROJECT_ACTION]
    baseline = by_fact[RouteFact.DIRECT_BASELINE_SUFFICIENT]
    graph_or_federation_trigger = structural + worthy + registry + cross_project

    if (project and federation) or (baseline and graph_or_federation_trigger):
        return _Projection(
            "defer",
            tuple(sorted(project + federation + baseline + graph_or_federation_trigger)),
            "conflicting_evidence",
        )
    if request.scope is RouteScope.UNKNOWN:
        return _Projection("defer", (), "unknown_scope")
    if request.scope is RouteScope.PROJECT:
        if federation or registry or cross_project:
            return _Projection(
                "defer",
                tuple(sorted(project + federation + registry + cross_project)),
                "conflicting_evidence",
            )
        if not project:
            return _Projection("defer", (), "incomplete_evidence")
        if structural or worthy:
            if request.operation not in GRAPH_ENGINEERING_OPERATIONS:
                return _Projection(
                    "defer",
                    tuple(sorted(project + structural + worthy)),
                    "operation_scope_mismatch",
                )
            if request.operation is RouteOperation.ASSESS:
                if not (worthy or structural):
                    return _Projection("defer", project, "incomplete_evidence")
                return _Projection(
                    "graph_engineering",
                    tuple(sorted(project + worthy + structural)),
                    "project_assessment_route",
                )
            if not structural:
                return _Projection(
                    "defer", tuple(sorted(project + worthy)), "incomplete_evidence"
                )
            return _Projection(
                "graph_engineering",
                tuple(sorted(project + structural)),
                "project_structural_route",
            )
        if baseline:
            return _Projection(
                "no_skill", tuple(sorted(project + baseline)), "direct_baseline_route"
            )
        return _Projection("defer", project, "incomplete_evidence")

    if project or structural or worthy or baseline:
        return _Projection(
            "defer",
            tuple(sorted(project + structural + worthy + baseline)),
            "conflicting_evidence",
        )
    if not federation:
        return _Projection("defer", (), "incomplete_evidence")
    if request.operation not in GRAPH_STEWARD_OPERATIONS:
        return _Projection(
            "defer", federation, "operation_scope_mismatch"
        )
    if not registry or not cross_project:
        return _Projection(
            "defer",
            tuple(sorted(federation + registry + cross_project)),
            "incomplete_evidence",
        )
    return _Projection(
        "graph_steward",
        tuple(sorted(federation + registry + cross_project)),
        "federation_structural_route",
    )


def _require_exact_keys(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{label} fields differ; missing={missing}, extra={extra}")


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def _string_array(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return value


def _raise_value(message: str) -> Any:
    raise ValueError(message)
