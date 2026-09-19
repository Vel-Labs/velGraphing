"""Canonical-core consumer tests for the PR9 successor helper repair.

These tests require the real repository and its existing dependencies. They are
not represented as executed by the isolated handoff tests.
"""
from __future__ import annotations
import hashlib
import random
import unittest

from packages.core import (Admission, AuthorityClass, EvidenceItem, Freshness,
                           Graph, GraphRecord, Provenance, RetrievalHit,
                           RetrievalResult, Sensitivity, SourceIdentityV4,
                           SourceSnapshotV4, TaskSpec, TrustClass,
                           build_repository_tag_index,
                           ranked_candidates_from_retrieval)
from packages.core.retrieval import _line_window, _MAX_TAGS_PER_RECORD

BUDGET = {
    "maximum_candidates": 64,
    "maximum_candidate_bytes": 32_768,
    "maximum_unit_bytes": 4096,
}


class Reader:
    def __init__(self, path, raw):
        self.path, self.raw = path, raw

    def read_bytes(self, path):
        if path != self.path:
            raise ValueError("fixture path outside allowlist")
        return self.raw

    def is_symlink(self, path):
        return False


def fixture(raw, path="docs/plain.md"):
    sha = hashlib.sha256(raw).hexdigest()
    record = GraphRecord(record_id="repo:" + path, kind="source", title=path,
                         content=raw.decode("utf-8"), provenance=Provenance(path, sha, "bytes", True),
                         trust=TrustClass.VERIFIED_SOURCE, sensitivity=Sensitivity.PUBLIC,
                         freshness=Freshness.CURRENT, admission=Admission.VERIFIER, eligible=True)
    snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), sha),))
    return Graph((record,)), snapshot, Reader(path, raw)


def result(path, *facets, evidence=()):
    return RetrievalResult(
        "direct", "fixture", (RetrievalHit(f"repo:{path}", path, 1, ("exact",), facets, 0),),
        (), "", 0, 100.0, (), (), False, evidence=evidence,
    )


class Pr9RetrievalHelperTests(unittest.TestCase):
    def test_window_keeps_deep_anchor(self):
        raw = b"prefix " * 800 + b"needle" + b" suffix" * 200
        start = raw.index(b"needle")
        left, right = _line_window(raw, start, start + 6, 800)
        self.assertTrue(left <= start < start + 6 <= right)
        self.assertLessEqual(right-left, 800)

    def test_window_keeps_utf8_character_boundaries(self):
        raw = ("界🙂é" * 700 + "needle" + "ø" * 300).encode()
        start = raw.index(b"needle")
        left, right = _line_window(raw, start, start+6, 800)
        self.assertIn("needle", raw[left:right].decode())
        self.assertLessEqual(right-left, 800)

    def test_oversize_anchor_is_empty_not_unrelated_evidence(self):
        self.assertEqual(_line_window(b"a"*1000, 100, 950, 800), (100, 100))

    def test_real_tag_extraction_retains_late_distinct_term(self):
        # No identifiers, code symbols, headings, or oracle-derived terms.
        graph, snapshot, reader = fixture(b"alpha " * (_MAX_TAGS_PER_RECORD + 32) + b"zeta\n")
        index = build_repository_tag_index(graph, snapshot, reader)
        self.assertIn("zeta", index.vocabulary)
        self.assertLessEqual(len(index.tags), _MAX_TAGS_PER_RECORD)
        self.assertEqual(index, build_repository_tag_index(graph, snapshot, reader))

    def test_changed_source_remains_rejected(self):
        graph, snapshot, reader = fixture(b"alpha zeta\n")
        reader.raw = b"changed source\n"
        with self.assertRaises(ValueError):
            build_repository_tag_index(graph, snapshot, reader)

    def test_seeded_utf8_windows_remain_bounded_and_anchored(self):
        rng = random.Random(20260918)
        for _ in range(300):
            text = "".join(rng.choice(("a", "é", "界", "🙂", "\n")) for _ in range(120))
            positions = [0]
            for char in text:
                positions.append(positions[-1] + len(char.encode()))
            i, j = sorted(rng.sample(range(len(positions)), 2))
            start, end = positions[i], positions[j]
            cap = end - start + rng.randint(0, 200)
            left, right = _line_window(text.encode(), start, end, cap)
            self.assertTrue(0 <= left <= start < end <= right <= len(text.encode()))
            self.assertLessEqual(right-left, cap)
            text.encode()[left:right].decode()

    def test_ranked_candidates_use_every_complete_source_occurrence(self):
        raw = (
            b'"""header and examples"""\n\n'
            b"def quick_sort(left):\n    return quick_sort(left[1:])\n\n"
            b"def quick_sort_right(right):\n    return quick_sort(right[:-1])\n"
        )
        graph, snapshot, reader = fixture(raw)
        candidates = ranked_candidates_from_retrieval(
            graph, TaskSpec("units", ("quick-sort",), node_budget=64), snapshot, reader,
            result("docs/plain.md", "quick-sort"), **BUDGET,
        )
        excerpts = [raw[item.byte_start:item.byte_end] for item in candidates]
        self.assertEqual(len(excerpts), 2)
        self.assertTrue(excerpts[0].startswith(b"def quick_sort(left)"))
        self.assertTrue(excerpts[1].startswith(b"def quick_sort_right"))
        self.assertEqual(candidates, ranked_candidates_from_retrieval(
            graph, TaskSpec("units", ("quick-sort",), node_budget=64), snapshot, reader,
            result("docs/plain.md", "quick-sort"), **BUDGET,
        ))

    def test_complete_function_precedes_equally_matched_header(self):
        raw = (
            b'"""quick_sort reference"""\n\n'
            b"def quick_sort(values):\n    return values\n"
        )
        graph, snapshot, reader = fixture(raw, "src/quick_sort.py")
        candidates = ranked_candidates_from_retrieval(
            graph, TaskSpec("complete-first", ("quick-sort",)), snapshot, reader,
            result("src/quick_sort.py", "quick-sort"), **BUDGET,
        )
        excerpts = [raw[item.byte_start:item.byte_end] for item in candidates]
        self.assertGreaterEqual(len(excerpts), 2)
        self.assertTrue(excerpts[0].startswith(b"def quick_sort"))
        self.assertTrue(any(item.startswith(b'"""quick_sort') for item in excerpts[1:]))

    def test_required_non_hit_evidence_is_first_and_fail_closed(self):
        sources = {
            "docs/hit.md": b"alpha optional\n",
            "docs/required.md": b"required proof\n",
        }
        records = []
        for path, raw in sources.items():
            digest = hashlib.sha256(raw).hexdigest()
            records.append(GraphRecord(
                f"repo:{path}", "source", path, raw.decode(),
                Provenance(path, digest, "bytes", True), TrustClass.VERIFIED_SOURCE,
                Sensitivity.PUBLIC, Freshness.CURRENT, Admission.VERIFIER, True,
            ))
        snapshot = SourceSnapshotV4(tuple(
            SourceIdentityV4(path, len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in sorted(sources.items())
        ))

        class MapReader:
            def read_bytes(self, path): return sources[path]
            def is_symlink(self, path): return False

        required_raw = sources["docs/required.md"]
        evidence = EvidenceItem(
            "repo:docs/required.md", "docs/required.md",
            hashlib.sha256(required_raw).hexdigest(), 0, len(required_raw),
            hashlib.sha256(required_raw).hexdigest(), AuthorityClass.RUNTIME,
            ("proof",),
        )
        retrieval = RetrievalResult(
            "direct", "fixture", (
                RetrievalHit("repo:docs/hit.md", "docs/hit.md", 1, ("exact",), ("alpha",), 0),
            ), (), "", 0, 100.0, (), (), False, evidence=(evidence,),
        )
        candidates = ranked_candidates_from_retrieval(
            Graph(tuple(records)), TaskSpec("required-non-hit", ("alpha",)),
            snapshot, MapReader(), retrieval, **BUDGET,
        )
        self.assertTrue(candidates[0].required)
        self.assertEqual(candidates[0].source_path, "docs/required.md")
        bad = EvidenceItem(
            evidence.record_id, evidence.source_path, evidence.source_sha256,
            evidence.byte_start, evidence.byte_end, "0" * 64,
            evidence.authority_class, evidence.obligation_ids,
        )
        with self.assertRaisesRegex(ValueError, "required_candidate_custody_mismatch"):
            ranked_candidates_from_retrieval(
                Graph(tuple(records)), TaskSpec("bad-required", ("alpha",)),
                snapshot, MapReader(),
                RetrievalResult(
                    "direct", "fixture", (), (), "", 0, 0.0, (), (), False,
                    evidence=(bad,),
                ),
                **BUDGET,
            )

    def test_required_overflow_and_changed_source_fail_closed(self):
        raw = b"alpha " * 900
        graph, snapshot, reader = fixture(raw)
        digest = hashlib.sha256(raw).hexdigest()
        evidence = EvidenceItem(
            "repo:docs/plain.md", "docs/plain.md", digest, 0, len(raw), digest,
            AuthorityClass.RUNTIME, ("required",),
        )
        with self.assertRaisesRegex(ValueError, "required_candidate_budget_exceeded"):
            ranked_candidates_from_retrieval(
                graph, TaskSpec("required", ("alpha",), byte_budget=20_000), snapshot,
                reader, result("docs/plain.md", "alpha", evidence=(evidence,)), **BUDGET,
            )
        reader.raw = b"changed\n"
        with self.assertRaises(ValueError):
            ranked_candidates_from_retrieval(
                graph, TaskSpec("stale", ("alpha",)), snapshot, reader,
                result("docs/plain.md", "alpha"), **BUDGET,
            )

    def test_ranked_candidate_caps_apply_to_all_occurrences(self):
        raw = b"\n\n".join(
            f"alpha paragraph {index}".encode() for index in range(100)
        ) + b"\n"
        graph, snapshot, reader = fixture(raw)
        candidates = ranked_candidates_from_retrieval(
            graph, TaskSpec("caps", ("alpha",), node_budget=200, byte_budget=100_000),
            snapshot, reader, result("docs/plain.md", "alpha"), **BUDGET,
        )
        self.assertEqual(len(candidates), 64)
        self.assertLessEqual(sum(item.byte_end-item.byte_start for item in candidates), 32_768)
        self.assertTrue(all(item.byte_end-item.byte_start <= 4096 for item in candidates))
        self.assertEqual(len({item.candidate_id for item in candidates}), len(candidates))
        low_node_budget = ranked_candidates_from_retrieval(
            graph, TaskSpec("caps-low-node", ("alpha",), node_budget=1),
            snapshot, reader, result("docs/plain.md", "alpha"), **BUDGET,
        )
        self.assertEqual(candidates, low_node_budget)

    def test_noisy_first_hit_cannot_crowd_out_later_complete_unit(self):
        sources = {
            "docs/noisy.md": b"\n\n".join(b"alpha" for _ in range(100)) + b"\n",
            "src/later.py": b"def alpha_later():\n    return 'kept'\n",
        }
        records = []
        for path, raw in sources.items():
            digest = hashlib.sha256(raw).hexdigest()
            records.append(GraphRecord(
                f"repo:{path}", "source", path, raw.decode(),
                Provenance(path, digest, "bytes", True),
                TrustClass.VERIFIED_SOURCE, Sensitivity.PUBLIC, Freshness.CURRENT,
                Admission.VERIFIER, True,
            ))
        snapshot = SourceSnapshotV4(tuple(
            SourceIdentityV4(path, len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in sorted(sources.items())
        ))

        class MapReader:
            def read_bytes(self, path): return sources[path]
            def is_symlink(self, path): return False

        retrieval = RetrievalResult(
            "direct", "fixture", (
                RetrievalHit("repo:docs/noisy.md", "docs/noisy.md", 2, ("exact",), ("alpha",), 0),
                RetrievalHit("repo:src/later.py", "src/later.py", 1, ("exact",), ("alpha",), 0),
            ), (), "", 0, 100.0, (), (), False,
        )
        candidates = ranked_candidates_from_retrieval(
            Graph(tuple(records)), TaskSpec("fair", ("alpha",), node_budget=64),
            snapshot, MapReader(), retrieval, **BUDGET,
        )
        self.assertEqual(len(candidates), 64)
        later = [item for item in candidates if item.source_path == "src/later.py"]
        self.assertEqual(len(later), 1)
        self.assertEqual(
            sources["src/later.py"][later[0].byte_start:later[0].byte_end],
            sources["src/later.py"],
        )


if __name__ == "__main__":
    unittest.main()
