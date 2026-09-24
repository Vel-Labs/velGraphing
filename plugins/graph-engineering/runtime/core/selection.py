"""Deterministic task projection and fail-closed authenticated selection."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Sequence

from .jev import PACKET_VERSION, canonical as jev_canonical, sha256 as jev_sha256, validate_packet

from .models import (
    Freshness,
    Graph,
    GraphEdge,
    GraphRecord,
    Sensitivity,
    TaskSpec,
    is_authenticated_eligible,
)
from .routing_v4 import (
    SourceIdentityV4,
    SourceReaderV4,
    SourceSnapshotV4,
    _read_verified_source_bytes,
    _require_relative_path,
)

_SHA256_LENGTH = 64
_RANKED_RESERVED_REQUEST_SHA256 = "0" * _SHA256_LENGTH
_ASSIST_OBSERVATION_SCHEMA_VERSION = "assist-observation-v1"
_ASSIST_REASONS = frozenset(
    {
        "fallback_context_exceeds_byte_budget",
        "fallback_sources_incomplete",
        "fallback_sources_unavailable",
        "fallback_sources_unreadable",
        "graph_projection_unavailable",
        "invalid_fallback_source_paths",
        "invalid_required_escalation",
        "invalid_required_source_paths",
        "required_escalation",
        "required_escalation_unavailable",
        "required_sources_direct",
        "required_sources_missing",
        "required_sources_selected",
    }
)
_REVERSE_RELATIONS = frozenset(
    {
        "calls", "consumes", "declares", "depends_on", "describes", "documents",
        "implements", "imports", "packages", "produces", "supports", "tested_by",
        "tests", "uses",
    }
)
_MAX_TASK_FACETS = 20
_CLASSIFICATION_OBSERVATION_SCHEMA = "retrievel-classification-observation-v1"


def _validated_task_facets(value: object) -> tuple[str, ...]:
    if type(value) not in {list, tuple}:
        raise TypeError("task_facets must be a list or tuple of strings")
    facets = tuple(value)
    if (
        len(facets) > _MAX_TASK_FACETS
        or any(
            type(facet) is not str
            or not facet
            or facet != facet.strip()
            or any(ord(character) < 32 for character in facet)
            for facet in facets
        )
        or len(facets) != len(set(facets))
    ):
        raise ValueError("task_facets must be unique, bounded, and printable")
    return facets


@dataclass(frozen=True)
class SelectionResult:
    task_id: str
    record_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    full_graph_record_ids: tuple[str, ...]
    authenticated_record_ids: tuple[str, ...]
    divergent_record_ids: tuple[str, ...]
    fail_closed: bool
    reason: str
    depth_reached: int
    scores: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "record_ids": list(self.record_ids),
            "edge_ids": list(self.edge_ids),
            "full_graph_record_ids": list(self.full_graph_record_ids),
            "authenticated_record_ids": list(self.authenticated_record_ids),
            "divergent_record_ids": list(self.divergent_record_ids),
            "fail_closed": self.fail_closed,
            "reason": self.reason,
            "depth_reached": self.depth_reached,
            "scores": {record_id: score for record_id, score in self.scores},
        }


@dataclass(frozen=True)
class ContextSpan:
    record_id: str
    byte_start: int
    byte_end: int
    excerpt_sha256: str

    def __post_init__(self) -> None:
        if type(self.record_id) is not str or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        if type(self.byte_start) is not int or type(self.byte_end) is not int:
            raise ValueError("context byte ranges must use exact integers")
        if self.byte_start < 0 or self.byte_end <= self.byte_start:
            raise ValueError("context byte ranges must be non-empty and ordered")
        if (
            type(self.excerpt_sha256) is not str
            or len(self.excerpt_sha256) != _SHA256_LENGTH
            or any(character not in "0123456789abcdef" for character in self.excerpt_sha256)
        ):
            raise ValueError("excerpt_sha256 must be a full lowercase SHA-256")


@dataclass(frozen=True)
class ContextProjection:
    content: str
    byte_count: int
    required_record_ids: tuple[str, ...]
    included_optional_record_ids: tuple[str, ...]
    fail_closed: bool
    reason: str


@dataclass(frozen=True)
class AssistResult:
    route: str
    reason: str
    projection: ContextProjection


@dataclass(frozen=True)
class AssistObservation:
    schema_version: str
    task_id: str
    source_snapshot_sha256: str
    route: str
    reason: str
    failure_class: str
    required_source_paths: tuple[str, ...]
    fallback_source_paths: tuple[str, ...]
    selected_source_paths: tuple[str, ...]
    context_bytes: int
    fail_closed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "context_bytes": self.context_bytes,
            "fail_closed": self.fail_closed,
            "failure_class": self.failure_class,
            "fallback_source_paths": list(self.fallback_source_paths),
            "reason": self.reason,
            "required_source_paths": list(self.required_source_paths),
            "route": self.route,
            "schema_version": self.schema_version,
            "selected_source_paths": list(self.selected_source_paths),
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "task_id": self.task_id,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class RankedContextCandidate:
    candidate_id: str
    source_path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    required: bool
    record_id: str
    relationship_parent_candidate_id: str | None = None
    relationship_edge_id: str | None = None
    relationship_direction: str | None = None
    relationship_relation: str | None = None
    relationship_sensitivity: Sensitivity | None = None
    source_unit_complete: bool = False

    def __post_init__(self) -> None:
        if type(self.source_unit_complete) is not bool:
            raise TypeError("source_unit_complete must be an exact boolean")
        if type(self.record_id) is not str or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        if (
            self.relationship_parent_candidate_id is not None
            and (
                type(self.relationship_parent_candidate_id) is not str
                or not self.relationship_parent_candidate_id
                or self.required
            )
        ):
            raise ValueError("relationship candidates must be optional with a parent ID")
        relationship_metadata = (
            self.relationship_edge_id,
            self.relationship_direction,
            self.relationship_relation,
            self.relationship_sensitivity,
        )
        if any(value is not None for value in relationship_metadata):
            if (
                self.relationship_parent_candidate_id is None
                or any(value is None for value in relationship_metadata)
                or self.relationship_direction not in {"incoming", "outgoing"}
                or not isinstance(self.relationship_sensitivity, Sensitivity)
            ):
                raise ValueError("relationship candidate metadata is incomplete")
        validate_packet({
            "schema_version": PACKET_VERSION,
            "query": "candidate validation",
            "candidates": [self._packet_value()],
        })

    def _packet_value(self) -> dict[str, object]:
        return {
            "id": self.candidate_id,
            "path": self.source_path,
            "source_sha256": self.source_sha256,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "required": self.required,
        }


@dataclass(frozen=True)
class RankedContextProjection:
    content: str
    serialized_byte_count: int
    excerpt_byte_count: int
    selected_candidate_ids: tuple[str, ...]
    required_candidate_ids: tuple[str, ...]
    included_optional_candidate_ids: tuple[str, ...]
    fail_closed: bool
    reason: str


@dataclass(frozen=True)
class RankedContextJevDecision:
    reason: str
    jev_enabled: bool
    jev_call_could_affect_selection: bool
    jev_observation_applied: bool
    baseline_selected_candidate_count: int
    baseline_selected_excerpt_bytes: int
    baseline_omitted_candidate_count: int
    baseline_omitted_excerpt_bytes: int
    relationship_candidate_signal: bool
    classification_observation_applied: bool = False
    classification_source: str = "none"

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_omitted_candidate_count": self.baseline_omitted_candidate_count,
            "baseline_omitted_excerpt_bytes": self.baseline_omitted_excerpt_bytes,
            "baseline_selected_candidate_count": self.baseline_selected_candidate_count,
            "baseline_selected_excerpt_bytes": self.baseline_selected_excerpt_bytes,
            "classification_observation_applied": self.classification_observation_applied,
            "classification_source": self.classification_source,
            "jev_call_could_affect_selection": self.jev_call_could_affect_selection,
            "jev_enabled": self.jev_enabled,
            "jev_observation_applied": self.jev_observation_applied,
            "reason": self.reason,
            "relationship_candidate_signal": self.relationship_candidate_signal,
            "schema_version": "graph-ranked-context-jev-decision-v1",
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class RankedContextResult:
    route: str
    reason: str
    order_source: str
    candidate_set_sha256: str
    approved_request_sha256: str | None
    jev_source_revalidated: bool
    source_revalidated: bool
    projection: RankedContextProjection
    jev_decision: RankedContextJevDecision


@dataclass(frozen=True)
class RankedContextPlan:
    route: str
    reason: str
    candidates: tuple[RankedContextCandidate, ...]
    baseline: RankedContextResult
    task_facets: tuple[str, ...] = ()
    context_fidelity: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if type(self.task_facets) is not tuple:
            raise TypeError("task_facets must be a tuple after plan construction")
        _validated_task_facets(self.task_facets)

    def realized_route(
        self,
        direct_candidates: tuple[RankedContextCandidate, ...],
        selected: RankedContextResult,
    ) -> str:
        if self.route != "graph":
            return "direct"
        selected_ids = set(selected.projection.selected_candidate_ids)
        direct_ids = {candidate.candidate_id for candidate in direct_candidates}
        return (
            "graph"
            if any(
                candidate.candidate_id not in direct_ids
                and candidate.candidate_id in selected_ids
                and candidate.relationship_parent_candidate_id in selected_ids
                for candidate in self.candidates
            )
            else "graph_pool_without_selected_relationship"
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "baseline_fail_closed": self.baseline.projection.fail_closed,
            "candidate_count": len(self.candidates),
            "candidate_set_sha256": self.baseline.candidate_set_sha256,
            "jev_decision": self.baseline.jev_decision.to_dict(),
            "reason": self.reason,
            "route": self.route,
            "schema_version": "graph-ranked-context-plan-v1",
        }
        if self.task_facets:
            result["task_facets"] = list(self.task_facets)
        if self.context_fidelity is not None:
            result["context_fidelity"] = self.context_fidelity
        return result

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _context_reuse_state(
    prior_plan: RankedContextPlan | None,
    *,
    query_sha256: str,
    source_snapshot_sha256: str,
    candidate_set_sha256: str,
    byte_budget: int,
    task_facets: tuple[str, ...],
) -> str:
    if prior_plan is None or type(prior_plan.context_fidelity) is not dict:
        return "rebuild"
    prior = prior_plan.context_fidelity
    if (
        prior.get("source_snapshot_sha256") != source_snapshot_sha256
        or prior.get("candidate_set_sha256") != candidate_set_sha256
    ):
        return "rebuild"
    if (
        prior.get("query_sha256") != query_sha256
        or prior.get("requested_task_facets") != list(task_facets)
    ):
        return "refresh"
    prior_budget = prior.get("byte_budget")
    if type(prior_budget) is not int:
        return "rebuild"
    if prior_budget == byte_budget:
        return "reuse"
    return "widen" if byte_budget > prior_budget else "refresh"


def _context_fidelity_metadata(
    candidates: tuple[RankedContextCandidate, ...],
    baseline: RankedContextResult,
    *,
    query_sha256: str,
    source_snapshot_sha256: str,
    byte_budget: int,
    task_facets: tuple[str, ...],
    prior_plan: RankedContextPlan | None,
) -> dict[str, object]:
    selected_ids = set(baseline.projection.selected_candidate_ids)
    decisions: list[dict[str, object]] = []
    for candidate in candidates:
        if candidate.candidate_id in selected_ids:
            mode = "source_unit" if candidate.source_unit_complete else "excerpt"
            reason = (
                "selected_complete_source_unit"
                if candidate.source_unit_complete
                else "selected_bounded_excerpt"
            )
        elif candidate.required:
            mode = "excerpt"
            reason = "required_candidate_deferred"
        else:
            mode = "omit"
            reason = "optional_candidate_not_selected"
        decisions.append({
            "candidate_id": candidate.candidate_id,
            "included": candidate.candidate_id in selected_ids,
            "mode": mode,
            "reason": reason,
            "source_path": candidate.source_path,
            "source_sha256": candidate.source_sha256,
            "byte_start": candidate.byte_start,
            "byte_end": candidate.byte_end,
            "source_unit_complete": candidate.source_unit_complete,
        })
    return {
        "schema_version": "graph-ranked-context-fidelity-v1",
        "query_sha256": query_sha256,
        "source_snapshot_sha256": source_snapshot_sha256,
        "candidate_set_sha256": baseline.candidate_set_sha256,
        "byte_budget": byte_budget,
        "reuse_state": _context_reuse_state(
            prior_plan,
            query_sha256=query_sha256,
            source_snapshot_sha256=source_snapshot_sha256,
            candidate_set_sha256=baseline.candidate_set_sha256,
            byte_budget=byte_budget,
            task_facets=task_facets,
        ),
        "remaining_byte_budget": max(
            0, byte_budget - baseline.projection.serialized_byte_count
        ),
        "requested_task_facets": list(task_facets),
        "decisions": decisions,
    }


def plan_ranked_context(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    query: str,
    direct_candidates: tuple[RankedContextCandidate, ...],
    graph_candidates: tuple[RankedContextCandidate, ...],
    jev_enabled: bool = False,
    fallback_source_paths: tuple[str, ...] = (),
    task_facets: Sequence[str] = (),
    prior_plan: RankedContextPlan | None = None,
) -> RankedContextPlan:
    """Choose a verified shortlist and plan optional Jev use without a provider call."""

    for name, values in (
        ("direct_candidates", direct_candidates),
        ("graph_candidates", graph_candidates),
    ):
        if type(values) is not tuple or any(
            type(candidate) is not RankedContextCandidate for candidate in values
        ):
            raise TypeError(f"{name} must be a tuple of exact RankedContextCandidate values")
    if type(jev_enabled) is not bool:
        raise TypeError("jev_enabled must be an exact boolean")
    if prior_plan is not None and type(prior_plan) is not RankedContextPlan:
        raise TypeError("prior_plan must be an exact RankedContextPlan or None")
    validated_task_facets = _validated_task_facets(task_facets)
    direct_by_id = {candidate.candidate_id: candidate for candidate in direct_candidates}
    graph_by_id = {candidate.candidate_id: candidate for candidate in graph_candidates}
    graph_adds_relationship = False
    relationship_gain_ids: set[str] = set()
    prior_graph_candidates: dict[str, RankedContextCandidate] = {}
    for candidate in graph_candidates:
        parent_id = candidate.relationship_parent_candidate_id
        parent = prior_graph_candidates.get(parent_id) if parent_id is not None else None
        if (
            candidate.candidate_id not in direct_by_id
            and parent is not None
            and parent.relationship_parent_candidate_id is None
            and parent.candidate_id != candidate.candidate_id
            and _has_verified_relationship_edge(
                graph, task, snapshot, parent, candidate
            )
        ):
            graph_adds_relationship = True
            relationship_gain_ids.add(candidate.candidate_id)
        prior_graph_candidates[candidate.candidate_id] = candidate
    required_preserved = all(
        not candidate.required or graph_by_id.get(candidate.candidate_id) == candidate
        for candidate in direct_candidates
    )
    use_graph = graph_adds_relationship and required_preserved
    route = "graph" if use_graph else "direct"
    reason = (
        "graph_adds_source_witnessed_relationship_candidates"
        if use_graph
        else "direct_baseline_no_graph_relationship_gain"
    )
    candidates = graph_candidates if use_graph else direct_candidates
    direct_baseline = None
    if use_graph:
        direct_baseline = select_ranked_context(
            graph,
            task,
            snapshot,
            reader,
            query=query,
            candidates=direct_candidates,
            jev_observation=None,
            jev_enabled=jev_enabled,
            fallback_source_paths=fallback_source_paths,
        )
    baseline = select_ranked_context(
        graph,
        task,
        snapshot,
        reader,
        query=query,
        candidates=candidates,
        jev_observation=None,
        jev_enabled=jev_enabled,
        fallback_source_paths=fallback_source_paths,
    )
    if use_graph and direct_baseline is not None and (
        not direct_baseline.projection.fail_closed
        and (
            baseline.projection.fail_closed
            or not {
                (
                    direct_by_id[candidate_id].source_path,
                    direct_by_id[candidate_id].source_sha256,
                    direct_by_id[candidate_id].byte_start,
                    direct_by_id[candidate_id].byte_end,
                )
                for candidate_id in direct_baseline.projection.selected_candidate_ids
            }.issubset({
                (
                    graph_by_id[candidate_id].source_path,
                    graph_by_id[candidate_id].source_sha256,
                    graph_by_id[candidate_id].byte_start,
                    graph_by_id[candidate_id].byte_end,
                )
                for candidate_id in baseline.projection.selected_candidate_ids
                if candidate_id in graph_by_id
            })
        )
    ):
        # Graph additions must not displace context that already fits the
        # verified Direct budget. A Direct fallback is explicit in the plan.
        route = "direct"
        reason = "graph_selection_would_displace_direct_baseline"
        candidates = direct_candidates
        baseline = direct_baseline
    if route == "graph" and direct_baseline is not None:
        selected_ids = set(baseline.projection.selected_candidate_ids)
        if not any(
            candidate_id in selected_ids
            and graph_by_id[candidate_id].relationship_parent_candidate_id in selected_ids
            for candidate_id in relationship_gain_ids
        ):
            # Pool-level edge gain is not a selected Graph contribution. Keep
            # the verified Direct result when every new relationship bundle
            # was pruned, without relaxing its preservation or byte budget.
            route = "direct"
            reason = "graph_selection_no_retained_relationship_gain"
            candidates = direct_candidates
            baseline = direct_baseline
    query_sha256 = jev_sha256(query.encode("utf-8"))
    context_fidelity = _context_fidelity_metadata(
        candidates,
        baseline,
        query_sha256=query_sha256,
        source_snapshot_sha256=snapshot.snapshot_sha256,
        byte_budget=task.byte_budget,
        task_facets=validated_task_facets,
        prior_plan=prior_plan,
    )
    return RankedContextPlan(
        route, reason, candidates, baseline, validated_task_facets, context_fidelity
    )


def select_ranked_context(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    query: str,
    candidates: tuple[RankedContextCandidate, ...],
    approved_request_sha256: str | None = None,
    jev_observation: Any = None,
    classification_observation: Any = None,
    jev_enabled: bool = False,
    jev_observation_qualified: bool = False,
    fallback_source_paths: tuple[str, ...] = (),
) -> RankedContextResult:
    """Select verified source spans from an immutable candidate shortlist."""

    if type(graph) is not Graph:
        raise TypeError("graph must be an exact Graph")
    if type(task) is not TaskSpec:
        raise TypeError("task must be an exact TaskSpec")
    if type(snapshot) is not SourceSnapshotV4:
        raise TypeError("snapshot must be an exact SourceSnapshotV4")
    if type(candidates) is not tuple or any(
        type(candidate) is not RankedContextCandidate for candidate in candidates
    ):
        raise TypeError("candidates must be a tuple of exact RankedContextCandidate values")
    if approved_request_sha256 is not None and not _valid_digest(approved_request_sha256):
        raise ValueError("approved_request_sha256 must be a full lowercase SHA-256")
    if type(fallback_source_paths) is not tuple or any(
        type(path) is not str for path in fallback_source_paths
    ):
        raise TypeError("fallback_source_paths must be a tuple of strings")
    if type(jev_enabled) is not bool or type(jev_observation_qualified) is not bool:
        raise TypeError("Jev controls must be exact booleans")
    observation_conflict = (
        jev_observation is not None and classification_observation is not None
    )
    classification_source = (
        "external"
        if classification_observation is not None
        else "jev"
        if jev_observation is not None
        else "none"
    )
    classification_active = (
        jev_enabled or classification_observation is not None
    )

    packet = validate_packet({
        "schema_version": PACKET_VERSION,
        "query": query,
        "candidates": [candidate._packet_value() for candidate in candidates],
    })
    baseline_order = tuple(candidate["id"] for candidate in packet["candidates"])
    required_ids = tuple(
        candidate["id"] for candidate in packet["candidates"] if candidate["required"]
    )
    seen_candidates: dict[str, RankedContextCandidate] = {}
    for candidate in candidates:
        parent = candidate.relationship_parent_candidate_id
        if parent is not None and (
            parent == candidate.candidate_id
            or parent not in seen_candidates
            or seen_candidates[parent].relationship_parent_candidate_id is not None
        ):
            raise ValueError(
                "relationship parent must be a distinct earlier primary candidate"
            )
        seen_candidates[candidate.candidate_id] = candidate
    unavailable_decision = RankedContextJevDecision(
        reason="verified_baseline_unavailable",
        jev_enabled=jev_enabled,
        jev_call_could_affect_selection=False,
        jev_observation_applied=False,
        classification_observation_applied=False,
        classification_source=classification_source,
        baseline_selected_candidate_count=0,
        baseline_selected_excerpt_bytes=0,
        baseline_omitted_candidate_count=0,
        baseline_omitted_excerpt_bytes=0,
        relationship_candidate_signal=any(
            candidate.relationship_parent_candidate_id is not None
            for candidate in candidates
        ),
    )
    candidate_set_sha256 = jev_sha256(jev_canonical(packet["candidates"]))
    query_sha256 = jev_sha256(packet["query"].encode("utf-8"))
    for candidate in candidates:
        parent_id = candidate.relationship_parent_candidate_id
        if (
            parent_id is not None
            and not _has_verified_relationship_edge(
                graph, task, snapshot, seen_candidates[parent_id], candidate
            )
        ):
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "relationship_candidate_custody_mismatch", unavailable_decision,
            )
    snapshot_sources = {source.path: source for source in snapshot.sources}
    records = graph.record_map()
    selected_sources: dict[str, SourceIdentityV4] = {}
    source_sensitivities: dict[str, object] = {}
    for candidate in candidates:
        source = snapshot_sources.get(candidate.source_path)
        if source is None or source.sha256 != candidate.source_sha256:
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "candidate_source_identity_mismatch", unavailable_decision,
            )
        record = records.get(candidate.record_id)
        if (
            record is None
            or record.provenance.path != candidate.source_path
            or record.provenance.sha256 != candidate.source_sha256
        ):
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "candidate_record_identity_mismatch", unavailable_decision,
            )
        if not is_authenticated_eligible(record, task.allowed_sensitivities):
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "candidate_record_not_authenticated", unavailable_decision,
            )
        prior_sensitivity = source_sensitivities.get(candidate.source_path)
        if prior_sensitivity is not None and prior_sensitivity is not record.sensitivity:
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "candidate_source_sensitivity_conflict", unavailable_decision,
            )
        source_sensitivities[candidate.source_path] = record.sensitivity
        selected_sources[source.path] = source
    subset = SourceSnapshotV4(tuple(selected_sources[path] for path in sorted(selected_sources)))
    try:
        if not callable(getattr(reader, "read_bytes", None)) or not callable(
            getattr(reader, "is_symlink", None)
        ):
            raise TypeError("reader must implement the read-only V4 reader protocol")
        source_bytes = _read_verified_source_bytes(subset, reader)
    except Exception:
        return _ranked_defer(
            task, candidate_set_sha256, approved_request_sha256, required_ids,
            "candidate_source_unavailable", unavailable_decision,
        )

    spans: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        raw = source_bytes[candidate.source_path]
        if candidate.byte_end > len(raw):
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "candidate_range_invalid", unavailable_decision,
            )
        excerpt = raw[candidate.byte_start:candidate.byte_end]
        try:
            content = excerpt.decode("utf-8")
        except UnicodeDecodeError:
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "candidate_excerpt_not_utf8", unavailable_decision,
            )
        if content.encode("utf-8") != excerpt:
            return _ranked_defer(
                task, candidate_set_sha256, approved_request_sha256, required_ids,
                "candidate_excerpt_not_utf8", unavailable_decision,
            )
        spans[candidate.candidate_id] = {
            "byte_end": candidate.byte_end,
            "byte_start": candidate.byte_start,
            "candidate_id": candidate.candidate_id,
            "content": content,
            "relationship_parent_candidate_id": (
                candidate.relationship_parent_candidate_id
            ),
            "source_path": candidate.source_path,
            "source_sha256": candidate.source_sha256,
        }

    source_set_sha256 = jev_sha256(jev_canonical([
        {"path": path, "sha256": selected_sources[path].sha256}
        for path in sorted(selected_sources)
    ]))
    baseline_projection = _ranked_projection_for_order(
        task,
        snapshot,
        candidate_set_sha256,
        query_sha256,
        approved_request_sha256,
        "baseline",
        baseline_order,
        required_ids,
        seen_candidates,
        spans,
    )
    if baseline_projection is None:
        return _ranked_required_fallback(
            task,
            snapshot,
            reader,
            candidates,
            required_ids,
            candidate_set_sha256,
            approved_request_sha256,
            graph,
            fallback_source_paths,
            unavailable_decision,
        )
    baseline_selected = set(baseline_projection.selected_candidate_ids)
    omitted_optional = tuple(
        candidate_id
        for candidate_id in baseline_order
        if candidate_id not in baseline_selected and candidate_id not in required_ids
    )
    movable_optional = tuple(
        candidate_id
        for candidate_id in baseline_order
        if candidate_id not in required_ids
    )
    provider_bound_baseline = _ranked_projection_for_order(
        task,
        snapshot,
        candidate_set_sha256,
        query_sha256,
        _RANKED_RESERVED_REQUEST_SHA256,
        "reranked",
        baseline_order,
        required_ids,
        seen_candidates,
        spans,
    )
    provider_bound_selected = (
        set(provider_bound_baseline.selected_candidate_ids)
        if provider_bound_baseline is not None
        else None
    )
    provider_bound_omitted = tuple(
        candidate_id
        for candidate_id in baseline_order
        if provider_bound_selected is not None
        and candidate_id not in provider_bound_selected
        and candidate_id not in required_ids
    )
    can_affect = (
        bool(omitted_optional)
        and len(movable_optional) >= 2
        and provider_bound_selected is not None
        and any(
            set(projection.selected_candidate_ids) != provider_bound_selected
            for candidate_id in provider_bound_omitted
            for projection in (
                _ranked_projection_for_order(
                    task,
                    snapshot,
                    candidate_set_sha256,
                    query_sha256,
                    _RANKED_RESERVED_REQUEST_SHA256,
                    "reranked",
                    _ranked_priority_order(
                        baseline_order,
                        required_ids,
                        seen_candidates,
                        candidate_id,
                    ),
                    required_ids,
                    seen_candidates,
                    spans,
                ),
            )
            if projection is not None
        )
    )
    reason = (
        "jev_disabled"
        if not classification_active
        else "no_optional_candidates"
        if not any(not candidate.required for candidate in candidates)
        else "all_optional_candidates_fit"
        if not omitted_optional
        else "optional_order_cannot_change_selection"
        if not can_affect
        else "classification_observation_conflict"
        if observation_conflict
        else "classification_observation_invalid"
        if classification_observation is not None
        else "jev_observation_missing"
        if jev_observation is None
        else "jev_observation_not_qualified"
        if not jev_observation_qualified
        else "jev_observation_invalid"
    )
    selected_projection = baseline_projection
    jev_order = None
    if (
        classification_active
        and can_affect
        and not observation_conflict
        and (
            classification_observation is not None
            or jev_observation_qualified
        )
        and _valid_digest(approved_request_sha256)
    ):
        if classification_observation is not None:
            jev_order = _controlled_classification_order(
                classification_observation,
                baseline_order,
                required_ids,
                candidate_set_sha256,
                query_sha256,
                source_set_sha256,
                approved_request_sha256,
            )
        else:
            jev_order = _controlled_jev_order(
                jev_observation,
                baseline_order,
                required_ids,
                candidate_set_sha256,
                query_sha256,
                source_set_sha256,
                approved_request_sha256,
            )
        if jev_order is not None:
            reranked_projection = _ranked_projection_for_order(
                task,
                snapshot,
                candidate_set_sha256,
                query_sha256,
                approved_request_sha256,
                "reranked",
                jev_order,
                required_ids,
                seen_candidates,
                spans,
            )
            if (
                reranked_projection is not None
                and set(reranked_projection.selected_candidate_ids)
                != provider_bound_selected
            ):
                selected_projection = reranked_projection
                reason = (
                    "classification_rerank_applied"
                    if classification_source == "external"
                    else "jev_rerank_applied"
                )
            else:
                jev_order = None
                reason = (
                    "classification_rerank_no_selection_effect"
                    if classification_source == "external"
                    else "jev_rerank_no_selection_effect"
                )
    selected_ids = set(baseline_projection.selected_candidate_ids)
    decision = RankedContextJevDecision(
        reason=reason,
        jev_enabled=jev_enabled,
        jev_call_could_affect_selection=can_affect,
        jev_observation_applied=(
            jev_order is not None and classification_source == "jev"
        ),
        classification_observation_applied=jev_order is not None,
        classification_source=classification_source,
        baseline_selected_candidate_count=len(selected_ids),
        baseline_selected_excerpt_bytes=sum(
            candidate.byte_end - candidate.byte_start
            for candidate in candidates
            if candidate.candidate_id in selected_ids
        ),
        baseline_omitted_candidate_count=len(candidates) - len(selected_ids),
        baseline_omitted_excerpt_bytes=sum(
            candidate.byte_end - candidate.byte_start
            for candidate in candidates
            if candidate.candidate_id not in selected_ids
        ),
        relationship_candidate_signal=any(
            candidate.relationship_parent_candidate_id is not None
            for candidate in candidates
        ),
    )
    return RankedContextResult(
        route="ranked",
        reason="verified_ranked_context_selected",
        order_source="reranked" if jev_order is not None else "baseline",
        candidate_set_sha256=candidate_set_sha256,
        approved_request_sha256=(
            approved_request_sha256 if jev_order is not None else None
        ),
        jev_source_revalidated=jev_order is not None,
        source_revalidated=True,
        projection=selected_projection,
        jev_decision=decision,
    )


def _ranked_projection_for_order(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    candidate_set_sha256: str,
    query_sha256: str,
    approved_request_sha256: str | None,
    order_source: str,
    effective_order: tuple[str, ...],
    required_ids: tuple[str, ...],
    candidates: dict[str, RankedContextCandidate],
    spans: dict[str, dict[str, object]],
) -> RankedContextProjection | None:
    required_set = set(required_ids)
    children_by_parent: dict[str, tuple[str, ...]] = {
        candidate_id: tuple(
            child_id
            for child_id in effective_order
            if candidates[child_id].relationship_parent_candidate_id == candidate_id
        )
        for candidate_id in effective_order
        if candidates[candidate_id].relationship_parent_candidate_id is None
    }
    selected = set(required_ids)
    for candidate_id in effective_order:
        if candidate_id in required_set and children_by_parent.get(candidate_id):
            # ponytail: one direct child closes the bundle; widen only if callers
            # require every sibling relationship to be selected atomically.
            selected.add(children_by_parent[candidate_id][0])
    required_order = tuple(
        candidate_id for candidate_id in effective_order if candidate_id in selected
    )
    required_optional_order = tuple(
        candidate_id for candidate_id in required_order if candidate_id not in required_set
    )
    payload = _ranked_payload(
        task,
        snapshot,
        candidate_set_sha256,
        query_sha256,
        approved_request_sha256,
        order_source,
        required_order,
        required_ids,
        required_optional_order,
        spans,
    )
    if _payload_byte_count(payload) > task.byte_budget:
        return None
    for candidate_id in effective_order:
        if candidate_id in selected:
            continue
        parent = candidates[candidate_id].relationship_parent_candidate_id
        bundle = {candidate_id}
        if parent is not None:
            bundle.add(parent)
        elif children_by_parent.get(candidate_id):
            bundle.add(children_by_parent[candidate_id][0])
        proposed = selected | bundle
        selected_order = tuple(item for item in effective_order if item in proposed)
        optional_order = tuple(item for item in selected_order if item not in required_set)
        candidate_payload = _ranked_payload(
            task,
            snapshot,
            candidate_set_sha256,
            query_sha256,
            approved_request_sha256,
            order_source,
            selected_order,
            required_ids,
            optional_order,
            spans,
        )
        if _payload_byte_count(candidate_payload) <= task.byte_budget:
            selected = proposed
            payload = candidate_payload
    selected_order = tuple(item for item in effective_order if item in selected)
    optional_order = tuple(item for item in selected_order if item not in required_set)
    return _ranked_projection(
        payload,
        selected_order,
        required_ids,
        optional_order,
    )


def _ranked_priority_order(
    baseline_order: tuple[str, ...],
    required_ids: tuple[str, ...],
    candidates: dict[str, RankedContextCandidate],
    candidate_id: str,
) -> tuple[str, ...]:
    required = set(required_ids)
    parent = candidates[candidate_id].relationship_parent_candidate_id
    priority = tuple(
        item
        for item in (parent, candidate_id)
        if item is not None and item not in required
    )
    optional = list(dict.fromkeys((
        *priority,
        *(item for item in baseline_order if item not in required),
    )))
    iterator = iter(optional)
    return tuple(
        candidate_id if candidate_id in required else next(iterator)
        for candidate_id in baseline_order
    )


def _has_verified_relationship_edge(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    parent: RankedContextCandidate,
    candidate: RankedContextCandidate,
) -> bool:
    metadata_bound = candidate.relationship_edge_id is not None
    records = graph.record_map()
    sensitivity_rank = {
        Sensitivity.PUBLIC: 0,
        Sensitivity.INTERNAL: 1,
        Sensitivity.RESTRICTED: 2,
    }
    for edge in graph.edges:
        source = edge.source_coordinate
        target = edge.target_coordinate
        direction = candidate.relationship_direction or "outgoing"
        expected_source = parent if direction == "outgoing" else candidate
        expected_target = candidate if direction == "outgoing" else parent
        source_record = records.get(edge.source_id)
        target_record = records.get(edge.target_id)
        if (
            (not metadata_bound or edge.edge_id == candidate.relationship_edge_id)
            and (not metadata_bound or edge.relation == candidate.relationship_relation)
            and (not metadata_bound or edge.sensitivity is candidate.relationship_sensitivity)
            and (direction != "incoming" or edge.relation in _REVERSE_RELATIONS)
            and edge.source_id == expected_source.record_id
            and edge.target_id == expected_target.record_id
            and is_authenticated_eligible(edge, task.allowed_sensitivities)
            and source_record is not None
            and target_record is not None
            and is_authenticated_eligible(source_record, task.allowed_sensitivities)
            and is_authenticated_eligible(target_record, task.allowed_sensitivities)
            and edge.sensitivity is max(
                (source_record.sensitivity, target_record.sensitivity),
                key=sensitivity_rank.__getitem__,
            )
            and source is not None
            and target is not None
            and source.snapshot_sha256 == snapshot.snapshot_sha256
            and target.snapshot_sha256 == snapshot.snapshot_sha256
            and (source.source_path, source.source_sha256)
            == (expected_source.source_path, expected_source.source_sha256)
            and (target.source_path, target.source_sha256)
            == (expected_target.source_path, expected_target.source_sha256)
            and expected_source.byte_start <= source.byte_start
            and source.byte_end <= expected_source.byte_end
            and expected_target.byte_start <= target.byte_start
            and target.byte_end <= expected_target.byte_end
        ):
            return True
    return False


def _valid_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA256_LENGTH
        and not any(character not in "0123456789abcdef" for character in value)
    )


def _controlled_jev_order(
    observation: Any,
    baseline_order: tuple[str, ...],
    required_ids: tuple[str, ...],
    candidate_set_sha256: str,
    query_sha256: str,
    source_set_sha256: str,
    approved_request_sha256: str | None,
) -> tuple[str, ...] | None:
    if type(observation) is not dict:
        return None
    if (
        observation.get("schema_version") != "velgraphing-jev-observation-v1"
        or observation.get("status") != "reranked"
        or observation.get("mode") != "rerank"
        or observation.get("authority_bearing") is not False
        or observation.get("sufficient") is not False
        or observation.get("source_revalidated") is not True
        or observation.get("baseline_order") != list(baseline_order)
        or observation.get("required_ids") != list(required_ids)
        or observation.get("candidate_set_sha256") != candidate_set_sha256
        or observation.get("query_sha256") != query_sha256
        or observation.get("source_set_sha256") != source_set_sha256
        or observation.get("request_sha256") != approved_request_sha256
    ):
        return None
    order = observation.get("order")
    if (
        type(order) is not list
        or any(type(candidate_id) is not str for candidate_id in order)
        or len(order) != len(baseline_order)
        or len(set(order)) != len(order)
        or set(order) != set(baseline_order)
    ):
        return None
    required = set(required_ids)
    if any(
        candidate_id in required and order[index] != candidate_id
        for index, candidate_id in enumerate(baseline_order)
    ):
        return None
    return tuple(order)


def _controlled_classification_order(
    observation: Any,
    baseline_order: tuple[str, ...],
    required_ids: tuple[str, ...],
    candidate_set_sha256: str,
    query_sha256: str,
    source_set_sha256: str,
    approved_request_sha256: str | None,
) -> tuple[str, ...] | None:
    if type(observation) is not dict or set(observation) != {
        "schema_version",
        "status",
        "candidate_set_sha256",
        "query_sha256",
        "source_set_sha256",
        "baseline_order",
        "proposed_order",
        "required_ids",
        "request_sha256",
        "source_revalidated",
        "authority_bearing",
        "sufficient",
    } or observation.get("schema_version") != _CLASSIFICATION_OBSERVATION_SCHEMA:
        return None
    native_observation = {
        "schema_version": "velgraphing-jev-observation-v1",
        "status": observation["status"],
        "mode": "rerank",
        "authority_bearing": observation["authority_bearing"],
        "sufficient": observation["sufficient"],
        "source_revalidated": observation["source_revalidated"],
        "baseline_order": observation["baseline_order"],
        "required_ids": observation["required_ids"],
        "order": observation["proposed_order"],
        "candidate_set_sha256": observation["candidate_set_sha256"],
        "query_sha256": observation["query_sha256"],
        "source_set_sha256": observation["source_set_sha256"],
        "request_sha256": observation["request_sha256"],
    }
    return _controlled_jev_order(
        native_observation,
        baseline_order,
        required_ids,
        candidate_set_sha256,
        query_sha256,
        source_set_sha256,
        approved_request_sha256,
    )


def _ranked_payload(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    candidate_set_sha256: str,
    query_sha256: str,
    approved_request_sha256: str | None,
    order_source: str,
    selected_ids: tuple[str, ...],
    required_ids: tuple[str, ...],
    optional_ids: tuple[str, ...],
    spans: dict[str, dict[str, object]],
) -> dict[str, object]:
    source_order: dict[object, int] = {}
    for candidate_id in selected_ids:
        source_order.setdefault(spans[candidate_id]["source_path"], len(source_order))
    presentation_ids = sorted(
        selected_ids,
        key=lambda candidate_id: (
            source_order[spans[candidate_id]["source_path"]],
            spans[candidate_id]["byte_start"],
            spans[candidate_id]["byte_end"],
            candidate_id,
        ),
    )
    payload: dict[str, object] = {
        "candidate_set_sha256": candidate_set_sha256,
        "fail_closed": False,
        "included_optional_candidate_ids": list(optional_ids),
        "order_source": order_source,
        "query_sha256": query_sha256,
        "reason": "verified_ranked_context_selected",
        "required_candidate_ids": list(required_ids),
        "schema_version": "graph-ranked-context-baseline-v1",
        "selected_candidate_ids": list(selected_ids),
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "spans": [spans[candidate_id] for candidate_id in presentation_ids],
        "task_id": task.task_id,
    }
    if order_source == "reranked":
        if not _valid_digest(approved_request_sha256):
            raise ValueError("reranked context requires an approved request SHA-256")
        payload["approved_request_sha256"] = approved_request_sha256
        payload["schema_version"] = "graph-ranked-context-v1"
    return payload


def _ranked_projection(
    payload: dict[str, object],
    selected_ids: tuple[str, ...],
    required_ids: tuple[str, ...],
    optional_ids: tuple[str, ...],
) -> RankedContextProjection:
    content = _canonical_json(payload)
    spans = payload.get("spans", [])
    excerpt_bytes = sum(
        span["byte_end"] - span["byte_start"] for span in spans  # type: ignore[index,operator]
    )
    return RankedContextProjection(
        content=content,
        serialized_byte_count=len(content.encode("utf-8")),
        excerpt_byte_count=excerpt_bytes,
        selected_candidate_ids=selected_ids,
        required_candidate_ids=required_ids,
        included_optional_candidate_ids=optional_ids,
        fail_closed=bool(payload["fail_closed"]),
        reason=str(payload["reason"]),
    )


def _ranked_defer(
    task: TaskSpec,
    candidate_set_sha256: str,
    approved_request_sha256: str | None,
    required_ids: tuple[str, ...],
    reason: str,
    jev_decision: RankedContextJevDecision,
    *,
    source_revalidated: bool = False,
) -> RankedContextResult:
    payload = {
        "fail_closed": True,
        "reason": reason,
        "schema_version": "graph-ranked-context-v1",
        "spans": [],
    }
    content = _canonical_json(payload)
    if len(content.encode("utf-8")) > task.byte_budget:
        content = ""
    projection = RankedContextProjection(
        content=content,
        serialized_byte_count=len(content.encode("utf-8")),
        excerpt_byte_count=0,
        selected_candidate_ids=(),
        required_candidate_ids=required_ids,
        included_optional_candidate_ids=(),
        fail_closed=True,
        reason=reason,
    )
    return RankedContextResult(
        route="defer",
        reason=reason,
        order_source="baseline",
        candidate_set_sha256=candidate_set_sha256,
        approved_request_sha256=None,
        jev_source_revalidated=False,
        source_revalidated=source_revalidated,
        projection=projection,
        jev_decision=jev_decision,
    )


def _ranked_required_fallback(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    candidates: tuple[RankedContextCandidate, ...],
    required_ids: tuple[str, ...],
    candidate_set_sha256: str,
    approved_request_sha256: str | None,
    graph: Graph,
    fallback_source_paths: tuple[str, ...],
    jev_decision: RankedContextJevDecision,
) -> RankedContextResult:
    required_paths = tuple(sorted({
        candidate.source_path for candidate in candidates if candidate.required
    }))
    if (
        not required_paths
        or not _valid_required_source_paths(fallback_source_paths)
        or not set(required_paths).issubset(fallback_source_paths)
    ):
        return _ranked_defer(
            task, candidate_set_sha256, approved_request_sha256, required_ids,
            "required_context_exceeds_byte_budget", jev_decision,
            source_revalidated=True,
        )
    try:
        direct = assist(
            graph,
            task,
            snapshot,
            reader,
            required_source_paths=required_paths,
            fallback_source_paths=fallback_source_paths,
            required_escalation=True,
        )
    except Exception:
        return _ranked_defer(
            task, candidate_set_sha256, approved_request_sha256, required_ids,
            "required_context_fallback_unavailable", jev_decision,
            source_revalidated=True,
        )
    if direct.route != "direct" or direct.projection.fail_closed:
        return _ranked_defer(
            task, candidate_set_sha256, approved_request_sha256, required_ids,
            "required_context_fallback_unavailable", jev_decision,
            source_revalidated=True,
        )
    payload = json.loads(direct.projection.content)
    excerpt_bytes = sum(document["byte_count"] for document in payload["documents"])
    projection = RankedContextProjection(
        content=direct.projection.content,
        serialized_byte_count=direct.projection.byte_count,
        excerpt_byte_count=excerpt_bytes,
        selected_candidate_ids=(),
        required_candidate_ids=required_ids,
        included_optional_candidate_ids=(),
        fail_closed=False,
        reason=direct.projection.reason,
    )
    return RankedContextResult(
        route="direct",
        reason="required_context_direct_fallback",
        order_source="direct",
        candidate_set_sha256=candidate_set_sha256,
        approved_request_sha256=None,
        jev_source_revalidated=False,
        source_revalidated=True,
        projection=projection,
        jev_decision=jev_decision,
    )


def assist(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    required_source_paths: tuple[str, ...] = (),
    fallback_source_paths: tuple[str, ...] = (),
    required_escalation: bool = False,
) -> AssistResult:
    """Return verified graph context or conservatively defer."""

    if type(required_escalation) is not bool:
        return _fallback_defer(task, snapshot, "invalid_required_escalation")

    if not _valid_required_source_paths(required_source_paths):
        projection = _document_failure_projection(
            task,
            snapshot,
            (),
            "invalid_required_source_paths",
        )
        return AssistResult(
            route="defer",
            reason="invalid_required_source_paths",
            projection=projection,
        )

    if required_escalation:
        escalated = _direct_fallback(
            graph,
            task,
            snapshot,
            reader,
            required_source_paths,
            fallback_source_paths,
        )
        if escalated.route == "direct":
            return AssistResult(
                route="direct",
                reason="required_escalation",
                projection=escalated.projection,
            )
        return AssistResult(
            route="defer",
            reason="required_escalation_unavailable",
            projection=escalated.projection,
        )

    try:
        projection = select_documents(graph, task, snapshot, reader)
    except (KeyError, OSError, UnicodeError, ValueError):
        projection = _document_failure_projection(
            task,
            snapshot,
            (),
            "graph_projection_unavailable",
        )
    if projection.fail_closed or not projection.required_record_ids:
        graph_result = AssistResult(
            route="defer",
            reason="graph_projection_unavailable",
            projection=projection,
        )
    else:
        payload = json.loads(projection.content)
        selected_source_paths = {
            document["source_path"] for document in payload["documents"]
        }
        if set(required_source_paths).issubset(selected_source_paths):
            return AssistResult(
                route="graph",
                reason="required_sources_selected",
                projection=projection,
            )
        graph_result = AssistResult(
            route="defer",
            reason="required_sources_missing",
            projection=projection,
        )

    if not fallback_source_paths:
        return graph_result
    return _direct_fallback(
        graph,
        task,
        snapshot,
        reader,
        required_source_paths,
        fallback_source_paths,
    )


def observe_assist(
    result: AssistResult,
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    *,
    required_source_paths: tuple[str, ...],
    fallback_source_paths: tuple[str, ...] = (),
) -> AssistObservation:
    """Derive deterministic source-bound telemetry without reading source files."""

    if type(result) is not AssistResult:
        raise TypeError("result must be an exact AssistResult")
    if type(graph) is not Graph:
        raise TypeError("graph must be an exact Graph")
    if type(task) is not TaskSpec:
        raise TypeError("task must be an exact TaskSpec")
    if type(snapshot) is not SourceSnapshotV4:
        raise TypeError("snapshot must be an exact SourceSnapshotV4")
    required_paths = _observation_paths(required_source_paths, "required_source_paths")
    fallback_paths = _observation_paths(fallback_source_paths, "fallback_source_paths")
    selected_paths = _selected_source_paths(result)
    if result.route not in {"graph", "direct", "defer"}:
        raise ValueError("assist route is not recognized")
    if result.reason not in _ASSIST_REASONS:
        raise ValueError("assist reason is not a stable core reason")
    return AssistObservation(
        schema_version=_ASSIST_OBSERVATION_SCHEMA_VERSION,
        task_id=task.task_id,
        source_snapshot_sha256=snapshot.snapshot_sha256,
        route=result.route,
        reason=result.reason,
        failure_class=_assist_failure_class(
            result,
            graph,
            task,
            snapshot,
            required_paths,
        ),
        required_source_paths=required_paths,
        fallback_source_paths=fallback_paths,
        selected_source_paths=selected_paths,
        context_bytes=result.projection.byte_count,
        fail_closed=result.projection.fail_closed,
    )


def _observation_paths(paths: object, label: str) -> tuple[str, ...]:
    if type(paths) is not tuple or any(type(path) is not str for path in paths):
        raise TypeError(f"{label} must be a tuple of strings")
    return tuple(sorted(set(paths)))


def _selected_source_paths(result: AssistResult) -> tuple[str, ...]:
    try:
        payload = json.loads(result.projection.content)
        documents = payload.get("documents", [])
        if type(documents) is not list:
            raise ValueError("assist projection documents must be a list")
        paths = tuple(document["source_path"] for document in documents)
    except (AttributeError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("assist projection must contain valid document metadata") from error
    if any(type(path) is not str for path in paths):
        raise ValueError("selected source paths must be strings")
    return tuple(sorted(set(paths)))


def _assist_failure_class(
    result: AssistResult,
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    required_paths: tuple[str, ...],
) -> str:
    if result.reason in {"required_escalation", "required_escalation_unavailable"}:
        return "required_escalation"
    if result.route == "graph":
        return "none"

    snapshot_sources = {source.path: source for source in snapshot.sources}
    records_by_path = {
        path: tuple(record for record in graph.records if record.provenance.path == path)
        for path in required_paths
    }
    if any(path not in snapshot_sources or not records_by_path[path] for path in required_paths):
        return "missing_knowledge"
    if any(
        all(record.freshness is not Freshness.CURRENT for record in records_by_path[path])
        for path in required_paths
    ):
        return "freshness_failure"

    selection = select(graph, task)
    considered_ids = set(selection.full_graph_record_ids) | set(selection.authenticated_record_ids)
    if any(
        record.record_id in considered_ids and record.freshness is not Freshness.CURRENT
        for record in graph.records
    ):
        return "freshness_failure"
    if selection.fail_closed:
        return "selection_failure"

    selected_records = tuple(
        record for record in graph.records if record.record_id in selection.record_ids
    )
    if any(
        len(record.content.encode("utf-8")) != snapshot_sources[record.provenance.path].byte_length
        for record in selected_records
        if record.provenance.path in snapshot_sources
    ):
        return "granularity_failure"
    selected_paths = {record.provenance.path for record in selected_records}
    if not set(required_paths).issubset(selected_paths):
        return "relationship_failure"
    if result.projection.reason == "selected_record_not_source_complete":
        return "granularity_failure"
    return "selection_failure"


def _valid_required_source_paths(required_source_paths: object) -> bool:
    if type(required_source_paths) is not tuple or not required_source_paths:
        return False
    if any(type(path) is not str for path in required_source_paths):
        return False
    if (
        required_source_paths != tuple(sorted(required_source_paths))
        or len(required_source_paths) != len(set(required_source_paths))
    ):
        return False
    try:
        for path in required_source_paths:
            _require_relative_path(path)
    except (TypeError, ValueError):
        return False
    return True


def _direct_fallback(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    required_source_paths: tuple[str, ...],
    fallback_source_paths: object,
) -> AssistResult:
    if not _valid_required_source_paths(fallback_source_paths):
        return _fallback_defer(task, snapshot, "invalid_fallback_source_paths")
    if not set(required_source_paths).issubset(fallback_source_paths):
        return _fallback_defer(task, snapshot, "fallback_sources_incomplete")

    snapshot_sources = {source.path: source for source in snapshot.sources}
    candidate_records_by_path: dict[str, tuple[GraphRecord, ...]] = {}
    for path in fallback_source_paths:
        source = snapshot_sources.get(path)
        if source is None:
            return _fallback_defer(task, snapshot, "fallback_sources_unavailable")
        candidates = tuple(
            record
            for record in graph.records
            if record.provenance.path == path
            and record.provenance.sha256 == source.sha256
            and is_authenticated_eligible(record, task.allowed_sensitivities)
        )
        if not candidates:
            return _fallback_defer(task, snapshot, "fallback_sources_unavailable")
        candidate_records_by_path[path] = candidates

    selected_snapshot = SourceSnapshotV4(
        tuple(snapshot_sources[path] for path in fallback_source_paths)
    )
    try:
        source_bytes = _read_verified_source_bytes(selected_snapshot, reader)
        record_ids_by_path = {
            path: tuple(
                sorted(
                    record.record_id
                    for record in candidate_records_by_path[path]
                    if record.content.encode("utf-8") == source_bytes[path]
                )
            )
            for path in fallback_source_paths
        }
        documents = tuple(
            _direct_document_payload(
                path,
                source_bytes[path],
                snapshot_sources[path],
                record_ids_by_path[path],
            )
            for path in fallback_source_paths
        )
    except (KeyError, OSError, UnicodeError, ValueError):
        return _fallback_defer(task, snapshot, "fallback_sources_unreadable")
    if any(not record_ids for record_ids in record_ids_by_path.values()):
        return _fallback_defer(task, snapshot, "fallback_sources_unavailable")

    required_ids = tuple(
        sorted(
            record_id
            for record_ids in record_ids_by_path.values()
            for record_id in record_ids
        )
    )
    payload = _document_payload(
        task,
        snapshot,
        required_ids,
        documents,
        fail_closed=False,
        reason="verified_direct_context_selected",
    )
    if _payload_byte_count(payload) > task.byte_budget:
        return _fallback_defer(
            task,
            snapshot,
            "fallback_context_exceeds_byte_budget",
        )
    return AssistResult(
        route="direct",
        reason="required_sources_direct",
        projection=_projection(payload, required_ids, ()),
    )


def _direct_document_payload(
    path: str,
    raw: bytes,
    source: SourceIdentityV4,
    record_ids: tuple[str, ...],
) -> dict[str, object]:
    content = raw.decode("utf-8")
    if content.encode("utf-8") != raw:
        raise ValueError("fallback source must round-trip as exact UTF-8")
    return {
        "byte_count": len(raw),
        "content": content,
        "record_ids": list(record_ids),
        "source_path": path,
        "source_sha256": source.sha256,
    }


def _fallback_defer(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reason: str,
) -> AssistResult:
    return AssistResult(
        route="defer",
        reason=reason,
        projection=_document_failure_projection(task, snapshot, (), reason),
    )


def select_context(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    required: tuple[ContextSpan, ...],
    optional: tuple[ContextSpan, ...] = (),
) -> ContextProjection:
    """Select a bounded context made only from verified source byte spans."""

    required_spans = _validate_spans(required, "required")
    optional_spans = _validate_spans(optional, "optional")
    if len(set((*required_spans, *optional_spans))) != len(required_spans) + len(optional_spans):
        raise ValueError("context spans must be unique")

    required_ids = tuple(sorted({span.record_id for span in required_spans}))
    selection = select(graph, task)
    if selection.fail_closed:
        return _failure_projection(task, snapshot, required_ids, "selection_fail_closed")
    if any(record_id not in required_ids for record_id in selection.record_ids):
        return _failure_projection(
            task,
            snapshot,
            required_ids,
            "selected_root_missing_required_span",
        )

    records = graph.record_map()
    for record_id in required_ids:
        record = records.get(record_id)
        if record is None or not is_authenticated_eligible(record, task.allowed_sensitivities):
            return _failure_projection(
                task,
                snapshot,
                required_ids,
                "required_record_not_authenticated",
            )

    source_bytes = _read_verified_source_bytes(snapshot, reader)
    sources = {source.path: source for source in snapshot.sources}
    required_payload_spans = tuple(
        _verified_span_payload(span, records, sources, source_bytes)
        for span in required_spans
    )
    payload = _context_payload(
        task,
        snapshot,
        required_ids,
        (),
        required_payload_spans,
        fail_closed=False,
        reason="verified_context_selected",
    )
    if _payload_byte_count(payload) > task.byte_budget:
        return _failure_projection(
            task,
            snapshot,
            required_ids,
            "required_context_exceeds_byte_budget",
        )

    accepted_optional: list[dict[str, object]] = []
    accepted_optional_ids: set[str] = set()
    for span in optional_spans:
        record = records.get(span.record_id)
        if record is None or not is_authenticated_eligible(record, task.allowed_sensitivities):
            continue
        candidate_span = _verified_span_payload(span, records, sources, source_bytes)
        candidate_ids = tuple(sorted(accepted_optional_ids | {span.record_id}))
        candidate_payload = _context_payload(
            task,
            snapshot,
            required_ids,
            candidate_ids,
            (*required_payload_spans, *accepted_optional, candidate_span),
            fail_closed=False,
            reason="verified_context_selected",
        )
        if _payload_byte_count(candidate_payload) <= task.byte_budget:
            accepted_optional.append(candidate_span)
            accepted_optional_ids.add(span.record_id)
            payload = candidate_payload

    return _projection(payload, required_ids, tuple(sorted(accepted_optional_ids)))


def select_documents(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
) -> ContextProjection:
    """Select whole verified source documents for authenticated records."""

    if type(snapshot) is not SourceSnapshotV4:
        raise TypeError("snapshot must be an exact SourceSnapshotV4")

    selection = select(graph, task)
    required_ids = tuple(sorted(selection.record_ids))
    if selection.fail_closed:
        return _document_failure_projection(
            task,
            snapshot,
            required_ids,
            "selection_fail_closed",
        )
    if not required_ids:
        payload = _document_payload(
            task,
            snapshot,
            required_ids,
            (),
            fail_closed=False,
            reason="verified_context_selected",
        )
        if _payload_byte_count(payload) > task.byte_budget:
            return _document_failure_projection(
                task,
                snapshot,
                required_ids,
                "required_context_exceeds_byte_budget",
            )
        return _projection(payload, required_ids, ())

    records = graph.record_map()
    snapshot_sources = {source.path: source for source in snapshot.sources}
    selected_records: list[GraphRecord] = []
    sensitivities: dict[str, object] = {}
    selected_paths: set[str] = set()
    for record_id in required_ids:
        record = records[record_id]
        source = snapshot_sources.get(record.provenance.path)
        if source is None or record.provenance.sha256 != source.sha256:
            raise ValueError("selected record provenance does not match snapshot")
        prior_sensitivity = sensitivities.get(source.path)
        if prior_sensitivity is not None and prior_sensitivity is not record.sensitivity:
            return _document_failure_projection(
                task,
                snapshot,
                required_ids,
                "selected_source_sensitivity_conflict",
            )
        sensitivities[source.path] = record.sensitivity
        selected_records.append(record)
        selected_paths.add(source.path)

    selected_snapshot = SourceSnapshotV4(
        tuple(snapshot_sources[path] for path in sorted(selected_paths))
    )
    source_bytes = _read_verified_source_bytes(selected_snapshot, reader)
    source_content: dict[str, str] = {}
    for path in sorted(selected_paths):
        raw = source_bytes[path]
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("selected source must be exact UTF-8") from error
        if content.encode("utf-8") != raw:
            raise ValueError("selected source must round-trip as exact UTF-8")
        source_content[path] = content

    record_ids_by_path: dict[str, list[str]] = {path: [] for path in selected_paths}
    for record in selected_records:
        try:
            record_bytes = record.content.encode("utf-8")
        except (AttributeError, UnicodeEncodeError) as error:
            raise ValueError("selected record content must be exact UTF-8") from error
        path = record.provenance.path
        if record_bytes != source_bytes[path]:
            return _document_failure_projection(
                task,
                snapshot,
                required_ids,
                "selected_record_not_source_complete",
            )
        record_ids_by_path[path].append(record.record_id)

    documents = tuple(
        {
            "byte_count": len(source_bytes[path]),
            "content": source_content[path],
            "record_ids": sorted(record_ids_by_path[path]),
            "source_path": path,
            "source_sha256": snapshot_sources[path].sha256,
        }
        for path in sorted(selected_paths)
    )
    payload = _document_payload(
        task,
        snapshot,
        required_ids,
        documents,
        fail_closed=False,
        reason="verified_context_selected",
    )
    if _payload_byte_count(payload) > task.byte_budget:
        return _document_failure_projection(
            task,
            snapshot,
            required_ids,
            "required_context_exceeds_byte_budget",
        )
    return _projection(payload, required_ids, ())


def _validate_spans(spans: object, label: str) -> tuple[ContextSpan, ...]:
    if type(spans) is not tuple or any(type(span) is not ContextSpan for span in spans):
        raise TypeError(f"{label} spans must be a tuple of exact ContextSpan values")
    return tuple(sorted(spans, key=lambda span: (span.record_id, span.byte_start, span.byte_end, span.excerpt_sha256)))


def _verified_span_payload(
    span: ContextSpan,
    records: dict[str, GraphRecord],
    sources: dict[str, object],
    source_bytes: dict[str, bytes],
) -> dict[str, object]:
    record = records.get(span.record_id)
    if record is None:
        raise ValueError("context span record does not exist")
    source = sources.get(record.provenance.path)
    if source is None or record.provenance.sha256 != source.sha256:
        raise ValueError("context record provenance does not match snapshot")
    raw = source_bytes[record.provenance.path]
    if span.byte_end > len(raw):
        raise ValueError("context byte range exceeds source")
    excerpt = raw[span.byte_start:span.byte_end]
    if hashlib.sha256(excerpt).hexdigest() != span.excerpt_sha256:
        raise ValueError("context excerpt does not match source bytes")
    try:
        content = excerpt.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("context excerpt must be exact UTF-8") from error
    if content.encode("utf-8") != excerpt:
        raise ValueError("context excerpt must round-trip as exact UTF-8")
    return {
        "byte_end": span.byte_end,
        "byte_start": span.byte_start,
        "content": content,
        "excerpt_sha256": span.excerpt_sha256,
        "record_id": span.record_id,
        "source_path": record.provenance.path,
        "source_sha256": record.provenance.sha256,
    }


def _context_payload(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    required_ids: tuple[str, ...],
    optional_ids: tuple[str, ...],
    spans: tuple[dict[str, object], ...],
    *,
    fail_closed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "fail_closed": fail_closed,
        "included_optional_record_ids": list(optional_ids),
        "reason": reason,
        "required_record_ids": list(required_ids),
        "schema_version": "graph-source-context-v1",
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "spans": list(spans),
        "task_id": task.task_id,
    }


def _document_payload(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    required_ids: tuple[str, ...],
    documents: tuple[dict[str, object], ...],
    *,
    fail_closed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "documents": list(documents),
        "fail_closed": fail_closed,
        "included_optional_record_ids": [],
        "reason": reason,
        "required_record_ids": list(required_ids),
        "schema_version": "graph-source-context-v2",
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "task_id": task.task_id,
    }


def _document_failure_projection(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    required_ids: tuple[str, ...],
    reason: str,
) -> ContextProjection:
    payload = _document_payload(
        task,
        snapshot,
        required_ids,
        (),
        fail_closed=True,
        reason=reason,
    )
    if _payload_byte_count(payload) > task.byte_budget:
        raise ValueError("context failure envelope exceeds byte budget")
    return _projection(payload, required_ids, ())


def _failure_projection(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    required_ids: tuple[str, ...],
    reason: str,
) -> ContextProjection:
    payload = _context_payload(
        task,
        snapshot,
        required_ids,
        (),
        (),
        fail_closed=True,
        reason=reason,
    )
    if _payload_byte_count(payload) > task.byte_budget:
        raise ValueError("context failure envelope exceeds byte budget")
    return _projection(payload, required_ids, ())


def _payload_byte_count(payload: dict[str, object]) -> int:
    return len(_canonical_json(payload).encode("utf-8"))


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _projection(
    payload: dict[str, object],
    required_ids: tuple[str, ...],
    optional_ids: tuple[str, ...],
) -> ContextProjection:
    content = _canonical_json(payload)
    return ContextProjection(
        content=content,
        byte_count=len(content.encode("utf-8")),
        required_record_ids=required_ids,
        included_optional_record_ids=optional_ids,
        fail_closed=bool(payload["fail_closed"]),
        reason=str(payload["reason"]),
    )


def select(graph: Graph, task: TaskSpec) -> SelectionResult:
    """Select only when full and authenticated projections agree.

    The full projection is diagnostic. Its records never become output. Any
    difference in consequential record identity causes an empty result.
    """

    full_records, _, _, _ = _project(graph, task, authenticated_only=False)
    auth_records, auth_edges, depth, scores = _project(
        graph, task, authenticated_only=True
    )
    full_ids = tuple(record.record_id for record in full_records)
    auth_ids = tuple(record.record_id for record in auth_records)
    selections_diverge = full_ids != auth_ids
    divergent_set = set(full_ids).symmetric_difference(auth_ids)
    if selections_diverge and not divergent_set:
        divergent_set.update(full_ids)
    divergent = tuple(sorted(divergent_set))
    if selections_diverge:
        return SelectionResult(
            task_id=task.task_id,
            record_ids=(),
            edge_ids=(),
            full_graph_record_ids=full_ids,
            authenticated_record_ids=auth_ids,
            divergent_record_ids=divergent,
            fail_closed=True,
            reason="full_graph_authenticated_subgraph_divergence",
            depth_reached=depth,
            scores=(),
        )
    return SelectionResult(
        task_id=task.task_id,
        record_ids=auth_ids,
        edge_ids=tuple(edge.edge_id for edge in auth_edges),
        full_graph_record_ids=full_ids,
        authenticated_record_ids=auth_ids,
        divergent_record_ids=(),
        fail_closed=False,
        reason="authenticated_projection_selected",
        depth_reached=depth,
        scores=tuple((record.record_id, scores[record.record_id]) for record in auth_records),
    )


def _project(
    graph: Graph,
    task: TaskSpec,
    *,
    authenticated_only: bool,
) -> tuple[list[GraphRecord], list[GraphEdge], int, dict[str, float]]:
    records = graph.record_map()
    allowed_records = {
        record.record_id: record
        for record in graph.records
        if not authenticated_only
        or is_authenticated_eligible(record, task.allowed_sensitivities)
    }
    allowed_edges = [
        edge
        for edge in graph.edges
        if edge.source_id in allowed_records
        and edge.target_id in allowed_records
        and (
            not authenticated_only
            or is_authenticated_eligible(edge, task.allowed_sensitivities)
        )
    ]
    scores = {
        record_id: _record_score(record, task)
        for record_id, record in allowed_records.items()
    }
    seeds = sorted(
        (
            record_id
            for record_id, score in scores.items()
            if score >= task.minimum_relevance
        ),
        key=lambda record_id: (-scores[record_id], record_id),
    )
    if not seeds and allowed_records:
        seeds = [min(allowed_records)]

    selected: set[str] = set(seeds[: task.node_budget])
    selected_edges: set[str] = set()
    frontier = list(seeds[: task.node_budget])
    depth_reached = 0
    for depth in range(1, task.max_depth + 1):
        if not frontier or len(selected) >= task.node_budget:
            break
        threshold = min(1.0, task.minimum_relevance + (depth - 1) * 0.1)
        candidates: list[tuple[float, str, GraphEdge]] = []
        frontier_set = set(frontier)
        for edge in allowed_edges:
            neighbor = None
            if edge.source_id in frontier_set:
                neighbor = edge.target_id
            elif edge.target_id in frontier_set:
                neighbor = edge.source_id
            if neighbor is None or neighbor in selected or edge.relevance < threshold:
                continue
            combined = round(edge.relevance * 0.7 + scores[neighbor] * 0.3, 12)
            candidates.append((combined, neighbor, edge))
        candidates.sort(key=lambda value: (-value[0], value[1], value[2].edge_id))
        next_frontier: list[str] = []
        for combined, neighbor, edge in candidates:
            if len(selected) >= task.node_budget:
                break
            if neighbor in selected:
                continue
            selected.add(neighbor)
            next_frontier.append(neighbor)
            selected_edges.add(edge.edge_id)
            scores[neighbor] = max(scores[neighbor], combined)
        frontier = next_frontier
        if frontier:
            depth_reached = depth

    ordered_records = sorted(
        (records[record_id] for record_id in selected),
        key=lambda record: (-scores[record.record_id], record.record_id),
    )
    selected_edges.update(
        edge.edge_id
        for edge in allowed_edges
        if edge.source_id in selected and edge.target_id in selected
    )
    ordered_edges = sorted(
        (edge for edge in allowed_edges if edge.edge_id in selected_edges),
        key=lambda edge: (-edge.relevance, edge.relation, edge.edge_id),
    )
    return ordered_records, ordered_edges, depth_reached, scores


def _record_score(record: GraphRecord, task: TaskSpec) -> float:
    terms = tuple(term.casefold() for term in task.query_terms if term.strip())
    if not terms:
        return 1.0
    fields = " ".join((record.kind, record.title, record.content, *record.tags)).casefold()
    matches = sum(1 for term in terms if term in fields)
    return round(matches / len(terms), 12)
