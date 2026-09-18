"""Observable public-fixture gates for the opt-in v4 frontier adapter."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "benchmarks"))
from time_to_correct_frontier import (Unit, add_literal_relationships,
                                     candidate_packet, digest, expand_with_core_select,
                                     finalize_packet, pack_units, select_frontier, units_for_record)
from packages.core.models import (Admission, Freshness, Graph, GraphRecord,
                                  Provenance, Sensitivity, TrustClass)


def graph_for(sources):
    return Graph(tuple(GraphRecord(
        record_id="repo:" + path, kind="source", title=path, content=raw.decode(),
        provenance=Provenance(path, digest(raw), "fixture-bytes", True),
        trust=TrustClass.VERIFIED_SOURCE, sensitivity=Sensitivity.INTERNAL,
        freshness=Freshness.CURRENT, admission=Admission.VERIFIER, eligible=True,
    ) for path, raw in sorted(sources.items())))


class PackingTests(unittest.TestCase):
    def setUp(self):
        self.sources = {"a.md": b"x" * 20000, "b.md": b"y" * 10000}
        self.units = tuple(Unit("a.md", digest(self.sources["a.md"]), i * 2000, (i + 1) * 2000,
                                ("same",)) for i in range(8)) + (
            Unit("b.md", digest(self.sources["b.md"]), 0, 2000, ("other",)),)

    def test_pool_is_larger_than_answer_and_order_changes_selected_subset(self):
        pool = pack_units(self.units, self.sources, byte_budget=32768, count_budget=24)
        self.assertEqual(len(pool), 9)
        first = finalize_packet("query", pool, self.sources)
        second = finalize_packet("query", pool, self.sources, tuple(f"c{i}" for i in reversed(range(9))))
        self.assertEqual(len(first["candidates"]), 8)
        self.assertNotEqual({c["id"] for c in first["candidates"]},
                            {c["id"] for c in second["candidates"]})
        self.assertEqual(sum(c["byte_end"] - c["byte_start"] for c in first["candidates"]), 16000)

    def test_distinct_spans_from_same_file_survive(self):
        selected = pack_units(self.units[:4], self.sources, byte_budget=10000, count_budget=6)
        self.assertEqual(len(selected), 4)

    def test_file_and_facet_diversity_overrides_redundant_prefix(self):
        chosen = pack_units(self.units, self.sources, byte_budget=4000, count_budget=2)
        self.assertEqual({u.path for u in chosen}, {"a.md", "b.md"})

    def test_required_unit_survives_optional_pruning(self):
        units = (*self.units[:-1], replace(self.units[-1], required=True))
        chosen = pack_units(units, self.sources, byte_budget=2000, count_budget=1)
        self.assertEqual(chosen, (units[-1],))

    def test_required_pool_slots_cannot_be_reordered(self):
        units = (replace(self.units[0], required=True), self.units[1])
        with self.assertRaisesRegex(ValueError, "required_pool_position"):
            pack_units(units, self.sources, byte_budget=4000, count_budget=2, order=(1, 0))

    def test_required_oversize_defers_instead_of_dropping(self):
        units = (replace(self.units[0], required=True),)
        with self.assertRaisesRegex(ValueError, "required_evidence"):
            pack_units(units, self.sources, byte_budget=1000, count_budget=1)

    def test_stale_source_does_not_fall_back_to_old_packet(self):
        changed = {**self.sources, "a.md": b"z" * 20000}
        with self.assertRaisesRegex(ValueError, "unit_source_invalid"):
            finalize_packet("query", self.units, changed)

    def test_outside_scope_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unit_source_invalid"):
            pack_units((replace(self.units[0], path="not-allowed.md"),), self.sources,
                       byte_budget=3000, count_budget=1)

    def test_traversal_path_is_rejected_even_if_in_mapping(self):
        sources = {"../escape.md": b"x"}
        with self.assertRaisesRegex(ValueError, "unit_shape_invalid"):
            pack_units((Unit("../escape.md", digest(b"x"), 0, 1),), sources,
                       byte_budget=10, count_budget=1)

    def test_utf8_split_is_rejected(self):
        with self.assertRaises(UnicodeError):
            pack_units((Unit("x.md", digest("é".encode()), 0, 1),), {"x.md": "é".encode()},
                       byte_budget=10, count_budget=1)

    def test_duplicate_and_malformed_orders_rejected(self):
        for order in ((0, 0), (0,), (0, True)):
            with self.subTest(order=order), self.assertRaises(ValueError):
                pack_units(self.units[:2], self.sources, byte_budget=4000, count_budget=2, order=order)

    def test_no_order_is_verified_baseline(self):
        expected = finalize_packet("query", self.units, self.sources)
        actual = finalize_packet("query", self.units, self.sources,
                                 tuple(f"c{i}" for i in range(len(self.units))))
        self.assertEqual(expected, actual)

    def test_selector_signature_has_no_oracle_or_label_channel(self):
        import inspect
        self.assertEqual(set(inspect.signature(select_frontier).parameters),
                         {"graph", "snapshot", "reader", "question", "route", "edges", "expansion",
                          "diversity", "byte_budget", "count_budget"})
        self.assertEqual(set(candidate_packet("q", self.units)), {"schema_version", "query", "candidates"})


class RelationshipTests(unittest.TestCase):
    def test_python_import_is_witnessed_in_exact_utf8_bytes(self):
        sources = {"pkg/a.py": "# é\nimport pkg.b\n".encode(), "pkg/b.py": b"def answer():\n    return 42\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(bases[0].relation, "imports")
        self.assertTrue(bases[0].verify(sources))
        self.assertEqual(sources["pkg/a.py"][bases[0].byte_start:bases[0].byte_end], b"import pkg.b")

    def test_relative_import_is_resolved_inside_allowlist(self):
        sources = {"pkg/a.py": b"from . import b\n", "pkg/b.py": b"value = 42\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(bases[0].target_path, "pkg/b.py")

    def test_literal_document_link_has_recoverable_basis(self):
        sources = {"docs/a.md": b"# A\nSee [details](b.md).\n", "docs/b.md": b"# B\nWitness.\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(bases[0].target_path, "docs/b.md")
        self.assertTrue(bases[0].verify(sources))

    def test_external_and_escaping_links_are_not_edges(self):
        sources = {"a.md": b"[x](https://example.org/x) [y](../secret) [z](/absolute)\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(graph.edges, ())

    def test_similar_filenames_do_not_create_edges(self):
        sources = {"cache.md": b"# Cache\n", "cache-detail.md": b"# Cache detail\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(bases, ())

    def test_rst_symbol_reference_needs_unique_target(self):
        sources = {"doc.rst": b"See :func:`widget`.\n", "code.py": b"def widget():\n    pass\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(len(bases), 1)
        sources["other.py"] = sources["code.py"]
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(bases, ())

    def test_stale_source_and_changed_scope_are_rejected(self):
        sources = {"a.py": b"import b\n", "b.py": b"value=1\n"}
        graph = graph_for(sources)
        with self.assertRaisesRegex(ValueError, "source_changed"):
            add_literal_relationships(graph, {**sources, "b.py": b"value=2\n"})
        with self.assertRaisesRegex(ValueError, "scope_mismatch"):
            add_literal_relationships(graph, {"a.py": sources["a.py"]})

    def test_target_staleness_invalidates_edge_basis(self):
        sources = {"a.py": b"import b\n", "b.py": b"value=1\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertFalse(bases[0].verify({**sources, "b.py": b"value=2\n"}))


class CoreIntegrationTests(unittest.TestCase):
    """These tests use the actual core, never a substitute graph implementation."""
    def test_edge_removal_changes_canonical_one_hop_result(self):
        sources = {"a.py": b"import b\n", "b.py": b"value=1\n", "c.py": b"value=2\n"}
        graph, bases = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(expand_with_core_select(graph, ("repo:a.py",)), ("repo:b.py",))
        self.assertEqual(expand_with_core_select(Graph(graph.records), ("repo:a.py",)), ())

    def test_expansion_is_one_hop_and_bounded(self):
        sources = {"a.py": b"import b\n", "b.py": b"import c\n", "c.py": b"value=2\n"}
        graph, _ = add_literal_relationships(graph_for(sources), sources)
        self.assertEqual(expand_with_core_select(graph, ("repo:a.py",)), ("repo:b.py",))
        self.assertEqual(expand_with_core_select(graph, ("repo:a.py",), limit=0), ())

    def test_later_same_file_occurrence_is_retained(self):
        raw = b"# First\n\nwidget overview.\n\n# Second\n\nwidget does not mutate its input.\n"
        graph = graph_for({"doc.md": raw})
        units = units_for_record(graph.records[0], raw, {"widget"}, origin="seed")
        self.assertEqual(len(units), 2)
        self.assertTrue(any(b"does not mutate" in raw[u.start:u.end] for u in units))

    def test_actual_scan_direct_and_typed_routes_are_observably_different(self):
        import subprocess
        import tempfile
        script = ROOT / "plugins/graph-engineering/skills/graph-find/scripts/graph_find.py"
        spec = importlib.util.spec_from_file_location("frontier_fixture_scan", script)
        scan = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = scan
        spec.loader.exec_module(scan)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lookup.py").write_text("import target\n\ndef widget():\n    return target.secret()\n")
            (root / "target.py").write_text("def secret():\n    return 42\n")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "--", "lookup.py", "target.py"], check=True)
            graph, snapshot, reader, meta = scan._scan(root, 1048576, 16777216)
            direct = select_frontier(graph, snapshot, reader, "widget lookup", route="direct")
            typed = select_frontier(graph, snapshot, reader, "widget lookup", route="typed")
            without = select_frontier(graph, snapshot, reader, "widget lookup", route="typed", edges=False)
            no_expand = select_frontier(graph, snapshot, reader, "widget lookup", route="typed", expansion=False)
            self.assertTrue(typed["edges"])
            self.assertIn("expand", typed["trace"])
            self.assertNotIn("expand", direct["trace"])
            self.assertEqual(typed["neighbor_ids"], ("repo:target.py",))
            self.assertNotEqual({u.path for u in typed["pool"]}, {u.path for u in direct["pool"]})
            self.assertEqual(without["pool"], no_expand["pool"])
            self.assertFalse(typed["sufficient"])


if __name__ == "__main__":
    unittest.main()
