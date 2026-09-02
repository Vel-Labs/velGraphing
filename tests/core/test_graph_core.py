from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from packages.core import (
    Admission,
    AssistObservation,
    AssistResult,
    ContextSpan,
    ExportPolicy,
    Freshness,
    Graph,
    GraphEdge,
    GraphRecord,
    Provenance,
    RetainedItem,
    RetentionClass,
    RetentionState,
    Sensitivity,
    SourceIdentityV4,
    SourceSnapshotV4,
    TaskSpec,
    Topology,
    TrustClass,
    assist,
    compact,
    export_graph,
    is_authenticated_eligible,
    observe_assist,
    select,
    select_context,
    select_documents,
    serialize_projection,
)


DIGEST = "a" * 64


def provenance(*, verified: bool = True) -> Provenance:
    return Provenance("contracts/example.md", DIGEST, "L1-L4", verified)


def record(
    record_id: str,
    content: str = "graph contract",
    **changes: object,
) -> GraphRecord:
    values = {
        "record_id": record_id,
        "kind": "contract",
        "title": record_id,
        "content": content,
        "provenance": provenance(),
        "trust": TrustClass.VERIFIED_SOURCE,
        "sensitivity": Sensitivity.PUBLIC,
        "freshness": Freshness.CURRENT,
        "admission": Admission.VERIFIER,
        "eligible": True,
        "export_allowed": False,
    }
    values.update(changes)
    return GraphRecord(**values)  # type: ignore[arg-type]


def edge(edge_id: str, source_id: str, target_id: str, **changes: object) -> GraphEdge:
    values = {
        "edge_id": edge_id,
        "source_id": source_id,
        "target_id": target_id,
        "relation": "depends_on",
        "relevance": 0.9,
        "provenance": provenance(),
        "trust": TrustClass.VERIFIED_SOURCE,
        "sensitivity": Sensitivity.PUBLIC,
        "freshness": Freshness.CURRENT,
        "admission": Admission.VERIFIER,
        "eligible": True,
        "export_allowed": False,
    }
    values.update(changes)
    return GraphEdge(**values)  # type: ignore[arg-type]


def task(**changes: object) -> TaskSpec:
    values = {
        "task_id": "T",
        "query_terms": ("graph",),
        "node_budget": 10,
        "byte_budget": 20000,
    }
    values.update(changes)
    return TaskSpec(**values)  # type: ignore[arg-type]


class SourceReader:
    def __init__(self, sources: dict[str, bytes], *, symlinks: tuple[str, ...] = ()) -> None:
        self.sources = sources
        self.symlinks = set(symlinks)

    def read_bytes(self, project_relative_path: str) -> bytes:
        return self.sources[project_relative_path]

    def is_symlink(self, project_relative_path: str) -> bool:
        return project_relative_path in self.symlinks


class TrackingSourceReader(SourceReader):
    def __init__(self, sources: dict[str, bytes], *, symlinks: tuple[str, ...] = ()) -> None:
        super().__init__(sources, symlinks=symlinks)
        self.checked_paths: list[str] = []
        self.read_paths: list[str] = []

    def read_bytes(self, project_relative_path: str) -> bytes:
        self.read_paths.append(project_relative_path)
        return super().read_bytes(project_relative_path)

    def is_symlink(self, project_relative_path: str) -> bool:
        self.checked_paths.append(project_relative_path)
        return super().is_symlink(project_relative_path)


def context_fixture() -> tuple[Graph, SourceSnapshotV4, SourceReader, ContextSpan, ContextSpan]:
    path = "docs/context.md"
    raw = b"root evidence\noptional detail\n"
    digest = hashlib.sha256(raw).hexdigest()
    root_bytes = b"root evidence"
    optional_bytes = b"optional detail"
    source_provenance = Provenance(path, digest, "bytes", True)
    graph = Graph(
        (
            record("root", "graph", provenance=source_provenance),
            record("optional", "detail", provenance=source_provenance),
        )
    )
    snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
    return (
        graph,
        snapshot,
        SourceReader({path: raw}),
        ContextSpan("root", 0, len(root_bytes), hashlib.sha256(root_bytes).hexdigest()),
        ContextSpan(
            "optional",
            len(root_bytes) + 1,
            len(root_bytes) + 1 + len(optional_bytes),
            hashlib.sha256(optional_bytes).hexdigest(),
        ),
    )


class ModelTests(unittest.TestCase):
    def test_records_are_stable_and_serializable(self) -> None:
        item = record("R1", tags=("policy",), sequence=2)
        self.assertEqual(item.to_dict(), item.to_dict())
        self.assertEqual(json.loads(json.dumps(item.to_dict()))["trust"], "verified_source")

    def test_graph_rejects_unknown_endpoint_and_duplicate_ids(self) -> None:
        with self.assertRaises(ValueError):
            Graph((record("R1"),), (edge("E1", "R1", "missing"),))
        with self.assertRaises(ValueError):
            Graph((record("R1"), record("R1")))

    def test_every_authentication_gate_is_required(self) -> None:
        base = record("R1")
        self.assertTrue(is_authenticated_eligible(base, (Sensitivity.PUBLIC,)))
        blocked = (
            replace(base, eligible=False),
            replace(base, agent_generated=True),
            replace(base, provenance=provenance(verified=False)),
            replace(base, trust=TrustClass.QUARANTINED),
            replace(base, freshness=Freshness.STALE),
            replace(base, sensitivity=Sensitivity.RESTRICTED),
            replace(base, admission=Admission.NONE),
        )
        self.assertTrue(all(not is_authenticated_eligible(item, (Sensitivity.PUBLIC,)) for item in blocked))

    def test_agent_origin_requires_verifier_promotion(self) -> None:
        promoted = record(
            "R1",
            agent_generated=True,
            trust=TrustClass.POLICY_ADMITTED,
            admission=Admission.VERIFIER,
        )
        self.assertTrue(is_authenticated_eligible(promoted, (Sensitivity.PUBLIC,)))
        self.assertFalse(
            is_authenticated_eligible(
                replace(promoted, admission=Admission.POLICY),
                (Sensitivity.PUBLIC,),
            )
        )


class SelectionTests(unittest.TestCase):
    def test_unauthenticated_edge_cannot_enter_selection(self) -> None:
        graph = Graph(
            (record("R1"), record("R2")),
            (
                edge(
                    "E1",
                    "R1",
                    "R2",
                    eligible=False,
                    trust=TrustClass.UNVERIFIABLE,
                ),
            ),
        )
        result = select(graph, task())
        self.assertFalse(result.fail_closed)
        self.assertEqual(result.edge_ids, ())
        self.assertEqual(result.record_ids, ("R1", "R2"))

    def test_unauthenticated_record_causes_empty_fail_closed_result(self) -> None:
        trusted = record("trusted", "graph contract")
        untrusted = record(
            "untrusted",
            "graph agent contract",
            trust=TrustClass.AGENT_GENERATED,
            agent_generated=True,
            admission=Admission.NONE,
        )
        result = select(
            Graph((trusted, untrusted)),
            task(query_terms=("graph", "agent"), node_budget=1),
        )
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.record_ids, ())
        self.assertIn("untrusted", result.divergent_record_ids)

    def test_stale_high_utility_record_causes_fail_closed_result(self) -> None:
        current = record("z-current", "graph")
        stale = record("a-stale", "graph graph", freshness=Freshness.STALE)
        result = select(Graph((current, stale)), task(node_budget=1))
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.record_ids, ())

    def test_adaptive_depth_prunes_low_relevance_edges(self) -> None:
        graph = Graph(
            (
                record("root", "graph"),
                record("near", "other"),
                record("far", "other"),
                record("pruned", "other"),
            ),
            (
                edge("E1", "root", "near", relevance=0.8),
                edge("E2", "near", "far", relevance=0.7),
                edge("E3", "far", "pruned", relevance=0.15),
            ),
        )
        result = select(graph, task(minimum_relevance=0.1, max_depth=4))
        self.assertFalse(result.fail_closed)
        self.assertEqual(result.record_ids, ("root", "near", "far"))
        self.assertEqual(result.depth_reached, 2)
        self.assertNotIn("E3", result.edge_ids)

    def test_selection_is_deterministic_for_input_order(self) -> None:
        records = (record("B"), record("A"))
        first = select(Graph(records), task())
        second = select(Graph(tuple(reversed(records))), task())
        self.assertEqual(first.to_dict(), second.to_dict())


class ContextSelectionTests(unittest.TestCase):
    def test_context_uses_verified_source_bytes_not_record_content(self) -> None:
        graph, snapshot, reader, root_span, _ = context_fixture()
        result = select_context(
            graph,
            task(),
            snapshot,
            reader,
            required=(root_span,),
        )
        payload = json.loads(result.content)
        self.assertFalse(result.fail_closed)
        self.assertEqual(result.reason, "verified_context_selected")
        self.assertEqual(payload["spans"][0]["content"], "root evidence")
        self.assertNotIn("graph", payload["spans"][0]["content"])
        self.assertEqual(result.byte_count, len(result.content.encode("utf-8")))
        self.assertFalse(
            {"route", "recommendation", "authority", "activate", "write_authority"}
            & set(payload)
        )

    def test_context_is_deterministic_for_span_order(self) -> None:
        graph, snapshot, reader, root_span, optional_span = context_fixture()
        extra_root = ContextSpan(
            "root",
            root_span.byte_start,
            root_span.byte_end + 1,
            hashlib.sha256(b"root evidence\n").hexdigest(),
        )
        first = select_context(
            graph,
            task(),
            snapshot,
            reader,
            required=(extra_root, root_span),
            optional=(optional_span,),
        )
        second = select_context(
            graph,
            task(),
            snapshot,
            reader,
            required=(root_span, extra_root),
            optional=(optional_span,),
        )
        self.assertEqual(first, second)

    def test_every_selected_root_requires_a_required_span(self) -> None:
        graph, snapshot, reader, _, optional_span = context_fixture()
        result = select_context(
            graph,
            task(query_terms=("graph", "detail")),
            snapshot,
            reader,
            required=(optional_span,),
        )
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "selected_root_missing_required_span")
        self.assertEqual(json.loads(result.content)["spans"], [])

    def test_missing_required_record_fails_closed(self) -> None:
        graph, snapshot, reader, root_span, _ = context_fixture()
        missing = replace(root_span, record_id="missing")
        result = select_context(
            graph,
            task(),
            snapshot,
            reader,
            required=(root_span, missing),
        )
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "required_record_not_authenticated")

    def test_optional_span_never_displaces_required_context(self) -> None:
        graph, snapshot, reader, root_span, optional_span = context_fixture()
        required_only = select_context(
            graph,
            task(),
            snapshot,
            reader,
            required=(root_span,),
        )
        bounded = select_context(
            graph,
            task(byte_budget=required_only.byte_count),
            snapshot,
            reader,
            required=(root_span,),
            optional=(optional_span,),
        )
        self.assertFalse(bounded.fail_closed)
        self.assertEqual(bounded.included_optional_record_ids, ())
        self.assertEqual(json.loads(bounded.content)["spans"][0]["content"], "root evidence")

    def test_required_context_fails_closed_when_it_exceeds_budget(self) -> None:
        graph, snapshot, reader, root_span, _ = context_fixture()
        selected = select_context(graph, task(), snapshot, reader, required=(root_span,))
        result = select_context(
            graph,
            task(byte_budget=selected.byte_count - 1),
            snapshot,
            reader,
            required=(root_span,),
        )
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "required_context_exceeds_byte_budget")
        self.assertEqual(json.loads(result.content)["spans"], [])

    def test_failure_envelope_must_also_fit_the_budget(self) -> None:
        graph, snapshot, reader, root_span, _ = context_fixture()
        missing = replace(root_span, record_id="missing")
        failure = select_context(
            graph,
            task(),
            snapshot,
            reader,
            required=(root_span, missing),
        )
        with self.assertRaises(ValueError):
            select_context(
                graph,
                task(byte_budget=failure.byte_count - 1),
                snapshot,
                reader,
                required=(root_span, missing),
            )

    def test_source_drift_symlink_and_excerpt_mismatch_are_rejected(self) -> None:
        graph, snapshot, reader, root_span, _ = context_fixture()
        path = snapshot.sources[0].path
        cases = (
            SourceReader({path: b"changed"}),
            SourceReader(reader.sources, symlinks=(path,)),
        )
        for invalid_reader in cases:
            with self.subTest(reader=invalid_reader):
                with self.assertRaises(ValueError):
                    select_context(graph, task(), snapshot, invalid_reader, required=(root_span,))
        with self.assertRaises(ValueError):
            select_context(
                graph,
                task(),
                snapshot,
                reader,
                required=(replace(root_span, excerpt_sha256="b" * 64),),
            )

    def test_duplicate_and_malformed_spans_are_rejected(self) -> None:
        graph, snapshot, reader, root_span, _ = context_fixture()
        with self.assertRaises(ValueError):
            select_context(
                graph,
                task(),
                snapshot,
                reader,
                required=(root_span,),
                optional=(root_span,),
            )
        with self.assertRaises(ValueError):
            ContextSpan("root", True, 2, "a" * 64)

    def test_provenance_range_and_utf8_boundaries_are_rejected(self) -> None:
        graph, snapshot, reader, root_span, _ = context_fixture()
        mismatched = replace(
            graph.records[0],
            provenance=replace(graph.records[0].provenance, sha256="b" * 64),
        )
        with self.assertRaises(ValueError):
            select_context(
                Graph((mismatched, graph.records[1])),
                task(),
                snapshot,
                reader,
                required=(root_span,),
            )
        with self.assertRaises(ValueError):
            select_context(
                graph,
                task(),
                snapshot,
                reader,
                required=(replace(root_span, byte_end=snapshot.sources[0].byte_length + 1),),
            )

        path = "docs/non-utf8.bin"
        raw = b"\xff"
        digest = hashlib.sha256(raw).hexdigest()
        invalid_graph = Graph(
            (
                record(
                    "root",
                    "graph",
                    provenance=Provenance(path, digest, "bytes", True),
                ),
            )
        )
        invalid_snapshot = SourceSnapshotV4((SourceIdentityV4(path, 1, digest),))
        invalid_span = ContextSpan("root", 0, 1, digest)
        with self.assertRaises(ValueError):
            select_context(
                invalid_graph,
                task(),
                invalid_snapshot,
                SourceReader({path: raw}),
                required=(invalid_span,),
            )


class DocumentSelectionTests(unittest.TestCase):
    def document_fixture(
        self,
        *,
        content: str = "graph evidence\nwhole source detail\n",
    ) -> tuple[Graph, SourceSnapshotV4, TrackingSourceReader]:
        path = "docs/whole.md"
        raw = content.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        source_provenance = Provenance(path, digest, "whole", True)
        return (
            Graph((record("root", content, provenance=source_provenance),)),
            SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),)),
            TrackingSourceReader({path: raw}),
        )

    def test_emits_exact_whole_verified_source(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        result = select_documents(graph, task(), snapshot, reader)
        payload = json.loads(result.content)

        self.assertFalse(result.fail_closed)
        self.assertEqual(result.reason, "verified_context_selected")
        self.assertEqual(payload["schema_version"], "graph-source-context-v2")
        self.assertEqual(payload["documents"][0]["content"], graph.records[0].content)
        self.assertIn("whole source detail", payload["documents"][0]["content"])
        self.assertEqual(
            payload["documents"][0]["byte_count"],
            len(graph.records[0].content.encode("utf-8")),
        )
        self.assertEqual(result.byte_count, len(result.content.encode("utf-8")))
        self.assertFalse(
            {
                "route",
                "recommendation",
                "activation",
                "authority",
                "provider",
                "callback",
                "write",
            }
            & set(payload)
        )

    def test_partial_and_empty_records_fail_closed(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        for incomplete in ("graph evidence", ""):
            with self.subTest(content=incomplete):
                changed = Graph((replace(graph.records[0], content=incomplete),))
                result = select_documents(changed, task(), snapshot, reader)
                self.assertTrue(result.fail_closed)
                self.assertEqual(result.reason, "selected_record_not_source_complete")
                self.assertEqual(json.loads(result.content)["documents"], [])

    def test_conflicting_same_source_sensitivity_fails_closed(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        duplicate = replace(
            graph.records[0],
            record_id="other",
            sensitivity=Sensitivity.INTERNAL,
        )
        result = select_documents(
            Graph((graph.records[0], duplicate)),
            task(allowed_sensitivities=(Sensitivity.PUBLIC, Sensitivity.INTERNAL)),
            snapshot,
            reader,
        )
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "selected_source_sensitivity_conflict")
        self.assertEqual(reader.read_paths, [])

    def test_same_source_is_emitted_once_with_sorted_record_ids(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        duplicate = replace(graph.records[0], record_id="alpha")
        result = select_documents(Graph((graph.records[0], duplicate)), task(), snapshot, reader)
        payload = json.loads(result.content)
        self.assertEqual(len(payload["documents"]), 1)
        self.assertEqual(payload["documents"][0]["record_ids"], ["alpha", "root"])
        self.assertEqual(reader.read_paths, [snapshot.sources[0].path])

    def test_unselected_snapshot_source_is_not_read(self) -> None:
        graph, snapshot, _ = self.document_fixture()
        unused_raw = b"unselected drift"
        unused = SourceIdentityV4(
            "docs/unused.md",
            len(unused_raw),
            hashlib.sha256(unused_raw).hexdigest(),
        )
        expanded = SourceSnapshotV4(
            tuple(sorted((*snapshot.sources, unused), key=lambda item: item.path))
        )
        reader = TrackingSourceReader(
            {snapshot.sources[0].path: graph.records[0].content.encode("utf-8")}
        )

        result = select_documents(graph, task(), expanded, reader)
        self.assertFalse(result.fail_closed)
        self.assertEqual(reader.checked_paths, [snapshot.sources[0].path])
        self.assertEqual(reader.read_paths, [snapshot.sources[0].path])
        self.assertEqual(
            json.loads(result.content)["source_snapshot_sha256"],
            expanded.snapshot_sha256,
        )

    def test_graph_order_does_not_change_canonical_output(self) -> None:
        first_raw = b"graph first"
        second_raw = b"graph second"
        identities = tuple(
            SourceIdentityV4(path, len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in (("docs/a.md", first_raw), ("docs/b.md", second_raw))
        )
        records = tuple(
            record(
                record_id,
                raw.decode("utf-8"),
                provenance=Provenance(identity.path, identity.sha256, "whole", True),
            )
            for record_id, raw, identity in zip(
                ("z", "a"),
                (first_raw, second_raw),
                identities,
            )
        )
        snapshot = SourceSnapshotV4(identities)
        sources = {
            identity.path: raw
            for identity, raw in zip(identities, (first_raw, second_raw))
        }
        first = select_documents(Graph(records), task(), snapshot, SourceReader(sources))
        second = select_documents(
            Graph(tuple(reversed(records))),
            task(),
            snapshot,
            SourceReader(sources),
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [item["source_path"] for item in json.loads(first.content)["documents"]],
            ["docs/a.md", "docs/b.md"],
        )

    def test_complete_payload_accepts_exact_budget_and_fails_one_byte_below(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        unbounded = select_documents(graph, task(), snapshot, reader)
        exact = select_documents(
            graph,
            task(byte_budget=unbounded.byte_count),
            snapshot,
            reader,
        )
        below = select_documents(
            graph,
            task(byte_budget=unbounded.byte_count - 1),
            snapshot,
            reader,
        )
        self.assertEqual(exact, unbounded)
        self.assertTrue(below.fail_closed)
        self.assertEqual(below.reason, "required_context_exceeds_byte_budget")
        self.assertEqual(json.loads(below.content)["documents"], [])

    def test_snapshot_provenance_reader_digest_symlink_and_utf8_defects_raise(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        path = snapshot.sources[0].path
        mismatched = Graph(
            (
                replace(
                    graph.records[0],
                    provenance=replace(graph.records[0].provenance, sha256="b" * 64),
                ),
            )
        )
        cases = (
            (mismatched, snapshot, reader),
            (graph, snapshot, SourceReader({path: b"changed"})),
            (graph, snapshot, SourceReader(reader.sources, symlinks=(path,))),
        )
        for invalid_graph, invalid_snapshot, invalid_reader in cases:
            with self.subTest(reader=invalid_reader):
                with self.assertRaises(ValueError):
                    select_documents(invalid_graph, task(), invalid_snapshot, invalid_reader)

        invalid_raw = b"\xff"
        invalid_digest = hashlib.sha256(invalid_raw).hexdigest()
        invalid_snapshot = SourceSnapshotV4((SourceIdentityV4(path, 1, invalid_digest),))
        invalid_graph = Graph(
            (
                replace(
                    graph.records[0],
                    provenance=Provenance(path, invalid_digest, "whole", True),
                ),
            )
        )
        with self.assertRaises(ValueError):
            select_documents(
                invalid_graph,
                task(),
                invalid_snapshot,
                SourceReader({path: invalid_raw}),
            )

    def test_selection_failure_and_empty_success_are_reader_free(self) -> None:
        graph, snapshot, _ = self.document_fixture()
        reader = TrackingSourceReader({})
        untrusted = record(
            "untrusted",
            "graph agent graph agent",
            trust=TrustClass.AGENT_GENERATED,
            agent_generated=True,
            admission=Admission.NONE,
        )
        failed = select_documents(
            Graph((graph.records[0], untrusted)),
            task(query_terms=("graph", "agent"), node_budget=1),
            snapshot,
            reader,
        )
        empty = select_documents(Graph(()), task(), snapshot, reader)

        self.assertTrue(failed.fail_closed)
        self.assertEqual(failed.reason, "selection_fail_closed")
        self.assertFalse(empty.fail_closed)
        self.assertEqual(empty.reason, "verified_context_selected")
        self.assertEqual(json.loads(empty.content)["documents"], [])
        self.assertEqual(reader.checked_paths, [])
        self.assertEqual(reader.read_paths, [])


class AssistTests(unittest.TestCase):
    def document_fixture(
        self,
        paths: tuple[str, ...] = ("docs/a.md", "docs/b.md"),
    ) -> tuple[Graph, SourceSnapshotV4, SourceReader]:
        contents = tuple(f"graph evidence from {path}\n".encode("utf-8") for path in paths)
        identities = tuple(
            SourceIdentityV4(path, len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in zip(paths, contents)
        )
        records = tuple(
            record(
                record_id,
                raw.decode("utf-8"),
                provenance=Provenance(identity.path, identity.sha256, "whole", True),
            )
            for record_id, raw, identity in zip(("z", "a"), contents, identities)
        )
        return (
            Graph(records),
            SourceSnapshotV4(identities),
            SourceReader({identity.path: raw for identity, raw in zip(identities, contents)}),
        )

    def fallback_fixture(
        self,
    ) -> tuple[Graph, TaskSpec, SourceSnapshotV4, dict[str, bytes]]:
        graph, snapshot, reader = self.document_fixture()
        untrusted = record(
            "untrusted",
            "agent-only record",
            trust=TrustClass.AGENT_GENERATED,
            agent_generated=True,
            admission=Admission.NONE,
        )
        return (
            Graph((*graph.records, untrusted)),
            task(query_terms=("agent",), node_budget=1),
            snapshot,
            reader.sources,
        )

    def test_graph_route_wraps_non_empty_document_projection(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        legacy = select_documents(graph, task(), snapshot, reader)

        result = assist(
            graph,
            task(),
            snapshot,
            reader,
            required_source_paths=("docs/a.md", "docs/b.md"),
        )

        self.assertIsInstance(result, AssistResult)
        self.assertEqual(result.route, "graph")
        self.assertEqual(result.reason, "required_sources_selected")
        self.assertEqual(result.projection, legacy)

    def test_output_is_deterministic_for_graph_input_order(self) -> None:
        graph, snapshot, reader = self.document_fixture()

        requirements = ("docs/a.md", "docs/b.md")
        first = assist(
            graph,
            task(),
            snapshot,
            reader,
            required_source_paths=requirements,
        )
        second = assist(
            Graph(tuple(reversed(graph.records))),
            task(),
            snapshot,
            reader,
            required_source_paths=requirements,
        )

        self.assertEqual(first, second)

    def test_empty_and_fail_closed_selection_conservatively_defer(self) -> None:
        graph, snapshot, _ = self.document_fixture(paths=("docs/a.md", "docs/b.md"))
        empty = assist(
            Graph(()),
            task(),
            snapshot,
            SourceReader({}),
            required_source_paths=("docs/a.md",),
        )
        untrusted = record(
            "untrusted",
            "graph agent graph agent",
            trust=TrustClass.AGENT_GENERATED,
            agent_generated=True,
            admission=Admission.NONE,
        )
        failed = assist(
            Graph((graph.records[0], untrusted)),
            task(query_terms=("graph", "agent"), node_budget=1),
            snapshot,
            SourceReader({}),
            required_source_paths=("docs/a.md",),
        )

        self.assertEqual(empty.route, "defer")
        self.assertEqual(empty.reason, "graph_projection_unavailable")
        self.assertFalse(empty.projection.fail_closed)
        self.assertEqual(empty.projection.required_record_ids, ())
        self.assertEqual(failed.route, "defer")
        self.assertEqual(failed.reason, "graph_projection_unavailable")
        self.assertTrue(failed.projection.fail_closed)
        self.assertEqual(failed.projection.reason, "selection_fail_closed")

    def test_invalid_requirements_defer_before_reader_access(self) -> None:
        graph, snapshot, source_reader = self.document_fixture()
        reader = TrackingSourceReader(source_reader.sources)
        invalid_requirements = (
            (),
            ["docs/a.md"],
            ("",),
            ("docs/a.md", "docs/a.md"),
            ("docs/b.md", "docs/a.md"),
            ("../docs/a.md",),
            ("/docs/a.md",),
            ("docs//a.md",),
        )

        for requirements in invalid_requirements:
            with self.subTest(requirements=requirements):
                result = assist(
                    graph,
                    task(),
                    snapshot,
                    reader,
                    required_source_paths=requirements,
                )
                self.assertEqual(result.route, "defer")
                self.assertEqual(result.reason, "invalid_required_source_paths")
                self.assertTrue(result.projection.fail_closed)
                self.assertEqual(
                    result.projection.reason,
                    "invalid_required_source_paths",
                )

        self.assertEqual(reader.checked_paths, [])
        self.assertEqual(reader.read_paths, [])

    def test_missing_selected_source_defers_with_stable_reason(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        requirements = ("docs/a.md",)

        first = assist(
            graph,
            task(node_budget=1),
            snapshot,
            reader,
            required_source_paths=requirements,
        )
        second = assist(
            Graph(tuple(reversed(graph.records))),
            task(node_budget=1),
            snapshot,
            reader,
            required_source_paths=requirements,
        )

        self.assertEqual(first, second)
        self.assertEqual(first.route, "defer")
        self.assertEqual(first.reason, "required_sources_missing")
        self.assertFalse(first.projection.fail_closed)

    def test_direct_fallback_reads_exact_allowlist_and_covers_required_subset(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        reader = TrackingSourceReader(sources)

        result = assist(
            graph,
            spec,
            snapshot,
            reader,
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )
        payload = json.loads(result.projection.content)

        self.assertEqual(result.route, "direct")
        self.assertEqual(result.reason, "required_sources_direct")
        self.assertFalse(result.projection.fail_closed)
        self.assertEqual(payload["schema_version"], "graph-source-context-v2")
        self.assertEqual(
            [document["source_path"] for document in payload["documents"]],
            ["docs/a.md", "docs/b.md"],
        )
        self.assertEqual(reader.checked_paths, ["docs/a.md", "docs/b.md"])
        self.assertEqual(reader.read_paths, ["docs/a.md", "docs/b.md"])

    def test_fallback_must_include_every_required_source(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        reader = TrackingSourceReader(sources)

        result = assist(
            graph,
            spec,
            snapshot,
            reader,
            required_source_paths=("docs/a.md", "docs/b.md"),
            fallback_source_paths=("docs/a.md",),
        )

        self.assertEqual(result.route, "defer")
        self.assertEqual(result.reason, "fallback_sources_incomplete")
        self.assertTrue(result.projection.fail_closed)
        self.assertEqual(reader.checked_paths, [])
        self.assertEqual(reader.read_paths, [])

    def test_graph_fast_path_does_not_read_fallback_only_source(self) -> None:
        graph, snapshot, source_reader = self.document_fixture()
        reader = TrackingSourceReader(source_reader.sources)

        result = assist(
            graph,
            task(node_budget=1),
            snapshot,
            reader,
            required_source_paths=("docs/b.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )

        self.assertEqual(result.route, "graph")
        self.assertEqual(reader.checked_paths, ["docs/b.md"])
        self.assertEqual(reader.read_paths, ["docs/b.md"])

    def test_direct_fallback_is_deterministic_for_graph_order(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        first = assist(
            graph,
            spec,
            snapshot,
            SourceReader(sources),
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )
        second = assist(
            Graph(tuple(reversed(graph.records))),
            spec,
            snapshot,
            SourceReader(sources),
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )

        self.assertEqual(first, second)

    def test_fallback_digest_symlink_and_utf8_defects_fail_closed(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        cases = (
            TrackingSourceReader({**sources, "docs/a.md": b"changed"}),
            TrackingSourceReader(sources, symlinks=("docs/a.md",)),
        )
        for reader in cases:
            with self.subTest(reader=reader):
                result = assist(
                    graph,
                    spec,
                    snapshot,
                    reader,
                    required_source_paths=("docs/a.md",),
                    fallback_source_paths=("docs/a.md",),
                )
                self.assertEqual(result.route, "defer")
                self.assertEqual(result.reason, "fallback_sources_unreadable")
                self.assertTrue(result.projection.fail_closed)

        path = "docs/invalid.md"
        raw = b"\xff"
        digest = hashlib.sha256(raw).hexdigest()
        invalid_snapshot = SourceSnapshotV4((SourceIdentityV4(path, 1, digest),))
        eligible = record(
            "eligible",
            "graph",
            provenance=Provenance(path, digest, "whole", True),
        )
        untrusted = record(
            "untrusted",
            "agent",
            trust=TrustClass.AGENT_GENERATED,
            agent_generated=True,
            admission=Admission.NONE,
        )
        invalid = assist(
            Graph((eligible, untrusted)),
            task(query_terms=("agent",), node_budget=1),
            invalid_snapshot,
            SourceReader({path: raw}),
            required_source_paths=(path,),
            fallback_source_paths=(path,),
        )
        self.assertEqual(invalid.route, "defer")
        self.assertEqual(invalid.reason, "fallback_sources_unreadable")
        self.assertTrue(invalid.projection.fail_closed)

    def test_fallback_over_budget_fails_closed(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        unbounded = assist(
            graph,
            spec,
            snapshot,
            SourceReader(sources),
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )

        bounded = assist(
            graph,
            replace(spec, byte_budget=unbounded.projection.byte_count - 1),
            snapshot,
            SourceReader(sources),
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )

        self.assertEqual(bounded.route, "defer")
        self.assertEqual(bounded.reason, "fallback_context_exceeds_byte_budget")
        self.assertTrue(bounded.projection.fail_closed)

    def test_fallback_requires_authenticated_allowed_sensitivity_binding(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        for changed_record in (
            replace(graph.records[0], eligible=False),
            replace(graph.records[0], sensitivity=Sensitivity.RESTRICTED),
        ):
            with self.subTest(record=changed_record):
                changed_graph = Graph((changed_record, *graph.records[1:]))
                reader = TrackingSourceReader(sources)
                result = assist(
                    changed_graph,
                    spec,
                    snapshot,
                    reader,
                    required_source_paths=("docs/a.md",),
                    fallback_source_paths=("docs/a.md",),
                )
                self.assertEqual(result.route, "defer")
                self.assertEqual(result.reason, "fallback_sources_unavailable")
                self.assertTrue(result.projection.fail_closed)
                self.assertEqual(reader.checked_paths, [])
                self.assertEqual(reader.read_paths, [])

    def test_public_prefix_cannot_authorize_restricted_full_source_fallback(self) -> None:
        path = "docs/mixed.md"
        raw = b"public prefix\nRESTRICTED SECRET\n"
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
        public_prefix = record(
            "public-prefix",
            "public prefix\n",
            provenance=Provenance(path, digest, "whole", True),
            sensitivity=Sensitivity.PUBLIC,
        )
        untrusted = record(
            "untrusted",
            "agent-only record",
            trust=TrustClass.AGENT_GENERATED,
            agent_generated=True,
            admission=Admission.NONE,
        )
        reader = TrackingSourceReader({path: raw})

        result = assist(
            Graph((public_prefix, untrusted)),
            task(query_terms=("agent",), node_budget=1),
            snapshot,
            reader,
            required_source_paths=(path,),
            fallback_source_paths=(path,),
        )

        self.assertEqual(result.route, "defer")
        self.assertEqual(result.reason, "fallback_sources_unavailable")
        self.assertTrue(result.projection.fail_closed)
        self.assertEqual(json.loads(result.projection.content)["documents"], [])
        self.assertNotIn("RESTRICTED SECRET", result.projection.content)
        self.assertEqual(reader.checked_paths, [path])
        self.assertEqual(reader.read_paths, [path])

    def test_invalid_and_unknown_fallback_paths_fail_closed_without_reads(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        cases = (
            (("docs/b.md", "docs/a.md"), "invalid_fallback_source_paths"),
            (("docs/missing.md",), "fallback_sources_unavailable"),
        )
        for fallback_paths, reason in cases:
            with self.subTest(fallback_paths=fallback_paths):
                reader = TrackingSourceReader(sources)
                result = assist(
                    graph,
                    spec,
                    snapshot,
                    reader,
                    required_source_paths=(fallback_paths[0],),
                    fallback_source_paths=fallback_paths,
                )
                self.assertEqual(result.route, "defer")
                self.assertEqual(result.reason, reason)
                self.assertTrue(result.projection.fail_closed)
                self.assertEqual(reader.checked_paths, [])
                self.assertEqual(reader.read_paths, [])

    def test_graph_observation_is_source_bound_deterministic_and_read_free(self) -> None:
        graph, snapshot, source_reader = self.document_fixture()
        reader = TrackingSourceReader(source_reader.sources)
        required_paths = ("docs/a.md", "docs/b.md")
        result = assist(
            graph,
            task(),
            snapshot,
            reader,
            required_source_paths=required_paths,
        )
        reads_before_observation = (tuple(reader.checked_paths), tuple(reader.read_paths))

        observation = observe_assist(
            result,
            graph,
            task(),
            snapshot,
            required_source_paths=required_paths,
            fallback_source_paths=("docs/b.md", "docs/a.md", "docs/a.md"),
        )
        repeated = observe_assist(
            result,
            Graph(tuple(reversed(graph.records))),
            task(),
            snapshot,
            required_source_paths=required_paths,
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )

        self.assertIsInstance(observation, AssistObservation)
        self.assertEqual(observation.schema_version, "assist-observation-v1")
        self.assertEqual(observation.route, "graph")
        self.assertEqual(observation.failure_class, "none")
        self.assertEqual(observation.source_snapshot_sha256, snapshot.snapshot_sha256)
        self.assertEqual(observation.selected_source_paths, required_paths)
        self.assertEqual(observation.fallback_source_paths, required_paths)
        self.assertEqual(observation.context_bytes, result.projection.byte_count)
        self.assertEqual(observation.to_json(), repeated.to_json())
        self.assertNotIn("content", observation.to_dict())
        self.assertNotIn("graph evidence", observation.to_json())
        self.assertEqual(
            (tuple(reader.checked_paths), tuple(reader.read_paths)),
            reads_before_observation,
        )

    def test_direct_and_defer_observations_use_closed_failure_taxonomy(self) -> None:
        graph, spec, snapshot, sources = self.fallback_fixture()
        direct = assist(
            graph,
            spec,
            snapshot,
            SourceReader(sources),
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )
        direct_observation = observe_assist(
            direct,
            graph,
            spec,
            snapshot,
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md", "docs/b.md"),
        )

        base_graph, base_snapshot, base_reader = self.document_fixture()
        missing = assist(
            base_graph,
            task(),
            base_snapshot,
            base_reader,
            required_source_paths=("docs/missing.md",),
        )
        missing_observation = observe_assist(
            missing,
            base_graph,
            task(),
            base_snapshot,
            required_source_paths=("docs/missing.md",),
        )

        self.assertEqual(direct.route, "direct")
        self.assertEqual(direct_observation.failure_class, "selection_failure")
        self.assertEqual(missing.route, "defer")
        self.assertEqual(missing_observation.failure_class, "missing_knowledge")

    def test_observation_classifies_relationship_granularity_freshness_and_selection(self) -> None:
        graph, snapshot, reader = self.document_fixture()
        relationship_spec = task(node_budget=1)
        relationship = assist(
            graph,
            relationship_spec,
            snapshot,
            reader,
            required_source_paths=("docs/a.md",),
        )

        partial = replace(graph.records[0], content="graph evidence")
        granular_graph = Graph((partial,))
        granular_snapshot = SourceSnapshotV4((snapshot.sources[0],))
        granular = assist(
            granular_graph,
            task(),
            granular_snapshot,
            SourceReader({"docs/a.md": reader.sources["docs/a.md"]}),
            required_source_paths=("docs/a.md",),
        )

        stale_graph = Graph((replace(graph.records[0], freshness=Freshness.STALE),))
        stale_snapshot = SourceSnapshotV4((snapshot.sources[0],))
        stale = assist(
            stale_graph,
            task(),
            stale_snapshot,
            SourceReader({"docs/a.md": reader.sources["docs/a.md"]}),
            required_source_paths=("docs/a.md",),
        )

        untrusted_graph = Graph(
            (
                graph.records[0],
                record(
                    "untrusted-selection",
                    "graph graph",
                    trust=TrustClass.AGENT_GENERATED,
                    agent_generated=True,
                    admission=Admission.NONE,
                ),
            )
        )
        selection = assist(
            untrusted_graph,
            task(node_budget=1),
            stale_snapshot,
            SourceReader({}),
            required_source_paths=("docs/a.md",),
        )

        cases = (
            (relationship, graph, relationship_spec, snapshot, "relationship_failure"),
            (granular, granular_graph, task(), granular_snapshot, "granularity_failure"),
            (stale, stale_graph, task(), stale_snapshot, "freshness_failure"),
            (selection, untrusted_graph, task(node_budget=1), stale_snapshot, "selection_failure"),
        )
        for result, candidate_graph, spec, candidate_snapshot, expected in cases:
            with self.subTest(failure_class=expected):
                observation = observe_assist(
                    result,
                    candidate_graph,
                    spec,
                    candidate_snapshot,
                    required_source_paths=("docs/a.md",),
                )
                self.assertEqual(observation.failure_class, expected)

    def test_required_escalation_forces_direct_or_fails_closed(self) -> None:
        graph, snapshot, source_reader = self.document_fixture()
        reader = TrackingSourceReader(source_reader.sources)
        escalated = assist(
            graph,
            task(),
            snapshot,
            reader,
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md",),
            required_escalation=True,
        )
        observation = observe_assist(
            escalated,
            graph,
            task(),
            snapshot,
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md",),
        )
        no_fallback_reader = TrackingSourceReader(source_reader.sources)
        unavailable = assist(
            graph,
            task(),
            snapshot,
            no_fallback_reader,
            required_source_paths=("docs/a.md",),
            required_escalation=True,
        )
        unavailable_observation = observe_assist(
            unavailable,
            graph,
            task(),
            snapshot,
            required_source_paths=("docs/a.md",),
        )

        self.assertEqual(escalated.route, "direct")
        self.assertEqual(escalated.reason, "required_escalation")
        self.assertEqual(observation.failure_class, "required_escalation")
        self.assertEqual(reader.read_paths, ["docs/a.md"])
        self.assertEqual(unavailable.route, "defer")
        self.assertEqual(unavailable.reason, "required_escalation_unavailable")
        self.assertTrue(unavailable.projection.fail_closed)
        self.assertEqual(unavailable_observation.failure_class, "required_escalation")
        self.assertEqual(no_fallback_reader.read_paths, [])

    def test_invalid_escalation_and_observation_inputs_fail_without_reads(self) -> None:
        graph, snapshot, source_reader = self.document_fixture()
        reader = TrackingSourceReader(source_reader.sources)
        invalid = assist(
            graph,
            task(),
            snapshot,
            reader,
            required_source_paths=("docs/a.md",),
            fallback_source_paths=("docs/a.md",),
            required_escalation=1,  # type: ignore[arg-type]
        )

        self.assertEqual(invalid.route, "defer")
        self.assertEqual(invalid.reason, "invalid_required_escalation")
        self.assertTrue(invalid.projection.fail_closed)
        self.assertEqual(reader.checked_paths, [])
        self.assertEqual(reader.read_paths, [])
        with self.assertRaises(TypeError):
            observe_assist(
                invalid,
                graph,
                task(),
                snapshot,
                required_source_paths=["docs/a.md"],  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            observe_assist(
                replace(invalid, reason="model prose is not telemetry"),
                graph,
                task(),
                snapshot,
                required_source_paths=("docs/a.md",),
            )

    def test_assist_observation_schema_matches_public_shape(self) -> None:
        schema_path = Path("contracts/core/assist-observation-v1.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema_version"]["const"], "assist-observation-v1")
        self.assertEqual(
            set(schema["properties"]["failure_class"]["enum"]),
            {
                "missing_knowledge",
                "selection_failure",
                "relationship_failure",
                "granularity_failure",
                "freshness_failure",
                "required_escalation",
                "none",
            },
        )


class SerializationTests(unittest.TestCase):
    def test_procedure_serialization_uses_sequence_and_is_deterministic(self) -> None:
        graph = Graph(
            (
                record("second", sequence=2),
                record("first", sequence=1),
            )
        )
        spec = task(topology=Topology.PROCEDURE)
        result = select(graph, spec)
        serialized = serialize_projection(graph, spec, result)
        payload = json.loads(serialized.content)
        self.assertEqual([item["record_id"] for item in payload["records"]], ["first", "second"])
        self.assertEqual(serialized.byte_count, len(serialized.content.encode("utf-8")))
        self.assertEqual(serialized.content, serialize_projection(graph, spec, result).content)

    def test_serialization_prunes_to_byte_budget(self) -> None:
        graph = Graph((record("A", "graph " + "x" * 500), record("B", "graph " + "y" * 500)))
        large = task(byte_budget=10000)
        result = select(graph, large)
        envelope_size = serialize_projection(graph, replace(large, byte_budget=10000), result).byte_count
        serialized = serialize_projection(graph, replace(large, byte_budget=envelope_size - 300), result)
        self.assertLessEqual(serialized.byte_count, envelope_size - 300)
        self.assertTrue(serialized.omitted_record_ids)

    def test_fail_closed_serialization_contains_no_records(self) -> None:
        graph = Graph((record("trusted"), record("bad", agent_generated=True)))
        spec = task(node_budget=1)
        result = select(graph, spec)
        payload = json.loads(serialize_projection(graph, spec, result).content)
        self.assertTrue(payload["fail_closed"])
        self.assertEqual(payload["records"], [])


class RetentionTests(unittest.TestCase):
    def test_pinned_rule_is_exact_through_five_compaction_cycles(self) -> None:
        rule = RetainedItem("rule", RetentionClass.PINNED_RULE, "MUST preserve exact bytes.\n")
        state = RetentionState(
            (rule, *(RetainedItem(f"d{i}", RetentionClass.DETAIL, f"detail {i}") for i in range(8)))
        )
        original = rule.content.encode("utf-8")
        for _ in range(5):
            state = compact(state, max_active=3)
            retained_rule = state.retrieve("rule")
            self.assertIsNotNone(retained_rule)
            self.assertIn(retained_rule, state.active)
            self.assertEqual(retained_rule.content.encode("utf-8"), original)
        self.assertEqual(state.cycles, 5)

    def test_folded_summary_keeps_retrievable_source_detail(self) -> None:
        detail = RetainedItem("detail", RetentionClass.DETAIL, "authoritative exact detail")
        state = compact(
            RetentionState((RetainedItem("rule", RetentionClass.PINNED_RULE, "rule"), detail)),
            max_active=2,
        )
        # Force the detail into the archive in a second state with more input.
        state = compact(
            RetentionState(
                (*state.active, RetainedItem("evidence", RetentionClass.EVIDENCE, "evidence")),
                state.archive,
                state.cycles,
            ),
            max_active=2,
        )
        summary = next(item for item in state.active if item.retention is RetentionClass.SUMMARY)
        self.assertIn("detail", summary.source_item_ids)
        self.assertEqual(state.retrieve("detail").content, "authoritative exact detail")

    def test_misleading_folded_summary_does_not_replace_source_detail(self) -> None:
        detail = RetainedItem(
            "detail",
            RetentionClass.DETAIL,
            "authoritative exact detail",
        )
        state = compact(
            RetentionState(
                (
                    RetainedItem("rule", RetentionClass.PINNED_RULE, "rule"),
                    detail,
                    RetainedItem("evidence", RetentionClass.EVIDENCE, "evidence"),
                )
            ),
            max_active=2,
        )
        summary = next(
            item for item in state.active if item.retention is RetentionClass.SUMMARY
        )
        misleading = replace(summary, content="Incorrect folded claim")
        active = tuple(misleading if item is summary else item for item in state.active)
        misleading_state = RetentionState(active, state.archive, state.cycles)

        self.assertIn("detail", misleading.source_item_ids)
        self.assertEqual(
            "authoritative exact detail",
            misleading_state.retrieve("detail").content,
        )


class ExportTests(unittest.TestCase):
    def test_export_is_default_deny(self) -> None:
        graph = Graph((record("R1", export_allowed=True),))
        self.assertFalse(export_graph(graph).allowed)
        self.assertEqual(export_graph(graph).payload, {})

    def test_export_requires_both_policy_and_item_authorization(self) -> None:
        denied_graph = Graph((record("R1"),))
        policy = ExportPolicy(enabled=True, record_ids=("R1",))
        self.assertFalse(export_graph(denied_graph, policy).allowed)
        allowed_graph = Graph((record("R1", export_allowed=True),))
        result = export_graph(allowed_graph, policy)
        self.assertTrue(result.allowed)
        self.assertEqual(result.payload["records"][0]["record_id"], "R1")

    def test_export_fails_closed_for_edge_without_exported_endpoints(self) -> None:
        graph = Graph(
            (record("R1", export_allowed=True), record("R2", export_allowed=True)),
            (edge("E1", "R1", "R2", export_allowed=True),),
        )
        result = export_graph(graph, ExportPolicy(enabled=True, record_ids=("R1",), edge_ids=("E1",)))
        self.assertFalse(result.allowed)
        self.assertEqual(result.payload, {})


class ContractTests(unittest.TestCase):
    def test_contract_documents_are_valid_json(self) -> None:
        contract_root = Path(__file__).parents[2] / "contracts" / "core"
        schemas = sorted(contract_root.glob("*.json"))
        self.assertGreaterEqual(len(schemas), 4)
        for schema in schemas:
            with self.subTest(schema=schema.name):
                payload = json.loads(schema.read_text(encoding="utf-8"))
                self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")


if __name__ == "__main__":
    unittest.main()
