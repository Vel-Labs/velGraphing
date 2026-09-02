import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "adapters" / "knowledge-compiler" / "adapter.py"
FIXTURE_PATH = ROOT / "adapters" / "knowledge-compiler" / "fixtures" / "valid-candidate.json"

SPEC = importlib.util.spec_from_file_location("knowledge_compiler_adapter", ADAPTER_PATH)
assert SPEC is not None and SPEC.loader is not None
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


class KnowledgeCompilerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.serialized = FIXTURE_PATH.read_text(encoding="utf-8")
        self.record = json.loads(self.serialized)

    def adapt(self, value):
        return ADAPTER.adapt_serialized_candidate(value)

    def test_accepts_serialized_fixture_and_preserves_complete_record(self):
        result = self.adapt(self.serialized)

        self.assertEqual("GraphCandidateV1", result["schema_version"])
        self.assertTrue(result["accepted"])
        self.assertFalse(result["eligibility"])
        self.assertEqual(self.record, result["compiler_candidate"])

    def test_human_review_never_grants_eligibility(self):
        self.assertTrue(self.record["human_reviewed"])

        result = self.adapt(json.dumps(self.record))

        self.assertFalse(result["eligibility"])
        self.assertIn("separate_policy_or_verifier_admission", result["eligibility_basis"])

    def test_malformed_json_returns_typed_rejection(self):
        result = self.adapt('{"schema_version":')

        self.assertEqual("GraphCandidateRejectionV1", result["schema_version"])
        self.assertFalse(result["accepted"])
        self.assertEqual("invalid_json", result["rejection"]["code"])

    def test_missing_digest_returns_typed_rejection(self):
        record = copy.deepcopy(self.record)
        del record["source"]["sha256"]

        result = self.adapt(json.dumps(record))

        self.assertEqual("missing_field", result["rejection"]["code"])
        self.assertEqual("source.sha256", result["rejection"]["field"])

    def test_invalid_digest_returns_typed_rejection(self):
        record = copy.deepcopy(self.record)
        record["source"]["sha256"] = "not-a-digest"

        result = self.adapt(json.dumps(record))

        self.assertEqual("invalid_digest", result["rejection"]["code"])
        self.assertEqual("source.sha256", result["rejection"]["field"])

    def test_absent_locator_returns_typed_rejection(self):
        record = copy.deepcopy(self.record)
        del record["source"]["locator"]

        result = self.adapt(json.dumps(record))

        self.assertEqual("missing_field", result["rejection"]["code"])
        self.assertEqual("source.locator", result["rejection"]["field"])

    def test_empty_locator_returns_typed_rejection(self):
        record = copy.deepcopy(self.record)
        record["source"]["locator"] = "  "

        result = self.adapt(json.dumps(record))

        self.assertEqual("invalid_locator", result["rejection"]["code"])

    def test_each_required_top_level_field_is_required(self):
        required = (
            "schema_version",
            "record_id",
            "source",
            "draft_status",
            "confidence",
            "agent_generated",
            "human_reviewed",
            "provenance",
            "candidate_type",
            "candidate_payload",
        )
        for field in required:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                del record[field]
                result = self.adapt(json.dumps(record))
                self.assertEqual("missing_field", result["rejection"]["code"])
                self.assertEqual(field, result["rejection"]["field"])

    def test_output_is_detached_from_decoded_input(self):
        result = self.adapt(json.dumps(self.record))
        result["compiler_candidate"]["candidate_payload"]["relation"] = "changed"

        self.assertEqual("supports", self.record["candidate_payload"]["relation"])


if __name__ == "__main__":
    unittest.main()
