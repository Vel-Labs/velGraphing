from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import unittest

from packages.core import (
    Admission,
    Freshness,
    Graph,
    GraphEdge,
    GraphRecord,
    Provenance,
    RankedContextCandidate,
    RankedContextPlan,
    Sensitivity,
    SourceCoordinate,
    SourceIdentityV4,
    SourceSnapshotV4,
    TaskSpec,
    TrustClass,
    plan_ranked_context,
    select_ranked_context,
)
from packages.core import jev


APPROVED = "f" * 64
QUERY = "find required and optional evidence"


class SourceReader:
    def __init__(self, sources: dict[str, bytes], symlinks: tuple[str, ...] = ()) -> None:
        self.sources = sources
        self.symlinks = set(symlinks)
        self.read_paths: list[str] = []
        self.checked_paths: list[str] = []

    def read_bytes(self, project_relative_path: str) -> bytes:
        self.read_paths.append(project_relative_path)
        return self.sources[project_relative_path]

    def is_symlink(self, project_relative_path: str) -> bool:
        self.checked_paths.append(project_relative_path)
        return project_relative_path in self.symlinks


class ExplodingReader(SourceReader):
    def read_bytes(self, project_relative_path: str) -> bytes:
        self.read_paths.append(project_relative_path)
        raise RuntimeError("INTERNAL_SOURCE_TEXT")


class FallbackExplodingReader(SourceReader):
    def read_bytes(self, project_relative_path: str) -> bytes:
        self.read_paths.append(project_relative_path)
        if len(self.read_paths) > 1:
            raise RuntimeError("INTERNAL_FALLBACK_SOURCE_TEXT")
        return self.sources[project_relative_path]


class PropertyExplodingReader:
    @property
    def read_bytes(self):
        raise RuntimeError("INTERNAL_READER_PROPERTY_TEXT")

    def is_symlink(self, project_relative_path: str) -> bool:
        return False


def spec(byte_budget: int = 20_000) -> TaskSpec:
    return TaskSpec("ranked", ("evidence",), byte_budget=byte_budget)


def candidate(
    identity: str,
    path: str,
    digest: str,
    start: int,
    end: int,
    *,
    required: bool,
    record_id: str | None = None,
    relationship_parent_candidate_id: str | None = None,
    source_unit_complete: bool = False,
) -> RankedContextCandidate:
    return RankedContextCandidate(
        identity,
        path,
        digest,
        start,
        end,
        required,
        record_id or f"record-{identity}",
        relationship_parent_candidate_id,
        source_unit_complete=source_unit_complete,
    )


def source_record(
    record_id: str,
    path: str,
    digest: str,
    content: str,
    *,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    freshness: Freshness = Freshness.CURRENT,
    eligible: bool = True,
) -> GraphRecord:
    return GraphRecord(
        record_id=record_id,
        kind="source",
        title=record_id,
        content=content,
        provenance=Provenance(path, digest, "candidate", True),
        trust=TrustClass.VERIFIED_SOURCE,
        sensitivity=sensitivity,
        freshness=freshness,
        admission=Admission.VERIFIER,
        eligible=eligible,
        export_allowed=False,
    )


def fixture() -> tuple[
    Graph, SourceSnapshotV4, SourceReader, tuple[RankedContextCandidate, ...]
]:
    path = "src/context.py"
    raw = b"requiredxx\noptional-a\noptional-b\n"
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
    candidates = (
        candidate("c0", path, digest, 0, 10, required=True),
        candidate("c1", path, digest, 11, 21, required=False),
        candidate("c2", path, digest, 22, 32, required=False),
    )
    graph = Graph(tuple(
        source_record(
            item.record_id,
            path,
            digest,
            raw[item.byte_start:item.byte_end].decode("utf-8"),
        )
        for item in candidates
    ))
    return graph, snapshot, SourceReader({path: raw}), candidates


def graph_with_relationship_edge(
    graph: Graph,
    snapshot: SourceSnapshotV4,
    reader: SourceReader,
    parent: RankedContextCandidate,
    relationship: RankedContextCandidate,
    *,
    relation: str = "references",
) -> Graph:
    records = tuple(
        replace(
            record,
            content=reader.sources[record.provenance.path].decode("utf-8"),
        )
        for record in graph.records
    )

    def coordinate(candidate: RankedContextCandidate) -> SourceCoordinate:
        raw = reader.sources[candidate.source_path]
        return SourceCoordinate(
            snapshot.snapshot_sha256,
            candidate.source_path,
            candidate.source_sha256,
            candidate.byte_start,
            candidate.byte_end,
            1 + raw[:candidate.byte_start].count(b"\n"),
            1 + raw[:candidate.byte_end - 1].count(b"\n"),
            "span",
            "reference",
            candidate.candidate_id,
        )

    edge = GraphEdge(
        "edge-c1-c2",
        parent.record_id,
        relationship.record_id,
        relation,
        1.0,
        Provenance(parent.source_path, parent.source_sha256, "relationship", True),
        TrustClass.VERIFIED_SOURCE,
        Sensitivity.PUBLIC,
        Freshness.CURRENT,
        Admission.VERIFIER,
        True,
        source_coordinate=coordinate(parent),
        target_coordinate=coordinate(relationship),
    )
    return Graph(records, (edge,))


def observation(
    candidates: tuple[RankedContextCandidate, ...],
    order: tuple[str, ...],
    snapshot: SourceSnapshotV4,
) -> dict[str, object]:
    packet = jev.validate_packet({
        "schema_version": jev.PACKET_VERSION,
        "query": QUERY,
        "candidates": [item._packet_value() for item in candidates],
    })
    baseline = [item["id"] for item in packet["candidates"]]
    return {
        "schema_version": "velgraphing-jev-observation-v1",
        "status": "reranked",
        "mode": "rerank",
        "authority_bearing": False,
        "sufficient": False,
        "source_revalidated": True,
        "baseline_order": baseline,
        "required_ids": [
            item["id"] for item in packet["candidates"] if item["required"]
        ],
        "order": list(order),
        "candidate_set_sha256": jev.sha256(jev.canonical(packet["candidates"])),
        "query_sha256": jev.sha256(QUERY.encode("utf-8")),
        "source_set_sha256": jev.sha256(jev.canonical([
            {"path": source.path, "sha256": source.sha256}
            for source in snapshot.sources
        ])),
        "request_sha256": APPROVED,
    }


def classification_observation(
    candidates: tuple[RankedContextCandidate, ...],
    order: tuple[str, ...],
    snapshot: SourceSnapshotV4,
) -> dict[str, object]:
    """Fixture custom adapter: standard library only, with no Jev import."""
    candidate_rows = [item._packet_value() for item in candidates]
    canonical = lambda value: (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    return {
        "schema_version": "retrievel-classification-observation-v1",
        "status": "reranked",
        "candidate_set_sha256": digest(canonical(candidate_rows)),
        "query_sha256": digest(QUERY.encode("utf-8")),
        "source_set_sha256": digest(canonical([
            {"path": source.path, "sha256": source.sha256}
            for source in snapshot.sources
        ])),
        "baseline_order": [item.candidate_id for item in candidates],
        "proposed_order": list(order),
        "required_ids": [item.candidate_id for item in candidates if item.required],
        "request_sha256": APPROVED,
        "source_revalidated": True,
        "authority_bearing": False,
        "sufficient": False,
    }


def select(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReader,
    candidates: tuple[RankedContextCandidate, ...],
    observed: object = None,
    *,
    jev_enabled: bool = False,
    jev_observation_qualified: bool = False,
    fallback_source_paths: tuple[str, ...] = (),
):
    return select_ranked_context(
        graph,
        task,
        snapshot,
        reader,
        query=QUERY,
        candidates=candidates,
        approved_request_sha256=APPROVED,
        jev_observation=observed,
        jev_enabled=jev_enabled,
        jev_observation_qualified=jev_observation_qualified,
        fallback_source_paths=fallback_source_paths,
    )


def whole_source_graph(path: str, raw: bytes) -> Graph:
    digest = hashlib.sha256(raw).hexdigest()
    return Graph((GraphRecord(
        record_id="whole",
        kind="source",
        title="whole",
        content=raw.decode("utf-8"),
        provenance=Provenance(path, digest, "whole", True),
        trust=TrustClass.VERIFIED_SOURCE,
        sensitivity=Sensitivity.PUBLIC,
        freshness=Freshness.CURRENT,
        admission=Admission.VERIFIER,
        eligible=True,
        export_allowed=False,
    ),))


class RankedContextSelectionTests(unittest.TestCase):
    def tight_fixture(self):
        graph, snapshot, reader, candidates = fixture()
        one_optional = select(graph, spec(), snapshot, reader, candidates[:2])
        tight = replace(
            spec(),
            byte_budget=one_optional.projection.serialized_byte_count + 128,
        )
        return graph, snapshot, reader, candidates, tight

    def test_valid_rerank_changes_optional_inclusion_and_keeps_required_slot(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        baseline = select(graph, tight, snapshot, reader, candidates)
        reranked = select(
            graph,
            tight,
            snapshot,
            reader,
            candidates,
            observation(candidates, ("c0", "c2", "c1"), snapshot),
            jev_enabled=True,
            jev_observation_qualified=True,
        )

        self.assertEqual(baseline.order_source, "baseline")
        self.assertEqual(baseline.projection.included_optional_candidate_ids, ("c1",))
        self.assertEqual(reranked.order_source, "reranked")
        self.assertTrue(reranked.jev_source_revalidated)
        self.assertEqual(reranked.jev_decision.reason, "jev_rerank_applied")
        self.assertTrue(reranked.jev_decision.jev_observation_applied)
        self.assertTrue(reranked.jev_decision.classification_observation_applied)
        self.assertEqual(reranked.jev_decision.classification_source, "jev")
        self.assertEqual(reranked.projection.included_optional_candidate_ids, ("c2",))
        self.assertEqual(baseline.projection.selected_candidate_ids[0], "c0")
        self.assertEqual(reranked.projection.selected_candidate_ids[0], "c0")
        self.assertEqual(
            json.loads(reranked.projection.content)["approved_request_sha256"],
            APPROVED,
        )
        self.assertLessEqual(reranked.projection.serialized_byte_count, tight.byte_budget)

    def test_provider_neutral_classification_observation_can_rerank(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        result = select_ranked_context(
            graph,
            tight,
            snapshot,
            reader,
            query=QUERY,
            candidates=candidates,
            approved_request_sha256=APPROVED,
            classification_observation=classification_observation(
                candidates, ("c0", "c2", "c1"), snapshot
            ),
            jev_enabled=False,
        )

        self.assertEqual(result.order_source, "reranked")
        self.assertFalse(result.jev_decision.jev_enabled)
        self.assertEqual(result.jev_decision.reason, "classification_rerank_applied")
        self.assertFalse(result.jev_decision.jev_observation_applied)
        self.assertTrue(result.jev_decision.classification_observation_applied)
        self.assertEqual(result.jev_decision.classification_source, "external")
        self.assertEqual(
            json.loads(result.jev_decision.to_json())["classification_source"],
            "external",
        )
        self.assertEqual(result.projection.included_optional_candidate_ids, ("c2",))

    def test_invalid_or_stale_classification_observation_retains_baseline(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        valid = classification_observation(candidates, ("c0", "c2", "c1"), snapshot)
        for invalid in (
            {**valid, "proposed_order": ["c0", "c1", "c1"]},
            {**valid, "candidate_set_sha256": "0" * 64},
            {**valid, "status": "unavailable"},
        ):
            with self.subTest(invalid=invalid):
                result = select_ranked_context(
                    graph,
                    tight,
                    snapshot,
                    reader,
                    query=QUERY,
                    candidates=candidates,
                    approved_request_sha256=APPROVED,
                    classification_observation=invalid,
                    jev_enabled=False,
                )
                self.assertEqual(result.order_source, "baseline")
                self.assertEqual(
                    result.projection.included_optional_candidate_ids, ("c1",)
                )
                self.assertEqual(
                    result.jev_decision.reason, "classification_observation_invalid"
                )
                self.assertFalse(result.jev_decision.jev_observation_applied)
                self.assertFalse(result.jev_decision.classification_observation_applied)
                self.assertEqual(result.jev_decision.classification_source, "external")

    def test_native_and_normalized_observations_cannot_be_combined(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        result = select_ranked_context(
            graph,
            tight,
            snapshot,
            reader,
            query=QUERY,
            candidates=candidates,
            approved_request_sha256=APPROVED,
            jev_observation=observation(candidates, ("c0", "c2", "c1"), snapshot),
            classification_observation=classification_observation(
                candidates, ("c0", "c2", "c1"), snapshot
            ),
            jev_enabled=False,
            jev_observation_qualified=True,
        )

        self.assertEqual(result.order_source, "baseline")
        self.assertEqual(result.jev_decision.reason, "classification_observation_conflict")
        self.assertFalse(result.jev_decision.jev_observation_applied)
        self.assertFalse(result.jev_decision.classification_observation_applied)
        self.assertEqual(result.jev_decision.classification_source, "external")

    def test_rerank_keeps_rank_telemetry_but_presents_same_file_spans_in_source_order(self) -> None:
        path = "src/ordered.py"
        raw = b"0\n1\n2\n3\n"
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
        candidates = tuple(
            candidate(
                f"c{index}", path, digest, index * 2, index * 2 + 1,
                required=index == 0,
            )
            for index in range(4)
        )
        graph = Graph(tuple(
            source_record(item.record_id, path, digest, str(index))
            for index, item in enumerate(candidates)
        ))
        reader = SourceReader({path: raw})
        three = select(graph, spec(), snapshot, reader, candidates[:3])
        tight = replace(
            spec(), byte_budget=three.projection.serialized_byte_count + 128
        )

        baseline = select(graph, tight, snapshot, reader, candidates, jev_enabled=True)
        reranked = select(
            graph,
            tight,
            snapshot,
            reader,
            candidates,
            observation(candidates, ("c0", "c3", "c2", "c1"), snapshot),
            jev_enabled=True,
            jev_observation_qualified=True,
        )
        payload = json.loads(reranked.projection.content)

        self.assertEqual(baseline.projection.selected_candidate_ids, ("c0", "c1", "c2"))
        self.assertEqual(reranked.projection.selected_candidate_ids, ("c0", "c3", "c2"))
        self.assertEqual(reranked.projection.required_candidate_ids, ("c0",))
        self.assertEqual(
            [span["candidate_id"] for span in payload["spans"]],
            ["c0", "c2", "c3"],
        )
        self.assertTrue(all(
            "relationship_parent_candidate_id" in span for span in payload["spans"]
        ))

    def test_provider_binding_overhead_never_counts_as_jev_selection_effect(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        same = observation(candidates, ("c0", "c1", "c2"), snapshot)
        changed = observation(candidates, ("c0", "c2", "c1"), snapshot)

        for budget, expected in (
            (1002, ("c0",)),
            (1003, ("c0", "c1")),
            (1004, ("c0", "c1")),
        ):
            with self.subTest(budget=budget):
                task = replace(spec(), byte_budget=budget)
                baseline = select(
                    graph, task, snapshot, reader, candidates, jev_enabled=True
                )
                for observed in (same, changed):
                    result = select(
                        graph,
                        task,
                        snapshot,
                        reader,
                        candidates,
                        observed,
                        jev_enabled=True,
                        jev_observation_qualified=True,
                    )
                    self.assertEqual(baseline.projection.selected_candidate_ids, expected)
                    self.assertEqual(result.projection.selected_candidate_ids, expected)
                    self.assertEqual(result.order_source, "baseline")
                    self.assertFalse(result.jev_decision.jev_observation_applied)
                    self.assertFalse(
                        result.jev_decision.jev_call_could_affect_selection
                    )

    def test_malformed_forged_incomplete_or_hash_mismatched_observation_uses_baseline(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        valid = observation(candidates, ("c0", "c2", "c1"), snapshot)
        variants = [None, {}, {**valid, "status": "fallback"},
                    {**valid, "schema_version": "wrong"},
                    {**valid, "baseline_order": ["c0", "c2", "c1"]},
                    {**valid, "required_ids": []},
                    {**valid, "order": ["c0", "c2"]},
                    {**valid, "order": ["c2", "c1", "c0"]},
                    {**valid, "candidate_set_sha256": "0" * 64},
                    {**valid, "query_sha256": "0" * 64},
                    {**valid, "source_set_sha256": "0" * 64},
                    {**valid, "request_sha256": "0" * 64},
                    {**valid, "authority_bearing": True},
                    {**valid, "sufficient": True},
                    {**valid, "source_revalidated": False}]
        for changed in variants:
            with self.subTest(observation=changed):
                result = select(graph, tight, snapshot, reader, candidates, changed)
                self.assertEqual(result.route, "ranked")
                self.assertEqual(result.order_source, "baseline")
                self.assertFalse(result.jev_source_revalidated)
                self.assertTrue(result.source_revalidated)
                self.assertEqual(
                    result.projection.included_optional_candidate_ids, ("c1",)
                )

    def test_jev_decision_bypasses_or_requests_from_verified_budget_effect(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        disabled = select(graph, tight, snapshot, reader, candidates)
        request = select(
            graph,
            tight,
            snapshot,
            reader,
            candidates,
            jev_enabled=True,
        )
        all_fit = select(
            graph,
            spec(),
            snapshot,
            reader,
            candidates,
            jev_enabled=True,
        )
        relationship = replace(
            candidates[2], relationship_parent_candidate_id="c1"
        )
        relationship_only = select(
            graph,
            spec(),
            snapshot,
            reader,
            (candidates[0], candidates[1], relationship),
            jev_enabled=True,
        )

        self.assertEqual(disabled.jev_decision.reason, "jev_disabled")
        self.assertEqual(request.jev_decision.reason, "jev_observation_missing")
        self.assertTrue(request.jev_decision.jev_call_could_affect_selection)
        self.assertEqual(request.jev_decision.baseline_selected_candidate_count, 2)
        self.assertEqual(request.jev_decision.baseline_omitted_candidate_count, 1)
        self.assertEqual(request.jev_decision.baseline_selected_excerpt_bytes, 20)
        self.assertEqual(request.jev_decision.baseline_omitted_excerpt_bytes, 10)
        self.assertEqual(all_fit.jev_decision.reason, "all_optional_candidates_fit")
        self.assertFalse(all_fit.jev_decision.jev_call_could_affect_selection)
        self.assertTrue(relationship_only.jev_decision.relationship_candidate_signal)
        self.assertFalse(
            relationship_only.jev_decision.jev_call_could_affect_selection
        )
        telemetry = request.jev_decision.to_json()
        self.assertNotIn(QUERY, telemetry)
        self.assertNotIn("src/", telemetry)
        self.assertEqual(
            json.loads(telemetry)["schema_version"],
            "graph-ranked-context-jev-decision-v1",
        )

    def test_product_planner_prefers_only_source_witnessed_graph_additions(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        relationship = replace(
            candidates[2],
            candidate_id="relationship-c2",
            relationship_parent_candidate_id="c1",
        )
        graph_candidates = (*candidates, relationship)
        verified_graph = graph_with_relationship_edge(
            graph, snapshot, reader, candidates[1], relationship
        )
        graph_bundle = select(
            verified_graph,
            spec(),
            snapshot,
            reader,
            (candidates[0], candidates[1], relationship),
        )
        graph_tight = replace(
            spec(), byte_budget=graph_bundle.projection.serialized_byte_count + 128
        )
        direct = plan_ranked_context(
            graph,
            graph_tight,
            snapshot,
            reader,
            query=QUERY,
            direct_candidates=candidates,
            graph_candidates=candidates,
            jev_enabled=True,
        )
        fabricated = plan_ranked_context(
            graph,
            graph_tight,
            snapshot,
            reader,
            query=QUERY,
            direct_candidates=candidates,
            graph_candidates=graph_candidates,
            jev_enabled=True,
        )
        planned = plan_ranked_context(
            verified_graph,
            graph_tight,
            snapshot,
            reader,
            query=QUERY,
            direct_candidates=candidates,
            graph_candidates=graph_candidates,
            jev_enabled=True,
        )
        changed_required = plan_ranked_context(
            verified_graph,
            graph_tight,
            snapshot,
            reader,
            query=QUERY,
            direct_candidates=candidates,
            graph_candidates=(
                replace(candidates[0], record_id="record-c1"),
                *graph_candidates[1:],
            ),
            jev_enabled=True,
        )
        all_fit = plan_ranked_context(
            verified_graph,
            spec(),
            snapshot,
            reader,
            query=QUERY,
            direct_candidates=candidates,
            graph_candidates=graph_candidates,
            jev_enabled=True,
        )
        partial_parent = replace(
            candidates[1], candidate_id="partial-parent",
            byte_start=candidates[1].byte_start + 1,
        )
        parent_outside = plan_ranked_context(
            verified_graph, graph_tight, snapshot, reader, query=QUERY,
            direct_candidates=candidates,
            graph_candidates=(
                candidates[0], partial_parent, candidates[2],
                replace(
                    relationship,
                    relationship_parent_candidate_id=partial_parent.candidate_id,
                ),
            ),
        )
        target_outside = plan_ranked_context(
            verified_graph, graph_tight, snapshot, reader, query=QUERY,
            direct_candidates=candidates,
            graph_candidates=(
                *candidates,
                replace(
                    relationship,
                    candidate_id="partial-target",
                    byte_start=relationship.byte_start + 1,
                ),
            ),
        )

        self.assertEqual(direct.route, "direct")
        self.assertEqual(fabricated.route, "direct")
        self.assertEqual(planned.route, "graph")
        self.assertEqual(changed_required.route, "direct")
        self.assertEqual(parent_outside.route, "direct")
        self.assertEqual(target_outside.route, "direct")
        self.assertIsNone(planned.baseline.approved_request_sha256)
        baseline_payload = json.loads(planned.baseline.projection.content)
        self.assertNotIn("approved_request_sha256", baseline_payload)
        self.assertEqual(
            baseline_payload["schema_version"],
            "graph-ranked-context-baseline-v1",
        )
        self.assertTrue(
            planned.baseline.jev_decision.jev_call_could_affect_selection
        )
        self.assertEqual(
            planned.baseline.jev_decision.reason, "jev_observation_missing"
        )
        self.assertEqual(all_fit.baseline.jev_decision.reason, "all_optional_candidates_fit")
        self.assertFalse(
            all_fit.baseline.jev_decision.jev_call_could_affect_selection
        )
        telemetry = planned.to_json()
        self.assertNotIn(QUERY, telemetry)
        self.assertIn("context_fidelity", telemetry)
        self.assertEqual(
            json.loads(telemetry)["schema_version"],
            "graph-ranked-context-plan-v1",
        )

    def test_plan_task_facets_are_optional_serialized_metadata(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        baseline = plan_ranked_context(
            graph, spec(), snapshot, reader, query=QUERY,
            direct_candidates=candidates, graph_candidates=candidates,
            jev_enabled=True,
        )
        with_facets = plan_ranked_context(
            graph, spec(), snapshot, reader, query=QUERY,
            direct_candidates=candidates, graph_candidates=candidates,
            jev_enabled=True, task_facets=["implementation", "consequence"],
        )

        self.assertNotIn("task_facets", json.loads(baseline.to_json()))
        self.assertEqual(with_facets.task_facets, ("implementation", "consequence"))
        self.assertEqual(
            json.loads(with_facets.to_json())["task_facets"],
            ["implementation", "consequence"],
        )
        self.assertEqual(with_facets.route, baseline.route)
        self.assertEqual(with_facets.candidates, baseline.candidates)
        self.assertEqual(with_facets.baseline, baseline.baseline)

    def test_plan_task_facets_reject_invalid_values(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        invalid = (
            "implementation",
            {"implementation"},
            [""],
            [" implementation"],
            ["implementation", "implementation"],
            ["implementation\nconsequence"],
            ["facet"] * 21,
        )
        for task_facets in invalid:
            with self.subTest(task_facets=task_facets):
                with self.assertRaises((TypeError, ValueError)):
                    plan_ranked_context(
                        graph, spec(), snapshot, reader, query=QUERY,
                        direct_candidates=candidates, graph_candidates=candidates,
                        task_facets=task_facets,
                    )

    def test_plan_context_fidelity_reports_complete_excerpt_and_omitted_modes(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        complete = replace(candidates[1], source_unit_complete=True)
        self.assertEqual(complete.candidate_id, candidates[1].candidate_id)
        self.assertEqual(complete._packet_value(), candidates[1]._packet_value())
        with self.assertRaises(TypeError):
            replace(candidates[1], source_unit_complete=1)
        complete_candidates = (candidates[0], complete, candidates[2])
        complete_plan = plan_ranked_context(
            graph,
            tight,
            snapshot,
            reader,
            query=QUERY,
            direct_candidates=complete_candidates,
            graph_candidates=complete_candidates,
            task_facets=["optional"],
        )
        bounded_plan = plan_ranked_context(
            graph,
            tight,
            snapshot,
            reader,
            query=QUERY,
            direct_candidates=candidates,
            graph_candidates=candidates,
            task_facets=["optional"],
        )

        complete_fidelity = complete_plan.to_dict()["context_fidelity"]
        complete_decisions = {
            item["candidate_id"]: item
            for item in complete_fidelity["decisions"]
        }
        bounded_fidelity = bounded_plan.to_dict()["context_fidelity"]
        bounded_decisions = {
            item["candidate_id"]: item
            for item in bounded_fidelity["decisions"]
        }
        self.assertEqual(complete_decisions["c0"]["mode"], "excerpt")
        self.assertEqual(complete_decisions["c1"]["mode"], "source_unit")
        self.assertEqual(complete_decisions["c2"]["mode"], "omit")
        self.assertTrue(complete_decisions["c0"]["included"])
        self.assertTrue(complete_decisions["c1"]["included"])
        self.assertFalse(complete_decisions["c2"]["included"])
        self.assertEqual(bounded_decisions["c1"]["mode"], "excerpt")
        self.assertEqual(
            complete_plan.baseline.projection.selected_candidate_ids,
            bounded_plan.baseline.projection.selected_candidate_ids,
        )

    def test_plan_context_fidelity_reuse_state_requires_current_identity(self) -> None:
        graph, snapshot, reader, candidates = fixture()

        def build(
            *,
            query: str = QUERY,
            task: TaskSpec | None = None,
            current_snapshot: SourceSnapshotV4 = snapshot,
            current_candidates: tuple[RankedContextCandidate, ...] = candidates,
            prior_plan: RankedContextPlan | None = None,
        ) -> RankedContextPlan:
            return plan_ranked_context(
                graph,
                task or spec(),
                current_snapshot,
                reader,
                query=query,
                direct_candidates=current_candidates,
                graph_candidates=current_candidates,
                task_facets=["optional"],
                prior_plan=prior_plan,
            )

        first = build()
        same = build(prior_plan=first)
        changed_query = build(query=QUERY + " changed", prior_plan=first)
        wider = build(
            task=replace(spec(), byte_budget=spec().byte_budget + 1),
            prior_plan=first,
        )
        changed_snapshot = SourceSnapshotV4(
            (*snapshot.sources, SourceIdentityV4(
                "src/other.py", 5, hashlib.sha256(b"other").hexdigest()
            ))
        )
        changed_snapshot_plan = build(
            current_snapshot=changed_snapshot, prior_plan=first
        )
        changed_candidates = (*candidates[:2], replace(candidates[2], candidate_id="c2-new"))
        changed_candidate_plan = build(
            current_candidates=changed_candidates, prior_plan=first
        )
        without_prior = build()

        def state(plan: RankedContextPlan) -> str:
            return plan.to_dict()["context_fidelity"]["reuse_state"]

        self.assertEqual(state(first), "rebuild")
        self.assertEqual(state(same), "reuse")
        self.assertEqual(state(changed_query), "refresh")
        self.assertEqual(state(wider), "widen")
        self.assertEqual(state(changed_snapshot_plan), "rebuild")
        self.assertEqual(state(changed_candidate_plan), "rebuild")
        self.assertEqual(state(without_prior), "rebuild")
        self.assertEqual(
            first.baseline.projection.selected_candidate_ids,
            same.baseline.projection.selected_candidate_ids,
        )
        self.assertEqual(
            first.baseline.projection.selected_candidate_ids,
            without_prior.baseline.projection.selected_candidate_ids,
        )

    def test_unqualified_or_invalid_jev_observation_retains_baseline(self) -> None:
        graph, snapshot, reader, candidates, tight = self.tight_fixture()
        valid = observation(candidates, ("c0", "c2", "c1"), snapshot)
        unqualified = select(
            graph,
            tight,
            snapshot,
            reader,
            candidates,
            valid,
            jev_enabled=True,
        )
        invalid = select(
            graph,
            tight,
            snapshot,
            reader,
            candidates,
            {**valid, "source_revalidated": False},
            jev_enabled=True,
            jev_observation_qualified=True,
        )
        unbound = select_ranked_context(
            graph,
            tight,
            snapshot,
            reader,
            query=QUERY,
            candidates=candidates,
            jev_observation=valid,
            jev_enabled=True,
            jev_observation_qualified=True,
        )

        for result, reason in (
            (unqualified, "jev_observation_not_qualified"),
            (invalid, "jev_observation_invalid"),
            (unbound, "jev_observation_invalid"),
        ):
            self.assertEqual(result.order_source, "baseline")
            self.assertEqual(
                result.projection.included_optional_candidate_ids, ("c1",)
            )
            self.assertEqual(result.jev_decision.reason, reason)
            self.assertFalse(result.jev_decision.jev_observation_applied)
            self.assertNotIn(
                "approved_request_sha256",
                json.loads(result.projection.content),
            )

    def test_stale_digest_range_and_non_utf8_source_defer_without_source_content(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        stale = (replace(candidates[0], source_sha256="0" * 64),)
        changed_reader = SourceReader({"src/context.py": b"changed"})
        outside = (replace(candidates[0], byte_end=100),)
        invalid_raw = b"\xff"
        invalid_digest = hashlib.sha256(invalid_raw).hexdigest()
        invalid_snapshot = SourceSnapshotV4((
            SourceIdentityV4("src/invalid.py", 1, invalid_digest),
        ))
        invalid = (candidate(
            "bad", "src/invalid.py", invalid_digest, 0, 1, required=True
        ),)
        invalid_graph = Graph((source_record(
            invalid[0].record_id,
            "src/invalid.py",
            invalid_digest,
            "invalid",
        ),))
        cases = (
            (graph, snapshot, reader, stale),
            (graph, snapshot, changed_reader, (candidates[0],)),
            (graph, snapshot, reader, outside),
            (invalid_graph, invalid_snapshot, SourceReader({"src/invalid.py": invalid_raw}), invalid),
        )
        for case in cases:
            with self.subTest(case=case):
                result = select(case[0], spec(), *case[1:])
                self.assertEqual(result.route, "defer")
                self.assertTrue(result.projection.fail_closed)
                self.assertEqual(result.projection.excerpt_byte_count, 0)
                self.assertNotIn("required", result.projection.content)

    def test_exact_serialized_boundary_and_required_overflow(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        required = (candidates[0],)
        unbounded = select(graph, spec(), snapshot, reader, required)
        exact = select(
            graph,
            replace(spec(), byte_budget=unbounded.projection.serialized_byte_count),
            snapshot,
            reader,
            required,
        )
        overflow = select(
            graph,
            replace(spec(), byte_budget=unbounded.projection.serialized_byte_count - 1),
            snapshot,
            reader,
            required,
        )

        self.assertEqual(exact.route, "ranked")
        self.assertEqual(
            exact.projection.serialized_byte_count,
            len(exact.projection.content.encode("utf-8")),
        )
        self.assertEqual(exact.projection.excerpt_byte_count, 10)
        self.assertEqual(overflow.route, "defer")
        self.assertEqual(overflow.projection.selected_candidate_ids, ())

    def test_required_overflow_uses_direct_only_with_complete_allowlist(self) -> None:
        path = "src/fallback.py"
        raw = b"required fallback\n"
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
        required = (candidate(
            "r" * 64, path, digest, 0, len(raw), required=True, record_id="whole"
        ),)
        reader = SourceReader({path: raw})
        graph = whole_source_graph(path, raw)
        ranked = select(graph, spec(), snapshot, reader, required)
        from packages.core import assist
        direct = assist(
            graph,
            spec(),
            snapshot,
            reader,
            required_source_paths=(path,),
            fallback_source_paths=(path,),
            required_escalation=True,
        )
        self.assertLess(direct.projection.byte_count, ranked.projection.serialized_byte_count)
        tight = replace(spec(), byte_budget=ranked.projection.serialized_byte_count - 1)

        selected = select(
            graph, tight, snapshot, reader, required, fallback_source_paths=(path,),
        )
        absent = select(graph, tight, snapshot, reader, required)
        incomplete = select(
            graph, tight, snapshot, reader, required,
            fallback_source_paths=("src/other.py",),
        )
        over_budget = select(
            graph,
            replace(tight, byte_budget=direct.projection.byte_count - 1),
            snapshot,
            reader,
            required,
            fallback_source_paths=(path,),
        )

        self.assertEqual(selected.route, "direct")
        self.assertEqual(selected.order_source, "direct")
        self.assertEqual(selected.projection.selected_candidate_ids, ())
        self.assertEqual(selected.projection.required_candidate_ids, ("r" * 64,))
        for result in (absent, incomplete, over_budget):
            self.assertEqual(result.route, "defer")
            self.assertTrue(result.projection.fail_closed)

    def test_relationship_style_optional_candidate_never_becomes_required(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        relationship = replace(
            candidates[1],
            candidate_id="relationship-target",
            relationship_parent_candidate_id="c0",
        )
        graph = graph_with_relationship_edge(
            graph, snapshot, reader, candidates[0], relationship
        )
        result = select(
            graph, spec(), snapshot, reader, (candidates[0], relationship)
        )
        required_only = select(
            graph, spec(), snapshot, reader, (candidates[0],)
        )
        fail_closed = select(
            graph,
            replace(
                spec(), byte_budget=required_only.projection.serialized_byte_count
            ),
            snapshot,
            reader,
            (candidates[0], relationship),
        )

        self.assertEqual(result.projection.required_candidate_ids, ("c0",))
        self.assertEqual(
            result.projection.included_optional_candidate_ids,
            ("relationship-target",),
        )
        self.assertNotIn("relationship-target", result.projection.required_candidate_ids)
        self.assertEqual(fail_closed.route, "defer")
        self.assertTrue(fail_closed.projection.fail_closed)

    def test_incoming_relationship_candidate_requires_exact_original_edge(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        source = candidates[1]
        parent = candidates[2]
        graph = graph_with_relationship_edge(
            graph, snapshot, reader, source, parent, relation="imports"
        )
        incoming = replace(
            source,
            relationship_parent_candidate_id=parent.candidate_id,
            relationship_edge_id="edge-c1-c2",
            relationship_direction="incoming",
            relationship_relation="imports",
            relationship_sensitivity=Sensitivity.PUBLIC,
        )
        ordered = (candidates[0], parent, incoming)

        result = select(graph, spec(), snapshot, reader, ordered)

        self.assertEqual("ranked", result.route)
        self.assertIn(incoming.candidate_id, result.projection.included_optional_candidate_ids)

        forged = (
            replace(incoming, relationship_direction="outgoing"),
            replace(incoming, relationship_edge_id="edge:forged"),
            replace(incoming, relationship_relation="references"),
            replace(incoming, relationship_sensitivity=Sensitivity.INTERNAL),
            replace(incoming, record_id="record:forged"),
            replace(
                incoming,
                relationship_edge_id=None,
                relationship_direction=None,
                relationship_relation=None,
                relationship_sensitivity=None,
            ),
        )
        for changed in forged:
            with self.subTest(changed=changed):
                rejected = select(
                    graph, spec(), snapshot, reader,
                    (candidates[0], parent, changed),
                )
                self.assertEqual("defer", rejected.route)
                self.assertEqual(
                    "relationship_candidate_custody_mismatch", rejected.reason
                )

        non_reverse_graph = graph_with_relationship_edge(
            Graph(graph.records), snapshot, reader, source, parent,
            relation="references",
        )
        non_reverse = replace(incoming, relationship_relation="references")
        rejected = select(
            non_reverse_graph, spec(), snapshot, reader,
            (candidates[0], parent, non_reverse),
        )
        self.assertEqual("defer", rejected.route)
        self.assertEqual("relationship_candidate_custody_mismatch", rejected.reason)

        extra_digest = hashlib.sha256(b"").hexdigest()
        forged_snapshot = SourceSnapshotV4(tuple(sorted((
            *snapshot.sources,
            SourceIdentityV4("extra.py", 0, extra_digest),
        ), key=lambda item: item.path)))
        rejected = select(graph, spec(), forged_snapshot, reader, ordered)
        self.assertEqual("defer", rejected.route)
        self.assertEqual("relationship_candidate_custody_mismatch", rejected.reason)

    def test_relationship_provenance_rejects_required_missing_or_later_parent(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        relationship = replace(
            candidates[1], relationship_parent_candidate_id="c0"
        )
        with self.assertRaises(ValueError):
            replace(relationship, required=True)
        for changed in (
            replace(relationship, relationship_parent_candidate_id="missing"),
            relationship,
        ):
            ordered = (
                (candidates[0], changed)
                if changed.relationship_parent_candidate_id == "missing"
                else (changed, candidates[0])
            )
            with self.subTest(candidates=ordered), self.assertRaises(ValueError):
                select(graph, spec(), snapshot, reader, ordered)
        self.assertEqual(reader.checked_paths, [])
        self.assertEqual(reader.read_paths, [])

    def test_relationship_target_is_not_selected_without_its_primary_parent(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        short_target = replace(candidates[2], byte_end=candidates[2].byte_start + 1)
        target_only = select(
            graph,
            spec(),
            snapshot,
            reader,
            (candidates[0], short_target),
        )
        target_only_budget = replace(
            spec(), byte_budget=target_only.projection.serialized_byte_count
        )
        unbound = select(
            graph,
            target_only_budget,
            snapshot,
            reader,
            (candidates[0], candidates[1], short_target),
        )
        relationship = replace(
            short_target, relationship_parent_candidate_id=candidates[1].candidate_id
        )
        bound = select(
            graph,
            target_only_budget,
            snapshot,
            reader,
            (candidates[0], candidates[1], relationship),
        )

        self.assertEqual(unbound.projection.included_optional_candidate_ids, ("c2",))
        self.assertEqual(bound.projection.included_optional_candidate_ids, ())

        chained = replace(candidates[1], relationship_parent_candidate_id="c0")
        child = replace(candidates[2], relationship_parent_candidate_id="c1")
        with self.assertRaises(ValueError):
            select(graph, spec(), snapshot, reader, (candidates[0], chained, child))

    def test_relationship_parent_and_first_direct_child_are_an_atomic_bundle(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        first_child = replace(
            candidates[2], relationship_parent_candidate_id="c1"
        )
        second_child = replace(
            first_child, candidate_id="c3", record_id="record-c3"
        )
        graph = Graph((*graph.records, source_record(
            second_child.record_id,
            second_child.source_path,
            second_child.source_sha256,
            "optional-b",
        )))
        graph = graph_with_relationship_edge(
            graph, snapshot, reader, candidates[1], first_child
        )
        graph = Graph(
            graph.records,
            (
                *graph.edges,
                replace(
                    graph.edges[0],
                    edge_id="edge-c1-c3",
                    target_id=second_child.record_id,
                ),
            ),
        )
        parent_only = select(graph, spec(), snapshot, reader, candidates[:2])
        tight = replace(
            spec(), byte_budget=parent_only.projection.serialized_byte_count
        )

        omitted = select(
            graph, tight, snapshot, reader, (candidates[0], candidates[1], first_child)
        )
        first_bundle = select(
            graph,
            replace(spec(), byte_budget=select(
                graph,
                spec(),
                snapshot,
                reader,
                (candidates[0], candidates[1], first_child),
            ).projection.serialized_byte_count),
            snapshot,
            reader,
            (candidates[0], candidates[1], first_child, second_child),
        )

        self.assertEqual(omitted.projection.selected_candidate_ids, ("c0",))
        self.assertEqual(first_bundle.projection.selected_candidate_ids, ("c0", "c1", "c2"))
        self.assertEqual(first_bundle.projection.required_candidate_ids, ("c0",))

    def test_graph_record_authorization_rejects_before_source_read(self) -> None:
        graph, snapshot, _, candidates = fixture()
        selected = (candidates[0],)
        base = graph.record_map()[candidates[0].record_id]
        mismatched = replace(
            base,
            provenance=Provenance(
                "src/other.py", base.provenance.sha256, "candidate", True
            ),
        )
        cases = (
            (Graph(()), spec()),
            (Graph((mismatched,)), spec()),
            (Graph((replace(base, freshness=Freshness.STALE),)), spec()),
            (Graph((replace(base, eligible=False),)), spec()),
            (Graph((replace(base, sensitivity=Sensitivity.INTERNAL),)), spec()),
            (Graph((replace(base, sensitivity=Sensitivity.RESTRICTED),)), spec()),
        )
        for candidate_graph, task in cases:
            reader = SourceReader({"src/context.py": b"INTERNAL_SOURCE_TEXT"})
            with self.subTest(graph=candidate_graph):
                result = select(candidate_graph, task, snapshot, reader, selected)
                self.assertEqual(result.route, "defer")
                self.assertTrue(result.projection.fail_closed)
                self.assertEqual(reader.checked_paths, [])
                self.assertEqual(reader.read_paths, [])
                self.assertNotIn("INTERNAL_SOURCE_TEXT", result.projection.content)

        conflict_graph = Graph((
            base,
            replace(
                graph.record_map()[candidates[1].record_id],
                sensitivity=Sensitivity.INTERNAL,
            ),
        ))
        conflict_reader = SourceReader({"src/context.py": b"INTERNAL_SOURCE_TEXT"})
        conflict_task = replace(
            spec(),
            allowed_sensitivities=(Sensitivity.PUBLIC, Sensitivity.INTERNAL),
        )
        conflict = select(
            conflict_graph,
            conflict_task,
            snapshot,
            conflict_reader,
            candidates[:2],
        )
        self.assertEqual(conflict.route, "defer")
        self.assertEqual(conflict_reader.checked_paths, [])
        self.assertEqual(conflict_reader.read_paths, [])

    def test_unexpected_reader_exception_is_sanitized(self) -> None:
        graph, snapshot, _, candidates = fixture()
        reader = ExplodingReader({"src/context.py": b"unused"})

        result = select(graph, spec(), snapshot, reader, (candidates[0],))

        self.assertEqual(result.route, "defer")
        self.assertEqual(result.reason, "candidate_source_unavailable")
        self.assertNotIn("INTERNAL_SOURCE_TEXT", repr(result))
        self.assertNotIn("INTERNAL_SOURCE_TEXT", result.projection.content)

        property_result = select(
            graph,
            spec(),
            snapshot,
            PropertyExplodingReader(),
            (candidates[0],),
        )
        self.assertEqual(property_result.route, "defer")
        self.assertEqual(property_result.reason, "candidate_source_unavailable")
        self.assertNotIn("INTERNAL_READER_PROPERTY_TEXT", repr(property_result))
        self.assertNotIn(
            "INTERNAL_READER_PROPERTY_TEXT", property_result.projection.content
        )

    def test_unexpected_fallback_reader_exception_is_sanitized(self) -> None:
        path = "src/fallback.py"
        raw = b"required fallback\n"
        digest = hashlib.sha256(raw).hexdigest()
        graph = whole_source_graph(path, raw)
        snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
        required = (candidate(
            "r" * 64, path, digest, 0, len(raw), required=True, record_id="whole"
        ),)
        ranked = select(graph, spec(), snapshot, SourceReader({path: raw}), required)
        tight = replace(spec(), byte_budget=ranked.projection.serialized_byte_count - 1)
        reader = FallbackExplodingReader({path: raw})

        result = select(
            graph,
            tight,
            snapshot,
            reader,
            required,
            fallback_source_paths=(path,),
        )

        self.assertEqual(result.route, "defer")
        self.assertEqual(result.reason, "required_context_fallback_unavailable")
        self.assertEqual(reader.read_paths, [path, path])
        self.assertNotIn("INTERNAL_FALLBACK_SOURCE_TEXT", repr(result))
        self.assertNotIn("INTERNAL_FALLBACK_SOURCE_TEXT", result.projection.content)

    def test_exact_public_input_types_and_digests_are_required(self) -> None:
        graph, snapshot, reader, candidates = fixture()
        with self.assertRaises(TypeError):
            select_ranked_context(
                graph, spec(), snapshot, reader, query=QUERY, candidates=list(candidates),
                approved_request_sha256=APPROVED, jev_observation=None,
            )
        with self.assertRaises(ValueError):
            select_ranked_context(
                graph, spec(), snapshot, reader, query=QUERY, candidates=candidates,
                approved_request_sha256="invalid", jev_observation=None,
            )
        baseline = select_ranked_context(
            graph,
            spec(),
            snapshot,
            reader,
            query=QUERY,
            candidates=candidates,
        )
        self.assertIsNone(baseline.approved_request_sha256)
        with self.assertRaises(TypeError):
            select_ranked_context(
                graph,
                spec(),
                snapshot,
                reader,
                query=QUERY,
                candidates=candidates,
                jev_enabled=1,
            )


if __name__ == "__main__":
    unittest.main()
