"""Host-neutral graph data types for the Graph Engineering V1 core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class TrustClass(str, Enum):
    VERIFIED_SOURCE = "verified_source"
    POLICY_ADMITTED = "policy_admitted"
    AGENT_GENERATED = "agent_generated"
    QUARANTINED = "quarantined"
    UNVERIFIABLE = "unverifiable"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class Freshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class Admission(str, Enum):
    NONE = "none"
    POLICY = "policy"
    VERIFIER = "verifier"


class Topology(str, Enum):
    DEPENDENCY = "dependency"
    EVIDENCE = "evidence"
    PROCEDURE = "procedure"


@dataclass(frozen=True)
class Provenance:
    path: str
    sha256: str
    locator: str
    verified: bool = False

    def is_verified(self) -> bool:
        return (
            self.verified
            and bool(self.path.strip())
            and bool(self.locator.strip())
            and len(self.sha256) == 64
            and all(character in "0123456789abcdef" for character in self.sha256)
        )


@dataclass(frozen=True)
class GraphRecord:
    record_id: str
    kind: str
    title: str
    content: str
    provenance: Provenance
    trust: TrustClass
    sensitivity: Sensitivity
    freshness: Freshness
    admission: Admission = Admission.NONE
    eligible: bool = False
    agent_generated: bool = False
    export_allowed: bool = False
    tags: tuple[str, ...] = ()
    sequence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    relevance: float
    provenance: Provenance
    trust: TrustClass
    sensitivity: Sensitivity
    freshness: Freshness
    admission: Admission = Admission.NONE
    eligible: bool = False
    agent_generated: bool = False
    export_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(frozen=True)
class Graph:
    records: tuple[GraphRecord, ...]
    edges: tuple[GraphEdge, ...] = ()

    def __post_init__(self) -> None:
        record_ids = [record.record_id for record in self.records]
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("record IDs must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("edge IDs must be unique")
        known = set(record_ids)
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise ValueError(f"edge {edge.edge_id} has an unknown endpoint")
            if not 0.0 <= edge.relevance <= 1.0:
                raise ValueError(f"edge {edge.edge_id} relevance must be between 0 and 1")

    def record_map(self) -> dict[str, GraphRecord]:
        return {record.record_id: record for record in self.records}

    def edge_map(self) -> dict[str, GraphEdge]:
        return {edge.edge_id: edge for edge in self.edges}


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    query_terms: tuple[str, ...]
    topology: Topology = Topology.EVIDENCE
    max_depth: int = 4
    node_budget: int = 200
    byte_budget: int = 32768
    minimum_relevance: float = 0.1
    allowed_sensitivities: tuple[Sensitivity, ...] = (Sensitivity.PUBLIC,)

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if self.max_depth < 0 or self.node_budget < 1 or self.byte_budget < 1:
            raise ValueError("task budgets must be positive")
        if not 0.0 <= self.minimum_relevance <= 1.0:
            raise ValueError("minimum_relevance must be between 0 and 1")


ALLOWED_TRUST = frozenset({TrustClass.VERIFIED_SOURCE, TrustClass.POLICY_ADMITTED})
ALLOWED_ADMISSION = frozenset({Admission.POLICY, Admission.VERIFIER})


def is_authenticated_eligible(
    item: GraphRecord | GraphEdge,
    allowed_sensitivities: tuple[Sensitivity, ...],
) -> bool:
    """Return true only when an item passes every V1 consequential-use gate."""

    agent_origin_admitted = not item.agent_generated or (
        item.trust is TrustClass.POLICY_ADMITTED
        and item.admission is Admission.VERIFIER
    )
    return (
        item.eligible
        and agent_origin_admitted
        and item.provenance.is_verified()
        and item.trust in ALLOWED_TRUST
        and item.freshness is Freshness.CURRENT
        and item.sensitivity in allowed_sensitivities
        and item.admission in ALLOWED_ADMISSION
    )


def _enum_values(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_values(item) for item in value]
    return value
