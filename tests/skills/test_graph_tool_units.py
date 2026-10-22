"""Full build/inspect/read source-unit protocol with disposable real files."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/graph-engineering/skills/graph-find/scripts/graph_tools.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("graph_tool_units", SCRIPT)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
from packages.core import Admission, Freshness, Graph, GraphRecord, Provenance, Sensitivity, SourceIdentityV4, SourceSnapshotV4, TrustClass

SOURCE = (
    "# Préface: café 🚦\n"
    "def alpha_gate(\n"
    "    beta_record,\n"
    "):\n"
    "    if not beta_record:\n"
    "        raise ValueError('reject_alpha')\n"
    "    return beta_record\n\n"
    "def beta_gate(beta_record):\n"
    "    return beta_record\n"
).encode("utf-8")


class GraphToolUnitProtocolTests(unittest.TestCase):
    def test_body_comment_does_not_replace_complete_function_label(self):
        raw = b'def alpha_gate():\n    # explain the source gate\n    return 1\n\ndef beta_gate():\n    return 2\n'
        with tempfile.TemporaryDirectory() as folder:
            session = self.session(Path(folder).resolve(), raw=raw)
            with patch.object(session, 'git_identity', return_value=session.identity):
                built = session.dispatch({'op': 'build', 'intent': 'alpha_gate', 'limit': 1})
                node = next(n for n in built['result']['nodes'] if n['kind'] == 'unit' and n['byte_start'] == 0)
                self.assertEqual(node['label'], 'def alpha_gate')
                read = session.dispatch({'op': 'read', 'id': node['id']})
                self.assertEqual(read['status'], 'ok')
                self.assertIn('# explain the source gate', read['result']['document']['text'])
                self.assertNotIn('def beta_gate', read['result']['document']['text'])

    def session(self, root, raw=SOURCE, budget=4096, path="source.py"):
        (root / path).write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        record = GraphRecord(record_id="fixed:" + path, kind="source", title=path, content=raw.decode(),
                             provenance=Provenance(path, digest, "git-tracked-bytes", True), trust=TrustClass.VERIFIED_SOURCE,
                             sensitivity=Sensitivity.INTERNAL, freshness=Freshness.CURRENT, admission=Admission.VERIFIER, eligible=True)
        graph = Graph((record,))
        snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(raw), digest),))
        reader = tools.adapter.SnapshotReader(root, {path: raw})
        scan = {"source_bytes_read": len(raw)}
        # Only corpus admission/Git identity are fixtures. Actions, real guarded
        # freshness, unit discovery, JSON responses and budgets are production code.
        with patch.object(tools.adapter, "_scan", return_value=(graph, snapshot, reader, scan)), \
             patch.object(tools.Session, "git_identity", return_value={"head": "1" * 40, "branch": "fixture"}):
            session = tools.Session(str(root), budget)
        return session

    def actions(self, session, path="source.py"):
        with patch.object(session, "git_identity", return_value=session.identity):
            built = session.dispatch({"op": "build", "intent": "find alpha_gate", "scope": path, "limit": 1})
            self.assertEqual(built["status"], "ok")
            binding = {k: built[k] for k in ("head", "branch", "snapshot_sha256")}
            inspected = session.dispatch({"op": "inspect", "scope": path, "limit": 1, **binding})
            self.assertEqual(inspected["status"], "ok")
            node = next(n for n in inspected["result"]["nodes"] if n["kind"] == "unit" and n["label"].endswith("alpha_gate"))
        return node, binding

    def read(self, session, node, binding):
        with patch.object(session, "git_identity", return_value=session.identity):
            return session.dispatch({"op": "read", "id": node["id"], **binding})

    def test_multiline_signature_read_contains_full_utf8_function_not_neighbor(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            session = self.session(root)
            node, binding = self.actions(session)
            result = self.read(session, node, binding)
            self.assertEqual(result["status"], "ok")
            document = result["result"]["document"]
            tree = ast.parse(SOURCE.decode())
            function, neighbor = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
            lines = SOURCE.splitlines(keepends=True)
            function_start = sum(map(len, lines[:function.lineno - 1])) + function.col_offset
            function_end = sum(map(len, lines[:function.end_lineno - 1])) + function.end_col_offset
            neighbor_start = sum(map(len, lines[:neighbor.lineno - 1])) + neighbor.col_offset
            self.assertLessEqual(document["byte_start"], function_start)
            self.assertGreaterEqual(document["byte_end"], function_end)
            self.assertLessEqual(document["byte_end"], neighbor_start)
            raw = SOURCE[document["byte_start"]:document["byte_end"]]
            self.assertEqual(document["text"].encode(), raw)
            self.assertEqual(document["source_sha256"], hashlib.sha256(SOURCE).hexdigest())
            self.assertEqual(document["excerpt_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result["budget"]["delivered_content_bytes"], len(raw))
            self.assertFalse(result["sufficient"])
            self.assertFalse(result["authority_bearing"])
            repeated = self.read(session, node, binding)
            self.assertTrue(repeated["result"]["duplicate"])
            self.assertEqual(repeated["budget"], {**result["budget"], "steps": result["budget"]["steps"] + 1})

    def test_decorated_async_class_and_nested_units_stay_contained(self):
        sources = (
            "@decorate(\n    'café',\n)\nasync def alpha_gate(\n    value,\n):\n    return value\n\ndef beta_gate():\n    pass\n",
            "class alpha_gate(\n    Base,\n):\n    def method(self):\n        return 'café'\n\nclass beta_gate:\n    pass\n",
            "class Outer:\n    def alpha_gate(\n        self,\n    ):\n        return 'café'\n\n    def beta_gate(self):\n        pass\n",
        )
        for text in sources:
            with self.subTest(source=text), tempfile.TemporaryDirectory() as folder:
                raw = text.encode()
                session = self.session(Path(folder).resolve(), raw=raw)
                node, binding = self.actions(session)
                result = self.read(session, node, binding)
                self.assertEqual(result["status"], "ok")
                doc = result["result"]["document"]
                target = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == "alpha_gate")
                lines = raw.splitlines(keepends=True)
                begin_line = min([target.lineno, *(d.lineno for d in target.decorator_list)])
                start = sum(map(len, lines[:begin_line - 1]))
                end = sum(map(len, lines[:target.end_lineno - 1])) + target.end_col_offset
                self.assertEqual(doc["byte_start"], start)
                self.assertGreaterEqual(doc["byte_end"], end)
                self.assertNotIn("beta_gate", doc["text"])
                self.assertNotIn("class Outer", doc["text"])
                self.assertEqual(doc["text"].encode(), raw[doc["byte_start"]:doc["byte_end"]])

    def test_declaration_label_wins_over_comments_inside_decorated_unit(self):
        for declaration in ('def alpha_gate():', 'async def alpha_gate():', 'class alpha_gate:'):
            for comment in ('', '# explain the source gate\n'):
                text = '@decorator\n' + comment + declaration + '\n    # body comment\n    return_value = 1\n\ndef beta_gate():\n    return 2\n'
                with self.subTest(declaration=declaration, comment=comment), tempfile.TemporaryDirectory() as folder:
                    raw = text.encode()
                    session = self.session(Path(folder).resolve(), raw=raw)
                    node, binding = self.actions(session)
                    self.assertEqual(node['label'], declaration.split('(')[0].rstrip(':'))
                    result = self.read(session, node, binding)
                    self.assertEqual(result['status'], 'ok')
                    document = result['result']['document']
                    excerpt = raw[document['byte_start']:document['byte_end']]
                    self.assertEqual(document['byte_start'], 0)
                    self.assertEqual(document['text'].encode(), excerpt)
                    self.assertEqual(document['source_sha256'], hashlib.sha256(raw).hexdigest())
                    self.assertEqual(document['excerpt_sha256'], hashlib.sha256(excerpt).hexdigest())
                    self.assertIn(declaration, document['text'])
                    self.assertNotIn('beta_gate', document['text'])

    def assert_complete_read(self, path, text):
        raw = text.encode()
        with tempfile.TemporaryDirectory() as folder:
            session = self.session(Path(folder).resolve(), raw=raw, path=path)
            node, binding = self.actions(session, path=path)
            result = self.read(session, node, binding)
            self.assertEqual(result["status"], "ok")
            doc = result["result"]["document"]
            target = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == "alpha_gate")
            # Independent byte-line oracle: literal Unicode separators inside
            # strings are not physical Python source line endings.
            physical = raw.splitlines(keepends=True)
            start = sum(map(len, physical[:target.lineno - 1])) + target.col_offset
            end = sum(map(len, physical[:target.end_lineno - 1])) + target.end_col_offset
            self.assertLessEqual(doc["byte_start"], start)
            self.assertGreaterEqual(doc["byte_end"], end)
            self.assertIn("return value", doc["text"])
            self.assertNotIn("beta_gate", doc["text"])
            excerpt = raw[doc["byte_start"]:doc["byte_end"]]
            self.assertEqual(doc["text"].encode(), excerpt)
            self.assertEqual(doc["source_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(doc["excerpt_sha256"], hashlib.sha256(excerpt).hexdigest())
            self.assertEqual(result["budget"]["delivered_content_bytes"], len(excerpt))
            self.assertFalse(result["sufficient"])
            self.assertFalse(result["authority_bearing"])

    def test_multiline_declarations_precede_configuration_filename_heuristics(self):
        text = "def alpha_gate(\n    value,\n):\n    if not value:\n        raise ValueError('reject_alpha')\n    return value\n\ndef beta_gate():\n    return 0\n"
        for path in ("config_gate.py", "settings_gate.py", "manifest_gate.py"):
            with self.subTest(path=path):
                self.assert_complete_read(path, text)

    def test_python_physical_line_offsets_ignore_string_literal_separators(self):
        for separator in ("\u2028", "\u2029", "\x85", "\v", "\f"):
            text = "def alpha_gate(\n    value,\n):\n    mark = 'left" + separator + "right'\n    if not value:\n        raise ValueError('reject_alpha')\n    return value\n\ndef beta_gate():\n    return 0\n"
            for newline in ("\n", "\r\n", "\r"):
                with self.subTest(separator=repr(separator), newline=repr(newline)):
                    self.assert_complete_read("source.py", text.replace("\n", newline))

    def test_python_byte_input_encoding_boundaries_preserve_complete_units(self):
        body = b'def alpha_gate(\n    value,\n):\n    if not value:\n        raise ValueError("reject_alpha")\n    return value\n\ndef beta_gate():\n    return 0\n'
        cases = (
            b'\xef\xbb\xbf# UTF-8 source\n' + body,
            b'\xef\xbb\xbf' + body,
            b'# coding: utf-8\n' + body,
            (b'\xef\xbb\xbf# coding: utf-8\n' + body).replace(b'\n', b'\r\n'),
        )
        for raw in cases:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                session = self.session(Path(folder).resolve(), raw=raw)
                node, binding = self.actions(session)
                result = self.read(session, node, binding)
                self.assertEqual(result["status"], "ok")
                doc = result["result"]["document"]
                target = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == "alpha_gate")
                physical = raw.splitlines(keepends=True)
                expected_end = sum(map(len, physical[:target.end_lineno - 1])) + target.end_col_offset
                self.assertGreaterEqual(doc["byte_end"], expected_end)
                self.assertIn("return value", doc["text"])
                self.assertNotIn("beta_gate", doc["text"])
                excerpt = raw[doc["byte_start"]:doc["byte_end"]]
                self.assertEqual(doc["text"].encode(), excerpt)
                self.assertEqual(doc["source_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(doc["excerpt_sha256"], hashlib.sha256(excerpt).hexdigest())

    def test_unestablished_units_refuse_with_complete_file_fallback_and_no_charge(self):
        cases = (
            ("source.py", b'def alpha_gate(\n    value,\n    return value\n'),
            ("source.py", b'\xef\xbb\xbf# coding: latin-1\ndef alpha_gate(value):\n    return value\n'),
            ("source.py", b'def alpha_gate(value):\n    return value\x00\n'),
            ("source.txt", b'def alpha_gate(value):\n    return value\n'),
        )
        for path, raw in cases:
            with self.subTest(path=path, raw=raw), tempfile.TemporaryDirectory() as folder:
                session = self.session(Path(folder).resolve(), raw=raw, path=path)
                with patch.object(session, "git_identity", return_value=session.identity):
                    built = session.dispatch({"op": "build", "intent": "find alpha_gate", "scope": path, "limit": 1})
                    self.assertEqual(built["status"], "ok")
                    binding = {k: built[k] for k in ("head", "branch", "snapshot_sha256")}
                    self.assertFalse(any(n["kind"] == "unit" for n in built["result"]["nodes"]))
                    node = next(n for n in built["result"]["nodes"] if n["kind"] == "unresolved_unit")
                    before = session.validation_bytes
                    refused = session.dispatch({"op": "read", "id": node["id"], **binding})
                    self.assertEqual(refused["status"], "defer")
                    self.assertEqual(refused["reason"], "complete_unit_unavailable")
                    self.assertEqual(refused["result"]["fallback_obligations"][0]["file_id"], "file:" + path)
                    self.assertEqual(session.validation_bytes, before)
                    self.assertEqual(session.used, 0)
                    self.assertFalse(session.seen)
                    self.assertNotIn("document", refused["result"])
                    file_read = session.dispatch({"op": "read", "id": "file:" + path, **binding})
                    self.assertEqual(file_read["status"], "ok")
                    self.assertEqual(file_read["result"]["document"]["text"].encode(), raw)

    def test_complete_unit_entry_refuses_invalid_anchor_and_unknown_format(self):
        raw = b'def alpha_gate(value):\n    return value\n'
        for start, end in ((-1, 3), (0, len(raw) + 1), (4, 4), (True, 3)):
            with self.subTest(start=start, end=end):
                self.assertIsNone(tools._certified_unit_bounds(raw, "source.py", start, end))
        self.assertIsNone(tools._certified_unit_bounds(b'\xff', "source.py", 0, 1))
        self.assertIsNone(tools._certified_unit_bounds(raw, "source.txt", 0, 3))
        self.assertIsNone(tools._certified_unit_bounds(b'{"key":', "settings.json", 2, 5))
        self.assertIsNone(tools._certified_unit_bounds("λ".encode(), "source.py", 1, 2))

    def test_existing_grammar_boundaries_never_substitute_fragments(self):
        from packages.core import javascript_coordinates
        raw = b'function alpha_gate() { return "}"; }\nfunction beta_gate() { return 0; }\n'
        unit = tools._certified_unit_bounds(raw, "source.js", 9, 19)
        self.assertIsNotNone(unit)
        self.assertIn(b'return "}";', raw[unit[0]:unit[1]])
        self.assertNotIn(b'beta_gate', raw[unit[0]:unit[1]])
        with patch.object(javascript_coordinates, "Parser", None):
            self.assertIsNone(tools._certified_unit_bounds(raw, "source.js", 9, 19))
        self.assertIsNone(tools._certified_unit_bounds(b'function alpha_gate() {', "source.js", 9, 19))
        markdown = b'# alpha_gate\n```\n## not_a_heading\n```\nstill in section\n'
        self.assertIsNone(tools._certified_unit_bounds(markdown, "README.md", 2, 12))

    def test_oversized_complete_unit_defers_before_freshness_and_charge(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            session = self.session(root, budget=70)
            node, binding = self.actions(session)
            before = session.validation_bytes
            result = self.read(session, node, binding)
            self.assertEqual(result["status"], "defer")
            self.assertEqual(result["reason"], "shared_content_budget_exhausted")
            self.assertEqual(session.validation_bytes, before)
            self.assertEqual(session.used, 0)
            self.assertFalse(session.seen)

    def test_changed_source_refuses_selected_unit_without_charge(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            session = self.session(root)
            node, binding = self.actions(session)
            (root / "source.py").write_bytes(SOURCE.replace(b"return beta_record", b"return None"))
            result = self.read(session, node, binding)
            self.assertEqual(result["status"], "defer")
            self.assertIn("stale_source", result["reason"])
            self.assertEqual(session.used, 0)
            self.assertFalse(session.seen)

    def test_missing_fresh_source_refuses_selected_unit_without_charge(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            session = self.session(root)
            node, binding = self.actions(session)
            actual = root / "source.py"
            real_open = tools.adapter.os.open
            def missing(path, *args, **kwargs):
                if path == actual:
                    raise FileNotFoundError("disposable source missing")
                return real_open(path, *args, **kwargs)
            # Fault only the disposable file's filesystem presence check. Keep
            # guarded read and dispatch logic unchanged; never remove originals.
            with patch.object(tools.adapter.os, "open", missing):
                result = self.read(session, node, binding)
            self.assertEqual(result["status"], "defer")
            self.assertIn("cannot read tracked path source.py", result["reason"])
            self.assertEqual(session.used, 0)
            self.assertFalse(session.seen)


if __name__ == "__main__":
    unittest.main()
