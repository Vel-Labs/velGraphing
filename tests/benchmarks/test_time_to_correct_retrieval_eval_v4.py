"""Public fixtures for post-hoc v4 diagnostics; no provider or hidden corpus."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from packages.core.routing_v4 import SourceIdentityV4, SourceSnapshotV4

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("retrieval_eval_v4", ROOT / "scripts/benchmarks/time_to_correct_retrieval_eval_v4.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
SHA = "a" * 64


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def candidate(path, start, end, *, required=False, parent=None):
    row = {
        "path": path,
        "source_sha256": SHA,
        "byte_start": start,
        "byte_end": end,
        "required": required,
        "record_id": f"repo:{path}",
        "relationship_parent_candidate_id": parent,
    }
    row["id"] = mod.candidate_id(row)
    return row


def fixture():
    sources = [{"path": path, "source_sha256": SHA, "byte_length": 100} for path in ("a.md", "b.md")]
    snapshot = SourceSnapshotV4(tuple(
        SourceIdentityV4(row["path"], row["byte_length"], row["source_sha256"])
        for row in sources
    )).snapshot_sha256
    candidates = [
        candidate("a.md", 0, 20),
        candidate("b.md", 40, 60, required=True),
    ]
    controls = {"seed_record_ids": ["repo:a.md"], "seed_limit": 2,
                "candidate_limit": 2, "candidate_aggregate_byte_budget": 40,
                "candidate_unit_byte_budget": 20, "derived_edge_count": 0,
                "active_edge_count": 0,
                "source_bound_expansion": False, "expand_one_hop": False}
    artifact = {"schema_version": mod.CANDIDATE_SCHEMA_VERSION, "study_id": "unit-fixture",
                "selector_commit": "1"*40, "question_registry_sha256": "2"*64,
                "runs": [{"task_id": "fixture", "corpus": "fixture-corpus",
                          "prompt_sha256": "3"*64, "route": "direct", "source_snapshot_sha256": snapshot,
                          "sources": sources, "candidates": candidates,
                          "controls": controls,
                          "metrics": dict.fromkeys(("source_operations", "cold_ns", "warm_ns", "retrieval_ns",
                                                   "expansion_ns", "fallback_ns", "source_failures", "authority_failures"))}]}
    labels = {"schema_version": "velgraphing-span-labels-v4", "tasks": {"fixture": {
        "source_snapshot_sha256": snapshot, "groups": [{"id": "support", "critical": True,
        "acceptable_spans": [{"path": "b.md", "source_sha256": SHA, "byte_start": 45, "byte_end": 55}]}]}}}
    return artifact, labels


def run(artifact, labels, k=(2,), budgets=(40,)):
    raw = encoded(artifact)
    return mod.evaluate(raw, hashlib.sha256(raw).hexdigest(), encoded(labels), k, budgets)


def typed_fixture():
    artifact, labels = fixture()
    template = artifact["runs"][0]
    primary = template["candidates"]
    relationship = candidate(
        "b.md", 60, 80, parent=primary[0]["id"]
    )
    runs = []
    for route, candidates in (
        ("typed_graph", [primary[0], relationship]),
        ("typed_graph_no_edges", primary),
        ("typed_graph_no_expansion", primary),
    ):
        row = copy.deepcopy(template)
        row["route"] = route
        row["candidates"] = copy.deepcopy(candidates)
        row["controls"].update(
            derived_edge_count=1,
            active_edge_count=0 if route == "typed_graph_no_edges" else 1,
            source_bound_expansion=True,
            expand_one_hop=route != "typed_graph_no_expansion",
        )
        runs.append(row)
    artifact["runs"] = runs
    return artifact, labels


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
        self.assertEqual(
            result["missing_required_ids_in_diagnostic_prefix"],
            [artifact["runs"][0]["candidates"][1]["id"]],
        )

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

    def test_bound_schema_and_relationship_metadata_are_strict(self):
        artifact, labels = fixture()
        old = copy.deepcopy(artifact)
        old["schema_version"] = "velgraphing-ranked-candidates-v4"
        with self.assertRaisesRegex(mod.EvaluationError, "invalid_candidate_artifact"):
            mod.validate_candidates(old)

        prefixed = copy.deepcopy(artifact)
        prefixed["runs"][0]["candidates"][0]["id"] = (
            "candidate:" + prefixed["runs"][0]["candidates"][0]["id"]
        )
        with self.assertRaisesRegex(mod.EvaluationError, "invalid_candidate_identity"):
            mod.validate_candidates(prefixed)

        for key, value in (
            ("candidate_limit", 65),
            ("candidate_aggregate_byte_budget", 32_769),
            ("candidate_unit_byte_budget", 4097),
        ):
            changed = copy.deepcopy(artifact)
            changed["runs"][0]["controls"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(
                mod.EvaluationError, "candidate_budget_exceeds_jev_limits"
            ):
                mod.validate_candidates(changed)

        for mutate in (
            lambda row: row.update(extra=None),
            lambda row: row.pop("record_id"),
            lambda row: row.update(record_id="repo:other.md"),
        ):
            changed = copy.deepcopy(artifact)
            mutate(changed["runs"][0]["candidates"][0])
            with self.subTest(mutate=mutate), self.assertRaises(mod.EvaluationError):
                mod.validate_candidates(changed)

        primary = artifact["runs"][0]["candidates"][0]
        relationship = candidate(
            "b.md", 60, 80, parent=primary["id"]
        )
        typed = copy.deepcopy(artifact)
        typed["runs"][0]["route"] = "typed_graph"
        typed["runs"][0]["controls"].update(
            derived_edge_count=1,
            active_edge_count=1,
            source_bound_expansion=True,
            expand_one_hop=True,
            seed_limit=3,
            candidate_limit=3,
            candidate_aggregate_byte_budget=60,
        )
        typed["runs"][0]["candidates"].append(relationship)
        mod.validate_candidates(copy.deepcopy(typed))

        invalid_rows = []
        required = copy.deepcopy(relationship); required["required"] = True
        invalid_rows.append(required)
        missing = copy.deepcopy(relationship); missing["relationship_parent_candidate_id"] = "missing"
        invalid_rows.append(missing)
        self_parent = copy.deepcopy(relationship); self_parent["relationship_parent_candidate_id"] = relationship["id"]
        invalid_rows.append(self_parent)
        for invalid in invalid_rows:
            changed = copy.deepcopy(typed)
            changed["runs"][0]["candidates"][-1] = invalid
            raw = encoded(changed)
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                mod.EvaluationError, "invalid_relationship_candidate"
            ):
                mod.evaluate(
                    raw,
                    hashlib.sha256(raw).hexdigest(),
                    b"labels were not read",
                    (3,),
                    (60,),
                )

        non_typed = copy.deepcopy(artifact)
        non_typed["runs"][0]["candidates"][1]["required"] = False
        non_typed["runs"][0]["candidates"][1][
            "relationship_parent_candidate_id"
        ] = primary["id"]
        raw = encoded(non_typed)
        with self.assertRaisesRegex(mod.EvaluationError, "invalid_relationship_candidate"):
            mod.evaluate(
                raw,
                hashlib.sha256(raw).hexdigest(),
                b"labels were not read",
                (2,),
                (40,),
            )

        late = copy.deepcopy(typed)
        late["runs"][0]["candidates"] = [relationship, primary]
        late["runs"][0]["candidates"][0]["relationship_parent_candidate_id"] = primary["id"]
        with self.assertRaisesRegex(mod.EvaluationError, "invalid_relationship_candidate"):
            mod.validate_candidates(late)

        chained = copy.deepcopy(typed)
        child = candidate("a.md", 20, 40, parent=relationship["id"])
        chained["runs"][0]["candidates"].append(child)
        chained["runs"][0]["controls"].update(
            seed_limit=4, candidate_limit=4, candidate_aggregate_byte_budget=80
        )
        with self.assertRaisesRegex(mod.EvaluationError, "invalid_relationship_candidate"):
            mod.validate_candidates(chained)

    def test_typed_primary_candidates_are_invariant_before_labels(self):
        artifact, _ = typed_fixture()
        mod.validate_candidates(copy.deepcopy(artifact))
        enabled = artifact["runs"][0]["candidates"]
        control = artifact["runs"][1]["candidates"]
        self.assertEqual(len(enabled), len(control))
        self.assertIsNotNone(enabled[1]["relationship_parent_candidate_id"])
        self.assertEqual(enabled[0], control[0])

        changed = copy.deepcopy(artifact)
        no_edges = next(
            row for row in changed["runs"] if row["route"] == "typed_graph_no_edges"
        )
        no_edges["candidates"][0]["byte_start"] = 1
        no_edges["candidates"][0]["id"] = mod.candidate_id(
            no_edges["candidates"][0]
        )
        raw = encoded(changed)
        with self.assertRaisesRegex(
            mod.EvaluationError, "typed_primary_candidate_mismatch"
        ):
            mod.evaluate(
                raw,
                hashlib.sha256(raw).hexdigest(),
                b"labels were not read",
                (2,),
                (40,),
            )

    def test_registered_relational_canary_is_source_bound_and_edge_isolated(self):
        sources = [
            {"path": path, "source_sha256": SHA, "byte_length": 20_000}
            for path in ("README.md", "STYLE_GUIDE.md")
        ]
        snapshot = SourceSnapshotV4(tuple(
            SourceIdentityV4(row["path"], row["byte_length"], row["source_sha256"])
            for row in sources
        )).snapshot_sha256
        parent = candidate("README.md", 5661, 7331)
        support = candidate(
            "STYLE_GUIDE.md", 13399, 15879, parent=parent["id"]
        )
        template = {
            "task_id": "R-01",
            "corpus": "engineering-handbook",
            "prompt_sha256": mod.RELATIONAL_CANARY_QUESTIONS["R-01"][1],
            "source_snapshot_sha256": snapshot,
            "sources": sources,
            "metrics": dict.fromkeys((
                "source_operations", "cold_ns", "warm_ns", "retrieval_ns",
                "expansion_ns", "fallback_ns", "source_failures", "authority_failures",
            )),
        }
        runs = []
        for route in sorted(mod.ROUTES):
            typed = route.startswith("typed_graph")
            row = copy.deepcopy(template)
            row["route"] = route
            row["candidates"] = (
                [parent, support] if route == "typed_graph" else [parent]
            )
            row["controls"] = {
                "seed_record_ids": ["repo:README.md"],
                "seed_limit": 12,
                "candidate_limit": 12,
                "candidate_aggregate_byte_budget": 24_576,
                "candidate_unit_byte_budget": 4096,
                "derived_edge_count": 1 if typed else 0,
                "active_edge_count": 1 if route in {"typed_graph", "typed_graph_no_expansion"} else 0,
                "source_bound_expansion": typed,
                "expand_one_hop": route in {"typed_graph", "typed_graph_no_edges"},
            }
            runs.append(row)
        artifact = {
            "schema_version": mod.CANDIDATE_SCHEMA_VERSION,
            "study_id": mod.RELATIONAL_CANARY_STUDY,
            "selector_commit": "1" * 40,
            "question_registry_sha256": mod.RELATIONAL_CANARY_QUESTION_REGISTRY_SHA256,
            "runs": runs,
        }
        mod.validate_candidates(artifact)

    def test_malformed_route_types_fail_with_schema_error(self):
        for route in (None, [], 3, "invented_route"):
            artifact, labels = fixture()
            artifact["runs"][0]["route"] = route
            with self.subTest(route=route), self.assertRaises(mod.EvaluationError):
                run(artifact, labels)

    def test_claimed_snapshot_identity_is_recomputed(self):
        artifact, labels = fixture()
        artifact["runs"][0]["source_snapshot_sha256"] = "c"*64
        with self.assertRaisesRegex(mod.EvaluationError, "source_snapshot_identity_mismatch"):
            run(artifact, labels)

    def test_snapshot_sources_require_canonical_nonempty_unique_identities(self):
        for mutate in (
            lambda rows: rows.reverse(),
            lambda rows: rows.append(copy.deepcopy(rows[0])),
            lambda rows: rows.clear(),
            lambda rows: rows[0].update(byte_length=-1),
            lambda rows: rows[0].update(path="../escape.md"),
            lambda rows: rows[0].update(source_sha256="invalid"),
        ):
            artifact, _ = fixture()
            mutate(artifact["runs"][0]["sources"])
            with self.subTest(mutate=mutate), self.assertRaises(mod.EvaluationError):
                mod.validate_candidates(artifact)

    def test_redundancy_counts_union_not_number_of_files(self):
        artifact, labels = fixture()
        duplicate = copy.deepcopy(artifact["runs"][0]["candidates"][0])
        duplicate["byte_start"], duplicate["byte_end"] = 10, 30
        duplicate["id"] = mod.candidate_id(duplicate)
        artifact["runs"][0]["candidates"].append(duplicate)
        artifact["runs"][0]["controls"].update(
            seed_limit=3, candidate_limit=3, candidate_aggregate_byte_budget=60
        )
        result = run(artifact, labels, k=(3,), budgets=(60,))["results"][0]
        self.assertAlmostEqual(result["repeated_range_byte_fraction"], 1/6)
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
                row["corpus"], row["prompt_sha256"] = mod.PRODUCTION_QUESTIONS[task]
                row["route"] = route
                derived = 1 if route.startswith("typed") else 0
                active = 0 if route in {"direct", "tag_index", "typed_graph_no_edges"} else derived
                row["controls"].update(
                    seed_record_ids=["repo:a.md"], seed_limit=12,
                    candidate_limit=12, candidate_aggregate_byte_budget=24576,
                    candidate_unit_byte_budget=4096, derived_edge_count=derived,
                    active_edge_count=active,
                    source_bound_expansion=flags[route][0], expand_one_hop=flags[route][1],
                )
                runs.append(row)
        artifact["study_id"] = mod.PRODUCTION_STUDY
        artifact["question_registry_sha256"] = mod.PRODUCTION_QUESTION_REGISTRY_SHA256
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

        changed = copy.deepcopy(artifact)
        no_edges = next(run for run in changed["runs"] if run["route"] == "typed_graph_no_edges")
        no_edges["controls"]["active_edge_count"] = 1
        with self.assertRaisesRegex(mod.EvaluationError, "route_control_mismatch"):
            mod.validate_candidates(changed)

        changed = copy.deepcopy(artifact)
        task_id = changed["runs"][0]["task_id"]
        for run in changed["runs"]:
            if run["task_id"] == task_id:
                run["prompt_sha256"] = "0" * 64
        with self.assertRaisesRegex(mod.EvaluationError, "production_question_binding_mismatch"):
            mod.validate_candidates(changed)

        high_recall = copy.deepcopy(artifact)
        high_recall["study_id"] = mod.HIGH_RECALL_STUDY
        for run in high_recall["runs"]:
            run["controls"].update(
                candidate_limit=64,
                candidate_aggregate_byte_budget=32_768,
                candidate_unit_byte_budget=4096,
            )
        mod.validate_candidates(high_recall)

    def test_gate_2_rejects_unknown_regression_or_failures_and_requires_edge_gain(self):
        def rows(direct=0.5, typed=0.5, no_edges=0.5, failures=0):
            output = []
            for task in mod.PRODUCTION_TASKS:
                for route, recall in (
                    ("direct", direct), ("typed_graph", typed),
                    ("typed_graph_no_edges", no_edges),
                ):
                    output.append({
                        "task_id": task, "route": route, "k": 12,
                        "byte_budget": 24_576,
                        "critical_span_group_overlap_recall": recall,
                        "acceptable_span_group_overlap_recall": recall,
                        "observed_route_metrics": {
                            "source_failures": failures,
                            "authority_failures": 0,
                        },
                    })
            return output

        equal = mod.gate_2_decision(rows())
        self.assertEqual(equal["status"], "pass")
        self.assertFalse(equal["positive_graph_value"])
        improved = mod.gate_2_decision(rows(typed=0.75))
        self.assertEqual(improved["status"], "pass")
        self.assertTrue(improved["positive_graph_value"])
        unknown = rows()
        for row in unknown:
            if row["route"] == "typed_graph":
                row["critical_span_group_overlap_recall"] = None
        for rejected in (
            mod.gate_2_decision(rows(direct=0.75, typed=0.5)),
            mod.gate_2_decision(unknown),
            mod.gate_2_decision(rows(failures=1)),
            mod.gate_2_decision(rows()[:-1]),
        ):
            self.assertEqual(rejected["status"], "reject")
            self.assertFalse(rejected["positive_graph_value"])

    def test_nested_oracle_shaped_field_is_rejected(self):
        artifact, _ = fixture()
        artifact["runs"][0]["controls"]["oracle"] = {}
        with self.assertRaisesRegex(mod.EvaluationError, "oracle_shaped_field"):
            mod.validate_candidates(artifact)


if __name__ == "__main__":
    unittest.main()
