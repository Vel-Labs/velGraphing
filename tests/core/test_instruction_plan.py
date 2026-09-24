from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import unittest

from packages.core import (
    InstructionPlan,
    InstructionPlanError,
    InstructionSection,
    plan_instructions,
)


ROOT = Path(__file__).resolve().parents[2]
INSTRUCTIONS = ROOT / "packages/core/instructions.py"
SCHEMA = ROOT / "contracts/core/instruction-plan-v1.schema.json"


def section(section_id: str, content: str, *, mandatory: bool) -> InstructionSection:
    return InstructionSection(
        section_id,
        f"instructions/{section_id}.md",
        hashlib.sha256(content.encode("utf-8")).hexdigest(),
        content,
        mandatory,
    )


class InstructionPlanTests(unittest.TestCase):
    def test_mandatory_sections_are_exact_and_supplemental_accounting_is_deterministic(self) -> None:
        mandatory = (
            section("root", "MUST keep this first.\n", mandatory=True),
            section("nested", "MUST keep this second.\n", mandatory=True),
        )
        supplemental = (
            section("optional-a", "Add source context A.\n", mandatory=False),
            section("optional-b", "Add source context B.\n", mandatory=False),
        )

        plan = plan_instructions(mandatory, supplemental, ("optional-b",))
        payload = plan.to_dict()

        self.assertEqual(
            [item["section_id"] for item in payload["mandatory_sections"]],
            ["root", "nested"],
        )
        self.assertEqual(
            [item["reason"] for item in payload["mandatory_sections"]],
            ["mandatory_inherited", "mandatory_inherited"],
        )
        self.assertEqual(
            [item["section_id"] for item in payload["selected_supplemental_sections"]],
            ["optional-b"],
        )
        self.assertEqual(
            payload["selected_supplemental_sections"][0]["reason"],
            "caller_selected",
        )
        self.assertEqual(
            [item["section_id"] for item in payload["omitted_supplemental_sections"]],
            ["optional-a"],
        )
        self.assertEqual(
            payload["omitted_supplemental_sections"][0]["reason"],
            "caller_not_selected",
        )
        self.assertEqual(
            payload["policy"],
            {
                "mandatory_rules_preserved": True,
                "classifier_may_omit_mandatory": False,
                "tools_activated": False,
                "host_interception_claimed": False,
            },
        )
        self.assertEqual(InstructionPlan.from_dict(payload), plan)
        mutable_plan = InstructionPlan(list(mandatory), list((supplemental[1],)), [])
        self.assertIsInstance(mutable_plan.mandatory_sections, tuple)
        self.assertIsInstance(mutable_plan.selected_supplemental_sections, tuple)
        self.assertIsInstance(mutable_plan.omitted_supplemental_sections, tuple)
        self.assertNotIn("retrieval", INSTRUCTIONS.read_text(encoding="utf-8"))
        self.assertNotIn("jev", INSTRUCTIONS.read_text(encoding="utf-8"))

    def test_invalid_inputs_and_changed_mandatory_digest_fail_closed(self) -> None:
        mandatory = (section("root", "MUST keep this.\n", mandatory=True),)
        supplemental = (section("optional", "Optional.\n", mandatory=False),)

        with self.assertRaises(InstructionPlanError):
            InstructionSection("root", "instructions/root.md", "0" * 64, "MUST", True)
        with self.assertRaises(InstructionPlanError):
            InstructionSection.from_dict(
                {"section_id": "root"},
                mandatory=True,
                reason="mandatory_inherited",
            )
        with self.assertRaises(InstructionPlanError):
            plan_instructions(mandatory, (mandatory[0],), ())
        with self.assertRaises(InstructionPlanError):
            plan_instructions(mandatory, supplemental, ("unknown",))
        with self.assertRaises(InstructionPlanError):
            plan_instructions(mandatory, supplemental, ("optional", "optional"))

        payload = json.loads(plan_instructions(mandatory, supplemental).to_json())
        payload["mandatory_sections"][0]["content_sha256"] = "0" * 64
        with self.assertRaises(InstructionPlanError):
            InstructionPlan.from_dict(payload)

        payload = json.loads(plan_instructions(mandatory, supplemental, ("optional",)).to_json())
        payload["mandatory_sections"][0]["reason"] = "caller_selected"
        with self.assertRaises(InstructionPlanError):
            InstructionPlan.from_dict(payload)
        payload = json.loads(plan_instructions(mandatory, supplemental, ("optional",)).to_json())
        payload["selected_supplemental_sections"][0]["reason"] = "mandatory_inherited"
        with self.assertRaises(InstructionPlanError):
            InstructionPlan.from_dict(payload)

    def test_instruction_planner_has_no_graph_classifier_or_provider_import(self) -> None:
        tree = ast.parse(INSTRUCTIONS.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        self.assertFalse(any("retrieval" in name or name.endswith(".jev") for name in imported))
        self.assertFalse(any(name in {"requests", "urllib", "httpx"} for name in imported))

    def test_schema_declares_portable_paths_and_canonical_validation_boundary(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("InstructionPlan.from_dict", schema["$comment"])
        self.assertIn("JSON Schema cannot express", schema["$comment"])
        expected_path_pattern = (
            r"^(?!/)(?!.*\\)(?!.*//)(?!.*(?:^|/)(?:\.|\.\.)(?:/|$))"
            r"[^\u0000/]+(?:/[^\u0000/]+)*$"
        )
        for field in (
            "mandatory_sections",
            "selected_supplemental_sections",
            "omitted_supplemental_sections",
        ):
            definition = schema["properties"][field]
            self.assertTrue(definition["uniqueItems"])
            item = schema["$defs"][definition["items"]["$ref"].rsplit("/", 1)[-1]]
            self.assertEqual(
                item["properties"]["source_path"]["pattern"],
                expected_path_pattern,
            )


if __name__ == "__main__":
    unittest.main()
