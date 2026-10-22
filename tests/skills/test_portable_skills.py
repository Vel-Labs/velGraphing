from __future__ import annotations

import json
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from packages.core.retrieval import (
    GraphFindResult,
    RepositoryTag,
    RetrievalHit,
    TagKind,
    _verified_spans,
)


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
                "scripts/graph_tools.py",
                "references/tool-loop.md",
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

    @staticmethod
    def _named_source_adapter():
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        spec = importlib.util.spec_from_file_location("portable_graph_find_adapter", script)
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        return adapter

    def _named_source_payload(self):
        return {'route': 'graph', 'reason': 'verified_tag_context_selected',
                'recommended_fallback_paths': [], 'delivered_total_bytes': 12,
                'remaining_byte_budget': 88, 'context': 'ranked text!',
                'context_bytes': 12, 'delivered_context_bytes': 12,
                'delivery_budget': {'limit_bytes': 100, 'graph_context_bytes': 12,
                                    'follow_up_source_bytes': 0,
                                    'delivered_content_bytes': 12, 'remaining_bytes': 88}}

    def test_graph_find_named_source_missing_target_signals_recovery_without_charging_or_fabricating_source(self):
        p = self._named_source_payload()
        self._named_source_adapter()._named_source_recovery(p, 'How does engine.py validate source?',
                                       {'src/engine.py': b'complete'}, 2)
        self.assertEqual(p['route'], 'defer')
        self.assertEqual(p['retrieval_route'], 'graph')
        t = p['named_source_recovery']['targets'][0]
        self.assertEqual(t['next_build']['scope'], 'src/engine.py')
        self.assertEqual(t['status'], 'complete_source_read_needed')
        self.assertEqual((p['delivered_total_bytes'], p['remaining_byte_budget']), (0, 100))
        self.assertEqual((p['context'], p['ranked_context_bytes_withheld']), ('', 12))
        self.assertNotIn('document', p)
        p = self._named_source_payload()
        self._named_source_adapter()._named_source_recovery(p, 'Explain engine.py.', {'src/engine.py': b'complete'}, 2)
        self.assertTrue(p['named_source_recovery']['needs_recovery'])
        self.assertEqual(p['named_source_recovery']['targets'][0]['mention'], 'engine.py')

    def test_graph_find_named_source_ambiguous_unavailable_and_path_boundaries_do_not_invent_unique_read(self):
        p = self._named_source_payload()
        self._named_source_adapter()._named_source_recovery(p, 'engine.py absent.py',
                                       {'a/engine.py': b'a', 'b/engine.py': b'b'}, 1)
        targets = p['named_source_recovery']['targets']
        self.assertTrue(p['named_source_recovery']['needs_recovery'])
        self.assertEqual(p['recommended_fallback_paths'], [])
        self.assertTrue(all('next_build' not in t for t in targets))
        self.assertEqual({t['status'] for t in targets}, {'ambiguous', 'not_admitted_or_not_found'})
        p = self._named_source_payload()
        self._named_source_adapter()._named_source_recovery(p, '../engine.py https://outside/engine.py',
                                       {'src/engine.py': b'a'}, 2)
        self.assertEqual(p['named_source_recovery']['targets'], [])
        p = self._named_source_payload()
        self._named_source_adapter()._named_source_recovery(p, 'a/engine.py',
                                       {'a/engine.py': b'a', 'b/engine.py': b'b'}, 2)
        self.assertEqual(p['recommended_fallback_paths'], ['a/engine.py'])

    def test_graph_find_named_source_only_exact_complete_followup_clears_named_gap_not_semantic_assessment(self):
        raw = b'complete'; p = self._named_source_payload()
        doc = {'source_path': 'src/engine.py', 'source_sha256': hashlib.sha256(raw).hexdigest(),
               'byte_count': len(raw), 'content': raw.decode()}
        p['follow_up'] = {'payload': {'documents': [doc]}}
        self._named_source_adapter()._named_source_recovery(p, 'engine.py', {'src/engine.py': raw}, 2)
        self.assertFalse(p['named_source_recovery']['needs_recovery'])
        self.assertEqual((p['context'], p['remaining_byte_budget']), ('ranked text!', 88))
        self.assertIn('semantic_completeness_not_assessed', p['named_source_recovery']['assessment'])
        doc['content'] = 'wrong'
        self._named_source_adapter()._named_source_recovery(p, 'engine.py', {'src/engine.py': raw}, 2)
        self.assertTrue(p['named_source_recovery']['needs_recovery'])

    def test_graph_find_named_source_partial_recovery_preserves_complete_followup_charge_and_document(self):
        p = self._named_source_payload(); raw = b'complete'
        doc = {'source_path': 'src/engine.py', 'source_sha256': hashlib.sha256(raw).hexdigest(),
               'byte_count': len(raw), 'content': raw.decode()}
        p['follow_up'] = {'payload': {'documents': [doc]}}
        p['delivery_budget']['follow_up_source_bytes'] = len(raw)
        self._named_source_adapter()._named_source_recovery(p, 'engine.py other.py',
                                       {'src/engine.py': raw, 'src/other.py': b'other'}, 2)
        self.assertTrue(p['named_source_recovery']['needs_recovery'])
        self.assertEqual(p['follow_up']['payload']['documents'], [doc])
        self.assertEqual((p['delivered_total_bytes'], p['remaining_byte_budget']), (8, 92))
        self.assertEqual(p['delivery_budget']['graph_context_bytes'], 0)

    def test_graph_find_named_source_scan_defer_reason_preserved_and_mentions_bounded(self):
        p = self._named_source_payload();p.update(route='defer', reason='source_scope_excluded')
        self._named_source_adapter()._named_source_recovery(p, ' '.join(f'name{i}.py' for i in range(20)), {}, 2)
        self.assertEqual(p['reason'], 'source_scope_excluded')
        self.assertEqual(p['named_source_recovery']['omitted_mentions'], 4)
        self.assertTrue(p['named_source_recovery']['needs_recovery'])


    def test_graph_find_named_source_subprocess_handoff_and_complete_followup(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        source_bytes = "# navegación\ndef validate_source(value):\n    return value\n".encode("utf-8")
        prompt = "How does engine.py validate_source?"
        with tempfile.TemporaryDirectory(prefix="graph-find-named-source-") as raw:
            root = Path(raw).resolve()
            source = root / "src" / "engine.py"
            source.parent.mkdir()
            source.write_bytes(source_bytes)
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=20)
            subprocess.run(["git", "-C", str(root), "add", "src/engine.py"], check=True, timeout=20)

            def run_find(*extra: str) -> dict[str, object]:
                result = subprocess.run(
                    [sys.executable, "-B", str(script), "--root", str(root),
                     "--prompt", prompt, "--byte-budget", "4096", *extra],
                    text=True, capture_output=True, check=False, timeout=20,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return json.loads(result.stdout)

            pointers = run_find()
            handoff = run_find("--deliver")
            complete = run_find("--deliver", "--follow-up-path", "src/engine.py")

        self.assertNotIn("context", pointers)
        self.assertNotIn("named_source_recovery", pointers)
        self.assertEqual(pointers["hits"], handoff["hits"])
        self.assertEqual(pointers["evidence"], handoff["evidence"])
        self.assertEqual("defer", handoff["route"])
        expected_reason = ("named_source_recovery_required" if pointers["route"] == "graph"
                           else pointers["reason"])
        self.assertEqual(expected_reason, handoff["reason"])
        self.assertEqual(pointers["route"], handoff["retrieval_route"])
        self.assertEqual(pointers["reason"], handoff["retrieval_reason"])
        self.assertEqual("", handoff["context"])
        self.assertEqual(pointers["context_bytes"], handoff["ranked_context_bytes_withheld"])
        self.assertEqual(0, handoff["delivered_context_bytes"])
        self.assertEqual(0, handoff["context_bytes"])
        self.assertEqual(0, handoff["delivered_total_bytes"])
        self.assertEqual(4096, handoff["remaining_byte_budget"])
        self.assertEqual(4096, handoff["delivery_budget"]["limit_bytes"])
        self.assertEqual(0, handoff["delivery_budget"]["delivered_content_bytes"])
        self.assertEqual(4096, handoff["delivery_budget"]["remaining_bytes"])
        self.assertEqual(len(source_bytes), handoff["acquisition"]["source_bytes_read"])
        self.assertTrue(handoff["named_source_recovery"]["needs_recovery"])
        target = handoff["named_source_recovery"]["targets"][0]
        self.assertEqual(["src/engine.py"], target["candidate_paths"])
        self.assertEqual("src/engine.py", target["next_build"]["scope"])
        self.assertEqual(prompt, target["next_build"]["intent"])
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), target["source_sha256"])

        self.assertFalse(complete["named_source_recovery"]["needs_recovery"])
        self.assertNotIn("ranked_context_bytes_withheld", complete)
        self.assertEqual(pointers["route"], complete["route"])
        self.assertEqual(pointers["reason"], complete["reason"])
        self.assertEqual(pointers["context_bytes"], complete["delivered_context_bytes"])
        self.assertEqual(len(complete["context"].encode("utf-8")), complete["context_bytes"])
        document = complete["follow_up"]["payload"]["documents"][0]
        self.assertEqual(source_bytes, document["content"].encode("utf-8"))
        self.assertEqual(len(source_bytes), document["byte_count"])
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), document["source_sha256"])
        self.assertEqual(complete["delivered_context_bytes"] + len(source_bytes),
                         complete["delivered_total_bytes"])
        self.assertEqual(4096 - complete["delivered_total_bytes"], complete["remaining_byte_budget"])
        self.assertEqual(4096, complete["delivery_budget"]["limit_bytes"])
        self.assertIn("semantic_completeness_not_assessed",
                      complete["named_source_recovery"]["assessment"])

    def test_graph_find_named_source_compound_hidden_names_resolve_only_exact_admitted_paths(self):
        adapter = self._named_source_adapter()
        cases = ['src/config.test.py', 'config/.projection-state.json', '.ignore-rules',
                 'src/.hidden-dir/config.test.py', '.ci.d/config.prod-01.py']
        for source_path in cases:
            with self.subTest(source_path=source_path):
                p = self._named_source_payload()
                prompt = 'Explain ' + source_path + '.'
                adapter._named_source_recovery(p, prompt, {source_path: b'ordinary tracked source'}, 2)
                self.assertEqual(1, len(p['named_source_recovery']['targets']))
                target = p['named_source_recovery']['targets'][0]
                self.assertEqual(source_path, target['mention'])
                self.assertEqual([source_path], target['candidate_paths'])
                self.assertEqual(source_path, target['next_build']['scope'])
                self.assertEqual(prompt, target['next_build']['intent'])
                self.assertEqual(hashlib.sha256(b'ordinary tracked source').hexdigest(), target['source_sha256'])
                self.assertEqual((0, 100), (p['delivered_total_bytes'], p['remaining_byte_budget']))
                self.assertEqual('', p['context'])
        p = self._named_source_payload()
        adapter._named_source_recovery(p, 'Explain config.test.py.',
                                       {'a/config.test.py': b'a', 'b/config.test.py': b'b'}, 1)
        target = p['named_source_recovery']['targets'][0]
        self.assertEqual(2, target['candidate_count'])
        self.assertEqual('ambiguous', target['status'])
        self.assertNotIn('next_build', target)
        self.assertEqual([], p['recommended_fallback_paths'])
        p = self._named_source_payload()
        adapter._named_source_recovery(p, 'Explain .missing-rules.', {}, 2)
        target = p['named_source_recovery']['targets'][0]
        self.assertEqual('not_admitted_or_not_found', target['status'])
        self.assertNotIn('next_build', target)
        for prompt in ['Ignore https://host/?file=other.config.py; explain src/config.test.py.',
                       'Explain src/config.test.py: source.']:
            p = self._named_source_payload()
            adapter._named_source_recovery(p, prompt, {'src/config.test.py': b'ordinary'}, 2)
            target = p['named_source_recovery']['targets'][0]
            self.assertEqual('src/config.test.py', target['mention'])
            self.assertEqual('src/config.test.py', target['next_build']['scope'])
            self.assertEqual(prompt, target['next_build']['intent'])

    def test_graph_find_named_source_compound_hidden_paths_do_not_match_escaped_suffixes(self):
        adapter = self._named_source_adapter()
        sources = {'src/config.test.py': b'ordinary', '.ignore-rules': b'ordinary'}
        for prompt in ['../config.test.py', '/src/config.test.py', 'src/../config.test.py',
                       'https://host/src/config.test.py', 'file:src/config.test.py',
                       'C:\\src\\config.test.py', 'src//config.test.py', '../.ignore-rules',
                       'https://host/.ignore-rules', './.ignore-rules', 'folder/.ignore-rules/child',
                       'https://host/?file=src/config.test.py', 'https://host/#config.test.py',
                       'config.test.py://outside', 'https://host/?file=[config.test.py]',
                       'mailto:reader@config.test.py', 'file:?name=.ignore-rules',
                       'custom-scheme:payload#config.test.py', 'custom_scheme://host/?file=config.test.py',
                       '[config.test.py](https://host/)', '(.ignore-rules://outside)',
                       'https://host/?file=ignored,config.test.py',
                       'https://host/?name=unknown&file=config.test.py', 'config.test.py:42']:
            with self.subTest(prompt=prompt):
                p = self._named_source_payload()
                adapter._named_source_recovery(p, prompt, sources, 2)
                self.assertEqual([], p['named_source_recovery']['targets'])
                self.assertEqual([], p['recommended_fallback_paths'])

    def test_graph_find_named_source_compound_hidden_subprocess_admission_and_complete_followup(self):
        script = SKILLS_ROOT / 'graph-find' / 'scripts' / 'graph_find.py'
        files = {'src/config.test.py': b'def validate_source(value):\n    return value\n',
                 'other/config.test.py': b'def other(value):\n    return value\n',
                 '.ignore-rules': b'*.generated\ncache/\n',
                 '.settings/.projection-state.json': b'{"status":"ordinary_tracked_fixture"}\n'}
        observations = []
        with tempfile.TemporaryDirectory(prefix='graph-find-compound-hidden-') as raw:
            root = Path(raw).resolve()
            for source_path, content in files.items():
                target = root / source_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            subprocess.run(['git', 'init', '-q', str(root)], check=True, timeout=20)
            subprocess.run(['git', '-C', str(root), 'add', *files], check=True, timeout=20)
            def run_find(name, prompt, *extra):
                argv = [sys.executable, '-B', str(script), '--root', str(root), '--prompt', prompt,
                        '--byte-budget', '4096', '--deliver', *extra]
                result = subprocess.run(argv, text=True, capture_output=True, check=False, timeout=20)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                output = json.loads(result.stdout)
                observations.append({'case': name, 'argv': argv, 'process_returncode': result.returncode,
                                     'stderr': result.stderr, 'payload': output})
                return output
            named = {source_path: run_find('unique:' + source_path, 'Explain ' + source_path + ' source validation.')
                     for source_path in ['src/config.test.py', '.ignore-rules', '.settings/.projection-state.json']}
            ambiguous = run_find('ambiguous', 'Explain config.test.py source validation.')
            excluded = {source_path: run_find('excluded:' + source_path, 'Explain ' + source_path + ' source validation.',
                        '--exclude-path-prefix', prefix)
                        for source_path, prefix in [('src/config.test.py', 'src'), ('.settings/.projection-state.json', '.settings')]}
            complete = {source_path: run_find('complete:' + source_path, 'Explain ' + source_path + ' source validation.',
                                             '--follow-up-path', source_path)
                        for source_path in ['src/config.test.py', '.ignore-rules']}
            boundary = run_find('boundary', 'Explain ../config.test.py and https://outside/.ignore-rules.')
            uri_boundary = run_find('uri-boundary', 'Explain https://host/?file=config.test.py and https://host/#.ignore-rules.')
            mixed = run_find('mixed-uri-local', 'Ignore https://host/?file=config.test.py; explain .ignore-rules.')
        # Optional bounded receipt for an explicitly selected task-copy run.
        if os.environ.get('RETRIEVEL_FILENAME_RECEIPT'):
            receipt_path = Path(os.environ['RETRIEVEL_FILENAME_RECEIPT']).resolve()
            self.assertEqual(PROJECT_ROOT.parent, receipt_path.parent)
            self.assertFalse(receipt_path.exists(), 'previous fixture evidence is preserved')
            receipt_path.write_text(json.dumps({'synthetic': True, 'admitted_sources': {
                source_path: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'content': raw.decode()}
                for source_path, raw in files.items()}, 'observations': observations}, indent=2) + '\n')
        for source_path, output in named.items():
            self.assertTrue(output['named_source_recovery']['needs_recovery'])
            self.assertEqual(1, len(output['named_source_recovery']['targets']))
            target = output['named_source_recovery']['targets'][0]
            self.assertEqual([source_path], target['candidate_paths'])
            self.assertEqual(source_path, target['next_build']['scope'])
            self.assertEqual(hashlib.sha256(files[source_path]).hexdigest(), target['source_sha256'])
            self.assertEqual(0, output['delivered_total_bytes'])
            self.assertEqual(4096, output['remaining_byte_budget'])
            self.assertEqual('', output['context'])
        target = ambiguous['named_source_recovery']['targets'][0]
        self.assertEqual(2, target['candidate_count'])
        self.assertEqual('ambiguous', target['status'])
        self.assertNotIn('next_build', target)
        for output in excluded.values():
            target = output['named_source_recovery']['targets'][0]
            self.assertEqual(0, target['candidate_count'])
            self.assertNotIn('next_build', target)
            self.assertFalse(output['scan']['scan_complete'])
        for source_path, output in complete.items():
            self.assertFalse(output['named_source_recovery']['needs_recovery'])
            document = next(d for d in output['follow_up']['payload']['documents'] if d['source_path'] == source_path)
            self.assertEqual(files[source_path], document['content'].encode())
            self.assertEqual(len(files[source_path]), document['byte_count'])
            self.assertEqual(hashlib.sha256(files[source_path]).hexdigest(), document['source_sha256'])
            self.assertEqual(output['delivery_budget']['limit_bytes'], output['delivered_total_bytes'] + output['remaining_byte_budget'])
        self.assertEqual([], boundary['named_source_recovery']['targets'])
        self.assertEqual([], uri_boundary['named_source_recovery']['targets'])
        target = mixed['named_source_recovery']['targets'][0]
        self.assertEqual(1, len(mixed['named_source_recovery']['targets']))
        self.assertEqual('.ignore-rules', target['mention'])
        self.assertEqual(['.ignore-rules'], target['candidate_paths'])

    def test_graph_find_named_source_same_request_followup_reuses_only_unemitted_context(self):
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        body = ("def validate_source(value):\n" +
                "    # Ordinary source commentary retained as part of the complete witness.\n" * 40 +
                "    return value\n").encode()
        prompt = "How does validate_source work? Also provide the complete engine.py implementation."
        observations = []
        with tempfile.TemporaryDirectory(prefix="graph-find-followup-allocation-") as raw:
            root = Path(raw).resolve()
            (root / "src").mkdir()
            (root / "src/engine.py").write_bytes(body)
            (root / "other.txt").write_text("Unrelated ordinary source.\n")
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=20)
            subprocess.run(["git", "-C", str(root), "add", "src/engine.py", "other.txt"], check=True, timeout=20)

            def run_find(label, question=prompt, budget=3600, extra=()):
                argv = [sys.executable, "-B", str(script), "--root", str(root), "--prompt", question,
                        "--byte-budget", str(budget), "--deliver", *extra]
                result = subprocess.run(argv, text=True, capture_output=True, timeout=20)
                observations.append({"label": label, "argv": argv, "process_returncode": result.returncode,
                                     "stdout": result.stdout, "stderr": result.stderr})
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return json.loads(result.stdout)

            handoff = run_find("without-followup")
            recovered = run_find("starved-same-request", extra=("--follow-up-path", "src/engine.py"))
            control = run_find("full-budget-projection-control", question="Locate absent Zephyr Obelisk.",
                               extra=("--follow-up-path", "src/engine.py"))
            successful = run_find("no-gap-preserves-context", budget=32768,
                                  extra=("--follow-up-path", "src/engine.py"))
            unnamed = run_find("no-explicit-name-no-reallocation", question="How does validate_source work?",
                               extra=("--follow-up-path", "src/engine.py"))
            nofit = run_find("complete-envelope-still-does-not-fit", budget=1024,
                            extra=("--follow-up-path", "src/engine.py"))
            excluded = run_find("excluded-source-is-not-a-budget-retry",
                               extra=("--follow-up-path", "src/engine.py", "--exclude-path-prefix", "src"))
        if os.environ.get('RETRIEVEL_FOLLOWUP_RECEIPT'):
            receipt_path = Path(os.environ['RETRIEVEL_FOLLOWUP_RECEIPT']).resolve()
            self.assertEqual(PROJECT_ROOT.parent, receipt_path.parent)
            self.assertFalse(receipt_path.exists(), 'previous fixture evidence is preserved')
            receipt_path.write_text(json.dumps({'synthetic': True, 'source_path': 'src/engine.py',
                'source_bytes': len(body), 'source_sha256': hashlib.sha256(body).hexdigest(),
                'source_content': body.decode(), 'observations': observations}, indent=2) + '\n')
        self.assertGreater(handoff['ranked_context_bytes_withheld'], 0)
        self.assertEqual(3600, handoff['remaining_byte_budget'])
        self.assertEqual(0, control['delivery_budget']['graph_context_bytes'])
        self.assertEqual(body.decode(), control['follow_up']['payload']['documents'][0]['content'])
        self.assertLessEqual(control['follow_up']['envelope_bytes'], 3600)
        self.assertGreater(control['follow_up']['envelope_bytes'], 3600 - handoff['ranked_context_bytes_withheld'])
        self.assertFalse(recovered['named_source_recovery']['needs_recovery'])
        self.assertEqual('', recovered['context'])
        self.assertEqual(handoff['ranked_context_bytes_withheld'], recovered['ranked_context_bytes_withheld'])
        self.assertEqual(handoff['hits'], recovered['hits'])
        self.assertEqual(handoff['evidence'], recovered['evidence'])
        self.assertEqual(handoff['acquisition'], recovered['acquisition'])
        document = recovered['follow_up']['payload']['documents'][0]
        self.assertEqual(body.decode(), document['content'])
        self.assertEqual(hashlib.sha256(body).hexdigest(), document['source_sha256'])
        self.assertEqual(len(body), document['byte_count'])
        self.assertEqual(len(body), recovered['delivered_total_bytes'])
        self.assertEqual(3600 - len(body), recovered['remaining_byte_budget'])
        self.assertLessEqual(recovered['follow_up']['envelope_bytes'], 3600)
        self.assertEqual(control['follow_up']['source_snapshot_sha256'], recovered['follow_up']['source_snapshot_sha256'])
        self.assertEqual(successful['context_bytes'], successful['delivery_budget']['graph_context_bytes'])
        self.assertGreater(successful['context_bytes'], 0)
        self.assertNotIn('ranked_context_bytes_withheld', successful)
        self.assertFalse(successful['named_source_recovery']['needs_recovery'])
        self.assertEqual(successful['delivered_total_bytes'], len(body) + successful['context_bytes'])
        self.assertEqual([], unnamed['named_source_recovery']['targets'])
        self.assertGreater(unnamed['context_bytes'], 0)
        self.assertNotIn('ranked_context_bytes_withheld', unnamed)
        self.assertEqual('defer', unnamed['follow_up']['route'])
        self.assertEqual('defer', nofit['follow_up']['route'])
        self.assertTrue(nofit['named_source_recovery']['needs_recovery'])
        self.assertEqual(0, nofit['delivered_total_bytes'])
        self.assertEqual(1024, nofit['remaining_byte_budget'])
        self.assertEqual([], (nofit['follow_up']['payload'] or {}).get('documents', []))
        self.assertEqual('defer', excluded['follow_up']['route'])
        self.assertEqual('fallback_sources_unavailable', excluded['follow_up']['payload']['reason'])
        self.assertEqual(0, excluded['named_source_recovery']['targets'][0]['candidate_count'])
        self.assertEqual(0, excluded['delivered_total_bytes'])

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
        self.assertIn("static relative JavaScript", skill)
        self.assertIn("change-impact", skill)
        self.assertIn("incoming edge", skill)
        self.assertIn("seed ranking, evidence, fallback paths, or byte budgets", skill)

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

    def test_graph_find_ranked_context_opt_in_plans_replays_and_falls_back(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-ranked-") as raw:
            root = Path(raw)
            source = root / "src" / "evidence.py"
            source.parent.mkdir()
            source.write_text(
                "\n\n".join(
                    f"def alpha_evidence_{index}():\n"
                    f"    return '{label} alpha evidence implementation behavior {'x' * 180}'"
                    for index, label in enumerate(("first", "second", "third", "fourth"))
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "src/evidence.py"], check=True)

            def run(
                mode: str | None,
                response: Path | None = None,
                prompt: str = "find alpha evidence implementation behavior",
            ) -> dict[str, object]:
                command = [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--prompt",
                    prompt,
                    "--maximum-results",
                    "3",
                    "--byte-budget",
                    "1600",
                ]
                if mode is not None:
                    command.extend(("--ranked-context", mode))
                if response is not None:
                    command.extend(("--jev-response", str(response)))
                env = dict(os.environ)
                env.pop("TYPESAFE_API_KEY", None)
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                result = subprocess.run(
                    command, text=True, capture_output=True, check=False, env=env
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return json.loads(result.stdout)

            default = run(None)
            planned = run("plan")
            short_planned = run("plan", prompt="alpha_evidence_0")
            previewed = run("preview")
            preview = previewed["ranked_context"]["jev_preview"]
            self.assertIsNotNone(preview, previewed["ranked_context"])
            questions = preview["request"]["questions"]
            answers = {}
            for offset, name in enumerate(sorted(questions)):
                high = offset == len(questions) - 1
                answers[name] = {
                    "type": "score",
                    "probabilities": {"0": 0.0 if high else 1.0, "1": 0.0, "2": 1.0 if high else 0.0},
                    "legend": {
                        str(index): criterion
                        for index, criterion in enumerate(questions[name]["criteria"])
                    },
                    "score": 2.0 if high else 0.0,
                    "confidence": 1.0,
                }
            replay = root / "replay.json"
            replay.write_text(json.dumps({
                "schema_version": "velgraphing-jev-replay-v1",
                "request_sha256": preview["request_sha256"],
                "response": {
                    "model": preview["request"]["model"],
                    "answers": answers,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            }), encoding="utf-8")
            replayed = run("replay", replay)
            invalid = root / "invalid-replay.json"
            invalid.write_text(json.dumps({
                "schema_version": "velgraphing-jev-replay-v1",
                "request_sha256": "0" * 64,
                "response": {
                    "model": preview["request"]["model"],
                    "answers": answers,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            }), encoding="utf-8")
            fallback = run("replay", invalid)

        self.assertNotIn("ranked_context", default)
        self.assertNotIn("context", default)
        self.assertEqual("plan", planned["ranked_context"]["mode"])
        self.assertFalse(planned["ranked_context"]["network_called"])
        self.assertIsNone(planned["ranked_context"]["jev_observation"])
        self.assertGreater(planned["ranked_context"]["plan"]["candidate_count"], 1)
        short_context = short_planned["ranked_context"]["selection"]["context"]
        self.assertTrue(short_context["required_candidate_ids"])
        self.assertTrue(
            set(short_context["required_candidate_ids"]).issubset(
                short_context["selected_candidate_ids"]
            )
        )
        self.assertFalse(previewed["ranked_context"]["network_called"])
        self.assertEqual("reranked", replayed["ranked_context"]["jev_observation"]["status"])
        self.assertEqual("replay", replayed["ranked_context"]["jev_observation"]["execution"])
        self.assertFalse(replayed["ranked_context"]["network_called"])
        self.assertEqual("reranked", replayed["ranked_context"]["selection"]["order_source"])
        self.assertTrue(
            replayed["ranked_context"]["selection"]["jev_decision"]["jev_observation_applied"]
        )
        self.assertEqual("fallback", fallback["ranked_context"]["jev_observation"]["status"])
        self.assertEqual("replay_request_mismatch", fallback["ranked_context"]["jev_observation"]["reason"])
        self.assertEqual("baseline", fallback["ranked_context"]["selection"]["order_source"])
        self.assertFalse(
            fallback["ranked_context"]["selection"]["jev_decision"]["jev_observation_applied"]
        )

    def test_graph_find_delivery_includes_verified_text_and_bounded_follow_up(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        source_text = "def refresh_token(token):\n    return token + '-current'\n"
        source_bytes = source_text.encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="graph-find-delivery-") as raw:
            root = Path(raw)
            source = root / "src" / "auth.py"
            source.parent.mkdir()
            source.write_bytes(source_bytes)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "src/auth.py"], check=True)

            def run_find(*extra: str, prompt: str) -> dict[str, object]:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--root",
                        str(root),
                        "--prompt",
                        prompt,
                        *extra,
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return json.loads(result.stdout)

            delivered = run_find("--deliver", prompt="find refresh_token")
            recovered = run_find(
                "--follow-up-path",
                "src/auth.py",
                prompt="Find the nonexistent Zephyr Obelisk florfle cleanup handler.",
            )
            combined = run_find(
                "--deliver",
                "--follow-up-path",
                "src/auth.py",
                "--byte-budget",
                "4096",
                prompt="find refresh_token",
            )
            exhausted = run_find(
                "--deliver",
                "--follow-up-path",
                "src/auth.py",
                "--byte-budget",
                "80",
                prompt="find refresh_token",
            )

        self.assertEqual("graph", delivered["route"])
        self.assertIn("def refresh_token(token):", delivered["context"])
        self.assertEqual(len(delivered["context"].encode("utf-8")), delivered["delivered_context_bytes"])
        self.assertEqual(delivered["scan"]["source_bytes_read"], delivered["acquisition"]["source_bytes_read"])
        self.assertEqual(delivered["scan"]["source_bytes"], delivered["acquisition"]["source_bytes_in_snapshot"])
        evidence = next(item for item in delivered["evidence"] if item["source_path"] == "src/auth.py")
        excerpt = source_bytes[evidence["byte_start"] : evidence["byte_end"]]
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), evidence["source_sha256"])
        self.assertEqual(hashlib.sha256(excerpt).hexdigest(), evidence["excerpt_sha256"])
        self.assertIn(excerpt.decode("utf-8"), delivered["context"])
        self.assertEqual("defer", recovered["route"])
        self.assertEqual("direct", recovered["follow_up"]["route"])
        document = recovered["follow_up"]["payload"]["documents"][0]
        self.assertEqual(source_text, document["content"])
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), document["source_sha256"])
        delivery_budget = combined["delivery_budget"]
        self.assertEqual(4096, delivery_budget["limit_bytes"])
        self.assertEqual(combined["delivered_context_bytes"], delivery_budget["graph_context_bytes"])
        self.assertEqual(document["byte_count"], combined["follow_up"]["source_bytes"])
        self.assertLessEqual(combined["follow_up"]["envelope_bytes"], 4096 - delivery_budget["graph_context_bytes"])
        self.assertLessEqual(combined["follow_up"]["source_bytes"], combined["follow_up"]["envelope_bytes"])
        self.assertEqual(
            delivery_budget["graph_context_bytes"] + combined["follow_up"]["source_bytes"],
            combined["delivered_total_bytes"],
        )
        self.assertEqual(combined["delivered_total_bytes"], delivery_budget["delivered_content_bytes"])
        self.assertEqual(4096 - combined["delivered_total_bytes"], combined["remaining_byte_budget"])
        self.assertLessEqual(combined["delivered_total_bytes"], 4096)
        self.assertEqual("graph", exhausted["route"])
        self.assertEqual("shared_delivery_budget_exhausted", exhausted["follow_up"]["reason"])
        self.assertIsNone(exhausted["follow_up"]["payload"])
        self.assertEqual(exhausted["delivered_context_bytes"], exhausted["delivered_total_bytes"])
        self.assertEqual(80 - exhausted["delivered_total_bytes"], exhausted["remaining_byte_budget"])

    def test_graph_find_follow_up_defers_for_excluded_and_over_budget_sources(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-follow-up-limits-") as raw:
            root = Path(raw)
            (root / "public.py").write_text("def public_item():\n    return 1\n", encoding="utf-8")
            (root / "large.txt").write_text("x" * 40000, encoding="utf-8")
            (root / ".env").write_text("private_value=must_not_escape\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)

            def run_follow_up(path: str, *extra: str) -> tuple[dict[str, object], str]:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--root",
                        str(root),
                        "--prompt",
                        "find absent Zephyr Obelisk",
                        "--follow-up-path",
                        path,
                        *extra,
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return json.loads(result.stdout), result.stdout

            excluded, excluded_output = run_follow_up(".env")
            over_budget, over_budget_output = run_follow_up("large.txt")

        self.assertEqual("defer", excluded["follow_up"]["route"])
        self.assertEqual("fallback_sources_unavailable", excluded["follow_up"]["payload"]["reason"])
        self.assertNotIn("must_not_escape", excluded_output)
        self.assertNotIn('"source_path":".env"', excluded_output)
        self.assertEqual("defer", over_budget["follow_up"]["route"])
        self.assertEqual("fallback_context_exceeds_byte_budget", over_budget["follow_up"]["payload"]["reason"])
        self.assertEqual([], over_budget["follow_up"]["payload"]["documents"])
        self.assertNotIn("x" * 128, over_budget_output)

    def test_graph_find_source_prefix_exclusion_applies_to_delivery_and_follow_up(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        allowed = b"def other_current_item():\n    return 'current'\n"
        excluded = b"def cache_control_new():\n    return 'historical_answer_must_not_escape'\n"
        sibling = b"def cache_control_new():\n    return 'allowed sibling'\n"
        with tempfile.TemporaryDirectory(prefix="graph-find-scope-") as raw:
            root = Path(raw)
            (root / "src").mkdir()
            (root / "benchmarks" / "responses").mkdir(parents=True)
            (root / "benchmarks" / "responses-old").mkdir()
            (root / "src" / "cache.py").write_bytes(allowed)
            (root / "benchmarks" / "responses" / "answer.py").write_bytes(excluded)
            (root / "benchmarks" / "responses-old" / "current.py").write_bytes(sibling)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--prompt",
                    "find cache_control_new",
                    "--deliver",
                    "--exclude-path-prefix",
                    "benchmarks/responses",
                    "--follow-up-path",
                    "benchmarks/responses/answer.py",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("defer", payload["route"])
        self.assertEqual("source_scope_excluded", payload["reason"])
        self.assertEqual("graph", payload["retrieval_route"])
        self.assertEqual("verified_tag_context_selected", payload["retrieval_reason"])
        self.assertIn("def cache_control_new():", payload["context"])
        self.assertTrue(payload["evidence"])
        self.assertEqual(["benchmarks/responses"], payload["scan"]["excluded_path_prefixes"])
        self.assertEqual(1, payload["scan"]["path_scope_excluded"])
        self.assertEqual(len(allowed) + len(sibling), payload["acquisition"]["source_bytes_read"])
        self.assertEqual(len(allowed) + len(sibling), payload["acquisition"]["source_bytes_in_snapshot"])
        self.assertNotIn("historical_answer_must_not_escape", result.stdout)
        self.assertEqual("defer", payload["follow_up"]["route"])
        self.assertEqual("fallback_sources_unavailable", payload["follow_up"]["payload"]["reason"])

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
            (root / "src" / "caller.js").write_text(
                "import { render } from './view.js';\nrender();\n", encoding="utf-8"
            )
            (root / "src" / "view.js").write_text(
                "export function render() { return 'view'; }\n", encoding="utf-8"
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
                    "find call_helper render install guide",
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
        self.assertEqual(payload["scan"]["edges_derived"], 3)
        self.assertEqual(
            payload["scan"]["relation_coverage"],
            [
                {
                    "relation": "imports",
                    "supported": "javascript_tree_sitter_static_relative_named_direct_export",
                    "resolved": 1,
                    "unresolved": 0,
                    "unsupported": 0,
                },
                {
                    "relation": "imports",
                    "supported": "python_ast_from_import_named_top_level_declaration",
                    "resolved": 1,
                    "unresolved": 0,
                    "unsupported": 0,
                },
                {
                    "relation": "links_to_heading",
                    "supported": "markdown_relative_path_fragment_unique_atx_heading",
                    "resolved": 1,
                    "unresolved": 0,
                    "unsupported": 0,
                },
            ],
        )
        self.assertTrue(all(item["source_coordinate"]["schema_version"] == "source-coordinate-v1" for item in supports))
        self.assertNotIn("return helper()", result.stdout)

    def test_graph_find_change_impact_exposes_incoming_support(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-impact-") as raw:
            root = Path(raw)
            (root / "src").mkdir()
            (root / "src" / "z_caller.py").write_text(
                "from src.a_target import helper\n\ndef invoke():\n    return helper()\n",
                encoding="utf-8",
            )
            (root / "src" / "a_target.py").write_text(
                "def helper():\n    value = 0\n"
                + "    value += 1\n" * 300
                + "    return value\n",
                encoding="utf-8",
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
                    "what changes if helper changes",
                    "--maximum-results",
                    "1",
                    "--ranked-context",
                    "plan",
                ],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        incoming = [
            item for item in payload["relationship_supports"]
            if item["direction"] == "incoming"
        ]
        self.assertEqual(1, len(incoming))
        self.assertEqual("src/a_target.py", incoming[0]["seed_coordinate"]["source_path"])
        self.assertEqual("src/z_caller.py", incoming[0]["related_coordinate"]["source_path"])
        self.assertEqual("helper", incoming[0]["seed_coordinate"]["symbol"])
        ranked = payload["ranked_context"]
        self.assertEqual("graph", ranked["plan"]["route"])
        spans = ranked["selection"]["context"]["spans"]
        self.assertTrue(any(item["relationship_parent_candidate_id"] for item in spans))

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
        self.assertEqual(
            [(item["supported"], item["resolved"], item["unresolved"], item["unsupported"])
             for item in payload["scan"]["relation_coverage"]],
            [
                ("javascript_tree_sitter_static_relative_named_direct_export", 0, 0, 0),
                ("python_ast_from_import_named_top_level_declaration", 0, 1, 0),
                ("markdown_relative_path_fragment_unique_atx_heading", 0, 1, 0),
            ],
        )

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
        self.assertEqual(
            [(item["supported"], item["resolved"], item["unresolved"], item["unsupported"])
             for item in payload["scan"]["relation_coverage"]],
            [
                ("javascript_tree_sitter_static_relative_named_direct_export", 0, 0, 0),
                ("python_ast_from_import_named_top_level_declaration", 0, 1, 2),
                ("markdown_relative_path_fragment_unique_atx_heading", 0, 1, 4),
            ],
        )

    def test_graph_find_ignores_headings_inside_markdown_fences(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-fences-") as raw:
            root = Path(raw)
            (root / "docs").mkdir()
            (root / "README.md").write_text(
                "# Index\n"
                "[real](docs/guide.md#real)\n"
                "[backtick](docs/guide.md#backtick-fake)\n"
                "[tilde](docs/guide.md#tilde-fake)\n"
                "[unclosed](docs/guide.md#unclosed-fake)\n",
                encoding="utf-8",
            )
            (root / "docs" / "guide.md").write_text(
                "```python\n# Backtick fake\n````\n"
                "# Real\n"
                "~~~~ text\n# Tilde fake\n~~~~~\n"
                "```\n# Unclosed fake\n",
                encoding="utf-8",
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
                    "find README Index real backtick tilde unclosed guide",
                ],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scan"]["edges_derived"], 1)
        self.assertEqual(
            {item["target_coordinate"]["symbol"] for item in payload["relationship_supports"]},
            {"real"},
        )

    def test_graph_find_resolves_only_package_valid_relative_imports(self) -> None:
        script = SKILLS_ROOT / "graph-find" / "scripts" / "graph_find.py"
        with tempfile.TemporaryDirectory(prefix="graph-find-relative-imports-") as raw:
            root = Path(raw)
            (root / "pkg" / "deep").mkdir(parents=True)
            (root / "root.py").write_text("from .helper import root_f\n", encoding="utf-8")
            (root / "helper.py").write_text(
                "def root_f():\n    pass\n\ndef escaped_f():\n    pass\n", encoding="utf-8"
            )
            (root / "pkg" / "mod.py").write_text(
                "from ..helper import escaped_f\n", encoding="utf-8"
            )
            (root / "pkg" / "valid.py").write_text(
                "from .helper import sibling_f\n", encoding="utf-8"
            )
            (root / "pkg" / "deep" / "mod.py").write_text(
                "from ..helper import parent_f\n", encoding="utf-8"
            )
            (root / "pkg" / "helper.py").write_text(
                "def sibling_f():\n    pass\n\ndef parent_f():\n    pass\n", encoding="utf-8"
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
                    "find root_f escaped_f sibling_f parent_f",
                    "--maximum-results",
                    "8",
                ],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scan"]["edges_derived"], 2)
        self.assertEqual(
            {item["source_coordinate"]["source_path"] for item in payload["relationship_supports"]},
            {"pkg/deep/mod.py", "pkg/valid.py"},
        )

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
            usable_bytes = b"def refresh_token():\n    return 'ok'\n"
            invalid_bytes = b"\xff\xfe\x00"
            (root / "usable.py").write_bytes(usable_bytes)
            (root / "binary.bin").write_bytes(invalid_bytes)
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
                    "--deliver",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual({"invalid_utf8": 1}, payload["scan"]["skip_counts"])
        self.assertEqual("binary.bin", payload["scan"]["files_skipped"][0]["path"])
        self.assertEqual(
            len(usable_bytes) + len(invalid_bytes),
            payload["acquisition"]["source_bytes_read"],
        )
        self.assertEqual(len(usable_bytes), payload["acquisition"]["source_bytes_in_snapshot"])

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
                    "--ranked-context",
                    "plan",
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
        self.assertEqual("defer", payload["ranked_context"]["route"])
        self.assertTrue(payload["ranked_context"]["fail_closed"])
        self.assertEqual("sensitive_paths_excluded", payload["ranked_context"]["reason"])
        self.assertIsNone(payload["ranked_context"]["selection"])
        for name in sensitive_names:
            self.assertNotIn(name, result.stdout)
        self.assertNotIn("refresh_token=secret", result.stdout)

    def test_graph_find_does_not_claim_evidence_completeness_after_budget_omission(self) -> None:
        source_path = "src/markers.py"
        record_id = f"repo:{source_path}"
        raw = (
            b"def alpha_marker():\n    return 1\n"
            + b"# distant source content\n" * 60
            + b"def omega_marker():\n    return 2\n"
        )
        first_start = raw.index(b"alpha_marker")
        second_start = raw.index(b"omega_marker")
        tags = (
            RepositoryTag(
                TagKind.SYMBOL,
                "alpha_marker",
                record_id,
                source_path,
                first_start,
                first_start + len(b"alpha_marker"),
            ),
            RepositoryTag(
                TagKind.SYMBOL,
                "omega_marker",
                record_id,
                source_path,
                second_start,
                second_start + len(b"omega_marker"),
            ),
        )
        hit = RetrievalHit(record_id, source_path, 100, ("exact",), ("alpha", "omega"), 0)
        source_sha256 = hashlib.sha256(raw).hexdigest()
        first_end = raw.index(b"\n")
        byte_budget = len(f"[{source_path}:0-{first_end}]\n".encode()) + first_end
        spans, evidence, context = _verified_spans(
            (hit,),
            {record_id: tags},
            {record_id: {"alpha_marker", "omega_marker"}},
            {},
            {},
            {},
            {source_path: raw},
            {source_path: source_sha256},
            byte_budget,
        )

        self.assertEqual(1, len(spans))
        self.assertEqual(1, len(evidence))
        self.assertIn("alpha_marker", context)
        self.assertNotIn("omega_marker", context)
        result = GraphFindResult(
            route="graph",
            reason="verified_tag_context_selected",
            hits=(hit,),
            evidence=evidence,
            source_snapshot_sha256=source_sha256,
            context_bytes=len(context.encode("utf-8")),
            facet_coverage_percent=100.0,
            recommended_fallback_paths=(),
            fail_closed=False,
            _context=context,
        ).to_delivery_dict()
        self.assertEqual("not_assessed", result["omissions"]["completeness_assessment"])
        self.assertNotIn("complete", result["omissions"])

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
