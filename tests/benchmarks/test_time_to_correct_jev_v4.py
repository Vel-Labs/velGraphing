"""Offline source-bound preview tests; no provider, labels, or oracle."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from packages.core.routing_v4 import SourceIdentityV4, SourceSnapshotV4


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "time_to_correct_jev_v4",
    ROOT / "scripts/benchmarks/time_to_correct_jev_v4.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class Fixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary.name).resolve()
        self.lanes = self.root / "lanes"
        self.manifests = self.root / "manifests"
        self.manifests.mkdir()
        self.sources = {
            "cpython": (
                "source.py",
                b"def alpha():\n    return 'cpython evidence'\n" + b"# evidence\n" * 12,
            ),
            "openchain-reference-material": (
                "source.md",
                b"# Policy\nOpenChain policy evidence for the fixed preview.\n",
            ),
        }
        self.identities: dict[str, tuple[str, str, int, str]] = {}
        manifest_names = {
            "cpython": "cpython.json",
            "openchain-reference-material": "openchain.json",
        }
        for corpus, (path, raw) in self.sources.items():
            lane = self.lanes / corpus
            lane.mkdir(parents=True)
            git(lane, "init", "-q")
            git(lane, "config", "user.email", "test@example.invalid")
            git(lane, "config", "user.name", "VelGraphing Test")
            (lane / path).write_bytes(raw)
            git(lane, "add", ".")
            git(lane, "commit", "-q", "-m", "fixture")
            commit = git(lane, "rev-parse", "HEAD")
            digest = hashlib.sha256(raw).hexdigest()
            source_rows = [{"path": path, "byte_length": len(raw), "sha256": digest}]
            manifest = {
                "schema_version": "velgraphing-corpus-source-manifest-v1",
                "repository": "git-object-source",
                "commit": commit,
                "includes": ["**"],
                "excludes": [],
                "sources": source_rows,
                "source_count": 1,
                "source_bytes": len(raw),
                "snapshot_sha256": mod.generator._snapshot_digest(source_rows),
                "skipped": {},
            }
            (self.manifests / manifest_names[corpus]).write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            self.identities[corpus] = (path, digest, len(raw), manifest["snapshot_sha256"])
        self.questions = (
            ROOT / "benchmarks/velgraphing-corpus-pilot-v1/corpus/questions.json"
        ).resolve()
        question_rows = json.loads(self.questions.read_text(encoding="utf-8"))["questions"]
        by_task = {row["id"]: row for row in question_rows}
        runs = []
        fallback_identity = (
            "source.txt",
            "a" * 64,
            100,
            SourceSnapshotV4((SourceIdentityV4("source.txt", 100, "a" * 64),)).snapshot_sha256,
        )
        for task_id in sorted(mod.evaluator.PRODUCTION_TASKS):
            corpus, prompt_sha256 = mod.evaluator.PRODUCTION_QUESTIONS[task_id]
            path, digest, length, snapshot_sha256 = self.identities.get(
                corpus, fallback_identity
            )
            candidate = {
                "path": path,
                "source_sha256": digest,
                "byte_start": 0,
                "byte_end": min(length, 80),
                "required": False,
                "record_id": f"repo:{path}",
                "relationship_parent_candidate_id": None,
            }
            candidate["id"] = mod.evaluator.candidate_id(candidate)
            sources = [{
                "path": path,
                "source_sha256": digest,
                "byte_length": length,
            }]
            for route in mod.generator.ROUTES:
                typed = route.startswith("typed_graph")
                candidates = [copy.deepcopy(candidate)]
                if task_id == "C-02" and route == "typed_graph":
                    relationship = {
                        "path": path,
                        "source_sha256": digest,
                        "byte_start": 80,
                        "byte_end": 100,
                        "required": False,
                        "record_id": f"repo:{path}",
                        "relationship_parent_candidate_id": candidate["id"],
                    }
                    relationship["id"] = mod.evaluator.candidate_id(relationship)
                    candidates.append(relationship)
                runs.append({
                    "task_id": task_id,
                    "corpus": corpus,
                    "prompt_sha256": prompt_sha256,
                    "route": route,
                    "source_snapshot_sha256": snapshot_sha256,
                    "sources": copy.deepcopy(sources),
                    "candidates": candidates,
                    "controls": {
                        "seed_record_ids": [f"repo:{path}"],
                        "seed_limit": 12,
                        "candidate_limit": 12,
                        "candidate_aggregate_byte_budget": 24_576,
                        "candidate_unit_byte_budget": 4096,
                        "derived_edge_count": 0,
                        "active_edge_count": 0,
                        "source_bound_expansion": typed,
                        "expand_one_hop": route != "typed_graph_no_expansion" if typed else False,
                    },
                    "metrics": {
                        "source_operations": 0,
                        "cold_ns": None,
                        "warm_ns": None,
                        "retrieval_ns": 0,
                        "expansion_ns": None,
                        "fallback_ns": None,
                        "source_failures": 0,
                        "authority_failures": 0,
                    },
                })
        artifact = {
            "schema_version": mod.evaluator.CANDIDATE_SCHEMA_VERSION,
            "study_id": mod.evaluator.PRODUCTION_STUDY,
            "selector_commit": "1" * 40,
            "question_registry_sha256": mod.evaluator.PRODUCTION_QUESTION_REGISTRY_SHA256,
            "runs": runs,
        }
        mod.evaluator.validate_candidates(copy.deepcopy(artifact))
        self.candidates = self.root / "candidates.json"
        self.candidates.write_bytes(mod.generator._canonical(artifact))
        self.candidate_sha256 = hashlib.sha256(self.candidates.read_bytes()).hexdigest()

    def build(self):
        with mock.patch.object(mod, "_tracked", return_value=None), mock.patch.object(
            mod.jev, "evaluate", side_effect=AssertionError("evaluate must not run")
        ):
            return mod.build_preview(
                self.candidates,
                self.candidate_sha256,
                self.questions,
                self.manifests,
                self.lanes,
                "2" * 40,
                mod.evaluator.PRODUCTION_STUDY,
            )

    def close(self) -> None:
        self.temporary.cleanup()


class JevPreviewTests(unittest.TestCase):
    def validate(self, preview, candidate_sha256):
        return mod.validate_preview(
            preview,
            expected_candidate_artifact_sha256=candidate_sha256,
            expected_candidate_selector_commit="1" * 40,
            expected_adapter_commit="2" * 40,
            expected_study_id=mod.evaluator.PRODUCTION_STUDY,
        )

    def test_direct_cli_loads_worktree_core(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(ROOT.parents[1]), str(ROOT)))
        help_result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/benchmarks/time_to_correct_jev_v4.py"),
                "--help",
            ],
            cwd=ROOT.parent,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        import_result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import runpy, sys; "
                    "runpy.run_path(sys.argv[1], run_name='_worktree_probe'); "
                    "import packages.core; print(packages.core.__file__)"
                ),
                str(ROOT / "scripts/benchmarks/time_to_correct_jev_v4.py"),
            ],
            cwd=ROOT.parent,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(import_result.returncode, 0, import_result.stderr)
        self.assertTrue(
            Path(import_result.stdout.strip()).resolve().is_relative_to(ROOT),
            import_result.stdout,
        )

    def test_canary_plan_binds_four_requests_without_live_authority(self) -> None:
        plan = json.loads(
            (ROOT / "benchmarks/velgraphing-time-to-correct-v4/canary-plan.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(plan["schema_version"], "velgraphing-v4-canary-plan-1")
        self.assertEqual(plan["status"], "approval_ready_live_not_authorized")
        self.assertEqual(plan["material_candidate_commit"], "06db3f1faa073fddca4a614968145758f11d55bb")
        self.assertEqual(plan["preview_artifact_sha256"], "0005d6c26523ab2da431eb5172f89f1aa077ce28d4c1b55ca1a10cd6ab71d6a9")
        self.assertEqual(plan["provider_request_trials"], ["B-C-02", "D-C-02", "B-M-01", "D-M-01"])
        self.assertEqual(plan["request_hashes"], {
            "B-C-02": "f0e48067a35d38e88b06c136e8aea7285af239e9a876deb65e23ab9ebf6026bf",
            "D-C-02": "cb88c899dc6b2752aff978eac7b568da2f740c461d4969d282a2a2431de64ad9",
            "B-M-01": "55a5fdcb9c20dd26fb90fec7896aab857acd14b709ae6e8a6949ccf3a496d8e7",
            "D-M-01": "a2d81d30d5af32d0b0041fdba1e1abbc6dc173ac7056e3b2c9e63af7ce1ee16f",
        })
        self.assertEqual(plan["max_jev_calls"], 4)
        self.assertFalse(plan["live_authorized"])
        self.assertEqual(plan["provider_calls_made"], 0)
        self.assertFalse(plan["promotion_eligible"])
        self.assertEqual(plan["gate_3_disposition"], "exploratory_only_no_promotion")
        self.assertEqual(plan["blocking_gates"], ["fresh_operator_approval"])
        receipt = plan["evidence_receipt"]
        self.assertEqual(receipt, {
            "validated_candidate_commit": "e3af84719b87896d56640d8210c0f426f7b760bf",
            "gate_1_commits": [
                "f98d38b808bf983cde29c9e5f846c31a9b0e2fc0",
                "e6bfa4d916cc1a916e824f8bdef85f6d220c6c29",
                "f16aa09949ddfec5c264556706c6c476ff4a70dd",
            ],
            "gate_1_status": "pass",
            "gate_2_status": "pass",
            "gate_2_labels_sha256": "37a2050454c0359eefbe47e3d9420df4b11318a01aae40921610e65b63ef8ca2",
            "gate_2_result_sha256": "7e0cd1b9e9582f4e087992fa8f7c40450454c0aa0373ea475bab97b048fa83a5",
            "gate_2_positive_delta_tasks": ["S-01"],
            "preview_artifact_sha256": "0005d6c26523ab2da431eb5172f89f1aa077ce28d4c1b55ca1a10cd6ab71d6a9",
            "package_candidate_sha256": "0e17875d87498c04016df2c8de28d3d8dc3a4ee61e7fbec60c0826bfb0bcf4d1",
            "v3_result_sha256": "916c5e766b9152df5dac21b3cf3fec0116002dfee8d4f6c68eec9885bf94fd96",
        })
        self.assertEqual(receipt["preview_artifact_sha256"], plan["preview_artifact_sha256"])
        self.assertEqual(plan["candidate_artifact_sha256"], "d147df356e72aa6588d0840ea32940b6db5d5dae975acf2b218e3d4cfc697ae9")

    def test_dependency_plan_is_source_free_and_closed(self) -> None:
        plan = json.loads(
            (ROOT / "benchmarks/velgraphing-time-to-correct-v4/dependency-behavior-canary-plan.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(set(plan), {
            "schema_version", "study_id", "task_id", "candidate_artifact_sha256",
            "candidate_selector_commit", "question_registry_sha256", "prompt_sha256",
            "source_snapshot_sha256", "label_artifact_sha256", "result_artifact_sha256",
            "private_result_sha256",
            "limits", "provider_calls_executed", "live_authorized",
            "provider_details_boundary", "request_details_boundary",
            "preview_adapter_commit", "preview_artifact_sha256", "request_sha256",
            "jev_model", "jev_rubric_version", "answer_model", "answer_reasoning",
            "grader_model", "grader_reasoning", "answer_rubric_sha256",
            "pool_sha256", "restricted_state_sha256",
            "repaired_candidate_commit", "package_candidate_sha256",
            "answer_response_contract_sha256", "grader_response_contract_sha256",
            "maximum_cost_usd", "aggregate_authorized_call_total",
            "aggregate_completed_call_total", "aggregate_authorization_envelope_usd",
            "successor_incremental_authorization_usd", "successor_jev_calls_authorized",
            "successor_provider_calls_executed", "successor_run_root",
            "successor_result_sha256", "successor_b_observation_sha256",
            "repair_incremental_authorization_usd", "repair_jev_calls_authorized",
            "repair_provider_calls_executed", "repair_run_root",
        })
        self.assertEqual(
            plan["schema_version"],
            "velgraphing-v4-dependency-behavior-canary-plan-v4",
        )
        self.assertEqual(plan["study_id"], mod.DEPENDENCY_STUDY)
        self.assertEqual(plan["task_id"], "D-01")
        self.assertEqual(plan["candidate_artifact_sha256"], mod.DEPENDENCY_CANDIDATE_SHA256)
        self.assertEqual(plan["candidate_selector_commit"], mod.DEPENDENCY_SELECTOR_COMMIT)
        self.assertEqual(plan["limits"], {
            "candidate_count": 64,
            "candidate_aggregate_bytes": 32_768,
            "candidate_unit_bytes": 4096,
            "final_answer_bytes": 16_384,
            "request_bytes": 131_072,
            "maximum_jev_calls": 2,
            "retries": 0,
        })
        self.assertEqual(plan["provider_calls_executed"], 2)
        self.assertTrue(plan["live_authorized"])
        self.assertEqual(plan["private_result_sha256"], (
            "bd03bd9944c55c142b1fc00773f1253f79dd4442213c3ab2b31c098b94313286"
        ))
        self.assertEqual(set(plan["request_sha256"]), {"B", "D"})

    def test_valid_synthetic_observation_changes_d_membership_and_keeps_required(self) -> None:
        from dataclasses import replace
        from packages.core import Graph
        from tests.core.test_ranked_context_selection import (
            fixture, graph_with_relationship_edge, observation, select,
            source_record, spec,
        )

        graph, snapshot, reader, candidates = fixture()
        displaced = replace(candidates[2], candidate_id="c3", record_id="record-c3")
        child = replace(candidates[2], relationship_parent_candidate_id="c1")
        graph = Graph((*graph.records, source_record(
            displaced.record_id, displaced.source_path, displaced.source_sha256,
            "optional-b",
        )))
        graph = graph_with_relationship_edge(
            graph, snapshot, reader, candidates[1], child
        )
        pool = (candidates[0], displaced, candidates[1], child)
        three = select(graph, spec(), snapshot, reader, pool[:3])
        task = replace(spec(), byte_budget=three.projection.serialized_byte_count + 128)
        baseline = select(graph, task, snapshot, reader, pool, jev_enabled=True)
        reranked = select(
            graph, task, snapshot, reader, pool,
            observation(pool, ("c0", "c1", "c2", "c3"), snapshot),
            jev_enabled=True, jev_observation_qualified=True,
        )

        self.assertTrue(baseline.jev_decision.jev_call_could_affect_selection)
        self.assertEqual(baseline.projection.selected_candidate_ids, ("c0", "c3"))
        self.assertEqual(reranked.projection.selected_candidate_ids, ("c0", "c1", "c2"))
        self.assertEqual(reranked.projection.required_candidate_ids, ("c0",))
        self.assertTrue(reranked.jev_source_revalidated)

    def test_fixed_four_previews_are_bound_and_offline(self) -> None:
        fixture = Fixture()
        try:
            preview = fixture.build()
        finally:
            fixture.close()
        self.assertEqual(
            [(row["task_id"], row["arm"], row["route"]) for row in preview["records"]],
            list(mod.PREVIEWS),
        )
        self.assertEqual(preview["provider_calls"], 0)
        self.assertFalse(preview["model_usefulness_qualified"])
        self.assertEqual(preview["model"], "jev-1.13.0")
        for record, index in zip(preview["records"], preview["index"]):
            self.assertEqual(record["prepared"]["request_sha256"], index["request_sha256"])
            self.assertLessEqual(index["request_bytes"], 131_072)
            self.assertLessEqual(index["candidate_count"], 12)
            self.assertEqual(index["selected_count"], len(index["selected_candidate_ids"]))
            expected_relationships = int(
                record["task_id"] == "C-02" and record["arm"] == "D"
            )
            self.assertEqual(
                index["relationship_candidate_count"], expected_relationships
            )
            self.assertLessEqual(index["serialized_byte_count"], 16_384)
            self.assertEqual(record["baseline_selection"]["route"], "ranked")
            self.assertEqual(record["baseline_selection"]["order_source"], "baseline")
            self.assertTrue(record["baseline_selection"]["source_revalidated"])

    def test_hash_and_noncanonical_inputs_fail_before_preview(self) -> None:
        fixture = Fixture()
        try:
            with mock.patch.object(mod, "_tracked", return_value=None):
                with self.assertRaisesRegex(mod.PreviewError, "candidate_artifact_changed"):
                    mod.build_preview(
                        fixture.candidates,
                        "0" * 64,
                        fixture.questions,
                        fixture.manifests,
                        fixture.lanes,
                        "2" * 40,
                        mod.evaluator.PRODUCTION_STUDY,
                    )
                with self.assertRaisesRegex(mod.PreviewError, "invalid_candidate_artifact_file"):
                    mod.build_preview(
                        Path("relative.json"),
                        fixture.candidate_sha256,
                        fixture.questions,
                        fixture.manifests,
                        fixture.lanes,
                        "2" * 40,
                        mod.evaluator.PRODUCTION_STUDY,
                    )
                alias = fixture.root / "candidate-alias.json"
                alias.symlink_to(fixture.candidates)
                with self.assertRaisesRegex(mod.PreviewError, "invalid_candidate_artifact_file"):
                    mod.build_preview(
                        alias,
                        fixture.candidate_sha256,
                        fixture.questions,
                        fixture.manifests,
                        fixture.lanes,
                        "2" * 40,
                        mod.evaluator.PRODUCTION_STUDY,
                    )
        finally:
            fixture.close()

    def test_strict_validation_rejects_identity_hash_budget_and_selection_tamper(self) -> None:
        fixture = Fixture()
        try:
            preview = fixture.build()
            candidate_sha256 = fixture.candidate_sha256
        finally:
            fixture.close()
        mutations = []
        changed = copy.deepcopy(preview); changed["schema_version"] = "old"; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["provider_calls"] = 1; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["candidate_artifact_sha256"] = "f" * 64; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["candidate_selector_commit"] = "f" * 40; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["adapter_commit"] = "f" * 40; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["question_registry_sha256"] = "f" * 64; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"].reverse(); mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["corpus"] = "wrong"; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["prepared"]["request_sha256"] = "0" * 64; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["prepared"]["candidate_set_sha256"] = "0" * 64; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["prepared"]["source_set_sha256"] = "0" * 64; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["prepared"]["query_sha256"] = "0" * 64; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["prepared"]["request_bytes"] = 131_073; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["prepared"]["request"]["state"]["candidates"][0]["excerpt"] += "tamper"; mutations.append(changed)
        changed = copy.deepcopy(preview)
        request = changed["records"][0]["prepared"]["request"]
        request["questions"]["candidate_0"]["instructions"]["question"] = "Different rubric"
        changed["records"][0]["prepared"]["request_sha256"] = mod.jev.sha256(
            mod.jev.canonical(request)
        )
        changed["records"][0]["prepared"]["request_bytes"] = len(
            mod.jev.canonical(request)
        )
        mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["baseline_selection"]["order_source"] = "reranked"; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["index"][0]["selected_candidate_ids"] = []; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["bound_candidates"][0]["record_id"] = "repo:other"; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["bound_candidates"][0]["relationship_parent_candidate_id"] = "missing"; mutations.append(changed)
        changed = copy.deepcopy(preview); changed["records"][0]["bound_candidates"][0]["byte_end"] -= 1; mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaises(mod.PreviewError):
                self.validate(changed, candidate_sha256)

    def test_selected_relationship_requires_selected_primary_parent(self) -> None:
        fixture = Fixture()
        try:
            preview = fixture.build()
            candidate_sha256 = fixture.candidate_sha256
        finally:
            fixture.close()
        changed = copy.deepcopy(preview)
        record_index = next(
            index for index, record in enumerate(changed["records"])
            if (record["task_id"], record["arm"]) == ("C-02", "D")
        )
        record = changed["records"][record_index]
        parent, relationship = record["bound_candidates"]
        self.assertEqual(
            relationship["relationship_parent_candidate_id"], parent["id"]
        )
        projection = record["baseline_selection"]["projection"]
        payload = json.loads(projection["content"])
        payload["selected_candidate_ids"] = [relationship["id"]]
        payload["included_optional_candidate_ids"] = [relationship["id"]]
        payload["spans"] = [
            span for span in payload["spans"]
            if span["candidate_id"] == relationship["id"]
        ]
        projection["selected_candidate_ids"] = [relationship["id"]]
        projection["included_optional_candidate_ids"] = [relationship["id"]]
        projection["excerpt_byte_count"] = (
            relationship["byte_end"] - relationship["byte_start"]
        )
        projection["content"] = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        projection["serialized_byte_count"] = len(
            projection["content"].encode("utf-8")
        )
        changed["index"][record_index] = mod._index_value(record)

        with self.assertRaisesRegex(
            mod.PreviewError, "selected_relationship_parent_missing"
        ):
            self.validate(changed, candidate_sha256)


if __name__ == "__main__":
    unittest.main()
