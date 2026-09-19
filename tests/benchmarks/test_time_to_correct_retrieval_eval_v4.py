"""Public fixtures for post-hoc v4 diagnostics; no provider or hidden corpus."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("retrieval_eval_v4", ROOT / "scripts/benchmarks/time_to_correct_retrieval_eval_v4.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
SHA = "a" * 64
SNAP = "b" * 64


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def fixture():
    sources = [{"path": path, "source_sha256": SHA, "byte_length": 100} for path in ("a.md", "b.md")]
    candidates = [{"id": "c0", "path": "a.md", "source_sha256": SHA, "byte_start": 0, "byte_end": 20, "required": False},
                  {"id": "c1", "path": "b.md", "source_sha256": SHA, "byte_start": 40, "byte_end": 60, "required": True}]
    controls = {"seed_record_ids": ["repo:a.md"], "seed_limit": 2,
                "shortlist_byte_budget": 40, "derived_edge_count": 0,
                "source_bound_expansion": False, "expand_one_hop": False}
    artifact = {"schema_version": "velgraphing-ranked-candidates-v4", "study_id": "unit-fixture",
                "selector_commit": "1"*40,
                "runs": [{"task_id": "fixture", "route": "direct", "source_snapshot_sha256": SNAP,
                          "sources": sources, "candidates": candidates,
                          "controls": controls,
                          "metrics": dict.fromkeys(("source_operations", "cold_ns", "warm_ns", "retrieval_ns",
                                                   "expansion_ns", "fallback_ns", "source_failures", "authority_failures"))}]}
    labels = {"schema_version": "velgraphing-span-labels-v4", "tasks": {"fixture": {
        "source_snapshot_sha256": SNAP, "groups": [{"id": "support", "critical": True,
        "acceptable_spans": [{"path": "b.md", "source_sha256": SHA, "byte_start": 45, "byte_end": 55}]}]}}}
    return artifact, labels


def run(artifact, labels, k=(2,), budgets=(40,)):
    raw = encoded(artifact)
    return mod.evaluate(raw, hashlib.sha256(raw).hexdigest(), encoded(labels), k, budgets)


class RetrievalEvaluationTests(unittest.TestCase):
    def test_exact_path_and_range_support_at_second_rank(self):
        result = run(*fixture())["results"][0]
        self.assertEqual(result["first_overlapping_rank"], 2)
        self.assertEqual(result["reciprocal_first_overlap_rank"], 0.5)
        self.assertEqual(result["critical_span_group_overlap_recall"], 1)
        self.assertEqual(result["single_candidate_full_span_group_recall"], 1)

    def test_identical_digest_in_different_path_is_not_support(self):
        artifact, labels = fixture()
        labels["tasks"]["fixture"]["groups"][0]["acceptable_spans"][0]["byte_start"] = 5
        labels["tasks"]["fixture"]["groups"][0]["acceptable_spans"][0]["byte_end"] = 15
        self.assertEqual(run(artifact, labels)["results"][0]["acceptable_span_group_overlap_recall"], 0)

    def test_prefix_never_skips_or_splits_to_improve_recall(self):
        artifact, labels = fixture()
        result = run(artifact, labels, budgets=(25,))["results"][0]
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["excerpt_bytes"], 20)
        self.assertEqual(result["acceptable_span_group_overlap_recall"], 0)
        self.assertEqual(result["missing_required_ids_in_diagnostic_prefix"], ["c1"])

    def test_overlap_is_not_complete_span_or_semantic_support(self):
        artifact, labels = fixture()
        labels["tasks"]["fixture"]["groups"][0]["acceptable_spans"][0]["byte_end"] = 90
        result = run(artifact, labels)["results"][0]
        self.assertEqual(result["acceptable_span_group_overlap_recall"], 1)
        self.assertEqual(result["single_candidate_full_span_group_recall"], 0)
        self.assertIsNone(result["semantic_fact_recall"])

    def test_unknown_critical_mapping_stays_null(self):
        artifact, labels = fixture()
        labels["tasks"]["fixture"]["groups"][0]["critical"] = None
        self.assertIsNone(run(artifact, labels)["results"][0]["critical_span_group_overlap_recall"])

    def test_label_changes_do_not_change_candidate_artifact_or_prefix(self):
        artifact, labels = fixture()
        before = encoded(artifact)
        baseline = mod.frozen_prefix(artifact["runs"][0]["candidates"], 1, 40)
        labels["tasks"]["fixture"]["groups"][0]["acceptable_spans"][0]["path"] = "a.md"
        run(artifact, labels)
        self.assertEqual(before, encoded(artifact))
        self.assertEqual(baseline, mod.frozen_prefix(artifact["runs"][0]["candidates"], 1, 40))

    def test_candidate_tamper_rejected_before_labels_decode(self):
        raw = encoded(fixture()[0])
        with self.assertRaisesRegex(mod.EvaluationError, "candidate_artifact_changed"):
            mod.evaluate(raw + b" ", hashlib.sha256(raw).hexdigest(), b"not-json", (2,), (40,))

    def test_oracle_field_in_candidate_contract_rejected(self):
        artifact, labels = fixture()
        artifact["oracle"] = labels
        with self.assertRaisesRegex(mod.EvaluationError, "oracle_shaped_field"):
            run(artifact, labels)

    def test_empty_ranked_candidate_run_set_rejected(self):
        artifact, labels = fixture()
        artifact["runs"] = []
        labels["tasks"] = {}
        with self.assertRaisesRegex(mod.EvaluationError, "invalid_candidate_artifact"):
            run(artifact, labels)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(mod.EvaluationError):
                mod.decode(raw)

    def test_scope_and_digest_mismatch_rejected(self):
        for key, value in (("path", "../escape.md"), ("path", "outside.md"),
                           ("source_sha256", "0"*64), ("byte_end", 101), ("byte_start", False)):
            artifact, labels = fixture()
            artifact["runs"][0]["candidates"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(mod.EvaluationError):
                run(artifact, labels)

    def test_malformed_route_types_fail_with_schema_error(self):
        for route in (None, [], 3, "invented_route"):
            artifact, labels = fixture()
            artifact["runs"][0]["route"] = route
            with self.subTest(route=route), self.assertRaises(mod.EvaluationError):
                run(artifact, labels)

    def test_pair_snapshot_mismatch_rejected(self):
        artifact, labels = fixture()
        new = copy.deepcopy(artifact["runs"][0]); new["route"] = "typed_graph"
        new["controls"]["source_bound_expansion"] = True
        new["controls"]["expand_one_hop"] = True
        new["source_snapshot_sha256"] = "c"*64
        artifact["runs"].append(new)
        with self.assertRaisesRegex(mod.EvaluationError, "paired_snapshot_mismatch"):
            run(artifact, labels)

    def test_redundancy_counts_union_not_number_of_files(self):
        artifact, labels = fixture()
        candidate = copy.deepcopy(artifact["runs"][0]["candidates"][0]); candidate["id"] = "c2"
        artifact["runs"][0]["candidates"].append(candidate)
        artifact["runs"][0]["controls"].update(seed_limit=3, shortlist_byte_budget=60)
        result = run(artifact, labels, k=(3,), budgets=(60,))["results"][0]
        self.assertAlmostEqual(result["repeated_range_byte_fraction"], 1/3)
        self.assertEqual(result["unique_paths"], 2)

    def test_symlink_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "real.json").write_bytes(b"{}")
            (root / "alias.json").symlink_to(root / "real.json")
            with self.assertRaises(OSError):
                mod.read_input(root / "alias.json")

    def test_missing_metrics_and_unproven_guarantees_remain_explicit(self):
        result = run(*fixture())
        self.assertEqual(result["provider_calls"], 0)
        self.assertFalse(result["candidate_source_bytes_independently_revalidated"])
        self.assertFalse(result["oracle_isolation_proven_by_this_scorer"])
        self.assertIsNone(result["results"][0]["observed_route_metrics"]["source_operations"])

    def test_no_match_mrr_is_zero_not_missing(self):
        result = run(*fixture(), k=(1,))["results"][0]
        self.assertIsNone(result["first_overlapping_rank"])
        self.assertEqual(result["reciprocal_first_overlap_rank"], 0.0)

    def test_production_matrix_and_controls_are_closed(self):
        artifact, _ = fixture()
        template = artifact["runs"][0]
        runs = []
        flags = {
            "direct": (False, False), "tag_index": (False, False),
            "typed_graph": (True, True), "typed_graph_no_edges": (True, True),
            "typed_graph_no_expansion": (True, False),
        }
        for task in mod.PRODUCTION_TASKS:
            for route in mod.ROUTES:
                row = copy.deepcopy(template)
                row["task_id"] = task
                row["route"] = route
                row["controls"].update(
                    seed_record_ids=["repo:a.md"], seed_limit=12,
                    shortlist_byte_budget=24576, derived_edge_count=1 if route.startswith("typed") else 0,
                    source_bound_expansion=flags[route][0], expand_one_hop=flags[route][1],
                )
                runs.append(row)
        artifact["study_id"] = mod.PRODUCTION_STUDY
        artifact["runs"] = runs
        mod.validate_candidates(copy.deepcopy(artifact))
        changed = copy.deepcopy(artifact)
        changed["runs"].pop()
        with self.assertRaisesRegex(mod.EvaluationError, "production_run_matrix_mismatch"):
            mod.validate_candidates(changed)
        changed = copy.deepcopy(artifact)
        changed["runs"][0]["controls"]["seed_limit"] = 11
        with self.assertRaisesRegex(mod.EvaluationError, "paired_control_mismatch"):
            mod.validate_candidates(changed)
        changed = copy.deepcopy(artifact)
        typed = next(run for run in changed["runs"] if run["route"] == "typed_graph")
        typed["controls"]["seed_record_ids"] = ["repo:b.md"]
        with self.assertRaisesRegex(mod.EvaluationError, "typed_seed_mismatch"):
            mod.validate_candidates(changed)

    def test_nested_oracle_shaped_field_is_rejected(self):
        artifact, _ = fixture()
        artifact["runs"][0]["controls"]["oracle"] = {}
        with self.assertRaisesRegex(mod.EvaluationError, "oracle_shaped_field"):
            mod.validate_candidates(artifact)


if __name__ == "__main__":
    unittest.main()
