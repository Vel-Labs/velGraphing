from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/package/verify_source_package_parity.py"
SPEC = importlib.util.spec_from_file_location("release_parity", SCRIPT)
assert SPEC and SPEC.loader
PARITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARITY)
PROJECTOR_SCRIPT = ROOT / "scripts/package/project_portable_plugin.py"
PROJECTOR_SPEC = importlib.util.spec_from_file_location("project_portable_plugin_for_parity", PROJECTOR_SCRIPT)
assert PROJECTOR_SPEC and PROJECTOR_SPEC.loader
PROJECTOR = importlib.util.module_from_spec(PROJECTOR_SPEC)
PROJECTOR_SPEC.loader.exec_module(PROJECTOR)
EXCLUSIONS = [
    "contracts/core/routing-authority-v3.schema.json",
    "contracts/core/routing-context-v3.schema.json",
    "contracts/core/routing-decision-v3.schema.json",
    "contracts/core/routing-evidence-v3.schema.json",
]


class SourcePackageParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        for relative in (
            "packages/core",
            "contracts/core",
            "adapters/knowledge-compiler",
            "contracts/package",
            "plugins/graph-engineering",
        ):
            source = ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
        shutil.rmtree(self.root / "plugins/graph-engineering/runtime")
        PROJECTOR.project(
            self.root,
            self.root / "contracts/package/projection-map.json",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_code(self, code: str, action) -> None:
        with self.assertRaises(PARITY.ParityError) as raised:
            action()
        self.assertEqual(code, raised.exception.code)

    def rewrite_manifest(self, transform) -> None:
        path = self.root / "plugins/graph-engineering/.codex-plugin/release-manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        transform(value)
        path.write_bytes(PARITY.canonical_json(value))

    def test_current_candidate_verifies_and_identity_is_deterministic(self) -> None:
        first = PARITY.write_manifest(self.root)
        second = PARITY.build_manifest(self.root)
        self.assertEqual(first, second)
        self.assertEqual(first, PARITY.verify(self.root))
        paths = [row["path"] for row in first["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertNotIn(".codex-plugin/release-manifest.json", paths)
        for exclusion in EXCLUSIONS:
            relative = Path(exclusion).relative_to("contracts/core").as_posix()
            self.assertNotIn(f"runtime/contracts/core/{relative}", paths)

    def test_projection_exclusions_reject_unapproved_and_invalid_contract_entries(self) -> None:
        contract_path = self.root / "contracts/package/projection-map.json"
        original = json.loads(contract_path.read_text(encoding="utf-8"))
        variants = (
            ("projection_exclusions_unapproved", EXCLUSIONS[:-1]),
            ("projection_exclusion_duplicate", EXCLUSIONS + [EXCLUSIONS[0]]),
            ("projection_exclusion_invalid", EXCLUSIONS[:-1] + ["../escape.json"]),
            ("projection_exclusions_unapproved", EXCLUSIONS[:-1] + ["contracts/core"]),
            (
                "projection_exclusions_unapproved",
                EXCLUSIONS[:-1] + ["docs/routing-evidence-v3.schema.json"],
            ),
        )
        for code, exclusions in variants:
            with self.subTest(code=code, exclusions=exclusions):
                contract = dict(original)
                contract["exclusions"] = exclusions
                contract_path.write_bytes(PARITY.canonical_json(contract))
                self.assert_code(code, lambda: PARITY.build_manifest(self.root))

    def test_projection_exclusions_reject_missing_directory_and_symlink_sources(self) -> None:
        for kind, code in (
            ("missing", "projection_exclusion_missing_or_nonregular"),
            ("directory", "projection_exclusion_missing_or_nonregular"),
            ("symlink", "tree_alias_forbidden"),
        ):
            with self.subTest(kind=kind):
                self.setUp_fixture_again()
                excluded = self.root / EXCLUSIONS[0]
                excluded.unlink()
                if kind == "directory":
                    excluded.mkdir()
                elif kind == "symlink":
                    excluded.symlink_to(self.root / EXCLUSIONS[1])
                self.assert_code(code, lambda: PARITY.build_manifest(self.root))

    def test_missing_extra_and_changed_package_files_fail_closed(self) -> None:
        PARITY.write_manifest(self.root)
        target = self.root / "plugins/graph-engineering/README.md"
        target.unlink()
        self.assert_code("source_package_drift", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        (self.root / "plugins/graph-engineering/extra.txt").write_text("extra", encoding="utf-8")
        self.assert_code("source_package_drift", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        target = self.root / "plugins/graph-engineering/README.md"
        target.write_text(target.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        self.assert_code("source_package_drift", lambda: PARITY.verify(self.root))

    def setUp_fixture_again(self) -> None:
        self.temporary.cleanup()
        self.setUp()

    def test_duplicate_escaping_unsorted_and_self_entries_fail_closed(self) -> None:
        PARITY.write_manifest(self.root)
        manifest = self.root / "plugins/graph-engineering/.codex-plugin/release-manifest.json"
        raw = manifest.read_text(encoding="utf-8")
        manifest.write_text(raw.replace('"files":', '"files":[],"files":', 1), encoding="utf-8")
        self.assert_code("json_duplicate_key", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        self.rewrite_manifest(lambda value: value["files"].__setitem__(0, {**value["files"][0], "path": "../escape"}))
        self.assert_code("release_path_invalid", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        self.rewrite_manifest(lambda value: value["files"].reverse())
        self.assert_code("release_paths_unsorted", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        self.rewrite_manifest(lambda value: value["files"].append({"path": ".codex-plugin/release-manifest.json", "sha256": "0" * 64, "size": 0}))
        self.assert_code("release_manifest_self_entry", lambda: PARITY.verify(self.root))

    def test_duplicate_rows_private_and_machine_paths_fail_closed(self) -> None:
        PARITY.write_manifest(self.root)
        self.rewrite_manifest(lambda value: value["files"].insert(1, dict(value["files"][0])))
        self.assert_code("release_duplicate_path", lambda: PARITY.verify(self.root))

        for forbidden in (".env", "__pycache__/cache.pyc", "Users:steven/state.json"):
            self.setUp_fixture_again()
            PARITY.write_manifest(self.root)
            self.rewrite_manifest(lambda value, forbidden=forbidden: value["files"].__setitem__(0, {**value["files"][0], "path": forbidden}))
            self.assert_code("private_or_machine_path", lambda: PARITY.verify(self.root))

    def test_symlink_and_nonregular_package_entries_fail_closed(self) -> None:
        PARITY.write_manifest(self.root)
        target = self.root / "plugins/graph-engineering/alias"
        target.symlink_to("README.md")
        self.assert_code("tree_alias_forbidden", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        fifo = self.root / "plugins/graph-engineering/fifo"
        try:
            fifo.parent.mkdir(parents=True, exist_ok=True)
            os.mkfifo(fifo)
        except (AttributeError, PermissionError, OSError):
            self.skipTest("FIFO fixtures are not supported on this host")
        self.assert_code("tree_nonregular_forbidden", lambda: PARITY.verify(self.root))

    def test_intermediate_symlink_hardlink_and_oversize_fail_closed(self) -> None:
        PARITY.write_manifest(self.root)
        with tempfile.TemporaryDirectory() as external_name:
            external = Path(external_name).resolve() / "plugins"
            shutil.copytree(self.root / "plugins", external)
            (self.root / "plugins").rename(self.root / "plugins-owned")
            (self.root / "plugins").symlink_to(external, target_is_directory=True)
            self.assert_code("file_nonregular_or_alias", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        plugin = self.root / "plugins/graph-engineering"
        os.link(plugin / "README.md", plugin / "README-copy.md")
        self.assert_code("file_hardlink_forbidden", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        oversized = self.root / "plugins/graph-engineering/oversized.bin"
        with oversized.open("wb") as stream:
            stream.truncate(PARITY.MAX_FILE_BYTES + 1)
        self.assert_code("file_oversize", lambda: PARITY.verify(self.root))

    def test_projection_missing_extra_changed_symlink_and_contract_duplicate_fail(self) -> None:
        PARITY.write_manifest(self.root)
        runtime = self.root / "plugins/graph-engineering/runtime/core/models.py"
        runtime.write_text(runtime.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        self.assert_code("projection_changed", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        (self.root / "plugins/graph-engineering/runtime/extra.txt").write_text("extra", encoding="utf-8")
        self.assert_code("projection_missing_or_extra", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        source = self.root / "packages/core/models.py"
        source.unlink()
        source.symlink_to("selection.py")
        self.assert_code("tree_alias_forbidden", lambda: PARITY.verify(self.root))

        self.setUp_fixture_again()
        PARITY.write_manifest(self.root)
        contract = self.root / "contracts/package/projection-map.json"
        raw = contract.read_text(encoding="utf-8")
        contract.write_text(raw.replace('"schema_version":', '"schema_version":"duplicate","schema_version":', 1), encoding="utf-8")
        self.assert_code("json_duplicate_key", lambda: PARITY.verify(self.root))

    def test_manifest_identity_binds_projection_map_and_package(self) -> None:
        manifest = PARITY.write_manifest(self.root)
        payload = {key: value for key, value in manifest.items() if key != "candidate_sha256"}
        self.assertEqual(PARITY.digest(PARITY.canonical_json(payload)), manifest["candidate_sha256"])

        plugin = self.root / "plugins/graph-engineering/.codex-plugin/plugin.json"
        value = json.loads(plugin.read_text(encoding="utf-8"))
        value["version"] = "0.1.5"
        plugin.write_text(json.dumps(value), encoding="utf-8")
        self.assert_code("plugin_identity_mismatch", lambda: PARITY.verify(self.root))


if __name__ == "__main__":
    unittest.main()
