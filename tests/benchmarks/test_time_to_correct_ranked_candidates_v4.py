"""Oracle-blind tests for the v4 ranked-candidate generator."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ranked_candidates_v4",
    ROOT / "scripts/benchmarks/time_to_correct_ranked_candidates_v4.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class Fixture:
    def __init__(
        self,
        sources: dict[str, bytes],
        prompt: str,
        *,
        corpus: str = "cpython",
    ) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary.name)
        self.lanes = self.root / "lanes"
        self.lane = self.lanes / corpus
        self.lane.mkdir(parents=True)
        git(self.lane, "init", "-q")
        git(self.lane, "config", "user.email", "test@example.invalid")
        git(self.lane, "config", "user.name", "VelGraphing Test")
        for path, raw in sources.items():
            target = self.lane.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        git(self.lane, "add", ".")
        git(self.lane, "commit", "-q", "-m", "fixture")
        self.commit = git(self.lane, "rev-parse", "HEAD")
        source_rows = [
            {"path": path, "byte_length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for path, raw in sorted(sources.items())
        ]
        self.manifest = {
            "schema_version": "velgraphing-corpus-source-manifest-v1",
            "repository": "git-object-source",
            "commit": self.commit,
            "includes": ["**"],
            "excludes": [],
            "sources": source_rows,
            "source_count": len(source_rows),
            "source_bytes": sum(row["byte_length"] for row in source_rows),
            "snapshot_sha256": mod._snapshot_digest(source_rows),
            "skipped": {},
        }
        self.manifests = self.root / "manifests"
        self.manifests.mkdir()
        (self.manifests / mod.CORPUS_MANIFESTS[corpus]).write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        self.questions = self.root / "questions.json"
        self.questions.write_text(
            json.dumps(
                {
                    "schema_version": "velgraphing-corpus-pilot-questions-v1",
                    "questions": [{"id": "fixture", "corpus": corpus, "prompt": prompt}],
                }
            ),
            encoding="utf-8",
        )

    def close(self) -> None:
        self.temporary.cleanup()


class RankedCandidateTests(unittest.TestCase):
    def test_registered_study_controls_and_canary_registry_are_exact(self) -> None:
        questions_path = (
            ROOT
            / "benchmarks/velgraphing-time-to-correct-v4/relational-canary-questions.json"
        )
        rows, registry_sha256 = mod._questions(questions_path)
        self.assertEqual(
            mod.STUDY_CANDIDATE_CONTROLS[mod.HIGH_RECALL_STUDY],
            (64, 32_768, 4096),
        )
        self.assertEqual(
            registry_sha256,
            mod.candidate_evaluator.RELATIONAL_CANARY_QUESTION_REGISTRY_SHA256,
        )
        self.assertEqual(
            rows,
            [{
                "id": "R-01",
                "corpus": "engineering-handbook",
                "prompt": "What belongs in content/dsa/editorials versus content/dsa/patterns?",
            }],
        )

        import_questions = (
            ROOT
            / "benchmarks/velgraphing-time-to-correct-v4/thealgorithms-import-canary-questions.json"
        )
        import_rows, import_registry_sha256 = mod._questions(import_questions)
        self.assertEqual(
            mod.STUDY_CANDIDATE_CONTROLS[mod.THEALGORITHMS_IMPORT_CANARY_STUDY],
            (64, 32_768, 4096),
        )
        self.assertEqual(
            import_registry_sha256,
            mod.candidate_evaluator.THEALGORITHMS_IMPORT_CANARY_QUESTION_REGISTRY_SHA256,
        )
        self.assertEqual(
            import_rows,
            [{
                "id": "I-01",
                "corpus": "thealgorithms-python",
                "prompt": "How does the benchmark_sorts module prepare timing cases?",
            }],
        )
        self.assertNotIn("quick_sort", import_rows[0]["prompt"])

        dependency_questions = (
            ROOT
            / "benchmarks/velgraphing-time-to-correct-v4/thealgorithms-dependency-behavior-canary-questions.json"
        )
        dependency_rows, dependency_registry_sha256 = mod._questions(
            dependency_questions
        )
        self.assertEqual(
            mod.STUDY_CANDIDATE_CONTROLS[
                mod.THEALGORITHMS_DEPENDENCY_BEHAVIOR_CANARY_STUDY
            ],
            (64, 32_768, 4096),
        )
        self.assertEqual(
            dependency_registry_sha256,
            mod.candidate_evaluator.THEALGORITHMS_DEPENDENCY_BEHAVIOR_CANARY_QUESTION_REGISTRY_SHA256,
        )
        self.assertEqual(
            dependency_rows,
            [{
                "id": "D-01",
                "corpus": "thealgorithms-python",
                "prompt": (
                    "In sorts/benchmark_sorts.py, follow the imported dependency "
                    "immediately after merge_sort and explain how that target "
                    "implementation orders values, including duplicate handling."
                ),
            }],
        )
        self.assertNotIn("quick_sort", dependency_rows[0]["prompt"])

    def test_relational_canary_prompt_isolated_by_typed_expansion(self) -> None:
        sources = {
            f"noise-{index:02d}.md": (
                b"# DSA editorial patterns\ncontent dsa editorials patterns\n"
            )
            for index in range(12)
        }
        sources.update(
            {
                "README.md": (
                    b"# Repository areas\n"
                    b"What belongs in content/dsa/editorials versus content/dsa/patterns?\n"
                    b"[Style details](STYLE_GUIDE.md#dsa-specific-deviations)\n"
                ),
                "STYLE_GUIDE.md": (
                    b"# Style guide\n\n"
                    b"## DSA-specific deviations\n"
                    b"Use the documented chapter structure.\n"
                ),
            }
        )
        fixture = Fixture(
            sources,
            "What belongs in content/dsa/editorials versus content/dsa/patterns?",
            corpus="engineering-handbook",
        )
        try:
            artifact, _ = mod.generate(
                fixture.questions, fixture.manifests, fixture.lanes, "1" * 40,
                study_id="unit-fixture",
            )
        finally:
            fixture.close()
        runs = {run["route"]: run for run in artifact["runs"]}
        control = runs["direct"]["candidates"]
        self.assertEqual(runs["tag_index"]["candidates"], control)
        self.assertEqual(runs["typed_graph_no_edges"]["candidates"], control)
        self.assertEqual(runs["typed_graph_no_expansion"]["candidates"], control)
        relationships = [
            candidate for candidate in runs["typed_graph"]["candidates"]
            if candidate["relationship_parent_candidate_id"] is not None
        ]
        self.assertEqual(len(relationships), 1)
        typed_primary = [
            candidate for candidate in runs["typed_graph"]["candidates"]
            if candidate["relationship_parent_candidate_id"] is None
        ]
        self.assertEqual(typed_primary, control[:len(typed_primary)])

    def test_typed_routes_keep_primary_seeds_and_only_enabled_adds_support(self) -> None:
        fixture = Fixture(
            {
                "src/caller.py": (
                    b"from src.helper import helper as call_dependency_import\n\n"
                    b"def call_helper():\n    return call_helper_import()\n"
                ),
                "src/helper.py": b"def helper():\n    return 1\n",
                "README.md": b"# Index\n[install guide](docs/guide.md#install)\n",
                "docs/guide.md": b"# Install\nUse call_helper.\n",
            },
            "find call_dependency_import caller Index README",
        )
        try:
            artifact, _ = mod.generate(
                fixture.questions, fixture.manifests, fixture.lanes, "1" * 40,
                study_id="unit-fixture",
            )
            graph, _, _, _ = mod.scan_lane(
                fixture.lane, fixture.manifest, derive_edges=True
            )
            records = graph.record_map()
        finally:
            fixture.close()
        runs = {run["route"]: run for run in artifact["runs"]}
        typed = runs["typed_graph"]
        no_edges = runs["typed_graph_no_edges"]
        no_expansion = runs["typed_graph_no_expansion"]
        self.assertEqual(
            typed["controls"]["seed_record_ids"], no_edges["controls"]["seed_record_ids"]
        )
        self.assertEqual(
            typed["controls"]["seed_record_ids"], no_expansion["controls"]["seed_record_ids"]
        )
        self.assertEqual(
            typed["controls"]["active_edge_count"],
            typed["controls"]["derived_edge_count"],
        )
        self.assertEqual(no_edges["controls"]["active_edge_count"], 0)
        self.assertEqual(
            no_expansion["controls"]["active_edge_count"],
            no_expansion["controls"]["derived_edge_count"],
        )
        self.assertEqual(no_edges["candidates"], no_expansion["candidates"])
        self.assertEqual(runs["direct"]["candidates"], runs["tag_index"]["candidates"])
        self.assertEqual(runs["direct"]["candidates"], no_edges["candidates"])
        candidate_budgets = {
            (
                run["controls"]["candidate_limit"],
                run["controls"]["candidate_aggregate_byte_budget"],
                run["controls"]["candidate_unit_byte_budget"],
            )
            for run in runs.values()
        }
        self.assertEqual(candidate_budgets, {(12, 24_576, 4096)})
        primary_ids = {item["id"] for item in no_expansion["candidates"]}
        typed_primary = [item for item in typed["candidates"] if item["id"] in primary_ids]
        self.assertEqual(typed_primary, no_expansion["candidates"][: len(typed_primary)])
        self.assertGreater(len(typed["candidates"]), len(typed_primary))
        positions = {item["id"]: index for index, item in enumerate(typed["candidates"])}
        relationships = [
            item for item in typed["candidates"]
            if item["relationship_parent_candidate_id"] is not None
        ]
        self.assertTrue(relationships)
        helper_support = next(
            item for item in relationships if item["path"] == "src/helper.py"
        )
        helper_raw = records[helper_support["record_id"]].content.encode("utf-8")
        self.assertEqual(
            helper_raw[helper_support["byte_start"]:helper_support["byte_end"]],
            helper_raw,
        )
        for item in typed["candidates"]:
            self.assertEqual(len(item["id"]), 64)
            self.assertFalse(set(item["id"]) - set("0123456789abcdef"))
            self.assertEqual(item["record_id"], f"repo:{item['path']}")
            record = records[item["record_id"]]
            self.assertEqual(record.provenance.path, item["path"])
            self.assertEqual(record.provenance.sha256, item["source_sha256"])
            parent = item["relationship_parent_candidate_id"]
            if parent is not None:
                self.assertFalse(item["required"])
                self.assertLess(positions[parent], positions[item["id"]])
                self.assertIsNone(
                    typed["candidates"][positions[parent]][
                        "relationship_parent_candidate_id"
                    ]
                )
        for route in ("direct", "tag_index", "typed_graph_no_edges", "typed_graph_no_expansion"):
            self.assertTrue(all(
                item["relationship_parent_candidate_id"] is None
                for item in runs[route]["candidates"]
            ))
        before = hashlib.sha256(mod._canonical(artifact)).hexdigest()
        changed = copy.deepcopy(artifact)
        changed["runs"][0]["candidates"][0]["record_id"] = "repo:changed"
        self.assertNotEqual(before, hashlib.sha256(mod._canonical(changed)).hexdigest())
        encoded = json.dumps(artifact, sort_keys=True)
        for forbidden in ("return helper()", "Use call_helper.", "acceptable_spans", "critical_facts"):
            self.assertNotIn(forbidden, encoded)

    def test_zero_edge_fixture_keeps_all_typed_candidates_identical(self) -> None:
        fixture = Fixture(
            {"README.md": b"# Alpha\nplain alpha evidence\n", "notes.md": b"# Beta\nplain beta evidence\n"},
            "find alpha beta evidence",
        )
        try:
            artifact, _ = mod.generate(
                fixture.questions, fixture.manifests, fixture.lanes, "1" * 40,
                study_id="unit-fixture",
            )
        finally:
            fixture.close()
        runs = {run["route"]: run for run in artifact["runs"]}
        candidates = [
            runs[route]["candidates"]
            for route in ("typed_graph", "typed_graph_no_edges", "typed_graph_no_expansion")
        ]
        self.assertEqual(candidates[0], candidates[1])
        self.assertEqual(candidates[0], candidates[2])
        self.assertEqual(runs["typed_graph"]["controls"]["derived_edge_count"], 0)
        self.assertEqual(runs["typed_graph"]["controls"]["active_edge_count"], 0)

    def test_question_registry_and_run_bindings_are_frozen_without_prompt_text(self) -> None:
        fixture = Fixture({"source.py": b"alpha evidence\n"}, "find alpha")
        try:
            artifact, _ = mod.generate(
                fixture.questions, fixture.manifests, fixture.lanes, "1" * 40,
                study_id="unit-fixture",
            )
            questions = json.loads(fixture.questions.read_text(encoding="utf-8"))
        finally:
            fixture.close()
        self.assertEqual(
            artifact["question_registry_sha256"],
            hashlib.sha256(mod._canonical(questions)).hexdigest(),
        )
        for run in artifact["runs"]:
            self.assertEqual(run["corpus"], "cpython")
            self.assertEqual(
                run["prompt_sha256"], hashlib.sha256(b"find alpha").hexdigest()
            )
        self.assertNotIn("find alpha", json.dumps(artifact))

    def test_direct_and_graph_controls_share_complete_unit_candidates(self) -> None:
        fixture = Fixture(
            {
                "sorts/quick_sort.py": (
                    b'"""Quick sort examples."""\n\n'
                    b"def quick_sort(values):\n"
                    b"    if len(values) < 2:\n        return values\n"
                    b"    return quick_sort(values[:-1]) + [values[-1]]\n"
                )
            },
            "find quick_sort implementation",
        )
        try:
            artifact, _ = mod.generate(
                fixture.questions, fixture.manifests, fixture.lanes, "1" * 40,
                study_id="unit-fixture",
            )
            raw = fixture.lane.joinpath("sorts/quick_sort.py").read_bytes()
        finally:
            fixture.close()
        runs = {run["route"]: run for run in artifact["runs"]}
        self.assertEqual(runs["direct"]["candidates"], runs["tag_index"]["candidates"])
        candidate = runs["direct"]["candidates"][0]
        excerpt = raw[candidate["byte_start"]:candidate["byte_end"]]
        self.assertTrue(excerpt.startswith(b"def quick_sort"))
        self.assertIn(b"return quick_sort", excerpt)
        self.assertLessEqual(len(excerpt), 4096)

    def test_manifest_source_range_and_utf8_fail_closed(self) -> None:
        fixture = Fixture({"source.py": b"value = '\xc3\xa9'\n"}, "find value")
        try:
            manifest = copy.deepcopy(fixture.manifest)
            manifest["commit"] = "0" * 40
            with self.assertRaisesRegex(mod.GenerationError, "lane_commit_mismatch"):
                mod.scan_lane(fixture.lane, manifest, derive_edges=False)

            manifest = copy.deepcopy(fixture.manifest)
            manifest["sources"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(mod.GenerationError, "lane_source_identity_mismatch"):
                mod.scan_lane(fixture.lane, manifest, derive_edges=False)

            manifest = copy.deepcopy(fixture.manifest)
            manifest["sources"].append(
                {"path": "missing.py", "byte_length": 1, "sha256": "0" * 64}
            )
            with self.assertRaisesRegex(mod.GenerationError, "lane_path_set_mismatch"):
                mod.scan_lane(fixture.lane, manifest, derive_edges=False)

            malformed = copy.deepcopy(fixture.manifest)
            malformed["source_bytes"] += 1
            malformed_path = fixture.manifests / "malformed.json"
            malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaisesRegex(mod.GenerationError, "manifest_totals_mismatch"):
                mod._manifest(malformed_path)

        finally:
            fixture.close()

    def test_output_is_canonical_regular_and_confined(self) -> None:
        artifact = {
            "schema_version": mod.SCHEMA_VERSION,
            "study_id": "unit-fixture",
            "selector_commit": "1" * 40,
            "runs": [],
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            output_root = Path(raw).resolve()
            output = output_root / "candidates.json"
            with mock.patch.object(mod, "OUTPUT_ROOT", output_root), mock.patch.object(
                mod.subprocess, "run", return_value=mock.Mock(returncode=0)
            ):
                self.assertEqual(mod._output_path(output), output)
                for invalid in (
                    output_root / ".." / "escape.json",
                    output_root / "nested" / "candidate.json",
                    ROOT / "outside.json",
                ):
                    with self.assertRaisesRegex(mod.GenerationError, "invalid_output_path"):
                        mod._output_path(invalid)
                digest, size = mod.write_artifact(output, artifact)
                self.assertEqual(digest, hashlib.sha256(output.read_bytes()).hexdigest())
                self.assertEqual(size, len(output.read_bytes()))
                self.assertEqual(output.read_bytes(), mod._canonical(artifact))
                self.assertTrue(output.is_file())
                with self.assertRaises(FileExistsError):
                    mod.write_artifact(output, artifact)
                with self.assertRaisesRegex(mod.GenerationError, "output_exists"):
                    mod._output_path(output)

    def test_output_root_bootstraps_once_and_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            parent = Path(raw).resolve() / "benchmark"
            parent.mkdir()
            output_root = parent / ".inputs"
            output = output_root / "first.json"
            accepted = mock.Mock(returncode=0)
            with mock.patch.object(mod, "OUTPUT_ROOT", output_root), mock.patch.object(
                mod.subprocess, "run", return_value=accepted
            ):
                self.assertFalse(output_root.exists())
                self.assertEqual(mod._output_path(output), output)
                self.assertTrue(output_root.is_dir())

                output_root.rmdir()
                target = parent / "redirected"
                target.mkdir()
                output_root.symlink_to(target, target_is_directory=True)
                with self.assertRaisesRegex(mod.GenerationError, "invalid_output_root"):
                    mod._output_path(output)


if __name__ == "__main__":
    unittest.main()
