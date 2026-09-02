"""Budgeted task- and topology-aware deterministic serialization."""

from __future__ import annotations

from dataclasses import dataclass
import json

from .models import Graph, GraphRecord, TaskSpec, Topology
from .selection import SelectionResult


@dataclass(frozen=True)
class SerializedProjection:
    content: str
    byte_count: int
    included_record_ids: tuple[str, ...]
    omitted_record_ids: tuple[str, ...]


def serialize_projection(
    graph: Graph, task: TaskSpec, selection: SelectionResult
) -> SerializedProjection:
    record_map = graph.record_map()
    edge_map = graph.edge_map()
    if selection.fail_closed:
        payload = {
            "schema_version": "graph-projection-v1",
            "task_id": task.task_id,
            "topology": task.topology.value,
            "fail_closed": True,
            "reason": selection.reason,
            "divergent_record_ids": list(selection.divergent_record_ids),
            "records": [],
            "edges": [],
        }
        content = _canonical_json(payload)
        if len(content.encode("utf-8")) > task.byte_budget:
            raise ValueError("byte budget cannot hold the fail-closed envelope")
        return SerializedProjection(content, len(content.encode("utf-8")), (), ())

    ordered = _topology_order(
        [record_map[record_id] for record_id in selection.record_ids], task
    )
    included = list(ordered)
    omitted: list[GraphRecord] = []
    while True:
        included_ids = {record.record_id for record in included}
        payload = {
            "schema_version": "graph-projection-v1",
            "task_id": task.task_id,
            "topology": task.topology.value,
            "fail_closed": False,
            "records": [record.to_dict() for record in included],
            "edges": [
                edge_map[edge_id].to_dict()
                for edge_id in selection.edge_ids
                if edge_map[edge_id].source_id in included_ids
                and edge_map[edge_id].target_id in included_ids
            ],
        }
        content = _canonical_json(payload)
        byte_count = len(content.encode("utf-8"))
        if byte_count <= task.byte_budget:
            return SerializedProjection(
                content=content,
                byte_count=byte_count,
                included_record_ids=tuple(record.record_id for record in included),
                omitted_record_ids=tuple(record.record_id for record in omitted),
            )
        if not included:
            raise ValueError("byte budget cannot hold the projection envelope")
        omitted.insert(0, included.pop())


def _topology_order(records: list[GraphRecord], task: TaskSpec) -> list[GraphRecord]:
    terms = tuple(term.casefold() for term in task.query_terms)

    def relevance(record: GraphRecord) -> int:
        text = " ".join((record.kind, record.title, record.content, *record.tags)).casefold()
        return sum(1 for term in terms if term and term in text)

    if task.topology is Topology.PROCEDURE:
        return sorted(
            records,
            key=lambda record: (
                record.sequence is None,
                record.sequence if record.sequence is not None else 0,
                record.record_id,
            ),
        )
    if task.topology is Topology.DEPENDENCY:
        return sorted(records, key=lambda record: (record.kind, record.record_id))
    return sorted(records, key=lambda record: (-relevance(record), record.record_id))


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
