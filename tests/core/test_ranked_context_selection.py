from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import unittest

from packages.core import (
    Admission,
    Freshness,
    Graph,
    GraphRecord,
    Provenance,
    RankedContextCandidate,
    Sensitivity,
    SourceIdentityV4,
    SourceSnapshotV4,
    TaskSpec,
    TrustClass,
    select_ranked_context,
)
from packages.core import jev


APPROVED = "f" * 64
QUERY = "find required and optional evidence"


class SourceReader:
    def __init__(self, sources: dict[str, bytes], symlinks: tuple[str, ...] = ()) -> None:
        self.sources = sources
        self.symlinks = set(symlinks)

    def read_bytes(self, project_relative_path: str) -> bytes:
        return self.sources[project_relative_path]

    def is_symlink(self, project_relative_path: str) -> bool:
        return project_relative_path in self.symlinks


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
) -> RankedContextCandidate:
    return RankedContextCandidate(identity, path, digest, start, end, required)


def fixture() -> tuple[SourceSnapshotV4, SourceReader, tuple[RankedContextCandidate, ...]]:
    path = "src/context.py"
    raw = b"requiredxx\noptional-a\noptional-b\n"
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
    candidates = (
        candidate("c0", path, digest, 0, 10, required=True),
        candidate("c1", path, digest, 11, 21, required=False),
        candidate("c2", path, digest, 22, 32, required=False),
    )
    return snapshot, SourceReader({path: raw}), candidates


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


def select(
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReader,
    candidates: tuple[RankedContextCandidate, ...],
    observed: object = None,
    *,
    fallback_graph: Graph | None = None,
    fallback_source_paths: tuple[str, ...] = (),
):
    return select_ranked_context(
        task,
        snapshot,
        reader,
        query=QUERY,
        candidates=candidates,
        approved_request_sha256=APPROVED,
        jev_observation=observed,
        fallback_graph=fallback_graph,
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
        snapshot, reader, candidates = fixture()
        one_optional = select(spec(), snapshot, reader, candidates[:2])
        tight = replace(spec(), byte_budget=one_optional.projection.serialized_byte_count)
        return snapshot, reader, candidates, tight

    def test_valid_rerank_changes_optional_inclusion_and_keeps_required_slot(self) -> None:
        snapshot, reader, candidates, tight = self.tight_fixture()
        baseline = select(tight, snapshot, reader, candidates)
        reranked = select(
            tight,
            snapshot,
            reader,
            candidates,
            observation(candidates, ("c0", "c2", "c1"), snapshot),
        )

        self.assertEqual(baseline.order_source, "baseline")
        self.assertEqual(baseline.projection.included_optional_candidate_ids, ("c1",))
        self.assertEqual(reranked.order_source, "reranked")
        self.assertTrue(reranked.jev_source_revalidated)
        self.assertEqual(reranked.projection.included_optional_candidate_ids, ("c2",))
        self.assertEqual(baseline.projection.selected_candidate_ids[0], "c0")
        self.assertEqual(reranked.projection.selected_candidate_ids[0], "c0")
        self.assertEqual(
            json.loads(reranked.projection.content)["approved_request_sha256"],
            APPROVED,
        )
        self.assertLessEqual(reranked.projection.serialized_byte_count, tight.byte_budget)

    def test_malformed_forged_incomplete_or_hash_mismatched_observation_uses_baseline(self) -> None:
        snapshot, reader, candidates, tight = self.tight_fixture()
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
                result = select(tight, snapshot, reader, candidates, changed)
                self.assertEqual(result.route, "ranked")
                self.assertEqual(result.order_source, "baseline")
                self.assertFalse(result.jev_source_revalidated)
                self.assertTrue(result.source_revalidated)
                self.assertEqual(
                    result.projection.included_optional_candidate_ids, ("c1",)
                )

    def test_stale_digest_range_and_non_utf8_source_defer_without_source_content(self) -> None:
        snapshot, reader, candidates = fixture()
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
        cases = (
            (snapshot, reader, stale),
            (snapshot, changed_reader, (candidates[0],)),
            (snapshot, reader, outside),
            (invalid_snapshot, SourceReader({"src/invalid.py": invalid_raw}), invalid),
        )
        for case in cases:
            with self.subTest(case=case):
                result = select(spec(), *case)
                self.assertEqual(result.route, "defer")
                self.assertTrue(result.projection.fail_closed)
                self.assertEqual(result.projection.excerpt_byte_count, 0)
                self.assertNotIn("required", result.projection.content)

    def test_exact_serialized_boundary_and_required_overflow(self) -> None:
        snapshot, reader, candidates = fixture()
        required = (candidates[0],)
        unbounded = select(spec(), snapshot, reader, required)
        exact = select(
            replace(spec(), byte_budget=unbounded.projection.serialized_byte_count),
            snapshot,
            reader,
            required,
        )
        overflow = select(
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
        required = (candidate("r" * 64, path, digest, 0, len(raw), required=True),)
        reader = SourceReader({path: raw})
        graph = whole_source_graph(path, raw)
        ranked = select(spec(), snapshot, reader, required)
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
            tight, snapshot, reader, required,
            fallback_graph=graph, fallback_source_paths=(path,),
        )
        absent = select(tight, snapshot, reader, required)
        incomplete = select(
            tight, snapshot, reader, required,
            fallback_graph=graph, fallback_source_paths=("src/other.py",),
        )
        over_budget = select(
            replace(tight, byte_budget=direct.projection.byte_count - 1),
            snapshot,
            reader,
            required,
            fallback_graph=graph,
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
        snapshot, reader, candidates = fixture()
        relationship = replace(candidates[1], candidate_id="relationship-target")
        result = select(spec(), snapshot, reader, (candidates[0], relationship))

        self.assertEqual(result.projection.required_candidate_ids, ("c0",))
        self.assertEqual(
            result.projection.included_optional_candidate_ids,
            ("relationship-target",),
        )
        self.assertNotIn("relationship-target", result.projection.required_candidate_ids)

    def test_exact_public_input_types_and_digests_are_required(self) -> None:
        snapshot, reader, candidates = fixture()
        with self.assertRaises(TypeError):
            select_ranked_context(
                spec(), snapshot, reader, query=QUERY, candidates=list(candidates),
                approved_request_sha256=APPROVED, jev_observation=None,
            )
        with self.assertRaises(ValueError):
            select_ranked_context(
                spec(), snapshot, reader, query=QUERY, candidates=candidates,
                approved_request_sha256="invalid", jev_observation=None,
            )


if __name__ == "__main__":
    unittest.main()
