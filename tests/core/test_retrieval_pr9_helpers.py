"""Canonical-core consumer tests for the PR9 successor helper repair.

These tests require the real repository and its existing dependencies. They are
not represented as executed by the isolated handoff tests.
"""
from __future__ import annotations
import hashlib
import random
import unittest

from packages.core import (Admission, Freshness, Graph, GraphRecord, Provenance,
                           Sensitivity, SourceIdentityV4, SourceSnapshotV4,
                           TrustClass, build_repository_tag_index)
from packages.core.retrieval import _line_window, _MAX_TAGS_PER_RECORD


class Reader:
    def __init__(self, path, raw):
        self.path, self.raw = path, raw

    def read_bytes(self, path):
        if path != self.path:
            raise ValueError("fixture path outside allowlist")
        return self.raw

    def is_symlink(self, path):
        return False


def fixture(raw):
    path = "docs/plain.md"
    sha = hashlib.sha256(raw).hexdigest()
    record = GraphRecord(record_id="repo:" + path, kind="source", title=path,
                         content=raw.decode("utf-8"), provenance=Provenance(path, sha, "bytes", True),
                         trust=TrustClass.VERIFIED_SOURCE, sensitivity=Sensitivity.PUBLIC,
                         freshness=Freshness.CURRENT, admission=Admission.VERIFIER, eligible=True)
    snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), sha),))
    return Graph((record,)), snapshot, Reader(path, raw)


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


if __name__ == "__main__":
    unittest.main()
