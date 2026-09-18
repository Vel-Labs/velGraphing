import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "benchmarks"
sys.path.insert(0, str(SCRIPT_DIR))
import velgraphing_corpus_pilot_v1 as pilot  # noqa: E402


class PilotPreparationTest(unittest.TestCase):
    def assert_rejected(self, function, *args):
        with self.assertRaises(SystemExit):
            function(*args)

    def test_rejects_unsafe_paths_and_git_modes(self):
        self.assert_rejected(pilot.safe_relative, "/etc/passwd")
        self.assert_rejected(pilot.safe_relative, "a/../b")
        self.assert_rejected(pilot.validate_mode, "120000")
        pilot.validate_mode("100644")

    def test_rejects_destination_boundary_and_digest_mismatch(self):
        lane_root = Path(__file__).resolve().parents[2] / "benchmarks" / "velgraphing-corpus-pilot-v1" / ".inputs" / "lanes"
        self.assert_rejected(pilot.validate_lane_destination, Path("/tmp/not-a-lane"), lane_root)
        self.assert_rejected(pilot.verify_source, {"path": "x.txt", "byte_length": 1, "sha256": "0" * 64}, b"x")

    def test_packets_do_not_contain_hidden_scoring_data(self):
        path = Path(__file__).resolve().parents[2] / "benchmarks" / "velgraphing-corpus-pilot-v1" / "packets.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["packets"]), 24)
        encoded = json.dumps(payload).lower()
        for forbidden in ("oracle", "acceptable_spans", "graph_expected", "scorer"):
            self.assertNotIn(forbidden, encoded)

    def test_result_seal_and_aggregate_contract(self):
        repository_root = Path(__file__).resolve().parents[2]
        path = repository_root / "benchmarks" / "velgraphing-corpus-pilot-v1" / "result.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        scope = payload["seal"]["scope"]
        canonical = json.dumps(
            {key: payload[key] for key in scope},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), payload["seal"]["sha256"])
        self.assertEqual(len(payload["results"]), 24)
        self.assertEqual(len({row["packet_id"] for row in payload["results"]}), 24)
        self.assertEqual({arm["required_fact_max"] for arm in payload["arm_aggregates"].values()}, {27})
        self.assertEqual(payload["provider_summary"]["live_calls"], 12)
        for row in payload["results"]:
            if row["arm"] in {"B", "D"}:
                self.assertEqual(set(row["telemetry"]), {"phase_1", "phase_2", "jev", "all_in"})
                self.assertEqual(row["telemetry"]["all_in"]["total_wall_ms"], "unknown")
        rows = {row["packet_id"]: row for row in payload["results"]}
        self.assertEqual(rows["B-C-02"]["telemetry"]["phase_1"]["model_visible_context_bytes"], 17337)
        self.assertEqual(rows["B-C-02"]["telemetry"]["phase_1"]["source_operations"], 8)
        self.assertEqual(rows["D-L-01"]["telemetry"]["phase_1"]["model_visible_context_bytes"], 17090)
        self.assertEqual(rows["D-L-01"]["telemetry"]["phase_1"]["source_operations"], 204)
        self.assertEqual(rows["D-L-01"]["telemetry"]["phase_1"]["fallback_reads_and_bytes"]["bytes"], 120092)
        self.assertEqual(
            {key: value["required_fact_recall"] for key, value in payload["arm_aggregates"].items()},
            {"A": 0.962963, "B": 0.962963, "C": 0.981481, "D": 0.944444},
        )

    def test_end_to_end_portable_materialization_and_packet_freeze(self):
        def run_git(repo, *args):
            return subprocess.run(
                ["git", "-C", str(repo), *args],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            run_git(source, "init", "-q")
            run_git(source, "config", "user.email", "test@example.invalid")
            run_git(source, "config", "user.name", "VelGraphing Test")
            (source / "README.md").write_text("tiny source\n", encoding="utf-8")
            (source / "code.py").write_text("answer = 42\n", encoding="utf-8")
            run_git(source, "add", "README.md", "code.py")
            run_git(source, "commit", "-q", "-m", "initial")
            pinned_commit = run_git(source, "rev-parse", "HEAD")
            source_manifest = pilot.manifest(source, pinned_commit, ("**",), ())
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")

            before = pilot.checkout_state(source)
            lane_root = root / "benchmarks" / "velgraphing-corpus-pilot-v1" / ".inputs" / "lanes"
            lane = lane_root / "test" / "tiny"
            result = pilot.materialize(source, manifest_path, lane, lane_root)
            self.assertEqual(pilot.checkout_state(source), before)
            self.assertEqual(result["commit"], pinned_commit)
            self.assertEqual(run_git(lane, "rev-parse", "HEAD"), pinned_commit)
            self.assertEqual(
                set(run_git(lane, "ls-files").splitlines()),
                {source["path"] for source in source_manifest["sources"]},
            )
            actual_sources = []
            for source_entry in source_manifest["sources"]:
                raw = lane.joinpath(*pilot.safe_relative(source_entry["path"]).parts).read_bytes()
                self.assertEqual(len(raw), source_entry["byte_length"])
                self.assertEqual(pilot.digest(raw), source_entry["sha256"])
                actual_sources.append({"path": source_entry["path"], "byte_length": len(raw), "sha256": pilot.digest(raw)})
            self.assertEqual(
                pilot.digest(pilot.canonical({"sources": actual_sources})),
                source_manifest["snapshot_sha256"],
            )

            (source / "link.md").symlink_to("README.md")
            run_git(source, "add", "link.md")
            run_git(source, "commit", "-q", "-m", "symlink")
            symlink_commit = run_git(source, "rev-parse", "HEAD")
            self.assert_rejected(pilot.manifest, source, symlink_commit, ("**",), ())

            repository_root = Path(__file__).resolve().parents[2]
            freeze_path = repository_root / "benchmarks" / "velgraphing-corpus-pilot-v1" / "freeze.json"
            questions_path = repository_root / "benchmarks" / "velgraphing-corpus-pilot-v1" / "corpus" / "questions.json"
            packets_path = root / "packets.json"
            pilot.write_packets(questions_path, freeze_path, packets_path, "$LANE_ROOT")
            payload = json.loads(packets_path.read_text(encoding="utf-8"))
            packets = payload["packets"]
            freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
            self.assertEqual(len(packets), 24)
            self.assertEqual(len({packet["packet_id"] for packet in packets}), 24)
            self.assertEqual({packet["packet_id"] for packet in packets}, set(freeze["dispatch"]["order"]))
            self.assertEqual(sum(packet["jev_request"] is not None for packet in packets), 12)
            encoded = packets_path.read_text(encoding="utf-8")
            self.assertNotIn(str(Path.home()), encoded)
            self.assertNotIn(str(repository_root), encoded)
            for packet in packets:
                packet_id = packet["packet_id"]
                self.assertEqual(packet["run_root"], f"$RUN_ROOT/{packet_id}")
                self.assertEqual(packet["observation_path"], f"$RUN_ROOT/{packet_id}/observation.json")
                graph = packet["arm"]["retrieval"] == "graph_assisted"
                jev = packet["arm"]["jev"] == "on"
                self.assertEqual(packet["graph_command"] is not None, graph)
                self.assertEqual(packet["jev_template"] is not None, jev)
                if graph:
                    self.assertIn("Run graph_command", " ".join(packet["instructions"]))
                if jev:
                    self.assertEqual(packet["jev_request"]["max_calls"], 1)
                    self.assertEqual(packet["jev_request"]["mode"], "rerank")
                    self.assertIn("phase_1", packet["jev_template"])
                    self.assertIn("phase_2", packet["jev_template"])
                    self.assertIn("--mode rerank", packet["jev_template"]["evaluate"])
                else:
                    self.assertIsNone(packet["jev_request"])
            for forbidden in ("oracle", "acceptable_spans", "graph_expected", "scorer"):
                self.assertNotIn(forbidden, encoded.lower())


if __name__ == "__main__":
    unittest.main()
