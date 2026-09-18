# PR9 frontier audit and bounded successor experiment

Status: work in progress on an isolated stacked branch. Not an acceptance certificate.

## 1. Executive verdict

Accept PR9 as a sealed measurement baseline, not as proof that Graph + Jev improves correctness, context, or time to correct. Do not merge or promote this successor yet. Zero live TypeSafe calls are authorized or executed by this audit.

The independently inspected code shows three separate bottlenecks: the public scanner creates no typed edges; the packet adapter retains only the first source span per file; and the answer byte budget is applied before Jev. The last mechanism makes paired answer-byte reduction impossible under the frozen v3 treatment. Adding edges alone cannot repair span loss or missing evidence.

## 2. Candidate identity and checkout status

PR9 head: `6931f0ffa72bd27f79f5515bd669404dbc4667d0`; base: `031a8390ae3accce7fe4b3756f01f98f2c606ee6`; source tree: `c7410852ffa45d56d59c972578f9f918b60291aa`; package 0.1.6. The new branch starts at that exact head. The audit container cannot clone GitHub because DNS resolution fails. Connector reads and branch writes work. Local materializations are not represented as a full original checkout. Existing CI will validate the actual repository candidate.

## 3. Exact PR9 validation reproduced

Remote baseline workflow 35400601662 is successful on Python 3.11 and 3.13. Its merge-preview commit 522040b120fa81861170f443aac64b5f70dab917 has the same tree as the assigned head. Inspected 3.11 logs report scaffold 11, core 229, adapters 18, skills 29, benchmarks 92 with one corpus-dependent skip, and parity 10. These are baseline CI observations, not new-candidate results. The previously reported local all-pass counts have not been relabeled as this audit's execution.

## 4. Current product and benchmark call graphs

`graph-find._scan -> Graph(file records, edges=()) -> core.graph_find -> tag index -> retrieve -> exact source pointers -> v3._graph_pointers(first span per file) -> _capture(answer cap) -> optional Jev permutation -> compose_answer_payload -> fresh answer -> independent grader`.

Core already has typed GraphEdge, one-hop retrieval expansion, authenticated selection, source-coordinate verification, hybrid assistance and V5 bounded navigation. `packages/core/graph.py` is not a tracked implementation file; graph data types live in `models.py`. V5 symbol hopping and legacy whole-file assistance are not a universal document relationship graph.

## 5. Research review with source-to-design mapping

Primary sources inspected on 2026-09-18 include TypeSafe's official skill, API, model list, advanced questions, confidence, routing, reranking, passage classification and citation checking; RepoGraph, CodexGraph, Code Graph Model, Microsoft GraphRAG, HippoRAG, RAPTOR, WildGraphBench, BRINK and Dissecting GraphRAG. Detailed source-to-design mapping will be completed with the evaluation. TypeSafe documentation still identifies jev-1.13.0 as stable. Shared-state questions cannot read one another's answers. Distribution confidence is not evidence completeness. Simple Jev explicitly does not establish equivalence to TypeSafe architecture, training, calibration, accuracy or speed.

## 6. Claim-to-evidence matrix

Supported: v3 measures a tag-index treatment, preserves paired candidate membership and answer bytes, and cannot recover omitted evidence by permutation. Unresolved: successor recall, semantic candidate quality, held-out calibration, graph utility, all-in cost and time-to-correct benefit.

## 7. Layer-by-layer causal diagnosis

Retrieval coverage, adapter span loss, pre-rerank budget placement, missing adaptive recovery and host timing are distinct layers. The observed 31.4% lower D-vs-B Jev input is not a Jev-induced answer-context saving. Sub-half-second provider intervals do not explain hundred-second terminal wall times. The A-C-02 grader timeout contaminates A's mean. One repetition does not identify stochastic latency effects. Detailed causal rows remain pending in this draft.

## 8. Findings ranked P0 through P3

P1: low-recall fixed candidate treatment and first-span-per-file loss prevent a fair test of the intended architecture. P1: pre-Jev final packing provides no context-reduction lever. P2: the public scanner supplies no relationships despite stronger canonical traversal seams. P2: the v3 citation regex can misclassify Markdown brackets as candidate citations; an empty matching source can abort Direct selection. These latent harness issues are not asserted to explain the recorded grader timeout. No new P0 finding is established.

## 9. Architecture alternatives and decision

Select Alternative 1 for an opt-in falsifiable slice: source-bound seeds, witnessed relationships, one existing core selection hop, multiple exact source units, one optional Jev rerank, deterministic required-evidence/diversity packing, exact source revalidation. Keep Direct explicitly graph-disabled. Reject early Jev-guided expansion for this slice because it adds an uncalibrated routing dependency and potentially a second approval/call. Defer the full task-shape/hierarchical architecture until adapter-specific utility is demonstrated.

## 10. Files changed and why

The new benchmark adapter and public-fixture tests do not modify canonical core, the portable plugin, the provider adapter, or sealed v1-v3 files. The CI adjustment runs the requested focused pattern and write-manifest parity check; a branch-limited three-day tracked-source artifact supports this authorized review without including .git, a credential store or a runtime environment.

## 11. Tests and exact results

Local isolated fixtures: PackingTests 13 passed; RelationshipTests 8 passed. They use the exact canonical models.py blob 863d304e0d3e2cca3028984a8ae128a55ef40850. Four actual-core integration tests are added but not yet executed in this draft. The full suite can find shared-core, host, source-custody and package-projection failures that isolated packing/extraction tests cannot. Do not reuse baseline counts after a material change.

## 12. Retrieval-only evaluation and ablations

Pending actual frozen-corpus execution. The six known tasks are development cases, not held-out confirmation. Selection has no oracle argument or filesystem discovery; the independent evaluator alone may load labels after candidate production. Graph-disabled, edge-disabled and expansion-disabled behavior must be separately reported. Nonzero edges are not a quality metric.

## 13. Jev rubric and calibration status

The existing evidence-usefulness-v1 rubric remains unchanged. No new semantic Jev quality or calibration claim is made. Atomic relevance, evidence, contradiction and instruction-risk judgments require separate labels and calibration before adoption. Retained v3 observations cannot be replayed against a changed request hash.

## 14. Two-task canary packet and unspent provider budget

Not authorized and not executed. Proposed C-02 plus a different-corpus critical-evidence case, four arms, at most four Jev calls with zero retries, eight answer lanes and eight graders. Exact requests, final candidate and approval hashes must be frozen first. Current decision: NO-GO pending offline gates.

## 15. Held-out confirmation plan

Reserve new independently authored tasks spanning code dependency/API behavior, exact local lookup, cross-document synthesis, long singular-document hierarchy and mixed authority. Keep labels outside selection. Repeated paired trials are required for stochastic timing or answer-quality claims. No confirmation provider budget has been spent.

## 16. Claims now supported

The new isolated controller fixtures preserve caller-required units, reject stale or out-of-scope source, allow multiple same-file units, and demonstrate that selection after ranking can change a bounded optional subset. These are structural claims only.

## 17. Claims still prohibited

No corpus recall gain, semantic sufficiency, Jev calibration, all-in token or cost reduction, faster correct answers, universal graph advantage, or acceptance-ready product is established by this draft.

## 18. Remaining risks and next owner

The local Parent owns integration, acceptance and any exact-scope live approval. This PR must remain unmerged while retrieval ablations and final-candidate validation are pending. The canonical report will record those outcomes rather than substituting this draft or chat history for evidence.
