"""Explicit, default-deny graph export."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Graph, Sensitivity, is_authenticated_eligible


@dataclass(frozen=True)
class ExportPolicy:
    enabled: bool = False
    record_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    allowed_sensitivities: tuple[Sensitivity, ...] = (Sensitivity.PUBLIC,)


@dataclass(frozen=True)
class ExportResult:
    allowed: bool
    reason: str
    payload: dict[str, object]


def export_graph(graph: Graph, policy: ExportPolicy | None = None) -> ExportResult:
    if policy is None or not policy.enabled:
        return ExportResult(False, "export_default_deny", {})
    records = graph.record_map()
    edges = graph.edge_map()
    requested_records = set(policy.record_ids)
    requested_edges = set(policy.edge_ids)
    if requested_records - records.keys() or requested_edges - edges.keys():
        return ExportResult(False, "unknown_export_identity", {})
    selected_records = [records[item_id] for item_id in sorted(requested_records)]
    selected_edges = [edges[item_id] for item_id in sorted(requested_edges)]
    if any(
        not item.export_allowed
        or not is_authenticated_eligible(item, policy.allowed_sensitivities)
        for item in (*selected_records, *selected_edges)
    ):
        return ExportResult(False, "export_item_not_authorized", {})
    if any(
        edge.source_id not in requested_records or edge.target_id not in requested_records
        for edge in selected_edges
    ):
        return ExportResult(False, "export_edge_endpoint_missing", {})
    return ExportResult(
        True,
        "explicit_export_allowed",
        {
            "schema_version": "graph-export-v1",
            "records": [record.to_dict() for record in selected_records],
            "edges": [edge.to_dict() for edge in selected_edges],
        },
    )
