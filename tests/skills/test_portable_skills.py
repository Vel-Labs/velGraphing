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
PUBLIC_COMMANDS = ("graph-find", "graph-start", "graph-update", "graph-audit", "graph-benchmark")


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
            "graph-find": {
                "SKILL.md",
                "agents/openai.yaml",
                "scripts/graph_find.py",
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

    def test_graph_find_is_discoverable_and_documents_defer_boundary(self) -> None:
        command = tomllib.loads((COMMANDS_ROOT / "graph-find.toml").read_text(encoding="utf-8"))
        skill = (SKILLS_ROOT / "graph-find" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("$graph-find", command["prompt"])
        self.assertIn("route: graph", skill)
        self.assertIn("route: defer", skill)
        self.assertIn("Repository source", skill)
        self.assertIn("remains", skill)
        self.assertIn("authoritative", skill)
        self.assertIn("does not write", skill)

    def test_graph_find_subprocess_returns_pointers_without_bodies(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        cache_before = sorted(str(path) for path in PROJECT_ROOT.rglob("__pycache__"))
        with tempfile.TemporaryDirectory(prefix="graph-find-") as raw:
            root = Path(raw)
            (root / "src").mkdir()
            (root / "src" / "auth.py").write_text(
                "def refresh_token(token):\n    return token\n", encoding="utf-8"
            )
            (root / "untracked.txt").write_text("must not be scanned\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "add", "src/auth.py"], check=True
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--prompt",
                    "find refresh_token",
                ],
                text=True,
                capture_output=True,
                check=False,
                env={key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"},
            )

        self.assertEqual(cache_before, sorted(str(path) for path in PROJECT_ROOT.rglob("__pycache__")))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("graph", payload["route"])
        self.assertTrue(payload["evidence"])
        self.assertNotIn("context", payload)
        self.assertNotIn("content", result.stdout)
        self.assertNotIn("untracked.txt", result.stdout)
        self.assertTrue(all("source_path" in item for item in payload["evidence"]))

    def test_graph_find_rebuilds_from_current_tracked_bytes(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-fresh-") as raw:
            root = Path(raw)
            source = root / "src" / "target.py"
            source.parent.mkdir()
            source.write_text(
                "def current_target():\n    return 'first'\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "src/target.py"], check=True)

            def run_find() -> dict[str, object]:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--root",
                        str(root),
                        "--prompt",
                        "find current_target",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return json.loads(result.stdout)

            first = run_find()
            source.write_text(
                "def current_target():\n    return 'second'\n", encoding="utf-8"
            )
            subprocess.run(["git", "-C", str(root), "add", "src/target.py"], check=True)
            second = run_find()

        self.assertNotEqual(
            first["source_snapshot_sha256"], second["source_snapshot_sha256"]
        )
        first_source_sha = first["evidence"][0]["source_sha256"]
        second_source_sha = second["evidence"][0]["source_sha256"]
        self.assertNotEqual(first_source_sha, second_source_sha)
        self.assertIn(
            "src/target.py",
            {item["source_path"] for item in second["hits"]},
        )

    def test_graph_find_returns_only_uniquely_resolved_source_bound_support(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-edges-") as raw:
            root = Path(raw)
            (root / "src").mkdir()
            (root / "docs").mkdir()
            (root / "src" / "caller.py").write_text(
                "from src.helper import helper\n\ndef call_helper():\n    return helper()\n",
                encoding="utf-8",
            )
            (root / "src" / "helper.py").write_text(
                "def helper():\n    return 1\n", encoding="utf-8"
            )
            (root / "README.md").write_text(
                "# Start\nSee the [install guide](docs/guide.md#install).\n",
                encoding="utf-8",
            )
            (root / "docs" / "guide.md").write_text(
                "# Install\nUse call_helper.\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--prompt",
                    "find call_helper install guide",
                ],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        supports = payload["relationship_supports"]
        self.assertEqual({item["relation"] for item in supports}, {"imports", "links_to_heading"})
        self.assertEqual(payload["scan"]["edges_derived"], 2)
        self.assertTrue(all(item["source_coordinate"]["schema_version"] == "source-coordinate-v1" for item in supports))
        self.assertNotIn("return helper()", result.stdout)

    def test_graph_find_leaves_ambiguous_relations_unresolved(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-ambiguous-") as raw:
            root = Path(raw)
            (root / "src").mkdir()
            (root / "src" / "caller.py").write_text(
                "from src.helper import helper\n", encoding="utf-8"
            )
            (root / "src" / "helper.py").write_text(
                "def helper():\n    return 1\n\ndef helper():\n    return 2\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "# Topic\n# Topic\n[topic](README.md#topic)\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "--prompt", "find helper topic"],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scan"]["edges_derived"], 0)
        self.assertEqual(payload["relationship_supports"], [])

    def test_graph_find_rejects_unsupported_imports_and_markdown_links(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-rejected-edges-") as raw:
            root = Path(raw)
            (root / "src").mkdir()
            (root / "docs").mkdir()
            (root / "src" / "caller.py").write_text(
                "import src.helper\nfrom src.helper import *\nfrom missing import helper\n",
                encoding="utf-8",
            )
            (root / "src" / "helper.py").write_text(
                "def helper():\n    return 1\n", encoding="utf-8"
            )
            (root / "README.md").write_text(
                "# Topic\n"
                "[external](https://example.com/page#topic)\n"
                "[alias](docs/../README.md#topic)\n"
                "[fragment](#topic)\n"
                "[missing target](docs/missing.md#topic)\n"
                "[missing fragment](docs/guide.md)\n",
                encoding="utf-8",
            )
            (root / "docs" / "guide.md").write_text("# Topic\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "--prompt", "find helper topic"],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scan"]["edges_derived"], 0)
        self.assertEqual(payload["relationship_supports"], [])

    def test_graph_find_subprocess_rejects_alias_and_byte_caps(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-unsafe-") as raw:
            root = Path(raw)
            (root / "large.txt").write_text("x" * 32, encoding="utf-8")
            (root / "ok.txt").write_text("ok\n", encoding="utf-8")
            (root / "small.txt").write_text("s\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "add", "large.txt", "ok.txt", "small.txt"], check=True
            )
            cap = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--prompt",
                    "find x",
                    "--max-file-bytes",
                    "8",
                    "--max-total-bytes",
                    "3",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            root_alias = root.parent / f"{root.name}-alias"
            root_alias.symlink_to(root, target_is_directory=True)
            alias = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root_alias),
                    "--prompt",
                    "find x",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, cap.returncode, cap.stdout + cap.stderr)
        self.assertEqual("defer", json.loads(cap.stdout)["route"])
        self.assertEqual("repository_scan_incomplete", json.loads(cap.stdout)["reason"])
        self.assertFalse(json.loads(cap.stdout)["scan"]["scan_complete"])
        self.assertEqual(
            {"max_file_bytes": 1, "max_total_bytes": 1},
            json.loads(cap.stdout)["scan"]["skip_counts"],
        )
        self.assertEqual(2, alias.returncode)
        self.assertIn("alias", alias.stderr)

    def test_graph_find_subprocess_skips_unsupported_tracked_files(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-skip-") as raw:
            root = Path(raw)
            (root / "usable.py").write_text(
                "def refresh_token():\n    return 'ok'\n", encoding="utf-8"
            )
            (root / "binary.bin").write_bytes(b"\xff\xfe\x00")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "add", "usable.py", "binary.bin"], check=True
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--prompt",
                    "find refresh_token",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual({"invalid_utf8": 1}, payload["scan"]["skip_counts"])
        self.assertEqual("binary.bin", payload["scan"]["files_skipped"][0]["path"])

    def test_graph_find_subprocess_excludes_sensitive_paths_without_names(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        sensitive_names = (".env", "private", "credentials", "id_rsa", "cert.pem", "bundle.p12")
        with tempfile.TemporaryDirectory(prefix="graph-find-sensitive-") as raw:
            root = Path(raw)
            (root / "usable.py").write_text(
                "def refresh_token():\n    return 'ok'\n", encoding="utf-8"
            )
            (root / ".env").write_text("refresh_token=secret\n", encoding="utf-8")
            (root / "private").mkdir()
            (root / "private" / "id_rsa").write_text("PRIVATE KEY\n", encoding="utf-8")
            (root / "credentials").mkdir()
            (root / "credentials" / "record.txt").write_text("secret\n", encoding="utf-8")
            (root / "cert.pem").write_text("PRIVATE KEY\n", encoding="utf-8")
            (root / "bundle.p12").write_text("PRIVATE KEY\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "add", "."], check=True
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--prompt",
                    "find refresh_token",
                ],
                text=True,
                capture_output=True,
                check=False,
                env={key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"},
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("defer", payload["route"])
        self.assertEqual("sensitive_paths_excluded", payload["reason"])
        self.assertEqual(5, payload["scan"]["sensitive_paths_excluded"])
        self.assertEqual(5, payload["scan"]["skip_counts"]["sensitive_paths_excluded"])
        self.assertTrue(payload["scan"]["scan_complete"] is False)
        for name in sensitive_names:
            self.assertNotIn(name, result.stdout)

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
