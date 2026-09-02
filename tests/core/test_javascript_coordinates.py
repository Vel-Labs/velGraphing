from __future__ import annotations

import unittest

from packages.core.javascript_coordinates import JavaScriptCoordinateProvider
from packages.core.source_coordinates import source_snapshot


class JavaScriptCoordinateProviderTests(unittest.TestCase):
    def test_roles_are_grammar_bound_and_enclosing_units_are_exact(self) -> None:
        snapshot = source_snapshot({"src/example.js": b"import { helper as alias } from './helper.js';\nfunction greet(name) { return alias(name); }\nconst result = greet('x');\n"})
        result = JavaScriptCoordinateProvider().index(snapshot)
        self.assertTrue(result.supported)
        self.assertEqual("tree-sitter", JavaScriptCoordinateProvider().identity["parser"])
        self.assertEqual("tree-sitter-javascript", JavaScriptCoordinateProvider().identity["grammar"])
        roles = {(item.symbol, item.occurrence_role) for item in result.coordinates}
        self.assertIn(("greet", "definition"), roles)
        self.assertIn(("name", "declaration"), roles)
        self.assertIn(("alias", "import"), roles)
        self.assertIn(("alias", "call"), roles)
        self.assertIn(("name", "read"), roles)
        unit = next(item for item in result.coordinates if item.symbol == "greet" and item.occurrence_role == "unknown")
        self.assertEqual(b"function greet(name) { return alias(name); }", snapshot.source(unit.source_path).content[unit.byte_start:unit.byte_end])

    def test_parse_errors_defer_without_coordinates(self) -> None:
        snapshot = source_snapshot({"broken.js": b"function broken( {"})
        result = JavaScriptCoordinateProvider().index(snapshot)
        self.assertFalse(result.supported)
        self.assertEqual((), result.coordinates)
        self.assertTrue(result.reason.startswith("javascript_parse_error:"))

    def test_non_javascript_snapshot_defers(self) -> None:
        result = JavaScriptCoordinateProvider().index(source_snapshot({"README.md": b"text"}))
        self.assertFalse(result.supported)
        self.assertEqual("no_supported_javascript_sources", result.reason)


if __name__ == "__main__":
    unittest.main()
