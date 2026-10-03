"""Focused action safety and real-file freshness checks; no Git mutation."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/graph-engineering/skills/graph-find/scripts/graph_tools.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("graph_tools", SCRIPT)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class GraphToolsTests(unittest.TestCase):
    def test_public_operations_and_identity_recovery(self):
        s = tools.Session(str(ROOT), 32768, ("benchmarks", "docs/reviews"))
        build = s.dispatch({"op": "build", "intent": "How does navigation stop source reads when the byte budget is exhausted?", "limit": 1})
        self.assertEqual(build["status"], "ok")
        self.assertGreater(build["result"]["omitted_files"], 0)
        unit = next(n for n in build["result"]["nodes"] if n["kind"] == "unit")
        read = s.dispatch({"op": "read", "id": unit["id"]})
        self.assertEqual(read["status"], "ok")
        self.assertEqual(read["result"]["document"]["excerpt_sha256"], tools.digest(read["result"]["document"]["text"].encode()))
        self.assertTrue(s.dispatch({"op": "read", "id": unit["id"]})["result"]["duplicate"])
        for bad in ({"op": "read", "id": "file:../../outside"}, {"op": "inspect", "branch": "wrong"},
                    {"op": "inspect", "snapshot_sha256": "0" * 64}, {"op": "shell", "command": "pwd"}):
            self.assertEqual(s.dispatch(bad)["status"], "defer")
        self.assertEqual(s.dispatch({"op": "inspect"})["status"], "ok")
        expanded = s.dispatch({"op": "expand", "id": unit["parent"], "limit": 2})
        self.assertEqual(expanded["status"], "ok")
        self.assertTrue(expanded["result"]["edges"])
        for edge in expanded["result"]["edges"]:
            ref = edge["witness"]
            raw = (ROOT / ref["path"]).read_bytes()
            self.assertEqual(ref["excerpt_sha256"], tools.digest(raw[ref["byte_start"]:ref["byte_end"]]))

    def test_changed_real_source_refuses_delivery(self):
        # Admission and Git identity are fixtures; freshness uses the real guarded reader.
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "source.py"
            path.write_text("def budget():\n    return 1\n")
            source = path.read_bytes()
            s = tools.Session.__new__(tools.Session)
            s.root = Path(folder)
            s.reader = tools.adapter.SnapshotReader(s.root, {"source.py": source})
            s.validation_bytes = 0
            s.fresh("source.py")
            path.write_text("def budget():\n    return 2\n")
            with self.assertRaisesRegex(ValueError, "stale_source"):
                s.fresh("source.py")

    def test_budget_stops_before_freshness_read(self):
        s = tools.Session(str(ROOT), 1, ("benchmarks", "docs/reviews"))
        built = s.dispatch({"op": "build", "intent": "source budget", "limit": 1})
        node = next(n for n in built["result"]["nodes"] if n["kind"] == "file")
        before = s.validation_bytes
        result = s.dispatch({"op": "read", "id": node["id"]})
        self.assertEqual(result["reason"], "shared_content_budget_exhausted")
        self.assertEqual(s.validation_bytes, before)
        self.assertEqual(s.used, 0)


if __name__ == "__main__":
    unittest.main()
