from __future__ import annotations

import unittest

from packages.core.navigation_v5 import NavigationBudget, NavigationV5
from packages.core.source_coordinates import DeterministicFixtureProvider, SourceCoordinate, source_snapshot


class NavigationV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = source_snapshot(
            {
                "src/a.py": "def run(value):\n    return helper(value)\n",
                "src/b.py": "def helper(value):\n    return value\n",
                "tests/test_run.py": "def test_run():\n    assert run(1) == 1\n",
            }
        )
        a = self.snapshot.source("src/a.py")
        b = self.snapshot.source("src/b.py")
        test = self.snapshot.source("tests/test_run.py")
        self.run = SourceCoordinate(self.snapshot.snapshot_sha256, a.path, a.source_sha256, 0, 14, 1, 1, "function", "definition", "run")
        self.call = SourceCoordinate(self.snapshot.snapshot_sha256, a.path, a.source_sha256, 32, 38, 2, 2, "function", "call", "helper", "run")
        self.helper = SourceCoordinate(self.snapshot.snapshot_sha256, b.path, b.source_sha256, 0, 17, 1, 1, "function", "definition", "helper")
        self.test_call = SourceCoordinate(self.snapshot.snapshot_sha256, test.path, test.source_sha256, 28, 31, 2, 2, "function", "call", "run", "test_run")
        self.navigator = NavigationV5(self.snapshot, DeterministicFixtureProvider((self.run, self.call, self.helper, self.test_call)))

    def test_graph_funnel_is_narrow_and_deterministic(self) -> None:
        graph = (
            {"source_path": "tests/test_run.py", "rank": 2},
            {"source_path": "src/a.py", "rank": 1},
        )
        result = self.navigator.search("run", graph, max_hops=0)
        self.assertTrue(result.supported)
        self.assertEqual(("src/a.py", "tests/test_run.py"), tuple(item.coordinate.source_path for item in result))
        self.assertTrue(all(item.content is None for item in result))
        self.assertFalse(result.authority_bearing)
        self.assertEqual(("src/a.py", "tests/test_run.py"), tuple(row["source_path"] for row in result.graph_trace))
        self.assertEqual(2, result.cost.regions_considered)
        self.assertEqual(result.cost["candidate_count"], len(result))

    def test_paths_are_custody_checked_and_malicious_paths_defer(self) -> None:
        cases = (
            ({"source_path": "/etc/passwd"}, "path_invalid"),
            ({"source_path": "../src/a.py"}, "path_traversal"),
            ({"source_path": "src/../b.py"}, "path_traversal"),
            ({"source_path": "missing.py"}, "path_unknown"),
            ({"source_path": "src/a.py", "source_sha256": "0" * 64}, "source_hash_mismatch"),
            ({"source_path": "src/a.py", "snapshot_sha256": "0" * 64}, "source_custody_mismatch"),
        )
        for entry, reason in cases:
            with self.subTest(entry=entry):
                result = self.navigator.search("run", (entry,), max_hops=0)
                self.assertTrue(result.deferred)
                self.assertEqual(reason, result.reason)

    def test_explicit_fallback_is_accounted_and_does_not_add_authority(self) -> None:
        result = self.navigator.search(
            "run",
            ({"source_path": "src/a.py", "rank": 1},),
            direct_paths=("tests/test_run.py",),
            max_hops=0,
        )
        self.assertTrue(result.supported)
        self.assertTrue(result.cost.direct_fallback_used)
        self.assertEqual(len(self.snapshot.source("tests/test_run.py").content), result.cost.fallback_bytes)
        self.assertEqual(result.cost.source_bytes_read, result.cost.fallback_bytes)
        self.assertFalse(result.authority_bearing)
        self.assertTrue(all(item.content is None for item in result))

    def test_exact_read_is_the_authority_bearing_operation(self) -> None:
        result = self.navigator.read_exact(self.run)
        self.assertTrue(result.supported)
        self.assertTrue(result.authority_bearing)
        self.assertEqual(b"def run(value)", result.items[0].content)
        foreign = SourceCoordinate("f" * 64, self.run.source_path, self.run.source_sha256, self.run.byte_start, self.run.byte_end, 1, 1, "function", "definition", "run")
        self.assertEqual("source_custody_mismatch", self.navigator.read_exact(foreign).reason)

    def test_one_hop_is_bounded_and_marks_supporting_context(self) -> None:
        result = self.navigator.search("helper", ({"source_path": "src/a.py", "rank": 1},))
        self.assertTrue(result.supported)
        self.assertEqual(1, result.cost.hops)
        self.assertEqual(("src/a.py", "src/b.py"), tuple(item.coordinate.source_path for item in result))
        self.assertEqual(("src/b.py",), tuple(item.source_path for item in result.supporting_context))
        self.assertEqual("supporting_context", result.items[-1].relation)
        self.assertTrue(self.navigator.search("helper", (), max_hops=2).deferred)

    def test_budget_overruns_defer_without_truncation(self) -> None:
        small = NavigationV5(
            self.snapshot,
            DeterministicFixtureProvider((self.run, self.call, self.helper, self.test_call)),
            budget=NavigationBudget(max_candidates=1, max_source_bytes=4, max_metadata_bytes=4096),
        )
        self.assertEqual("candidate_budget_exhausted", small.search("run", ({"source_path": "src/a.py"}, {"source_path": "tests/test_run.py"}), max_hops=0).reason)
        self.assertEqual("source_budget_exhausted", small.search("run", (), direct_paths=("tests/test_run.py",), max_hops=0).reason)
        with self.assertRaises(ValueError):
            NavigationBudget(max_steps=7)

    def test_result_costs_are_deterministic(self) -> None:
        graph = ({"source_path": "src/a.py", "rank": 3}, {"source_path": "tests/test_run.py", "rank": 2})
        first = self.navigator.search("run", graph, max_hops=0).to_dict()
        second = self.navigator.search("run", tuple(reversed(graph)), max_hops=0).to_dict()
        self.assertEqual(first, second)
        self.assertIn("result_metadata_bytes", first["cost"])


if __name__ == "__main__":
    unittest.main()
