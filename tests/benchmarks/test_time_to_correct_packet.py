"""Deterministic v3 packet construction. No model, credential, or network."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))

from time_to_correct import Answer, Budget, Grade, Trial, digest
from time_to_correct_packet import (EVIDENCE_BUDGET_BYTES, MAX_CANDIDATES,
                                    MAX_SPAN_BYTES, build_candidate_packet,
                                    compose_answer_payload)


def identity(arm: str, trial_id: str) -> dict:
    return {
        "run_id": "packet-v3", "trial_id": trial_id, "task_id": "task", "arm": arm,
        "repository_id": "fixture", "repository_commit": "a" * 40,
        "source_snapshot_sha256": "b" * 64, "dirty_state_sha256": "c" * 64,
        "answer_model": "fixture", "reasoning": "none", "prompt_sha256": "d" * 64,
        "rubric_sha256": "e" * 64, "rubric_version": "fixture-v1",
        "answer_lane_id": f"answer-{trial_id}",
    }


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "alpha.py").write_text(
            "def cancel_task(task):\n    return task.cancel()\n", encoding="utf-8")
        (self.root / "guide.md").write_text(
            "# Cancellation\nUse cancel_task to request cancellation.\n", encoding="utf-8")
        self.scope = ["alpha.py", "guide.md"]
        self.question = "How does cancel_task request cancellation?"

    def run_packet(self, arm: str, trial_id: str, *, route: str,
                   navigation=None, reverse=False, selected_count=None):
        trial = Trial(identity(arm, trial_id), Budget(0, 1_000_000_000), execution="fixture")
        retained = {}
        def prepare(current, _):
            if route == "direct":
                current.not_applicable("cold_graph_build", "warm_graph_load")
            else:
                current.current["graph_observation"] = {"record_count": 2, "edge_count": 0}
                current.not_applicable("cold_graph_build", "warm_graph_load")
            current.not_applicable("fallback", "jev_preparation", "provider",
                                   "source_revalidation", "response_validation",
                                   "operator_approval")
            packet = build_candidate_packet(
                current, self.root, self.question, self.scope,
                route=route, graph_navigation=navigation,
            )
            selected = [row["id"] for row in packet["candidates"]]
            if reverse:
                selected.reverse()
            if selected_count is not None:
                selected = selected[:selected_count]
            payload = compose_answer_payload(current, self.root, packet, selected)
            current.coverage(source_operations=True)
            retained.update(packet=packet, payload=payload)
            return payload
        def answer(current, payload, _):
            current.context(json.dumps(payload, sort_keys=True).encode("utf-8"))
            current.usage(f"answer-{trial_id}", "answer", provenance="fixture",
                          model="fixture", input_tokens=1, output_tokens=1)
            return Answer("fixture")
        def grade(current, _answer, _):
            current.coverage(source_operations=True, model_calls=True,
                             context_deliveries=True)
            return Grade(True, 1, 1, True, 0, "grader", "e" * 64)
        result = trial.run(prepare, answer, grade)
        return result, retained

    def test_direct_pairs_bind_identical_packets_and_payload_is_minimal(self):
        a, a_retained = self.run_packet("A", "A-task", route="direct")
        b, b_retained = self.run_packet("B", "B-task", route="direct")
        a_observation = a["attempts"][0]["candidate_observation"]
        b_observation = b["attempts"][0]["candidate_observation"]
        for key in ("candidate_packet_sha256", "candidate_set_sha256",
                    "baseline_order_sha256"):
            self.assertEqual(a_observation[key], b_observation[key])
        self.assertEqual(a_observation["route"], "direct_flat")
        self.assertTrue(a["attempts"][0]["coverage"]["source_operations"])
        self.assertEqual(set(a_retained["payload"]), {
            "schema_version", "question", "citation_instruction", "evidence"})
        self.assertEqual(set(a_retained["payload"]["evidence"][0]), {
            "id", "excerpt", "path", "source_sha256", "byte_start", "byte_end"})
        retained = json.dumps(a_retained["payload"], sort_keys=True)
        for forbidden in (str(self.root), "source_scope", "corpus_root", "graph_navigation",
                          "recommended_fallback_paths", "scores"):
            self.assertNotIn(forbidden, retained)
        for evidence in a_retained["payload"]["evidence"]:
            raw = (self.root / evidence["path"]).read_bytes()
            self.assertEqual(digest(raw), evidence["source_sha256"])
            self.assertEqual(raw[evidence["byte_start"]:evidence["byte_end"]].decode(),
                             evidence["excerpt"])

    def test_graph_pairs_use_top_hit_pointers_and_report_zero_edges(self):
        (self.root / "LICENSE").write_text("license text", encoding="utf-8")
        self.scope.insert(0, "LICENSE")
        evidence = []
        hits = []
        for path in self.scope:
            raw = (self.root / path).read_bytes()
            hits.append({"source_path": path})
            end = min(10, len(raw))
            evidence.append({
                "source_path": path, "source_sha256": digest(raw),
                "byte_start": 0, "byte_end": end,
                "excerpt_sha256": digest(raw[:end]),
            })
        navigation = {"route": "graph", "fail_closed": False,
                      "hits": hits, "evidence": evidence}
        c, c_retained = self.run_packet("C", "C-task", route="graph", navigation=navigation)
        d, d_retained = self.run_packet(
            "D", "D-task", route="graph", navigation=navigation, reverse=True)
        c_observation = c["attempts"][0]["candidate_observation"]
        d_observation = d["attempts"][0]["candidate_observation"]
        self.assertEqual(c_observation["candidate_packet_sha256"],
                         d_observation["candidate_packet_sha256"])
        self.assertEqual(c_observation["baseline_order_sha256"],
                         d_observation["baseline_order_sha256"])
        self.assertEqual(c_observation["route"], "graph_find_tag_index")
        self.assertEqual((c_observation["record_count"], c_observation["edge_count"],
                          c_observation["edge_expansion_status"]),
                         (2, 0, "not_available"))
        self.assertNotIn("LICENSE", [row["path"] for row in c_retained["packet"]["candidates"]])
        self.assertTrue(all(row["byte_end"] - row["byte_start"] > 10
                            for row in c_retained["packet"]["candidates"]))
        original = {row["id"]: row for row in c_retained["payload"]["evidence"]}
        reordered = d_retained["payload"]["evidence"]
        self.assertEqual([row["id"] for row in reordered], list(reversed(original)))
        self.assertEqual({row["id"]: {k: v for k, v in row.items() if k != "id"}
                          for row in reordered},
                         {candidate_id: {k: v for k, v in row.items() if k != "id"}
                          for candidate_id, row in original.items()})

    def test_fixed_caps_limit_candidates_spans_and_total_evidence(self):
        self.scope = []
        self.question = "needle"
        for index in range(8):
            path = f"source-{index}.txt"
            (self.root / path).write_text("needle " * 900, encoding="utf-8")
            self.scope.append(path)
        result, retained = self.run_packet("A", "A-cap", route="direct")
        candidates = retained["packet"]["candidates"]
        self.assertLessEqual(len(candidates), MAX_CANDIDATES)
        self.assertTrue(all(row["byte_end"] - row["byte_start"] <= MAX_SPAN_BYTES
                            for row in candidates))
        self.assertLessEqual(sum(row["byte_end"] - row["byte_start"] for row in candidates),
                             EVIDENCE_BUDGET_BYTES)
        self.assertEqual(result["attempts"][0]["candidate_observation"]["evidence_bytes"],
                         sum(row["byte_end"] - row["byte_start"] for row in candidates))

    def test_answer_payload_accepts_selected_subset_in_order(self):
        result, retained = self.run_packet(
            "A", "A-subset", route="direct", selected_count=1,
        )
        expected = [retained["packet"]["candidates"][0]["id"]]
        actual = [row["id"] for row in retained["payload"]["evidence"]]
        self.assertEqual(actual, expected)
        self.assertEqual(result["terminal_reason"], "passed")

    def test_graph_defer_and_fail_closed_are_rejected(self):
        for navigation in ({"route": "defer", "fail_closed": False, "hits": [], "evidence": []},
                           {"route": "malformed", "fail_closed": False, "hits": [], "evidence": []},
                           {"route": "graph", "fail_closed": True, "hits": [], "evidence": []}):
            result, _ = self.run_packet(
                "C", f"C-{navigation['route']}-{navigation['fail_closed']}",
                route="graph", navigation=navigation)
            self.assertEqual(result["terminal_reason"], "measurement_error")
            self.assertEqual(result["attempts"][0]["failure_reason"],
                             "graph_navigation_deferred")

    def test_real_frozen_cpython_lane_skips_license_and_builds_direct_packet(self):
        lane = ROOT / "benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4/cpython"
        manifest_path = ROOT / "benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/cpython.json"
        if not lane.is_dir():
            self.skipTest("retained v4 CPython lane unavailable")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.root = lane
        self.scope = [row["path"] for row in manifest["sources"]]
        self.question = "How do asyncio create_task Task TaskGroup current_task and all_tasks relate?"
        self.assertIn("LICENSE", self.scope)
        result, retained = self.run_packet("A", "A-frozen-cpython", route="direct")
        self.assertEqual(result["terminal_reason"], "passed")
        self.assertNotIn("LICENSE", [row["path"] for row in retained["packet"]["candidates"]])


if __name__ == "__main__":
    unittest.main()
