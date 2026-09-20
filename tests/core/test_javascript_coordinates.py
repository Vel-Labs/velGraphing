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

    def test_relation_index_uses_named_import_and_direct_export_nodes(self) -> None:
        snapshot = source_snapshot({
            "src/caller.js": (
                b"import main, { helper as alias } from './helper.js';\n"
                b"import * as helpers from './helper.js';\n"
                b"import './side.js';\n"
                b"import { packageHelper } from 'package';\n"
                b"const later = import('./lazy.js');\n"
                b"export { helper } from './helper.js';\n"
            ),
            "src/helper.js": (
                b"export function helper() {}\n"
                b"export const other = 1;\n"
                b"export default function hidden() {}\n"
            ),
        })

        result = JavaScriptCoordinateProvider().relations(snapshot)

        self.assertTrue(result.supported)
        self.assertEqual(6, result.unsupported)
        self.assertEqual(
            [(item.source_path, item.module, item.symbol) for item in result.imports],
            [("src/caller.js", "./helper.js", "helper")],
        )
        self.assertEqual(
            [(item.source_path, item.symbol) for item in result.exports],
            [("src/helper.js", "helper"), ("src/helper.js", "other")],
        )
        imported = result.imports[0]
        exported = result.exports[0]
        self.assertEqual(b"helper", snapshot.source(imported.source_path).content[imported.byte_start:imported.byte_end])
        self.assertEqual(b"function helper() {}", snapshot.source(exported.source_path).content[exported.byte_start:exported.byte_end])

    def test_relation_parse_errors_fail_closed(self) -> None:
        result = JavaScriptCoordinateProvider().relations(
            source_snapshot({"broken.js": b"import { broken from './broken.js';"})
        )
        self.assertFalse(result.supported)
        self.assertEqual((), result.imports)
        self.assertTrue(result.reason.startswith("javascript_parse_error:"))


if __name__ == "__main__":
    unittest.main()
