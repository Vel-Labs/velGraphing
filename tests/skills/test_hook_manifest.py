from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "plugins/graph-engineering/hooks/manifest.json"
COMMANDS = ROOT / "plugins/graph-engineering/commands"
HOOK_IDS = (
    "before-context",
    "before-instructions",
    "after-compaction",
    "before-capability-selection",
    "after-change",
    "on-review-idle",
    "before-sensitive-action",
)
STATUSES = {
    "before-context": "implemented_capability",
    "before-instructions": "partial_capability",
    "after-change": "partial_capability",
    **{
        hook_id: "declaration_only"
        for hook_id in HOOK_IDS
        if hook_id not in {"before-context", "before-instructions", "after-change"}
    },
}
FIELDS = {
    "id",
    "status",
    "enabled_by_default",
    "mode",
    "trigger",
    "reads",
    "outputs",
    "dependencies",
    "network",
    "external_effects",
    "host_entry_point",
    "fallback",
    "limitation",
}


class HookManifestTests(unittest.TestCase):
    def test_manifest_is_closed_and_declares_only_supported_fallbacks(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"schema_version", "hooks"})
        self.assertEqual(payload["schema_version"], "retrievel-hook-manifest-v1")
        hooks = payload["hooks"]
        self.assertIsInstance(hooks, list)
        self.assertEqual(tuple(item["id"] for item in hooks), HOOK_IDS)

        for hook in hooks:
            with self.subTest(hook=hook["id"]):
                self.assertEqual(set(hook), FIELDS)
                self.assertEqual(hook["status"], STATUSES[hook["id"]])
                self.assertFalse(hook["enabled_by_default"])
                self.assertEqual(hook["mode"], "advisory")
                self.assertIsInstance(hook["reads"], list)
                self.assertIsInstance(hook["outputs"], list)
                self.assertEqual(set(hook["dependencies"]), {"graph", "classifier"})
                self.assertTrue(
                    all(value in {"required", "optional", "none"}
                        for value in hook["dependencies"].values())
                )
                self.assertEqual(hook["network"], "none")
                self.assertEqual(hook["external_effects"], [])
                self.assertEqual(
                    set(hook["host_entry_point"]), {"available", "name"}
                )
                self.assertFalse(hook["host_entry_point"]["available"])
                self.assertIsNone(hook["host_entry_point"]["name"])
                self.assertIn("does not grant authority", hook["limitation"])
                self.assertIn("intercept host lifecycle", hook["limitation"])
                self.assertIn("claim host availability", hook["limitation"])

                fallback = hook["fallback"]
                if fallback is None:
                    self.assertIn(
                        hook["id"],
                        {
                            item
                            for item in HOOK_IDS
                            if item not in {"before-context", "after-change"}
                        },
                    )
                    continue
                self.assertEqual(set(fallback), {"kind", "command"})
                self.assertEqual(fallback["kind"], "explicit_command")
                command = fallback["command"].split()[0].removeprefix("/")
                self.assertTrue((COMMANDS / f"{command}.toml").is_file(), command)

        self.assertEqual(
            next(item for item in hooks if item["id"] == "before-context")["fallback"]["command"],
            "/graph-find --ranked-context plan",
        )
        self.assertEqual(
            next(item for item in hooks if item["id"] == "after-change")["fallback"]["command"],
            "/graph-update",
        )
        after_change = next(item for item in hooks if item["id"] == "after-change")
        self.assertEqual(after_change["outputs"], ["graph-update-result"])
        self.assertIn("does not create a review packet", after_change["limitation"])


if __name__ == "__main__":
    unittest.main()
