"""Deterministic task projection and fail-closed authenticated selection."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .models import (
    Freshness,
    Graph,
    GraphEdge,
    GraphRecord,
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
