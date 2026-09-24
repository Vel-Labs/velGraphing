"""A Graph route must survive packing, not merely appear in a candidate pool."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from packages.core import RankedContextCandidate, Sensitivity, TaskSpec
from packages.core.selection import plan_ranked_context

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "plugins/graph-engineering/skills/graph-find/scripts/graph_find.py"
_spec = importlib.util.spec_from_file_location("selected_relationship_route_adapter", ADAPTER_PATH)
assert _spec is not None and _spec.loader is not None
adapter = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = adapter
_spec.loader.exec_module(adapter)


class SelectedRelationshipRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, *, child_padding: int = 0, baseline_padding: int = 0):
        self.files = {
            "notes.txt": b"Verified baseline context.\n" + b"n" * baseline_padding,
            "main.py": b"from dependency import process\n",
            "dependency.py": b'def process():\n    """' + b"x" * child_padding + b'"""\n    return 1\n',
        }
        for path, raw in self.files.items():
            (self.root / path).write_bytes(raw)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        graph, snapshot, reader, _ = adapter._scan(self.root, 100_000, 200_000)
        self.assertEqual(1, len(graph.edges))
        edge = graph.edges[0]

        def candidate(path: str, **kwargs) -> RankedContextCandidate:
            raw = self.files[path]
            return RankedContextCandidate(
                hashlib.sha256(path.encode()).hexdigest(), path,
                hashlib.sha256(raw).hexdigest(), 0, len(raw), False,
                "repo:" + path, **kwargs,
            )

        baseline = candidate("notes.txt")
        parent = candidate("main.py")
        child = candidate(
            "dependency.py",
            relationship_parent_candidate_id=parent.candidate_id,
            relationship_edge_id=edge.edge_id,
            relationship_direction="outgoing",
            relationship_relation=edge.relation,
            relationship_sensitivity=edge.sensitivity,
        )
        return graph, snapshot, reader, baseline, parent, child

    def plan(self, fixture, *, budget: int, graph_order=None, direct_order=None):
        graph, snapshot, reader, baseline, parent, child = fixture
        task = TaskSpec(
            "public-route-canary", ("process",), byte_budget=budget,
            allowed_sensitivities=(Sensitivity.PUBLIC, Sensitivity.INTERNAL),
        )
        return plan_ranked_context(
            graph, task, snapshot, reader,
            query="Explain process using the supplied source.",
            direct_candidates=(baseline,) if direct_order is None else direct_order,
            graph_candidates=(baseline, parent, child) if graph_order is None else graph_order,
        )

    def test_pruned_relationship_bundle_falls_back_to_exact_direct_baseline(self) -> None:
        fixture = self.fixture(child_padding=3500)
        plan = self.plan(fixture, budget=2000)
        self.assertEqual("direct", plan.route)
        self.assertEqual("graph_selection_no_retained_relationship_gain", plan.reason)
        self.assertEqual((fixture[3],), plan.candidates)
        self.assertEqual((fixture[3].candidate_id,), plan.baseline.projection.selected_candidate_ids)
        self.assertFalse(plan.baseline.projection.fail_closed)
        self.assertLessEqual(plan.baseline.projection.serialized_byte_count, 2000)

    def test_fitting_new_relationship_remains_graph(self) -> None:
        fixture = self.fixture()
        plan = self.plan(fixture, budget=10_000)
        self.assertEqual("graph", plan.route)
        selected = set(plan.baseline.projection.selected_candidate_ids)
        self.assertEqual({c.candidate_id for c in fixture[3:]}, selected)
        self.assertEqual("graph_adds_source_witnessed_relationship_candidates", plan.reason)

    def test_displacement_guard_reason_is_preserved(self) -> None:
        fixture = self.fixture(baseline_padding=600)
        _, _, _, baseline, parent, child = fixture
        plan = self.plan(fixture, budget=2300, graph_order=(parent, child, baseline))
        self.assertEqual("direct", plan.route)
        self.assertEqual("graph_selection_would_displace_direct_baseline", plan.reason)
        self.assertEqual((baseline,), plan.candidates)

    def test_unchanged_direct_pool_does_not_claim_graph(self) -> None:
        fixture = self.fixture()
        plan = self.plan(fixture, budget=10_000, graph_order=(fixture[3],))
        self.assertEqual("direct", plan.route)
        self.assertEqual("direct_baseline_no_graph_relationship_gain", plan.reason)

    def test_missing_parent_cannot_establish_relationship_gain(self) -> None:
        fixture = self.fixture()
        plan = self.plan(fixture, budget=10_000, graph_order=(fixture[3], fixture[5]))
        self.assertEqual("direct", plan.route)
        self.assertEqual((fixture[3],), plan.candidates)

    def test_stale_relationship_source_cannot_become_graph(self) -> None:
        fixture = self.fixture()
        fixture[2].sources["dependency.py"] = b"untrusted changed source\n"
        plan = self.plan(fixture, budget=10_000)
        self.assertEqual("direct", plan.route)
        self.assertEqual((fixture[3],), plan.candidates)

    def test_required_direct_candidate_cannot_be_dropped(self) -> None:
        fixture = self.fixture()
        baseline = replace(fixture[3], required=True)
        plan = self.plan(
            fixture, budget=10_000,
            direct_order=(baseline,), graph_order=(fixture[4], fixture[5]),
        )
        self.assertEqual("direct", plan.route)
        self.assertIn(baseline.candidate_id, plan.baseline.projection.required_candidate_ids)

    def test_existing_direct_child_is_not_new_graph_gain(self) -> None:
        fixture = self.fixture()
        _, _, _, baseline, parent, child = fixture
        plan = self.plan(
            fixture, budget=10_000,
            direct_order=(baseline, parent, child),
        )
        self.assertEqual("direct", plan.route)
        self.assertEqual("direct_baseline_no_graph_relationship_gain", plan.reason)


if __name__ == "__main__":
    unittest.main()
