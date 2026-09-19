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
    def __init__(self, sources: dict[str, bytes], prompt: str) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary.name)
        self.lanes = self.root / "lanes"
        self.lane = self.lanes / "cpython"
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
        (self.manifests / "cpython.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        self.questions = self.root / "questions.json"
        self.questions.write_text(
            json.dumps(
                {
                    "schema_version": "velgraphing-corpus-pilot-questions-v1",
                    "questions": [{"id": "fixture", "corpus": "cpython", "prompt": prompt}],
                }
            ),
            encoding="utf-8",
        )

    def close(self) -> None:
        self.temporary.cleanup()


class RankedCandidateTests(unittest.TestCase):
    def test_typed_routes_keep_primary_seeds_and_only_enabled_adds_support(self) -> None:
        fixture = Fixture(
            {
                "src/caller.py": b"from src.helper import helper\n\ndef call_helper():\n    return helper()\n",
                "src/helper.py": b"def helper():\n    return 1\n",
                "README.md": b"# Index\n[install guide](docs/guide.md#install)\n",
                "docs/guide.md": b"# Install\nUse call_helper.\n",
            },
            "find call_helper caller Index README",
        )
        try:
            artifact, _ = mod.generate(
                fixture.questions, fixture.manifests, fixture.lanes, "1" * 40,
                study_id="unit-fixture",
            )
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
        self.assertEqual(no_edges["candidates"], no_expansion["candidates"])
        primary_ids = {item["id"] for item in no_expansion["candidates"]}
        typed_primary = [item for item in typed["candidates"] if item["id"] in primary_ids]
        self.assertEqual(typed_primary, no_expansion["candidates"][: len(typed_primary)])
        self.assertGreater(len(typed["candidates"]), len(typed_primary))
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

    def test_optional_overflow_is_skipped_and_seeded_support_precedes_later_primary(self) -> None:
        def row(identity: str, start: int, end: int) -> dict[str, object]:
            return {
                "id": identity, "path": "source.py", "source_sha256": "a" * 64,
                "byte_start": start, "byte_end": end, "required": False,
            }

        overflow_rows = [
            (row("large", 0, 24_575), "seed:0"),
            (row("overflow", 0, 2), "seed:1"),
            (row("fits", 0, 1), "seed:2"),
        ]
        retained, _ = mod._retain(overflow_rows)
        self.assertEqual([item["id"] for item in retained], ["large", "fits"])

        primary = [(row(f"p{index}", index, index + 1), f"seed:{index}") for index in range(13)]
        retained, support_count = mod._retain_with_supports(
            primary, {"seed:0": row("support", 20, 21)}
        )
        self.assertEqual(support_count, 1)
        self.assertEqual([item["id"] for item in retained[:3]], ["p0", "support", "p1"])
        typed_primary = [item["id"] for item in retained if item["id"].startswith("p")]
        self.assertEqual(typed_primary, [f"p{index}" for index in range(11)])

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

            raw = fixture.lane.joinpath("source.py").read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(mod.GenerationError, "candidate_range_invalid"):
                mod._candidate("source.py", digest, 0, len(raw) + 1, {"source.py": raw})
            position = raw.index(b"\xc3\xa9")
            with self.assertRaisesRegex(mod.GenerationError, "candidate_utf8_invalid"):
                mod._candidate("source.py", digest, position + 1, position + 2, {"source.py": raw})
        finally:
            fixture.close()

    def test_output_is_canonical_and_refuses_overwrite(self) -> None:
        artifact = {
            "schema_version": mod.SCHEMA_VERSION,
            "study_id": "unit-fixture",
            "selector_commit": "1" * 40,
            "runs": [],
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            output = Path(raw) / "candidates.json"
            digest, size = mod.write_artifact(output, artifact)
            self.assertEqual(digest, hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(size, len(output.read_bytes()))
            self.assertEqual(output.read_bytes(), mod._canonical(artifact))
            with self.assertRaises(FileExistsError):
                mod.write_artifact(output, artifact)


if __name__ == "__main__":
    unittest.main()
