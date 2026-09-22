import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest

from packages.core.instructions import InstructionPlan, InstructionSection
from packages.core.review_packet import ReviewPacket, ReviewPacketError, check_review_packet, prepare_review_packet
from packages.core.routing_v4 import SourceIdentityV4, SourceSnapshotV4
from packages.core.selection import RankedContextCandidate, RankedContextJevDecision, RankedContextPlan, RankedContextProjection, RankedContextResult


class Reader:
    def __init__(self, sources):
        self.sources = dict(sources)
        self.calls = []

    def is_symlink(self, path):
        self.calls.append(("symlink", path))
        return False

    def read_bytes(self, path):
        self.calls.append(("read", path))
        return self.sources[path]


def digest(value):
    return hashlib.sha256(value).hexdigest()


def make_fixture():
    raw = b"alpha beta"
    identity = SourceIdentityV4("docs/a.md", len(raw), digest(raw))
    snapshot = SourceSnapshotV4((identity,))
    candidate = RankedContextCandidate("candidate-a", identity.path, identity.sha256, 0, 5, True, "record-a")
    decision = {
        "candidate_id": candidate.candidate_id,
        "included": True,
        "mode": "excerpt",
        "reason": "selected_bounded_excerpt",
        "source_path": candidate.source_path,
        "source_sha256": candidate.source_sha256,
        "byte_start": candidate.byte_start,
        "byte_end": candidate.byte_end,
        "source_unit_complete": candidate.source_unit_complete,
    }
    fidelity = {
        "schema_version": "graph-ranked-context-fidelity-v1",
        "query_sha256": "1" * 64,
        "source_snapshot_sha256": snapshot.snapshot_sha256,
        "candidate_set_sha256": "2" * 64,
        "byte_budget": 100,
        "reuse_state": "rebuild",
        "remaining_byte_budget": 90,
        "requested_task_facets": [],
        "decisions": [decision],
    }
    jev = RankedContextJevDecision("baseline", False, False, False, 1, 5, 0, 0, False)
    projection = RankedContextProjection("alpha", 5, 5, (candidate.candidate_id,), (candidate.candidate_id,), (), False, "selected")
    baseline = RankedContextResult("direct", "baseline", "baseline", "2" * 64, None, False, True, projection, jev)
    plan = RankedContextPlan("direct", "baseline", (candidate,), baseline, (), fidelity)
    instructions = InstructionPlan((InstructionSection("rules", "docs/rules.md", digest(b"rules"), "rules", True),), (), ())
    manifest = json.loads((Path(__file__).parents[2] / "plugins/graph-engineering/skills/manifest.json").read_text())
    reader = Reader({identity.path: raw})
    return snapshot, reader, plan, instructions, manifest


class ReviewPacketTests(unittest.TestCase):
    def test_eligible_packet_has_exact_snapshot_and_selected_binding(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        packet = prepare_review_packet("T07", "Review source", "Is the packet eligible?", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], ["source-bound"])
        self.assertEqual(check_review_packet(packet, snapshot, reader), "eligible")
        self.assertEqual(packet.to_dict()["source_snapshot_sha256"], snapshot.snapshot_sha256)
        self.assertEqual(packet.to_dict()["selected_context"][0]["candidate_id"], "candidate-a")
        self.assertEqual(len(packet.packet_sha256), 64)

    def test_stale_snapshot_stops_before_reader(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        packet = prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        changed = b"changed"
        current = SourceSnapshotV4((SourceIdentityV4("docs/a.md", len(changed), digest(changed)),))
        reader.calls.clear()
        self.assertEqual(check_review_packet(packet, current, reader), "stale_snapshot")
        self.assertEqual(reader.calls, [])

    def test_mutated_selected_source_is_source_mismatch(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        packet = prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        reader.sources["docs/a.md"] = b"mutated"
        self.assertEqual(check_review_packet(packet, snapshot, reader), "source_mismatch")

    def test_selected_ids_must_cover_every_included_decision(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        packet = prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        value = packet.to_dict()
        value["selected_candidate_ids"] = []
        value["selected_context"] = []
        with self.assertRaises(ReviewPacketError):
            ReviewPacket.from_dict(value)

    def test_embedded_manifest_entry_shape_is_closed(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        packet = prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        value = packet.to_dict()
        value["skill_manifest"]["skills"][0]["unexpected"] = True
        with self.assertRaises(ReviewPacketError):
            ReviewPacket.from_dict(value)

    def test_plan_instruction_and_skill_hashes_are_closed(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        packet = prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        for field in ("context_plan_sha256", "instruction_plan_sha256", "skill_manifest_sha256"):
            value = packet.to_dict()
            value[field] = "0" * 64
            with self.assertRaises(ReviewPacketError):
                ReviewPacket.from_dict(value)

    def test_paths_and_ordered_lists_are_rejected(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        for changed_paths in (["docs/../x"], ["b.md", "a.md"], ["a.md", "a.md"]):
            with self.assertRaises(ReviewPacketError):
                prepare_review_packet("T07", "Review source", "Question", changed_paths, snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        with self.assertRaises(ReviewPacketError):
            prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], ["risk-b", "risk-a"])
        with self.assertRaises(ReviewPacketError):
            prepare_review_packet("T07", "Review source", "Question", ["docs/missing.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])

        packet = prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        value = packet.to_dict()
        value["changed_paths"] = ["docs/missing.md"]
        with self.assertRaises(ReviewPacketError):
            ReviewPacket.from_dict(value)

    def test_blocking_codes_require_exact_policy_identity(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        with self.assertRaises(ReviewPacketError):
                prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [], {"blocking_finding_codes": ["unsafe"]})

    def test_reader_protocol_guard_and_unexpected_reader_bug(self):
        snapshot, reader, plan, instructions, manifest = make_fixture()
        packet = prepare_review_packet("T07", "Review source", "Question", ["docs/a.md"], snapshot, reader, plan, instructions, manifest, ["graph-audit"], [])
        with self.assertRaises(ReviewPacketError):
            check_review_packet(packet, snapshot, object())

        class BugReader(Reader):
            def read_bytes(self, path):
                raise RuntimeError("programming defect")

        with self.assertRaises(RuntimeError):
            check_review_packet(packet, snapshot, BugReader(reader.sources))

    def test_component_removal_has_no_provider_or_scheduler_imports(self):
        source = Path(__file__).parents[2] / "packages/core/review_packet.py"
        tree = ast.parse(source.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        forbidden = ("graph", "jev", "provider", "network", "scheduler", "subprocess", "socket", "threading", "asyncio")
        self.assertFalse(any(any(word in item.lower() for word in forbidden) for item in imports))


if __name__ == "__main__":
    unittest.main()
