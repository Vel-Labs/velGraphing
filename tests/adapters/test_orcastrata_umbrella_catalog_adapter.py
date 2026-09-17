import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "adapters" / "orcastrata-umbrella-catalog" / "adapter.py"
FIXTURES = ROOT / "adapters" / "orcastrata-umbrella-catalog" / "fixtures"

SPEC = importlib.util.spec_from_file_location("orcastrata_umbrella_catalog_adapter", ADAPTER_PATH)
assert SPEC is not None and SPEC.loader is not None
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def source_backed_catalog(root: Path):
    preview = {"issues": [], "umbrella": {"title": "Routing improvement"}}
    receipt = {
        "artifact_type": "orcastrata_github_umbrella_projection_receipt_v1",
        "canonical_state": {
            "active_task": "T020",
            "board_sha256": "sha256:" + "b" * 64,
            "owner": "GoalBuddy",
        },
        "effect_boundary": {
            "acceptance_granted": False,
            "authority_granted": False,
            "goalbuddy_mutated": False,
            "github_called": False,
            "github_mutated": False,
            "network_used": False,
            "provider_called": False,
        },
        "graph_id": "routing-improvement-v1",
        "graph_sha256": "sha256:" + "a" * 64,
        "preview": preview,
        "projection_sha256": digest(preview),
        "schema_version": 1,
        "status": "ok",
        "target": {"host": "github.com", "repository": "Vel-Labs/orcastrata-max"},
    }
    receipt_raw = canonical(receipt) + b"\n"
    projection = root / "projection.json"
    projection.write_bytes(receipt_raw)
    unsigned = {
        "schema_version": 1,
        "record_type": "umbrella",
        "umbrella_id": "orcastrata:umbrella:v1:github.com/vel-labs/orcastrata-max:routing-improvement-v1",
        "title": "Routing improvement",
        "summary": "Improve worker routing context.",
        "tags": [{
            "class": "topic", "value": "routing", "owner": "Orcastrata",
            "source": "operator",
        }],
        "lifecycle": {"active_task": "T020", "owner": "GoalBuddy", "state": "snapshot"},
        "references": {
            "github_repository": "https://github.com/Vel-Labs/orcastrata-max",
            "projection": "projection.json",
            "workgraph_id": "routing-improvement-v1",
            "goalbuddy_owner": "GoalBuddy",
        },
        "digests": {
            "raw_receipt_sha256": "sha256:" + hashlib.sha256(receipt_raw).hexdigest(),
            "projection_sha256": receipt["projection_sha256"],
            "graph_sha256": receipt["graph_sha256"],
            "board_sha256": receipt["canonical_state"]["board_sha256"],
        },
        "evidence_state": "observed",
        "sensitivity": "internal",
        "exportable": False,
    }
    record = {**unsigned, "record_sha256": digest(unsigned)}
    catalog = {
        "schema_version": 1,
        "artifact_type": "orcastrata_umbrella_catalog_v1",
        "manifest_sha256": "sha256:" + "c" * 64,
        "record_count": 1,
        "catalog_sha256": digest([record]),
        "records": [record],
    }
    return catalog, canonical(catalog) + b"\n"


class OrcastrataUmbrellaCatalogAdapterTests(unittest.TestCase):
    def test_accepts_exact_valid_producer_fixture(self):
        result = ADAPTER.adapt_catalog_jsonl((FIXTURES / "valid.jsonl").read_bytes())

        self.assertTrue(result["accepted"])
        self.assertEqual("catalog_navigation", result["route"])
        self.assertEqual([], result["graph"]["records"])

    def test_rejects_exact_invalid_producer_fixture(self):
        result = ADAPTER.adapt_catalog_jsonl((FIXTURES / "invalid.jsonl").read_bytes())

        self.assertFalse(result["accepted"])
        self.assertEqual("shape_invalid", result["rejection"]["code"])

    def test_source_backed_record_preserves_catalog_and_stays_nonconsequential(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, serialized = source_backed_catalog(root)
            result = ADAPTER.adapt_catalog_jsonl(serialized, source_root=root)

        self.assertTrue(result["accepted"])
        self.assertFalse(result["consequential_use"])
        self.assertTrue(result["direct_source_fallback_required"])
        self.assertEqual(catalog, result["catalog"])
        record = result["graph"]["records"][0]
        self.assertFalse(record["eligible"])
        self.assertEqual("unknown", record["freshness"])
        self.assertEqual("topic:routing", record["tags"][0])
        self.assertEqual(catalog["records"][0], json.loads(record["content"]))
        checks = result["source_checks"][catalog["records"][0]["umbrella_id"]]
        self.assertEqual("digest_matched", checks["raw_receipt"])
        self.assertEqual("bound_not_recomputed", checks["board"])
        self.assertFalse(record["provenance"]["verified"])

    def test_stale_source_defers_without_graph_or_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, serialized = source_backed_catalog(root)
            (root / "projection.json").write_text("stale\n", encoding="utf-8")
            result = ADAPTER.adapt_catalog_jsonl(serialized, source_root=root)

        self.assertFalse(result["accepted"])
        self.assertEqual("defer", result["route"])
        self.assertEqual("stale_source", result["rejection"]["code"])
        self.assertNotIn("graph", result)
        self.assertNotIn("answer", result)

    def test_unknown_schema_version_defers(self):
        fixture = json.loads((FIXTURES / "valid.jsonl").read_text(encoding="utf-8"))
        fixture["schema_version"] = 2
        serialized = canonical(fixture) + b"\n"

        result = ADAPTER.adapt_catalog_jsonl(serialized)

        self.assertFalse(result["accepted"])
        self.assertEqual("unsupported_schema", result["rejection"]["code"])

    def test_record_or_catalog_digest_change_defers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, _ = source_backed_catalog(root)
            changed = copy.deepcopy(catalog)
            changed["records"][0]["summary"] = "Changed without resealing."
            serialized = canonical(changed) + b"\n"

            result = ADAPTER.adapt_catalog_jsonl(serialized, source_root=root)

        self.assertFalse(result["accepted"])
        self.assertEqual("record_digest_mismatch", result["rejection"]["code"])

    def test_source_binding_change_defers_after_valid_reseal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, _ = source_backed_catalog(root)
            changed = copy.deepcopy(catalog)
            record = changed["records"][0]
            record["references"]["workgraph_id"] = "different-graph"
            unsigned = {key: item for key, item in record.items() if key != "record_sha256"}
            record["record_sha256"] = digest(unsigned)
            changed["catalog_sha256"] = digest(changed["records"])
            serialized = canonical(changed) + b"\n"

            result = ADAPTER.adapt_catalog_jsonl(serialized, source_root=root)

        self.assertFalse(result["accepted"])
        self.assertEqual("stale_workgraph_binding", result["rejection"]["code"])

    def test_catalog_only_traversal_path_defers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, _ = source_backed_catalog(root)
            record = catalog["records"][0]
            record["references"]["projection"] = "../outside.json"
            unsigned = {key: item for key, item in record.items() if key != "record_sha256"}
            record["record_sha256"] = digest(unsigned)
            catalog["catalog_sha256"] = digest(catalog["records"])

            result = ADAPTER.adapt_catalog_jsonl(canonical(catalog) + b"\n")

        self.assertFalse(result["accepted"])
        self.assertEqual("source_path_uncontained", result["rejection"]["code"])

    def test_symlinked_source_root_defers(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real_root = base / "real"
            real_root.mkdir()
            _, serialized = source_backed_catalog(real_root)
            alias = base / "alias"
            alias.symlink_to(real_root, target_is_directory=True)

            result = ADAPTER.adapt_catalog_jsonl(serialized, source_root=alias)

        self.assertFalse(result["accepted"])
        self.assertEqual("source_root_invalid", result["rejection"]["code"])


if __name__ == "__main__":
    unittest.main()
