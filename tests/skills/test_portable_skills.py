from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = PROJECT_ROOT / "plugins" / "graph-engineering" / "skills"
COMMANDS_ROOT = PROJECT_ROOT / "plugins" / "graph-engineering" / "commands"
PUBLIC_COMMANDS = ("graph-start", "graph-update", "graph-audit", "graph-benchmark")


class PortableSkillTests(unittest.TestCase):
    def test_public_commands_resolve_to_matching_skills(self) -> None:
        for name in PUBLIC_COMMANDS:
            command = tomllib.loads(
                (COMMANDS_ROOT / f"{name}.toml").read_text(encoding="utf-8")
            )
            self.assertTrue(command["description"])
            self.assertIn(f"${name}", command["prompt"])
            skill = SKILLS_ROOT / name / "SKILL.md"
            self.assertTrue(skill.is_file(), name)
            self.assertIn(f"name: {name}", skill.read_text(encoding="utf-8"))

    def test_graph_benchmark_uses_native_fresh_lanes(self) -> None:
        skill = (SKILLS_ROOT / "graph-benchmark" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        command = tomllib.loads(
            (COMMANDS_ROOT / "graph-benchmark.toml").read_text(encoding="utf-8")
        )
        self.assertIn("host-native worker lanes", skill)
        self.assertIn("no inherited conversation history", skill)
        self.assertIn("Do not invoke `codex`, `codex exec`", skill)
        self.assertIn("fresh_lane_execution_unavailable", skill)
        self.assertIn("never launch a nested Codex CLI process", command["prompt"])

    def test_graph_benchmark_has_complete_report_template(self) -> None:
        template = " ".join(
            (
                SKILLS_ROOT / "graph-benchmark" / "templates" / "benchmark-report.md"
            )
            .read_text(encoding="utf-8")
            .split()
        )
        for section in (
            "## Benchmark Identity",
            "## Overall Results",
            "## Results By Track",
            "## Task Results",
            "## Quality And Safety",
            "## Efficiency Detail",
            "## Cold And Warm Interpretation",
            "## Product Interpretation",
            "## Evidence Inventory",
            "## Upstream Feedback Candidates",
            "## Limitations And Next Proof",
        ):
            self.assertIn(section, template)
        self.assertIn("unknown", template)
        self.assertIn("Repetitions and seeds", template)
        self.assertIn("Tool use and validation", template)
        self.assertIn("Product and visual design", template)
        self.assertIn("Creative writing", template)
        self.assertIn("Do not calculate a weighted cross-track quality score", template)
        self.assertIn("Do not open the issue until the operator approves this exact draft", template)

        skill = (SKILLS_ROOT / "graph-benchmark" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Vel-Labs/velGraphing", skill)
        self.assertIn("Installation and benchmark authority do not authorize publication", skill)
        self.assertIn("Your name, repository identity, local paths", skill)
        self.assertIn("This issue could help improve", skill)
        self.assertIn("public or synthetic reproduction", skill)

    def test_expected_skill_roots_and_resources_exist(self) -> None:
        expected = {
            "graph-engineering": {
                "SKILL.md",
                "assets/graph-profile.schema.json",
                "assets/graph-record.schema.json",
                "assets/readiness-report.schema.json",
                "references/architecture.md",
                "references/evidence-base.md",
                "references/quality-gates.md",
                "references/readiness.md",
                "scripts/graphctl.py",
                "templates/graph-evaluation.md",
                "templates/graph-profile.json",
            },
            "graph-steward": {
                "SKILL.md",
                "assets/federation-registry.schema.json",
                "references/federation-and-lifecycle.md",
                "scripts/stewardctl.py",
                "templates/federation-registry.json",
            },
        }
        for skill_name, resources in expected.items():
            root = SKILLS_ROOT / skill_name
            self.assertTrue(root.is_dir(), skill_name)
            actual = {
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(resources, actual, skill_name)

    def test_markdown_resource_links_are_relative_and_resolve(self) -> None:
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for skill_file in SKILLS_ROOT.glob("*/SKILL.md"):
            text = skill_file.read_text(encoding="utf-8")
            for target in link_pattern.findall(text):
                if "://" in target:
                    continue
                self.assertFalse(target.startswith(("/", "~")), target)
                resolved = (skill_file.parent / target).resolve()
                self.assertTrue(resolved.is_relative_to(SKILLS_ROOT.resolve()), target)
                self.assertTrue(resolved.is_file(), target)

    def test_packaged_text_has_no_machine_specific_workspace_path(self) -> None:
        banned = ("/Users/", "~/.codex", "/.codex/", "Workspace/_skills")
        for path in SKILLS_ROOT.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for marker in banned:
                    self.assertNotIn(marker, text, f"{marker} in {path}")

    def test_graph_engineering_preserves_proof_and_trust_boundaries(self) -> None:
        text = " ".join(
            (SKILLS_ROOT / "graph-engineering" / "SKILL.md")
            .read_text(encoding="utf-8")
            .split()
        )
        required = (
            "A graph view is not proof",
            "Default export to deny",
            "unauthenticated edge",
            "does not claim installation, federation, execution, or acceptance",
        )
        for phrase in required:
            self.assertIn(phrase, text)

    def test_graph_engineering_documents_bounded_context_assist(self) -> None:
        skill = " ".join(
            (SKILLS_ROOT / "graph-engineering" / "SKILL.md")
            .read_text(encoding="utf-8")
            .split()
        )
        readme = " ".join(
            (PROJECT_ROOT / "plugins" / "graph-engineering" / "README.md")
            .read_text(encoding="utf-8")
            .split()
        )
        for text in (skill, readme):
            self.assertIn("same verified source snapshot", text)
            self.assertIn("does not enumerate or search a repository", text)
            self.assertIn("does not call a provider", text)
        self.assertIn("caller-declared fallback allowlist", skill)
        self.assertIn("fail-closed defer route", readme)

    def test_graph_engineering_documents_readiness_as_advisory_only(self) -> None:
        skill = " ".join(
            (SKILLS_ROOT / "graph-engineering" / "SKILL.md")
            .read_text(encoding="utf-8")
            .split()
        )
        plugin_readme = " ".join(
            (PROJECT_ROOT / "plugins" / "graph-engineering" / "README.md")
            .read_text(encoding="utf-8")
            .split()
        )
        self.assertIn("`readiness`", skill)
        self.assertIn("incomplete scan as `unknown`", skill)
        self.assertIn("cannot execute", skill)
        self.assertIn("auto_apply: false", plugin_readme)

    def test_graph_steward_preserves_authority_and_admission_boundaries(self) -> None:
        text = " ".join(
            (SKILLS_ROOT / "graph-steward" / "SKILL.md")
            .read_text(encoding="utf-8")
            .split()
        )
        required = (
            "does not become the canonical owner",
            "Export defaults to deny",
            "A proposal or validation pass is not admission",
            "not a live query, index, service, or operational acceptance result",
        )
        for phrase in required:
            self.assertIn(phrase, text)

    def test_skill_entrypoints_keep_v4_recommendations_advisory_only(self) -> None:
        engineering = " ".join(
            (SKILLS_ROOT / "graph-engineering" / "SKILL.md")
            .read_text(encoding="utf-8")
            .split()
        )
        steward = " ".join(
            (SKILLS_ROOT / "graph-steward" / "SKILL.md")
            .read_text(encoding="utf-8")
            .split()
        )
        self.assertIn("explicit current task authority", engineering)
        self.assertIn("explicit current task authority", steward)
        for text, route in ((engineering, "`graph_engineering`"), (steward, "`graph_steward`")):
            self.assertIn(route, text)
            self.assertIn("optional advisory planning metadata", text)
            self.assertIn("insufficient for activation", text)
            self.assertIn("does not authorize a write", text)
            self.assertIn("visible task authority remains controlling", text)
            self.assertIn("`defer` grants no authority", text)
            self.assertIn("Neither V2 nor V4 can activate this skill", text)
            self.assertIn("V3 is rejected and non-callable", text)
            self.assertIn("caller or model routing fields", text)
            self.assertIn("hostile-host containment", text)

    def test_steward_cli_accepts_equivalent_workspace_root_alias(self) -> None:
        steward = (
            SKILLS_ROOT / "graph-steward" / "scripts" / "stewardctl.py"
        )
        profile_template = (
            SKILLS_ROOT
            / "graph-engineering"
            / "templates"
            / "graph-profile.json"
        )
        with tempfile.TemporaryDirectory(prefix="graph-steward-root-") as raw:
            fixture_root = Path(raw)
            workspace_root = fixture_root / "workspace"
            workspace_root.mkdir()
            alias_root = fixture_root / "workspace-alias"
            alias_root.symlink_to(workspace_root, target_is_directory=True)

            (workspace_root / "profile.json").write_bytes(
                profile_template.read_bytes()
            )
            (workspace_root / "export.jsonl").write_text("", encoding="utf-8")
            registry = workspace_root / "registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "graph_id": "workspace-collective",
                        "namespace": "workspace",
                        "owner": "workspace-owner",
                        "workspace_root": str(alias_root),
                        "children": [
                            {
                                "graph_id": "project-example",
                                "namespace": "example",
                                "owner": "project-owner",
                                "definition_version": "1",
                                "profile_path": "profile.json",
                                "export_path": "export.jsonl",
                                "lifecycle": "proposed",
                                "ingest_mode": "disabled",
                                "sensitivity_ceiling": "internal",
                                "allowed_node_types": [],
                                "allowed_edge_types": [],
                            }
                        ],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(steward),
                    "validate-registry",
                    "--workspace-root",
                    str(workspace_root),
                    str(registry),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("pass", json.loads(result.stdout)["status"])

    @property
    def graphctl(self) -> Path:
        return SKILLS_ROOT / "graph-engineering" / "scripts" / "graphctl.py"

    def run_readiness(
        self,
        root: Path,
        *includes: str,
        complete: bool = False,
        max_file_bytes: int | None = None,
        source_identity: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(self.graphctl),
            "readiness",
            "--root",
            str(root),
        ]
        for include in includes:
            command.extend(("--include", include))
        if complete:
            command.extend(("--policy-status", "complete"))
        if max_file_bytes is not None:
            command.extend(("--max-file-bytes", str(max_file_bytes)))
        if source_identity:
            command.extend(
                (
                    "--source-revision",
                    "fixture-revision",
                    "--source-observed-at",
                    "2026-08-27T12:00:00Z",
                )
            )
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def make_readiness_fixture(self, root: Path) -> None:
        (root / "docs").mkdir()
        (root / "contracts").mkdir()
        (root / "tests").mkdir()
        (root / "scripts").mkdir()
        (root / "src").mkdir()
        (root / ".git").mkdir()
        (root / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
        (root / "README.md").write_text(
            "[Plan](docs/plan.md) [Missing](docs/missing.md)\n", encoding="utf-8"
        )
        (root / "package.json").write_text("{}\n", encoding="utf-8")
        (root / "SKILL.md").write_text("# Workflow\n", encoding="utf-8")
        (root / "docs" / "plan.md").write_text("# Plan\n", encoding="utf-8")
        (root / "docs" / "state.yaml").write_text("status: active\n", encoding="utf-8")
        (root / "contracts" / "item.schema.json").write_text("{}\n", encoding="utf-8")
        (root / "tests" / "test_item.py").write_text("pass\n", encoding="utf-8")
        (root / "scripts" / "check.py").write_text("pass\n", encoding="utf-8")
        (root / "src" / "item.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / ".git" / "private-state").write_text("do not read\n", encoding="utf-8")

    def test_readiness_report_is_deterministic_and_classifies_anchor_roles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="graph-readiness-") as raw:
            root = Path(raw)
            self.make_readiness_fixture(root)
            first = self.run_readiness(root, ".", complete=True)
            second = self.run_readiness(root, ".", complete=True)

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        roles = {item["path"]: item["role"] for item in report["files"]}
        self.assertEqual("instructions", roles["AGENTS.md"])
        self.assertEqual("overview", roles["README.md"])
        self.assertEqual("manifest", roles["package.json"])
        self.assertEqual("workflow", roles["SKILL.md"])
        self.assertEqual("plan", roles["docs/plan.md"])
        self.assertEqual("task_truth", roles["docs/state.yaml"])
        self.assertEqual("contract", roles["contracts/item.schema.json"])
        self.assertEqual("validation_test", roles["tests/test_item.py"])
        self.assertEqual("validation_script", roles["scripts/check.py"])
        self.assertEqual("source", roles["src/item.py"])
        self.assertNotIn(".git/private-state", roles)
        self.assertEqual(
            hashlib.sha256(b"VALUE = 1\n").hexdigest(),
            next(item["sha256"] for item in report["files"] if item["path"] == "src/item.py"),
        )
        self.assertEqual(
            sorted(item["path"] for item in report["files"]),
            [item["path"] for item in report["files"]],
        )
        self.assertEqual(
            ["broken", "resolved"], sorted(link["status"] for link in report["links"])
        )
        self.assertIn("broken_local_reference", {item["code"] for item in report["findings"]})

    def test_readiness_missing_anchors_and_incomplete_policy_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="graph-readiness-") as raw:
            root = Path(raw)
            (root / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = self.run_readiness(root, "source.py")

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("unknown", report["status"])
        codes = {item["code"] for item in report["findings"]}
        self.assertTrue(
            {
                "missing_root_instructions",
                "missing_root_overview",
                "missing_validation_entrypoint",
                "incomplete_scan_policy",
            }.issubset(codes)
        )

    def test_readiness_reports_unavailable_source_identity_and_nonexecuting_advice(self) -> None:
        with tempfile.TemporaryDirectory(prefix="graph-readiness-") as raw:
            root = Path(raw)
            self.make_readiness_fixture(root)
            result = self.run_readiness(root, ".", complete=True, source_identity=False)

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        codes = {item["code"] for item in report["findings"]}
        self.assertIn("source_identity_unavailable", codes)
        for recommendation in report["recommendations"]:
            self.assertFalse(recommendation["auto_apply"])
            self.assertTrue(recommendation["requires_human_authority"])
            self.assertTrue(recommendation["finding_codes"])
            self.assertTrue(recommendation["target_refs"])
            self.assertTrue(recommendation["expected_proof"])

    def test_readiness_rejects_unsafe_or_missing_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="graph-readiness-") as raw:
            root = Path(raw)
            (root / "safe.txt").write_text("safe\n", encoding="utf-8")

            cases = []
            cases.append(("traversal", self.run_readiness(root, "../outside")))
            cases.append(("missing", self.run_readiness(root, "missing.txt")))
            cases.append(("oversize", self.run_readiness(root, "safe.txt", max_file_bytes=3)))

            symlink = root / "linked.txt"
            symlink.symlink_to(root / "safe.txt")
            cases.append(("symlink", self.run_readiness(root, "linked.txt")))
            symlink.unlink()

            real_directory = root / "real-directory"
            real_directory.mkdir()
            (real_directory / "nested.txt").write_text("nested\n", encoding="utf-8")
            linked_directory = root / "linked-directory"
            linked_directory.symlink_to(real_directory, target_is_directory=True)
            cases.append(
                ("symlink-component", self.run_readiness(root, "linked-directory/nested.txt"))
            )
            linked_directory.unlink()

            fifo = root / "named-pipe"
            os.mkfifo(fifo)
            cases.append(("non-regular", self.run_readiness(root, "named-pipe")))
            fifo.unlink()

            alias = root / "alias.txt"
            os.link(root / "safe.txt", alias)
            cases.append(("hardlink", self.run_readiness(root, ".")))

        for name, result in cases:
            with self.subTest(name=name):
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertEqual("", result.stdout)
                self.assertFalse(json.loads(result.stderr)["valid"])

    def test_readiness_stdout_only_and_paths_are_portable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="graph-readiness-") as raw:
            root = Path(raw)
            self.make_readiness_fixture(root)
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            result = self.run_readiness(root, ".", complete=True)
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, after)
        self.assertNotIn(str(root), result.stdout)
        report = json.loads(result.stdout)
        for item in report["files"]:
            self.assertFalse(Path(item["path"]).is_absolute())
            self.assertNotIn("..", Path(item["path"]).parts)

    def test_readiness_schema_is_valid_json_and_describes_combined_report(self) -> None:
        schema_path = (
            SKILLS_ROOT
            / "graph-engineering"
            / "assets"
            / "readiness-report.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual("object", schema["type"])
        for field in (
            "scan_policy",
            "files",
            "links",
            "findings",
            "recommendations",
        ):
            self.assertIn(field, schema["required"])


if __name__ == "__main__":
    unittest.main()
