from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts/package/project_portable_plugin.py"
SPEC = importlib.util.spec_from_file_location("project_portable_plugin", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PROJECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROJECTOR)
EXCLUSIONS = [
    "contracts/core/routing-authority-v3.schema.json",
    "contracts/core/routing-context-v3.schema.json",
    "contracts/core/routing-decision-v3.schema.json",
    "contracts/core/routing-evidence-v3.schema.json",
]


class ProjectionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        production_contract = json.loads(
            (PROJECT_ROOT / "contracts/package/projection-map.json").read_text(encoding="utf-8")
        )
        self.contract_path = self.root / "contracts/package/projection-map.json"
        self.contract_path.parent.mkdir(parents=True)
        self.contract_path.write_text(json.dumps(production_contract), encoding="utf-8")
        for mapping in production_contract["mappings"]:
            source = self.root / mapping["source"]
            source.mkdir(parents=True)
        (self.root / "packages/core/zeta.txt").write_text("zeta\n", encoding="utf-8")
        (self.root / "packages/core/alpha.txt").write_text("alpha\n", encoding="utf-8")
        (self.root / "contracts/core/schema.json").write_text("{}\n", encoding="utf-8")
        for exclusion in EXCLUSIONS:
            (self.root / exclusion).write_text("{}\n", encoding="utf-8")
        (self.root / "adapters/knowledge-compiler/adapter.py").write_text("VALUE = 1\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_contract_encodes_the_frozen_mappings(self) -> None:
        contract = json.loads(
            (PROJECT_ROOT / "contracts/package/projection-map.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            contract["mappings"],
            [
                {"source": "packages/core", "target": "plugins/graph-engineering/runtime/core"},
                {
                    "source": "contracts/core",
                    "target": "plugins/graph-engineering/runtime/contracts/core",
                },
                {
                    "source": "adapters/knowledge-compiler",
                    "target": "plugins/graph-engineering/runtime/adapters/knowledge-compiler",
                },
            ],
        )
        self.assertEqual(contract["exclusions"], EXCLUSIONS)

    def test_projection_is_deterministic_and_host_neutral(self) -> None:
        first = PROJECTOR.project(self.root, self.contract_path)
        state_path = self.root / "plugins/graph-engineering/runtime/.projection-state.json"
        first_bytes = state_path.read_bytes()
        second = PROJECTOR.project(self.root, self.contract_path)
        self.assertEqual(first, second)
        self.assertEqual(first_bytes, state_path.read_bytes())
        paths = [entry["path"] for entry in second["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertNotIn(str(self.root), first_bytes.decode("utf-8"))
        self.assertEqual(
            (self.root / "plugins/graph-engineering/runtime/core/alpha.txt").read_text(encoding="utf-8"),
            "alpha\n",
        )
        projected = {entry["path"] for entry in second["files"]}
        for exclusion in EXCLUSIONS:
            relative = Path(exclusion).relative_to("contracts/core")
            self.assertNotIn(f"contracts/core/{relative.as_posix()}", projected)
            self.assertFalse(
                (self.root / "plugins/graph-engineering/runtime/contracts/core" / relative).exists()
            )

    def test_projection_ignores_python_bytecode_caches(self) -> None:
        cache = self.root / "packages/core/__pycache__"
        cache.mkdir()
        (cache / "module.cpython-314.pyc").write_bytes(b"machine bytecode")

        state = PROJECTOR.project(self.root, self.contract_path)

        projected_paths = {entry["path"] for entry in state["files"]}
        self.assertFalse(
            any("__pycache__" in path or path.endswith(".pyc") for path in projected_paths)
        )

    def test_unapproved_duplicate_escaping_overlapping_and_non_source_exclusions_fail_closed(self) -> None:
        variants = {
            "missing": EXCLUSIONS[:-1],
            "duplicate": EXCLUSIONS + [EXCLUSIONS[0]],
            "escaping": EXCLUSIONS[:-1] + ["../escape.json"],
            "overlapping": EXCLUSIONS[:-1] + ["contracts/core"],
            "non_source": EXCLUSIONS[:-1] + ["docs/routing-evidence-v3.schema.json"],
            "broader": EXCLUSIONS[:-1] + ["contracts/core/routing-evidence-v3.schema.json/child"],
        }
        original = json.loads(self.contract_path.read_text(encoding="utf-8"))
        for label, exclusions in variants.items():
            with self.subTest(label=label):
                contract = dict(original)
                contract["exclusions"] = exclusions
                self.contract_path.write_text(json.dumps(contract), encoding="utf-8")
                with self.assertRaises(PROJECTOR.ProjectionError):
                    PROJECTOR.project(self.root, self.contract_path)
                self.assertFalse((self.root / "plugins").exists())

    def test_missing_directory_and_symlink_exclusions_fail_before_writes(self) -> None:
        for kind in ("missing", "directory", "symlink"):
            with self.subTest(kind=kind):
                excluded = self.root / EXCLUSIONS[0]
                excluded.unlink()
                if kind == "directory":
                    excluded.mkdir()
                elif kind == "symlink":
                    excluded.symlink_to(self.root / EXCLUSIONS[1])
                with self.assertRaises(PROJECTOR.ProjectionError):
                    PROJECTOR.project(self.root, self.contract_path)
                self.assertFalse((self.root / "plugins").exists())
                if kind != "symlink":
                    if excluded.is_dir():
                        excluded.rmdir()
                    excluded.write_text("{}\n", encoding="utf-8")
                else:
                    excluded.unlink()
                    excluded.write_text("{}\n", encoding="utf-8")

    def test_contract_traversal_is_rejected_before_writes(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        contract["mappings"][0]["target"] = "../escape"
        self.contract_path.write_text(json.dumps(contract), encoding="utf-8")
        with self.assertRaises(PROJECTOR.ProjectionError):
            PROJECTOR.project(self.root, self.contract_path)
        self.assertFalse((self.root / "plugins").exists())
        self.assertFalse((self.root.parent / "escape").exists())

    def test_source_symlink_is_rejected_before_writes(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        (self.root / "packages/core/link.txt").symlink_to(outside)
        with self.assertRaises(PROJECTOR.ProjectionError):
            PROJECTOR.project(self.root, self.contract_path)
        self.assertFalse((self.root / "plugins").exists())

    def test_target_symlink_is_rejected_before_writes(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        plugin_root = self.root / "plugins/graph-engineering"
        plugin_root.mkdir(parents=True)
        (plugin_root / "runtime").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PROJECTOR.ProjectionError):
            PROJECTOR.project(self.root, self.contract_path)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unmanaged_destination_is_rejected_without_mutation(self) -> None:
        unmanaged = self.root / "plugins/graph-engineering/runtime/core/unmanaged.txt"
        unmanaged.parent.mkdir(parents=True)
        unmanaged.write_text("preserve me\n", encoding="utf-8")
        with self.assertRaises(PROJECTOR.ProjectionError):
            PROJECTOR.project(self.root, self.contract_path)
        self.assertEqual(unmanaged.read_text(encoding="utf-8"), "preserve me\n")
        self.assertFalse((unmanaged.parent / "alpha.txt").exists())

    def test_managed_update_replaces_only_verified_projection(self) -> None:
        PROJECTOR.project(self.root, self.contract_path)
        source = self.root / "packages/core/alpha.txt"
        source.write_text("changed\n", encoding="utf-8")
        PROJECTOR.project(self.root, self.contract_path)
        target = self.root / "plugins/graph-engineering/runtime/core/alpha.txt"
        self.assertEqual(target.read_text(encoding="utf-8"), "changed\n")

    def test_modified_managed_file_is_rejected_without_mutation(self) -> None:
        PROJECTOR.project(self.root, self.contract_path)
        target = self.root / "plugins/graph-engineering/runtime/core/alpha.txt"
        target.write_text("external edit\n", encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(PROJECTOR.ProjectionError):
            PROJECTOR.project(self.root, self.contract_path)
        self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
