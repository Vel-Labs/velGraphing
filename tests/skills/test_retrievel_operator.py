"""Exercise the source operator through its real CLI with disposable sources."""

import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "plugins/graph-engineering/skills/graph-find/scripts/graph_find.py"
TOOL = ADAPTER.with_name("graph_tools.py")
OPERATOR = ROOT / "scripts/operators/retrievel"


class RetrievelOperatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name).resolve()
        self.source = self.work / "source"
        self.source.mkdir()
        self.evidence = self.work / "evidence"
        self.evidence.mkdir()
        self.files = {
            "alpha.py": "def alpha():\n    return 'café'\n",
            "beta.py": "def beta():\n    return 'second source'\n",
        }
        for path, text in self.files.items():
            (self.source / path).write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(self.source), "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
        ], check=True)

    def run_cli(self, script, *args):
        return subprocess.run(
            [sys.executable, "-B", str(script), *map(str, args)],
            capture_output=True, text=True, timeout=20,
        )

    def handoff(self, prompt="Compare alpha.py and beta.py.", budget=4096):
        result = self.run_cli(
            ADAPTER, "--root", self.source, "--prompt", prompt,
            "--deliver", "--byte-budget", budget,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.evidence / "handoff.json"
        path.write_text(result.stdout)
        return path

    def receive(self, handoff, name="received"):
        return self.run_cli(
            OPERATOR / "handoff_client.py", "--handoff", handoff,
            "--root", self.source, "--python", sys.executable, "--tool", TOOL,
            "--evidence-root", self.evidence, "--output", self.evidence / name,
        )

    def test_handoff_save_reopen_and_duplicate_destination_preserve_exact_source(self):
        handoff = self.handoff()
        result = self.receive(handoff)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("COMPLETE", result.stdout)
        output = self.evidence / "received"
        original = {p.name: p.read_bytes() for p in output.iterdir()}
        receipt = json.loads(original["receipt.json"])
        self.assertTrue(receipt["requested_sources_complete"])
        self.assertEqual(receipt["provider_calls"], 0)
        self.assertEqual(receipt["native_budget_validation"], "accepted")
        self.assertEqual(receipt["native_source_validation"], "accepted")
        self.assertEqual(receipt["source_identity_validation"], "before_after_equal")
        self.assertTrue(receipt["cleanup"]["reaped"])
        text = {}
        for line in original["responses.jsonl"].splitlines():
            document = json.loads(line)["result"].get("document")
            if document:
                text[document["path"]] = document["text"]
        self.assertEqual(text, self.files)
        self.assertEqual(receipt["received_source_bytes"], sum(len(s.encode()) for s in self.files.values()))
        reopened = self.run_cli(OPERATOR / "inspect_evidence.py", output)
        self.assertEqual(reopened.returncode, 0, reopened.stderr)
        # Reopening must use saved evidence, even after the original source changes.
        (self.source / "alpha.py").write_text("changed after capture\n")
        again = self.run_cli(OPERATOR / "inspect_evidence.py", output)
        self.assertEqual(again.stdout, reopened.stdout)
        displayed = self.run_cli(OPERATOR / "inspect_evidence.py", output, "--show-source")
        self.assertEqual(displayed.returncode, 0, displayed.stderr)
        self.assertIn("café", displayed.stdout)
        self.assertNotIn("changed after capture", displayed.stdout)
        duplicate = self.receive(handoff)
        self.assertEqual(duplicate.returncode, 2)
        self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, original)

    def test_missing_named_source_refuses_before_native_start(self):
        result = self.receive(self.handoff("Read absent.py."))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        receipt = json.loads((self.evidence / "received/receipt.json").read_text())
        self.assertEqual(receipt["actions"], [])
        self.assertNotIn("argv", receipt)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertEqual(receipt["received_source_bytes"], 0)

    def test_delivery_preserves_relation_support_and_modes_keep_separate_budgets(self):
        (self.source / "alpha.py").write_text(
            "from beta import beta\n\ndef alpha():\n    return beta()\n"
        )
        arguments = ("--root", self.source, "--prompt", "find alpha")
        pointers = self.run_cli(ADAPTER, *arguments)
        delivered = self.run_cli(ADAPTER, *arguments, "--deliver")
        self.assertEqual(pointers.returncode, 0, pointers.stderr)
        self.assertEqual(delivered.returncode, 0, delivered.stderr)
        pointer_payload = json.loads(pointers.stdout)
        delivery_payload = json.loads(delivered.stdout)
        self.assertTrue(pointer_payload["relationship_supports"])
        self.assertEqual(pointer_payload["hits"], delivery_payload["hits"])
        self.assertEqual(pointer_payload["relationship_supports"], delivery_payload["relationship_supports"])
        self.assertNotIn("context", pointer_payload)
        self.assertIn("return beta()", delivery_payload["context"])
        for option in ("--deliver", "--follow-up-path"):
            extra = [option] if option == "--deliver" else [option, "alpha.py"]
            mixed = self.run_cli(ADAPTER, *arguments, "--ranked-context", "plan", *extra)
            self.assertEqual(mixed.returncode, 2)
            self.assertIn("separate budgeted modes", mixed.stderr)

    def test_partial_delivery_preserves_first_file_and_its_charge(self):
        (self.source / "beta.py").write_text("def beta():\n    return '" + "x" * 1500 + "'\n")
        result = self.receive(self.handoff(budget=512))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("PARTIAL", result.stdout)
        receipt = json.loads((self.evidence / "received/receipt.json").read_text())
        self.assertEqual(receipt["completed_target_paths"], ["alpha.py"])
        self.assertEqual(receipt["remaining_target_paths"], ["beta.py"])
        self.assertFalse(receipt["requested_sources_complete"])
        charged = len(self.files["alpha.py"].encode())
        self.assertEqual(receipt["received_source_bytes"], charged)
        self.assertEqual(receipt["last_accepted_budget"]["delivered_content_bytes"], charged)
        self.assertEqual(receipt["last_accepted_budget"]["remaining_bytes"], 512 - charged)
        self.assertTrue(receipt["cleanup"]["reaped"])

    def guided_command(self, name):
        return [
            sys.executable, "-B", str(OPERATOR / "guided.py"),
            "--root", str(self.source), "--question", "find alpha",
            "--python", sys.executable, "--tool", str(TOOL), "--limit", "1",
            "--evidence-root", str(self.evidence), "--output", str(self.evidence / name),
        ]

    def test_guided_read_stops_and_a_fresh_session_restarts(self):
        for name in ("first", "second"):
            result = subprocess.run(
                [*self.guided_command(name), "--step", "read-file:alpha.py"],
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(self.files["alpha.py"], result.stdout)
            receipt = json.loads((self.evidence / name / "receipt.json").read_text())
            self.assertTrue(receipt["cleanup"]["reaped"])
            self.assertEqual(receipt["provider_calls"], 0)
            self.assertEqual(receipt["last_budget"]["delivered_content_bytes"], len(self.files["alpha.py"].encode()))

    def test_interrupt_saves_receipt_and_closes_owned_native_client(self):
        with (self.evidence / "terminal.log").open("w+") as terminal:
            process = subprocess.Popen(
                self.guided_command("interrupted"), stdin=subprocess.PIPE,
                stdout=terminal, stderr=subprocess.STDOUT, text=True,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    terminal.seek(0)
                    if "Choice (" in terminal.read():
                        break
                    self.assertIsNone(process.poll())
                    time.sleep(0.05)
                else:
                    self.fail("operator did not reach its interactive prompt")
                process.send_signal(signal.SIGINT)
                process.communicate(timeout=10)
                self.assertEqual(process.returncode, 130)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=10)
                if process.stdin:
                    process.stdin.close()
            receipt = json.loads((self.evidence / "interrupted/receipt.json").read_text())
            self.assertEqual(receipt["exit_code"], 130)
            self.assertTrue(receipt["cleanup"]["reaped"])
            self.assertEqual(receipt["provider_calls"], 0)
