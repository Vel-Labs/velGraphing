"""Portable Jev onboarding and fixture checks, without network or an API key."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/graph-engineering"
SKILL = PLUGIN / "skills/graph-jev"

class JevSkillTests(unittest.TestCase):
    def test_command_and_explicit_invocation_policy(self):
        command = tomllib.loads((PLUGIN / "commands/graph-jev.toml").read_text())
        self.assertIn("$graph-jev", command["prompt"])
        self.assertIn("explicit operator approval", command["prompt"])
        policy = (SKILL / "agents/openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: false", policy)

    def test_portable_mirror(self):
        self.assertEqual((ROOT / "packages/core/jev.py").read_bytes(),
                         (PLUGIN / "runtime/core/jev.py").read_bytes())

    def test_portable_runtime_exports_ranked_context_planner(self):
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = "runtime"
        run = subprocess.run(
            [sys.executable, "-c", "import core; assert callable(core.plan_ranked_context)"],
            cwd=PLUGIN,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_skill_links_and_no_machine_paths(self):
        text = (SKILL / "SKILL.md").read_text()
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if "://" not in target:
                dest = (SKILL / target).resolve()
                self.assertTrue(dest.is_relative_to((PLUGIN / "skills").resolve()))
                self.assertTrue(dest.is_file())
        for path in SKILL.rglob("*"):
            if path.is_file():
                text = path.read_text()
                for forbidden in ("/Users/", "~/.codex", "/.codex/", "Workspace/_skills"):
                    self.assertNotIn(forbidden, text)

    def test_portable_replay_without_key(self):
        env = dict(os.environ)
        env.pop("TYPESAFE_API_KEY", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        run = subprocess.run([sys.executable, "runtime/core/jev.py", "replay",
            "skills/graph-jev/examples/packet.json", "--root", "skills/graph-jev/examples/source",
            "--response", "skills/graph-jev/examples/replay.json", "--mode", "rerank"],
            cwd=PLUGIN, env=env, capture_output=True, text=True, check=True)
        result = json.loads(run.stdout)
        self.assertEqual(result["order"], ["c1", "c0", "c2"])
        self.assertEqual(result["execution"], "replay")
        self.assertEqual(result["attempted_calls"], 0)
        self.assertIsNone(result["usage"])
        self.assertFalse(result["authority_bearing"])
        self.assertFalse(result["sufficient"])

    def test_guidance_distinguishes_live_from_replay(self):
        guide = (SKILL / "references/usage.md").read_text()
        self.assertIn("ONE installation route", guide)
        self.assertIn("npx skills add typesafe-ai/skills --skill typesafe-ai", guide)
        self.assertIn("not a live service test", (SKILL / "SKILL.md").read_text())
        self.assertIn("NOT a full-repository snapshot", guide)
        self.assertIn("not a hard wall-clock", guide)

if __name__ == "__main__":
    unittest.main()
