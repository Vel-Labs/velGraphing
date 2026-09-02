from __future__ import annotations

import unittest

from packages.core.navigation_v4 import NavigationV4
from packages.core.source_coordinates import DeterministicFixtureProvider, SourceCoordinate, source_snapshot


class NavigationV4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = source_snapshot({"src/mod.py": "def greet(name):\n    return helper(name)\n\ndef helper(value):\n    return value\n"})
        source = self.snapshot.source("src/mod.py")
        specs = (
            (0, 15, 1, 1, "function", "definition", "greet", None),
            (28, 34, 2, 2, "function", "call", "helper", "greet"),
            (35, 39, 2, 2, "parameter", "reference", "name", "greet"),
            (42, 52, 4, 4, "function", "definition", "helper", None),
            (72, 77, 5, 5, "parameter", "reference", "value", "helper"),
        )
        coords = tuple(SourceCoordinate(self.snapshot.snapshot_sha256, source.path, source.source_sha256, *spec) for spec in specs)
        self.navigator = NavigationV4(self.snapshot, DeterministicFixtureProvider(coords))

    def test_exact_lookup_and_role_filter(self) -> None:
        result = self.navigator.find_symbols("helper", role="definition")
        self.assertTrue(result.supported)
        self.assertEqual(1, len(result))
        self.assertEqual(self.snapshot.snapshot_sha256, result.items[0].snapshot_sha256)

        references = self.navigator.find_references("helper")
        self.assertEqual(1, len(references))
        self.assertEqual("call", references.items[0].coordinate.occurrence_role)

    def test_exact_read_and_enclosing_unit(self) -> None:
        result = self.navigator.read_symbol("greet")
        self.assertEqual(b"def greet(name)", result.items[0].content)
        unit = self.navigator.read_enclosing_unit("helper")
        self.assertTrue(unit.supported)
        self.assertEqual(b"def helper(value):\n    return value", unit.items[0].content)

    def test_neighbors_are_bounded_and_unsupported_defers(self) -> None:
        result = self.navigator.related_symbols("name", limit=1)
        self.assertEqual(1, len(result))
        unsupported = NavigationV4(self.snapshot, DeterministicFixtureProvider(supported=False))
        self.assertTrue(unsupported.find_symbols("greet").deferred)

    def test_custody_mismatch_defers(self) -> None:
        source = self.snapshot.source("src/mod.py")
        foreign = SourceCoordinate("f" * 64, source.path, source.source_sha256, 0, 1, 1, 1, "token", "reference", "x")
        result = self.navigator.read_span(foreign)
        self.assertTrue(result.deferred)
        self.assertEqual("source_custody_mismatch", result.reason)


if __name__ == "__main__":
    unittest.main()
