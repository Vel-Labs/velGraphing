from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/graph-engineering"
MANIFEST = PLUGIN / "skills/manifest.json"
SKILL_IDS = (
    "graph-audit",
    "graph-benchmark",
    "graph-engineering",
    "graph-find",
    "graph-jev",
    "graph-start",
    "graph-steward",
    "graph-update",
)
FIELDS = {
    "skill_id",
    "source",
    "metadata",
    "command",
    "purpose",
    "applicability",
    "required_context",
    "tools",
    "external_effects",
    "permission_needs",
    "expected_output",
    "validation",
    "overlaps",
    "incompatibilities",
    "invocation",
}
EFFECTS = {
    "none",
    "host_worker_execution",
    "local_write_after_explicit_approval",
    "network_provider_source_excerpts_when_evaluate",
}


class SkillManifestTests(unittest.TestCase):
    def test_manifest_is_closed_and_recommendation_only(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"schema_version", "skills"})
        self.assertEqual(payload["schema_version"], "retrievel-skill-manifest-v1")
        skills = payload["skills"]
        self.assertEqual(tuple(item["skill_id"] for item in skills), SKILL_IDS)

        for skill in skills:
            with self.subTest(skill=skill["skill_id"]):
                self.assertEqual(set(skill), FIELDS)
                self.assertTrue(skill["source"].startswith("skills/"))
                self.assertTrue((PLUGIN / skill["source"]).is_file())
                if skill["metadata"] is not None:
                    self.assertTrue(skill["metadata"].startswith("skills/"))
                    self.assertTrue((PLUGIN / skill["metadata"]).is_file())
                if skill["command"] is not None:
                    self.assertTrue(skill["command"].startswith("commands/"))
                    self.assertTrue((PLUGIN / skill["command"]).is_file())
                for field in (
                    "applicability",
                    "required_context",
                    "tools",
                    "external_effects",
                    "permission_needs",
                    "expected_output",
                    "validation",
                    "overlaps",
                    "incompatibilities",
                ):
                    self.assertIsInstance(skill[field], list)
                    self.assertTrue(all(type(item) is str and item for item in skill[field]))
                self.assertTrue(set(skill["external_effects"]).issubset(EFFECTS))
                self.assertEqual(
                    set(skill["invocation"]), {"recommendation_only", "implicit"}
                )
                self.assertTrue(skill["invocation"]["recommendation_only"])
                self.assertFalse(skill["invocation"]["implicit"])
                self.assertNotIn("/Users/", json.dumps(skill))
                self.assertNotIn("~/.codex", json.dumps(skill))

        jev = next(item for item in skills if item["skill_id"] == "graph-jev")
        self.assertIn("network_provider_source_excerpts_when_evaluate", jev["external_effects"])
        for skill_id in ("graph-engineering", "graph-start", "graph-steward", "graph-update"):
            skill = next(item for item in skills if item["skill_id"] == skill_id)
            self.assertIn("local_write_after_explicit_approval", skill["external_effects"])


if __name__ == "__main__":
    unittest.main()
