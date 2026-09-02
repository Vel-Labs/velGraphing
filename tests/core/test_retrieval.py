from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from packages.core import (
    Admission,
    AuthorityClass,
    FacetKind,
    Freshness,
    Graph,
    GraphEdge,
    GraphRecord,
    PromptFacet,
    PromptFacetSet,
    ProofObligation,
    Provenance,
    Sensitivity,
    SourceIdentityV4,
    SourceSnapshotV4,
    compose_navigation_context,
    TaskSpec,
    TrustClass,
    build_repository_tag_index,
    build_repository_file_cards,
    compile_prompt,
    compile_proof_obligations,
    navigate,
    retrieve,
    retrieve_hybrid,
)


class Reader:
    def __init__(self, sources: dict[str, bytes]) -> None:
        self.sources = sources
        self.read_paths: list[str] = []

    def read_bytes(self, project_relative_path: str) -> bytes:
        self.read_paths.append(project_relative_path)
        return self.sources[project_relative_path]

    def is_symlink(self, project_relative_path: str) -> bool:
        return False


def fixture() -> tuple[Graph, SourceSnapshotV4, Reader]:
    sources = {
        "src/auth/token_service.py": (
            b"from config import TOKEN_EXPIRY\n\n"
            b"AUTH_RUNTIME_OWNER = 'content'\n\n"
            b"def refresh_token(token):\n    return validate_token(token, TOKEN_EXPIRY)\n"
        ),
        "src/config.py": b"TOKEN_EXPIRY = 3600\n",
        "tests/test_token_service.py": (
            b"def test_refresh_token_expiry():\n    assert refresh_token('x')\n"
        ),
        "docs/AUTH.md": b"# Authentication token lifecycle\nToken expiry and refresh behavior.\n",
        "src/unrelated.py": b"def router():\n    return 'route'\n",
    }
    records: list[GraphRecord] = []
    for path, raw in sources.items():
        digest = hashlib.sha256(raw).hexdigest()
        records.append(
            GraphRecord(
                record_id=f"repo:{path}",
                kind="source",
                title=path,
                content=raw.decode("utf-8"),
                provenance=Provenance(path, digest, "bytes", True),
                trust=TrustClass.VERIFIED_SOURCE,
                sensitivity=Sensitivity.PUBLIC,
                freshness=Freshness.CURRENT,
                admission=Admission.VERIFIER,
                eligible=True,
            )
        )
    by_path = {record.provenance.path: record.record_id for record in records}
    edge_provenance = records[0].provenance
    edges = (
        GraphEdge(
            "edge:auth-config",
            by_path["src/auth/token_service.py"],
            by_path["src/config.py"],
            "imports",
            1.0,
            edge_provenance,
            TrustClass.VERIFIED_SOURCE,
            Sensitivity.PUBLIC,
            Freshness.CURRENT,
            Admission.VERIFIER,
            True,
        ),
        GraphEdge(
            "edge:config-test",
            by_path["src/config.py"],
            by_path["tests/test_token_service.py"],
            "tested_by",
            1.0,
            edge_provenance,
            TrustClass.VERIFIED_SOURCE,
            Sensitivity.PUBLIC,
            Freshness.CURRENT,
            Admission.VERIFIER,
            True,
        ),
    )
    snapshot = SourceSnapshotV4(
        tuple(
            SourceIdentityV4(path, len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in sorted(sources.items())
        )
    )
    return Graph(tuple(records), edges), snapshot, Reader(sources)


def task(**changes: object) -> TaskSpec:
    values = {
        "task_id": "tag-retrieval-test",
        "query_terms": ("token",),
        "node_budget": 8,
        "byte_budget": 12000,
    }
    values.update(changes)
    return TaskSpec(**values)  # type: ignore[arg-type]


def single_source_fixture(content: bytes, path: str = "src/example.py") -> tuple[Graph, SourceSnapshotV4, Reader]:
    digest = hashlib.sha256(content).hexdigest()
    record = GraphRecord(
        record_id=f"repo:{path}",
        kind="source",
        title=path,
        content=content.decode("utf-8"),
        provenance=Provenance(path, digest, "bytes", True),
        trust=TrustClass.VERIFIED_SOURCE,
        sensitivity=Sensitivity.PUBLIC,
        freshness=Freshness.CURRENT,
        admission=Admission.VERIFIER,
        eligible=True,
    )
    snapshot = SourceSnapshotV4((SourceIdentityV4(path, len(content), digest),))
    return Graph((record,)), snapshot, Reader({path: content})


def multi_source_fixture(sources: dict[str, bytes]) -> tuple[Graph, SourceSnapshotV4, Reader]:
    records = []
    for path, raw in sources.items():
        digest = hashlib.sha256(raw).hexdigest()
        records.append(
            GraphRecord(
                record_id=f"repo:{path}",
                kind="source",
                title=path,
                content=raw.decode("utf-8"),
                provenance=Provenance(path, digest, "bytes", True),
                trust=TrustClass.VERIFIED_SOURCE,
                sensitivity=Sensitivity.PUBLIC,
                freshness=Freshness.CURRENT,
                admission=Admission.VERIFIER,
                eligible=True,
            )
        )
    snapshot = SourceSnapshotV4(
        tuple(
            SourceIdentityV4(path, len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in sorted(sources.items())
        )
    )
    return Graph(tuple(records)), snapshot, Reader(sources)


def obligated_facets(*obligations: ProofObligation, count: int = 8) -> PromptFacetSet:
    return PromptFacetSet(
        "f" * 64,
        tuple(PromptFacet(FacetKind.ENTITY, f"facet-{index}", 1) for index in range(count)),
        proof_obligations=obligations,
    )


class ProofObligationCompilerTests(unittest.TestCase):
    def test_compilation_is_deterministic_and_caps_behavioral_units(self) -> None:
        content = (
            b"def alpha():\n    return alpha_helper()\n\n"
            b"def beta():\n    return beta_helper()\n"
        )
        graph, snapshot, reader = single_source_fixture(content)
        index = build_repository_tag_index(graph, snapshot, reader)
        first = compile_proof_obligations(
            "Explain alpha beta behavior and return evidence",
            graph, index, snapshot, reader,
        )
        second = compile_proof_obligations(
            "Explain alpha beta behavior and return evidence",
            graph, index, snapshot, reader,
        )
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 6)
        self.assertTrue(all(item.obligation_id for item in first))
        self.assertTrue(all(len(item.source_hints) == 1 for item in first))
        self.assertTrue(all("return" not in item.anchor_hints for item in first))

    def test_behavioral_anchors_in_one_complete_unit_form_one_obligation(self) -> None:
        content = b"def alpha():\n    return alpha_helper()\n"
        graph, snapshot, reader = single_source_fixture(content)
        index = build_repository_tag_index(graph, snapshot, reader)
        obligations = compile_proof_obligations(
            "Explain alpha alpha_helper behavior", graph, index, snapshot, reader
        )
        self.assertEqual(len(obligations), 1)
        self.assertEqual(set(obligations[0].anchor_hints), {"alpha", "alpha-helper"})
        result = retrieve(
            graph, task(), index, obligated_facets(*obligations), snapshot, reader,
            channels=("exact",), expand_one_hop=False,
        )
        self.assertEqual(result.route, "graph")
        self.assertEqual(result.unresolved_obligation_ids, ())

    def test_prompt_clause_spanning_separate_functions_stays_unresolved(self) -> None:
        content = (
            b"def alpha():\n    return 'alpha'\n\n"
            b"def beta():\n    return 'beta'\n"
        )
        graph, snapshot, reader = single_source_fixture(content)
        index = build_repository_tag_index(graph, snapshot, reader)
        obligations = compile_proof_obligations(
            "Explain alpha beta behavior", graph, index, snapshot, reader
        )
        self.assertEqual(len(obligations), 1)
        self.assertEqual(set(obligations[0].anchor_hints), {"alpha", "beta"})
        result = retrieve(
            graph, task(), index, obligated_facets(*obligations), snapshot, reader,
            channels=("exact",), expand_one_hop=False,
        )
        self.assertEqual(result.route, "defer")
        self.assertEqual(result.unresolved_obligation_ids, (obligations[0].obligation_id,))

    def test_root_markdown_is_documentation_authority(self) -> None:
        content = b"# Root behavior\nThe alpha behavior is documented here.\n"
        graph, snapshot, reader = single_source_fixture(content, "README.md")
        index = build_repository_tag_index(graph, snapshot, reader)
        obligations = compile_proof_obligations(
            "Explain alpha behavior", graph, index, snapshot, reader
        )
        self.assertEqual(len(obligations), 1)
        self.assertIs(obligations[0].authority_class, AuthorityClass.DOCUMENTATION)

    def test_docs_path_is_documentation_even_for_executable_source(self) -> None:
        content = b"def receipt_anchor():\n    return 'documented'\n"
        graph, snapshot, reader = single_source_fixture(content, "docs/receipt.py")
        index = build_repository_tag_index(graph, snapshot, reader)
        obligations = compile_proof_obligations(
            "Explain receipt_anchor", graph, index, snapshot, reader
        )
        self.assertEqual(len(obligations), 1)
        self.assertEqual(obligations[0].source_hints, ("docs/receipt.py",))
        self.assertIs(obligations[0].authority_class, AuthorityClass.DOCUMENTATION)

    def test_runtime_hint_wins_over_matching_docs_receipt(self) -> None:
        sources = {
            "docs/receipt.py": b"def runtime_anchor():\n    return 'receipt'\n",
            "src/runtime.py": b"def runtime_anchor():\n    return 'runtime'\n",
        }
        graph, snapshot, reader = multi_source_fixture(sources)
        index = build_repository_tag_index(graph, snapshot, reader)
        obligations = compile_proof_obligations(
            "Explain runtime_anchor", graph, index, snapshot, reader
        )
        self.assertEqual(len(obligations), 1)
        self.assertEqual(obligations[0].source_hints, ("src/runtime.py",))
        self.assertIs(obligations[0].authority_class, AuthorityClass.RUNTIME)

    def test_compound_prompt_splitting_is_deterministic_and_evidence_backed(self) -> None:
        content = (
            b"def alpha():\n    return 1\n\n"
            b"def beta():\n    return 2\n\n"
            b"def gamma():\n    return 3\n"
        )
        graph, snapshot, reader = single_source_fixture(content)
        index = build_repository_tag_index(graph, snapshot, reader)
        prompt = "Explain alpha and beta, then gamma"
        first = compile_proof_obligations(prompt, graph, index, snapshot, reader)
        second = compile_proof_obligations(prompt, graph, index, snapshot, reader)
        self.assertEqual(first, second)
        self.assertEqual(
            [item.anchor_hints for item in first],
            [("alpha",), ("beta",), ("gamma",)],
        )
        self.assertEqual(
            [item.obligation_id for item in first],
            ["behavior-clause:01", "behavior-clause:02", "behavior-clause:03"],
        )

    def test_authority_priority_preserves_runtime_with_verbose_documentation(self) -> None:
        sources = {
            "README.md": b"# docs\n" + b"\n".join(
                f"doc{index} details".encode("utf-8") for index in range(8)
            ),
            "src/runtime.py": b"def critical_runtime():\n    return 1\n",
        }
        graph, snapshot, reader = multi_source_fixture(sources)
        index = build_repository_tag_index(graph, snapshot, reader)
        prompt = "; ".join([f"doc{index}" for index in range(8)] + ["critical_runtime"])
        obligations = compile_proof_obligations(prompt, graph, index, snapshot, reader)
        self.assertEqual(len(obligations), 6)
        self.assertEqual(obligations[0].authority_class, AuthorityClass.RUNTIME)
        self.assertEqual(obligations[0].obligation_id, "behavior-clause:09")

    def test_stale_reader_is_rejected_before_obligations_are_emitted(self) -> None:
        content = b"def alpha():\n    return alpha_helper()\n"
        graph, snapshot, reader = single_source_fixture(content)
        index = build_repository_tag_index(graph, snapshot, reader)
        stale = Reader({"src/example.py": content.replace(b"alpha", b"omega", 1)})
        with self.assertRaisesRegex(
            ValueError, "proof obligation inputs do not bind to verified source snapshot"
        ):
            compile_proof_obligations(
                "Explain alpha behavior", graph, index, snapshot, stale
            )


class ObligatedEvidencePackingTests(unittest.TestCase):
    def test_critical_runtime_precedes_oversized_documentation(self) -> None:
        sources = {
            "src/runtime.py": b"def critical_runtime():\n    return 'small proof'\n",
            "README.md": b"# doc-anchor\n" + (b"documentation " * 1000),
        }
        graph, snapshot, reader = multi_source_fixture(sources)
        index = build_repository_tag_index(graph, snapshot, reader)
        runtime = ProofObligation(
            "critical-runtime", AuthorityClass.RUNTIME,
            source_hints=("src/runtime.py",), anchor_hints=("critical-runtime",), critical=True,
        )
        documentation = ProofObligation(
            "large-documentation", AuthorityClass.DOCUMENTATION,
            source_hints=("README.md",), anchor_hints=("doc-anchor",),
        )
        result = retrieve(
            graph, task(byte_budget=1000), index,
            obligated_facets(runtime, documentation), snapshot, reader,
            channels=("exact",), expand_one_hop=False,
        )
        self.assertIn("critical-runtime", result.covered_obligation_ids)
        self.assertIn("large-documentation", result.unresolved_obligation_ids)
        self.assertIn("src/runtime.py", result.context)
        self.assertNotIn("README.md", result.context)

    def test_overlapping_obligation_ranges_are_charged_once(self) -> None:
        content = b"# root-anchor\nroot text\n## nested-anchor\nnested text\n"
        graph, snapshot, reader = single_source_fixture(content, "README.md")
        index = build_repository_tag_index(graph, snapshot, reader)
        root = ProofObligation(
            "root-doc", AuthorityClass.DOCUMENTATION,
            anchor_hints=("root-anchor",),
        )
        nested = ProofObligation(
            "nested-doc", AuthorityClass.DOCUMENTATION,
            anchor_hints=("nested-anchor",),
        )
        result = retrieve(
            graph, task(byte_budget=1000), index,
            obligated_facets(root, nested), snapshot, reader,
            channels=("exact",), expand_one_hop=False,
        )
        self.assertEqual(len(result.spans), 1)
        self.assertEqual(result.covered_obligation_ids, ("nested-doc", "root-doc"))
        self.assertEqual(result.unresolved_obligation_ids, ())
        self.assertEqual(result.context_bytes, len(result.context.encode("utf-8")))

    def test_obligated_packing_is_serial_parallel_identical(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "refresh-runtime", AuthorityClass.RUNTIME,
            source_hints=("src/auth/token_service.py",), anchor_hints=("refresh-token",),
        )
        facets = obligated_facets(obligation)
        serial = retrieve(graph, task(), index, facets, snapshot, reader, parallel=False)
        parallel = retrieve(graph, task(), index, facets, snapshot, Reader(reader.sources), parallel=True)
        self.assertEqual(serial, parallel)


class TagIndexTests(unittest.TestCase):
    def test_repository_tags_are_source_bound_and_deterministic(self) -> None:
        graph, snapshot, reader = fixture()
        first = build_repository_tag_index(graph, snapshot, reader)
        second = build_repository_tag_index(graph, snapshot, Reader(reader.sources))
        self.assertEqual(first, second)
        self.assertIn("token-expiry", first.vocabulary)
        self.assertIn("authentication-token-lifecycle", first.vocabulary)
        self.assertTrue(all(tag.source_path in reader.sources for tag in first.tags))

    def test_source_incomplete_record_is_rejected(self) -> None:
        graph, snapshot, reader = fixture()
        changed = replace(graph.records[0], content="summary only")
        with self.assertRaisesRegex(ValueError, "source-complete"):
            build_repository_tag_index(Graph((changed, *graph.records[1:]), graph.edges), snapshot, reader)

    def test_semantic_expansion_is_repository_vocabulary_constrained(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        facets = compile_prompt(
            "Trace token refresh expiry configuration and tests",
            index,
            semantic_candidates=("token", "invented-provider-secret"),
        )
        self.assertLessEqual(len(facets.facets), 20)
        self.assertGreaterEqual(len(facets.facets), 8)
        self.assertIn("invented-provider-secret", facets.rejected_semantic_candidates)
        self.assertIn(
            (FacetKind.SEMANTIC, "token"),
            {(facet.kind, facet.value) for facet in facets.facets},
        )

    def test_short_or_generic_prompt_is_insufficient_without_padding(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        facets = compile_prompt("graph policy", index)
        self.assertFalse(facets.sufficient)
        result = retrieve(graph, task(), index, facets, snapshot, reader)
        self.assertEqual(result.reason, "prompt_facets_insufficient")
        self.assertEqual(result.hits, ())

    def test_minimal_file_cards_are_source_bound_and_deterministic(self) -> None:
        graph, snapshot, reader = fixture()
        first = build_repository_file_cards(graph, snapshot, reader)
        second = build_repository_file_cards(graph, snapshot, Reader(reader.sources))
        self.assertEqual(first, second)
        self.assertEqual(first[0].source_path, "docs/AUTH.md")
        self.assertEqual(first[0].source_sha256, hashlib.sha256(reader.sources[first[0].source_path]).hexdigest())

    def test_proof_obligation_retrieval_returns_complete_function_evidence(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "refresh-runtime",
            AuthorityClass.RUNTIME,
            source_hints=("src/auth/token_service.py",),
            anchor_hints=("refresh-token",),
        )
        facets = PromptFacetSet(
            "d" * 64,
            tuple(PromptFacet(FacetKind.ENTITY, f"facet-{index}", 1) for index in range(8)),
            proof_obligations=(obligation,),
        )
        result = retrieve(
            graph, task(), index, facets, snapshot, reader,
            channels=("exact",), expand_one_hop=True, maximum_results=4,
        )
        self.assertEqual(result.route, "graph")
        self.assertEqual(result.recommended_fallback_paths, ())
        self.assertEqual(result.evidence[0].obligation_ids, ("refresh-runtime",))
        self.assertIn(b"def refresh_token", reader.sources[result.evidence[0].source_path][result.evidence[0].byte_start:result.evidence[0].byte_end])
        self.assertIn(b"return validate_token", reader.sources[result.evidence[0].source_path][result.evidence[0].byte_start:result.evidence[0].byte_end])

    def test_compile_prompt_preserves_caller_owned_obligations(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "refresh-runtime",
            AuthorityClass.RUNTIME,
            anchor_hints=("refresh-token",),
            critical=True,
        )
        facets = compile_prompt(
            "Trace refresh token behavior and configuration evidence",
            index,
            proof_obligations=(obligation,),
        )
        self.assertEqual(facets.proof_obligations, (obligation,))

    def test_obligation_closure_and_remaining_budget_are_explicit(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        covered = ProofObligation(
            "refresh-runtime",
            AuthorityClass.RUNTIME,
            anchor_hints=("refresh-token",),
            critical=True,
        )
        missing = ProofObligation(
            "missing-config",
            AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            required_tag_values=("missing-setting",),
            critical=True,
        )
        result = retrieve(
            graph,
            task(),
            index,
            obligated_facets(covered, missing),
            snapshot,
            reader,
        )
        self.assertEqual(result.route, "defer")
        self.assertEqual(result.covered_obligation_ids, ("refresh-runtime",))
        self.assertEqual(result.unresolved_obligation_ids, ("missing-config",))
        self.assertEqual(result.unresolved_critical_obligation_ids, ("missing-config",))
        self.assertEqual(result.remaining_byte_budget, task().byte_budget - result.context_bytes)

    def test_budget_skipped_evidence_remains_unresolved(self) -> None:
        graph, snapshot, reader = single_source_fixture(
            b"def critical_unit():\n    return 'evidence that does not fit'\n"
        )
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "critical-unit",
            AuthorityClass.RUNTIME,
            anchor_hints=("critical-unit",),
            critical=True,
        )
        result = retrieve(
            graph,
            task(byte_budget=8),
            index,
            obligated_facets(obligation),
            snapshot,
            reader,
            expand_one_hop=False,
        )
        self.assertEqual(result.route, "defer")
        self.assertEqual(result.covered_obligation_ids, ())
        self.assertEqual(result.unresolved_obligation_ids, ("critical-unit",))
        self.assertEqual(result.unresolved_critical_obligation_ids, ("critical-unit",))
        self.assertEqual(result.remaining_byte_budget, 8)

    def test_uncovered_obligations_recommend_only_their_source_hints(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "missing-config-fact",
            AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            required_tag_values=("missing-setting",),
        )
        facets = PromptFacetSet(
            "e" * 64,
            tuple(PromptFacet(FacetKind.ENTITY, f"facet-{index}", 1) for index in range(8)),
            proof_obligations=(obligation,),
        )
        result = retrieve(graph, task(), index, facets, snapshot, reader, channels=("exact",), expand_one_hop=False)
        self.assertEqual(result.route, "defer")
        self.assertEqual(result.evidence, ())
        self.assertEqual(result.recommended_fallback_paths, ("src/config.py",))

    def test_geo05_source_only_obligation_never_produces_graph_evidence(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "inspect-runtime-file",
            AuthorityClass.RUNTIME,
            source_hints=("src/auth/token_service.py",),
        )
        result = retrieve(graph, task(), index, obligated_facets(obligation), snapshot, reader)
        self.assertEqual(result.route, "defer")
        self.assertEqual(result.hits, ())
        self.assertEqual(result.evidence, ())
        self.assertEqual(result.recommended_fallback_paths, ("src/auth/token_service.py",))

    def test_geo09_source_hint_restricts_anchor_matching_to_that_path(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "config-anchor",
            AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            anchor_hints=("refresh-token",),
        )
        result = retrieve(graph, task(), index, obligated_facets(obligation), snapshot, reader)
        self.assertEqual(result.route, "defer")
        self.assertEqual(result.hits, ())
        self.assertEqual(result.recommended_fallback_paths, ("src/config.py",))

    def test_geo12_distinct_anchors_do_not_copy_obligations_across_spans(self) -> None:
        graph, snapshot, reader = single_source_fixture(
            b"def first():\n    return 'first'\n\ndef second():\n    return 'second'\n"
        )
        index = build_repository_tag_index(graph, snapshot, reader)
        first = ProofObligation("first-proof", AuthorityClass.RUNTIME, anchor_hints=("first",))
        second = ProofObligation("second-proof", AuthorityClass.RUNTIME, anchor_hints=("absent",))
        result = retrieve(graph, task(), index, obligated_facets(first, second), snapshot, reader)
        self.assertEqual(result.route, "defer")
        self.assertEqual({item.obligation_ids for item in result.evidence}, {("first-proof",)})
        self.assertEqual(result.recommended_fallback_paths, ())

    def test_atomic_alpha_beta_requirement_does_not_cross_functions(self) -> None:
        graph, snapshot, reader = single_source_fixture(
            b"def alpha():\n    return 'alpha'\n\ndef beta():\n    return 'beta'\n"
        )
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "alpha-beta",
            AuthorityClass.RUNTIME,
            anchor_hints=("alpha", "beta"),
        )
        result = retrieve(graph, task(), index, obligated_facets(obligation), snapshot, reader)
        self.assertEqual(result.route, "defer")
        self.assertEqual(result.evidence, ())

    def test_distinct_obligations_in_separate_units_can_succeed(self) -> None:
        graph, snapshot, reader = single_source_fixture(
            b"def alpha():\n    return 'alpha'\n\ndef beta():\n    return 'beta'\n"
        )
        index = build_repository_tag_index(graph, snapshot, reader)
        obligations = (
            ProofObligation("alpha", AuthorityClass.RUNTIME, anchor_hints=("alpha",)),
            ProofObligation("beta", AuthorityClass.RUNTIME, anchor_hints=("beta",)),
        )
        result = retrieve(graph, task(), index, obligated_facets(*obligations), snapshot, reader)
        self.assertEqual(result.route, "graph")
        self.assertEqual({item.obligation_ids for item in result.evidence}, {("alpha",), ("beta",)})

    def test_stale_index_fails_closed_before_evidence_extraction(self) -> None:
        graph, snapshot, reader = single_source_fixture(b"def alpha():\n    return 1\n")
        index = build_repository_tag_index(graph, snapshot, reader)
        shifted = b"# shifted\ndef alpha():\n    return 1\n"
        shifted_graph, shifted_snapshot, shifted_reader = single_source_fixture(shifted)
        obligation = ProofObligation("alpha", AuthorityClass.RUNTIME, anchor_hints=("alpha",))
        result = retrieve(
            shifted_graph,
            task(),
            index,
            obligated_facets(obligation),
            shifted_snapshot,
            shifted_reader,
        )
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "repository_index_custody_mismatch")
        self.assertEqual(result.evidence, ())

    def test_forged_graph_provenance_sha_fails_closed_before_ranking(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        original = graph.records[0]
        forged = replace(
            original,
            provenance=Provenance(original.provenance.path, "0" * 64, "bytes", True),
        )
        forged_graph = Graph((forged, *graph.records[1:]), graph.edges)
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        result = retrieve(forged_graph, task(), index, obligated_facets(obligation), snapshot, reader)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "repository_index_custody_mismatch")
        self.assertEqual(result.hits, ())
        self.assertEqual(result.context, "")
        self.assertEqual(result.evidence, ())

    def test_graph_path_mismatch_fails_closed_before_source_read(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        original = graph.records[0]
        config_sha = hashlib.sha256(reader.sources["src/config.py"]).hexdigest()
        forged = replace(
            original,
            provenance=Provenance("src/config.py", config_sha, "bytes", True),
        )
        forged_graph = Graph((forged, *graph.records[1:]), graph.edges)
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        reader.read_paths.clear()
        result = retrieve(forged_graph, task(), index, obligated_facets(obligation), snapshot, reader)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "repository_index_custody_mismatch")
        self.assertEqual(result.evidence, ())
        self.assertEqual(set(reader.read_paths), set(source.path for source in snapshot.sources))

    def test_fabricated_in_range_tag_value_fails_closed(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        forged_tag = replace(index.tags[0], value="fabricated-anchor")
        forged_index = replace(index, tags=(forged_tag, *index.tags[1:]))
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        result = retrieve(graph, task(), forged_index, obligated_facets(obligation), snapshot, reader)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "repository_index_custody_mismatch")
        self.assertEqual(result.evidence, ())

    def test_fabricated_valid_tag_offset_fails_closed(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        original = next(tag for tag in index.tags if tag.byte_start is not None)
        forged_tag = replace(original, byte_start=original.byte_start + 1, byte_end=original.byte_end + 1)
        forged_tags = tuple(forged_tag if tag is original else tag for tag in index.tags)
        forged_index = replace(index, tags=forged_tags)
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        result = retrieve(graph, task(), forged_index, obligated_facets(obligation), snapshot, reader)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "repository_index_custody_mismatch")
        self.assertEqual(result.evidence, ())

    def test_missing_index_tag_fails_closed(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        forged_index = replace(index, tags=index.tags[:-1])
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        result = retrieve(graph, task(), forged_index, obligated_facets(obligation), snapshot, reader)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "repository_index_custody_mismatch")
        self.assertEqual(result.evidence, ())

    def test_extra_index_tag_fails_closed(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        forged_index = replace(index, tags=(*index.tags, index.tags[0]))
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        result = retrieve(graph, task(), forged_index, obligated_facets(obligation), snapshot, reader)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "repository_index_custody_mismatch")
        self.assertEqual(result.evidence, ())

    def test_clean_index_graph_and_snapshot_custody_succeeds(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        result = retrieve(graph, task(), index, obligated_facets(obligation), snapshot, reader)
        self.assertEqual(result.route, "graph")
        self.assertTrue(result.evidence)

    def test_javascript_function_and_arrow_units_are_complete(self) -> None:
        cases = (
            (b"function handle() {\n  return 'ok';\n}\n\nfunction other() {\n  return 'no';\n}\n", "handle", b"return 'ok';"),
            (b"const handle = () => {\n  return 'ok';\n};\n\nconst other = () => {\n  return 'no';\n};\n", "handle", b"return 'ok';"),
        )
        for content, anchor, expected in cases:
            with self.subTest(anchor=anchor):
                graph, snapshot, reader = single_source_fixture(content, "src/shape.js")
                index = build_repository_tag_index(graph, snapshot, reader)
                obligation = ProofObligation("unit", AuthorityClass.RUNTIME, anchor_hints=(anchor,))
                result = retrieve(graph, task(), index, obligated_facets(obligation), snapshot, reader, expand_one_hop=False)
                self.assertEqual(result.route, "graph")
                self.assertIn(expected, result.context.encode("utf-8"))

    def test_geo19_incomplete_hybrid_fallback_allowlist_fails_closed(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "missing-config-fact",
            AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            required_tag_values=("missing-setting",),
        )
        result = retrieve_hybrid(
            graph,
            task(),
            index,
            obligated_facets(obligation),
            snapshot,
            reader,
            fallback_source_paths=("src/auth/token_service.py",),
        )
        self.assertIsNone(result.fallback)
        self.assertFalse(result.retrieval.fail_closed)
        self.assertEqual(result.retrieval.reason, "no_repository_tag_match")

    def test_critical_hybrid_fallback_uses_only_critical_paths(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        critical = ProofObligation(
            "missing-config-critical",
            AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            required_tag_values=("missing-setting",),
            critical=True,
        )
        noncritical = ProofObligation(
            "missing-runtime-noncritical",
            AuthorityClass.RUNTIME,
            source_hints=("src/auth/token_service.py",),
            required_tag_values=("missing-runtime",),
        )
        result = retrieve_hybrid(
            graph, task(), index, obligated_facets(critical, noncritical), snapshot, reader,
            fallback_source_paths=("src/auth/token_service.py", "src/config.py"),
        )
        self.assertIsNotNone(result.fallback)
        assert result.fallback is not None
        self.assertEqual(result.fallback.route, "direct")
        self.assertEqual(
            result.fallback.projection.required_record_ids,
            ("repo:src/config.py",),
        )
        self.assertNotIn("src/auth/token_service.py", result.fallback.projection.content)
        self.assertEqual(result.retrieval.unresolved_obligation_ids, (
            "missing-config-critical", "missing-runtime-noncritical",
        ))

    def test_critical_fallback_without_source_hint_is_unavailable(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "missing-critical", AuthorityClass.RUNTIME,
            required_tag_values=("missing-critical",), critical=True,
        )
        result = retrieve_hybrid(
            graph, task(), index, obligated_facets(obligation), snapshot, reader,
            fallback_source_paths=("src/auth/token_service.py",),
        )
        self.assertIsNone(result.fallback)
        self.assertFalse(result.retrieval.fail_closed)
        self.assertEqual(result.retrieval.reason, "critical_fallback_unavailable")

    def test_critical_fallback_with_no_remaining_budget_is_exhausted(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        covered = ProofObligation(
            "covered-runtime", AuthorityClass.RUNTIME,
            anchor_hints=("refresh-token",),
        )
        missing = ProofObligation(
            "missing-critical", AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            required_tag_values=("missing-setting",), critical=True,
        )
        large = retrieve(
            graph, task(byte_budget=12000), index,
            obligated_facets(covered, missing), snapshot, reader,
            channels=("exact",), expand_one_hop=False,
        )
        self.assertGreater(large.context_bytes, 0)
        result = retrieve_hybrid(
            graph, task(byte_budget=large.context_bytes), index,
            obligated_facets(covered, missing), snapshot, reader,
            fallback_source_paths=("src/config.py",),
            channels=("exact",), expand_one_hop=False,
        )
        self.assertIsNone(result.fallback)
        self.assertEqual(result.retrieval.remaining_byte_budget, 0)
        self.assertEqual(result.retrieval.reason, "critical_fallback_budget_exhausted")

    def test_fail_closed_retrieval_never_calls_critical_fallback(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        original = graph.records[0]
        forged = replace(
            original,
            provenance=Provenance(original.provenance.path, "0" * 64, "bytes", True),
        )
        forged_graph = Graph((forged, *graph.records[1:]), graph.edges)
        obligation = ProofObligation(
            "missing-critical", AuthorityClass.RUNTIME,
            source_hints=("src/auth/token_service.py",),
            required_tag_values=("missing-critical",), critical=True,
        )
        result = retrieve_hybrid(
            forged_graph, task(), index, obligated_facets(obligation), snapshot,
            reader, fallback_source_paths=("src/auth/token_service.py",),
        )
        self.assertTrue(result.retrieval.fail_closed)
        self.assertEqual(result.retrieval.reason, "repository_index_custody_mismatch")
        self.assertIsNone(result.fallback)

    def test_critical_hybrid_fallback_is_serial_parallel_identical(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "missing-critical", AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            required_tag_values=("missing-setting",), critical=True,
        )
        facets = obligated_facets(obligation)
        serial = retrieve_hybrid(
            graph, task(), index, facets, snapshot, reader,
            fallback_source_paths=("src/config.py",), parallel=False,
        )
        parallel = retrieve_hybrid(
            graph, task(), index, facets, snapshot, Reader(reader.sources),
            fallback_source_paths=("src/config.py",), parallel=True,
        )
        self.assertEqual(serial, parallel)

    def test_direct_fallback_does_not_claim_lexical_obligation_closure(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "missing-config-fact",
            AuthorityClass.CONFIGURATION,
            source_hints=("src/config.py",),
            required_tag_values=("missing-setting",),
            critical=True,
        )
        result = retrieve_hybrid(
            graph,
            task(),
            index,
            obligated_facets(obligation),
            snapshot,
            reader,
            fallback_source_paths=("src/config.py",),
        )
        self.assertIsNotNone(result.fallback)
        assert result.fallback is not None
        self.assertEqual(result.fallback.route, "direct")
        self.assertEqual(result.retrieval.unresolved_obligation_ids, ("missing-config-fact",))
        self.assertEqual(result.retrieval.unresolved_critical_obligation_ids, ("missing-config-fact",))
        self.assertLessEqual(result.fallback.projection.byte_count, result.retrieval.remaining_byte_budget)

    def test_low_facet_v2_uses_obligations_and_preserves_fallback_hints(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation(
            "refresh-runtime",
            AuthorityClass.RUNTIME,
            source_hints=("src/auth/token_service.py",),
            anchor_hints=("refresh-token",),
        )
        result = retrieve(graph, task(), index, obligated_facets(obligation, count=1), snapshot, reader)
        self.assertEqual(result.route, "graph")
        self.assertEqual(result.recommended_fallback_paths, ())

    def test_complete_units_cover_representative_shapes(self) -> None:
        cases = (
            (b"def handle():\n    return 'ok'\n\ndef other():\n    return 'no'\n", "src/shape.py", "handle", b"return 'ok'"),
            (b"class Service:\n    def run(self):\n        return 1\n\nclass Other:\n    pass\n", "src/shape.py", "service", b"return 1"),
            (b'{"setting": {"value": 1}, "other": 2}\n', "config/settings.json", "setting", b'"value": 1'),
            (b"# Policy\nThe policy text.\n\n## Next\nOther text.\n", "docs/policy.md", "policy", b"The policy text."),
        )
        for content, path, anchor, expected in cases:
            with self.subTest(path=path):
                graph, snapshot, reader = single_source_fixture(content, path)
                index = build_repository_tag_index(graph, snapshot, reader)
                obligation = ProofObligation("unit", AuthorityClass.RUNTIME, anchor_hints=(anchor,))
                result = retrieve(graph, task(), index, obligated_facets(obligation), snapshot, reader, expand_one_hop=False)
                self.assertEqual(result.route, "graph")
                self.assertIn(expected, result.context.encode("utf-8"))

    def test_evidence_shape_and_digest_binding_are_observable(self) -> None:
        graph, snapshot, reader = fixture()
        index = build_repository_tag_index(graph, snapshot, reader)
        obligation = ProofObligation("refresh-runtime", AuthorityClass.RUNTIME, anchor_hints=("refresh-token",))
        result = retrieve(graph, task(), index, obligated_facets(obligation), snapshot, reader)
        item = result.evidence[0]
        raw = reader.sources[item.source_path]
        self.assertEqual(item.to_dict()["authority_class"], "runtime")
        self.assertEqual(item.to_dict()["obligation_ids"], ["refresh-runtime"])
        self.assertEqual(item.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(item.excerpt_sha256, hashlib.sha256(raw[item.byte_start:item.byte_end]).hexdigest())

    def test_v1_unanchored_context_remains_bounded_to_800_bytes(self) -> None:
        content = (b"token " * 300) + b"\n"
        graph, snapshot, reader = single_source_fixture(content)
        index = build_repository_tag_index(graph, snapshot, reader)
        facets = PromptFacetSet(
            "0" * 64,
            tuple(PromptFacet(FacetKind.ENTITY, f"facet-{index}", 1) for index in range(8)),
        )
        facets = PromptFacetSet(
            facets.prompt_sha256,
            (*facets.facets[:-1], PromptFacet(FacetKind.ENTITY, "token", 1)),
        )
        result = retrieve(graph, task(), index, facets, snapshot, reader, channels=("sparse",), expand_one_hop=False)
        self.assertTrue(result.spans)
        self.assertLessEqual(result.spans[0].byte_end - result.spans[0].byte_start, 800)


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph, self.snapshot, self.reader = fixture()
        self.index = build_repository_tag_index(self.graph, self.snapshot, self.reader)
        self.facets = compile_prompt(
            "Trace how refresh_token reads token expiry configuration and which tests validate changes",
            self.index,
            semantic_candidates=("authentication", "token", "expiry", "refresh"),
        )

    def test_parallel_and_serial_rank_fusion_are_identical(self) -> None:
        parallel = retrieve(
            self.graph, task(), self.index, self.facets, self.snapshot, self.reader,
            minimum_coverage_percent=0, parallel=True,
        )
        serial = retrieve(
            self.graph, task(), self.index, self.facets, self.snapshot, self.reader,
            minimum_coverage_percent=0, parallel=False,
        )
        self.assertEqual(parallel, serial)
        self.assertIn("src/auth/token_service.py", {hit.source_path for hit in parallel.hits[:3]})
        self.assertTrue(parallel.spans)
        for span in parallel.spans:
            raw = self.reader.sources[self.graph.record_map()[span.record_id].provenance.path]
            self.assertEqual(hashlib.sha256(raw[span.byte_start:span.byte_end]).hexdigest(), span.excerpt_sha256)

    def test_one_hop_does_not_expand_a_second_hop(self) -> None:
        facets = PromptFacetSet(
            "c" * 64,
            (
                PromptFacet(FacetKind.IDENTIFIER, "auth-runtime-owner", 10, True),
                PromptFacet(FacetKind.ENTITY, "absent-one", 1),
                PromptFacet(FacetKind.ENTITY, "absent-two", 1),
                PromptFacet(FacetKind.INTENT, "locate", 1),
                PromptFacet(FacetKind.RELATION, "owns", 1),
                PromptFacet(FacetKind.ARTIFACT, "source", 1),
                PromptFacet(FacetKind.OPERATION, "inspect", 1),
                PromptFacet(FacetKind.CONSTRAINT, "exact", 1),
            ),
        )
        result = retrieve(
            self.graph, task(), self.index, facets, self.snapshot, self.reader,
            channels=("exact",), expand_one_hop=True, maximum_results=3,
            minimum_coverage_percent=0,
        )
        hits = {hit.source_path: hit for hit in result.hits}
        self.assertIn("src/config.py", hits)
        self.assertNotIn("tests/test_token_service.py", hits)
        self.assertLessEqual(max(hit.hop for hit in result.hits), 1)

    def test_no_match_never_selects_an_arbitrary_record(self) -> None:
        facets = PromptFacetSet(
            "a" * 64,
            tuple(PromptFacet(FacetKind.ENTITY, f"absent-{index}", 5) for index in range(8)),
        )
        result = retrieve(self.graph, task(), self.index, facets, self.snapshot, self.reader)
        self.assertEqual(result.reason, "no_repository_tag_match")
        self.assertEqual(result.hits, ())

    def test_tag_match_on_unauthenticated_record_fails_closed(self) -> None:
        poisoned = replace(
            self.graph.records[0],
            trust=TrustClass.AGENT_GENERATED,
            admission=Admission.NONE,
            agent_generated=True,
        )
        graph = Graph((poisoned, *self.graph.records[1:]), self.graph.edges)
        index = build_repository_tag_index(graph, self.snapshot, self.reader)
        result = retrieve(graph, task(), index, self.facets, self.snapshot, self.reader)
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.reason, "tag_match_crosses_authentication_boundary")

    def test_fallback_reads_only_the_explicit_same_snapshot_allowlist(self) -> None:
        result = retrieve_hybrid(
            self.graph,
            task(),
            self.index,
            self.facets,
            self.snapshot,
            self.reader,
            fallback_source_paths=("src/auth/token_service.py", "src/config.py"),
            minimum_coverage_percent=100,
        )
        self.assertEqual(result.retrieval.route, "defer")
        self.assertIsNotNone(result.fallback)
        assert result.fallback is not None
        self.assertEqual(result.fallback.route, "direct")
        self.assertEqual(result.fallback.reason, "required_escalation")
        self.assertNotIn("src/unrelated.py", self.reader.read_paths[-2:])

    def test_identifier_matching_does_not_use_substrings(self) -> None:
        facets = PromptFacetSet(
            "b" * 64,
            (
                PromptFacet(FacetKind.IDENTIFIER, "route", 10, True),
                PromptFacet(FacetKind.ENTITY, "unrelated", 6),
                PromptFacet(FacetKind.INTENT, "locate", 8),
                PromptFacet(FacetKind.RELATION, "owns", 5),
                PromptFacet(FacetKind.RELATION, "declares", 5),
                PromptFacet(FacetKind.ARTIFACT, "source", 5),
                PromptFacet(FacetKind.OPERATION, "inspect", 4),
                PromptFacet(FacetKind.CONSTRAINT, "exact", 4),
            ),
        )
        result = retrieve(
            self.graph, task(), self.index, facets, self.snapshot, self.reader,
            channels=("exact",), minimum_coverage_percent=0,
        )
        self.assertFalse(any("router" in hit.matched_facets for hit in result.hits))


class ProgressiveNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph, self.snapshot, self.reader = fixture()
        self.index = build_repository_tag_index(self.graph, self.snapshot, self.reader)
        self.facets = compile_prompt(
            "Trace how refresh_token reads token expiry configuration and which tests validate changes",
            self.index,
        )

    def test_navigation_returns_exact_previews_without_answer_context(self) -> None:
        result = navigate(
            self.graph, task(), self.index, self.facets, self.snapshot, self.reader,
            channels=("exact", "sparse"), expand_one_hop=True, maximum_results=4,
        )
        self.assertFalse(result.fail_closed)
        self.assertTrue(result.previews)
        self.assertTrue(all(preview.source_snapshot_sha256 == self.snapshot.snapshot_sha256 for preview in result.previews))
        self.assertEqual(result.source_previews, result.previews)
        context = compose_navigation_context(
            result, self.snapshot, self.reader, primary=(result.previews[0],),
        )
        self.assertFalse(context.fail_closed)
        self.assertNotIn("[src/", context.answer_context)
        self.assertEqual(context.context_bytes, len(result.previews[0].text.encode("utf-8")))

    def test_one_hop_candidates_do_not_become_evidence(self) -> None:
        facets = PromptFacetSet(
            "c" * 64,
            (
                PromptFacet(FacetKind.IDENTIFIER, "auth-runtime-owner", 10, True),
                PromptFacet(FacetKind.ENTITY, "absent-one", 1),
                PromptFacet(FacetKind.ENTITY, "absent-two", 1),
                PromptFacet(FacetKind.INTENT, "locate", 1),
                PromptFacet(FacetKind.RELATION, "owns", 1),
                PromptFacet(FacetKind.ARTIFACT, "source", 1),
                PromptFacet(FacetKind.OPERATION, "inspect", 1),
                PromptFacet(FacetKind.CONSTRAINT, "exact", 1),
            ),
        )
        result = navigate(
            self.graph, task(), self.index, facets, self.snapshot, self.reader,
            channels=("exact",), expand_one_hop=True, maximum_results=3,
        )
        self.assertLessEqual(max((hit.hop for hit in result.candidates), default=0), 1)
        self.assertTrue(all(preview.hop == 0 for preview in result.previews))

    def test_context_rejects_unknown_duplicate_stale_forged_and_cross_snapshot(self) -> None:
        result = navigate(self.graph, task(), self.index, self.facets, self.snapshot, self.reader)
        preview = result.previews[0]
        for label, primary in (
            ("duplicate", (preview, preview)),
            ("unknown", (replace(preview, record_id="unknown"),)),
            ("forged", (replace(preview, byte_start=preview.byte_start + 1, byte_end=preview.byte_end + 1),)),
            ("cross", (replace(preview, source_snapshot_sha256="1" * 64),)),
        ):
            with self.subTest(label=label):
                context = compose_navigation_context(
                    result, self.snapshot, self.reader, primary=primary,
                )
                self.assertTrue(context.fail_closed)
                self.assertEqual(context.answer_context, "")

    def test_context_requires_explicit_primary_or_support_selection_and_bounds_roles(self) -> None:
        result = navigate(self.graph, task(), self.index, self.facets, self.snapshot, self.reader)
        empty = compose_navigation_context(result, self.snapshot, self.reader)
        self.assertTrue(empty.fail_closed)
        bounded = compose_navigation_context(
            result, self.snapshot, self.reader,
            primary=tuple(result.previews[:4]), maximum_primary=3,
        )
        self.assertTrue(bounded.fail_closed)

    def test_navigation_custody_mismatch_fails_closed(self) -> None:
        shifted = dict(self.reader.sources)
        shifted["src/config.py"] = b"TOKEN_EXPIRY = 999\n"
        shifted_graph, shifted_snapshot, shifted_reader = fixture()
        shifted_reader.sources = shifted
        result = navigate(
            shifted_graph, task(), self.index, self.facets, shifted_snapshot, shifted_reader,
        )
        self.assertTrue(result.fail_closed)
        self.assertEqual(result.previews, ())

    def test_navigation_preview_bound_is_hard_capped(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 512"):
            navigate(
                self.graph, task(), self.index, self.facets, self.snapshot, self.reader,
                preview_bytes=513,
            )


if __name__ == "__main__":
    unittest.main()
