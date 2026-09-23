# GPT-Pro request: RetrieVel M09 process and product audit

Audit [Vel-Labs/velGraphing PR #18](https://github.com/Vel-Labs/velGraphing/pull/18) and its `codex/retrievel-0.2.0-rc1` branch. Use the companion M09 evidence ZIP if I attach it. The ZIP holds ignored local run receipts that Git does not contain. Start with a read-only audit. Then make focused draft PRs for fixes that the evidence supports. Base each fix PR on `codex/retrievel-0.2.0-rc1`. Do not merge, release, publish a package, or change the frozen trials.

## Goal and authority

The product goal is source-verified repository context that improves answer correctness or time to accepted correctness without hiding missing evidence. M09 compares four frozen configurations on S-01, D-01, L-01, and M-02, with two independent repeats each:

| Arm | Retrieval configuration | Jev configuration |
| --- | --- | --- |
| A | Direct | Off |
| B | Direct | On |
| C | Graph enabled | Off |
| D | Graph enabled | On |

Measure retrieval and Jev separately. A valid result can show no benefit. Keep the same 16,384-byte final context cap, public task questions, source validation, independent grading, and actual route accounting. A Direct fallback in C or D is not a Graph result. Jev configured is not Jev executed. Do not tune selection to make Graph or Jev win. The Parent task owns scope, integration, review, and M09 acceptance. Keep the existing M09 roadmap as the canonical receipt. Do not create another board or duplicate audit ledger.

## Primary evidence

1. Read `AGENTS.md`, `README.md`, `docs/INDEX.md`, `docs/roadmaps/RETRIEVEL_CONTEXT_PLATFORM_ROADMAP.md`, and the current implementation and benchmark contracts. Follow the real installed CLI path from caller to package projection and result validator.
2. Treat the source candidate `4b4f41b015b1d25ff94c67d8dc38d5ec820f89b9` as the R13 tested implementation. Later documentation commits do not change its product identity. R13 contract SHA-256 is `2ed032a360b0a7e389aac063a4cddd49b99adab52ac00b63e557a9693516dad6`; lane manifest SHA-256 is `e3c809849321977a56db5ce170d22d5ec8027be67796276f42a4b410f5a03378`.
3. In the ZIP, start with `evidence/m09-four-arm-repeated-20260923-r13/result.json`, `comparison-contract.json`, `lane-manifest.json`, all 32 completed receipts, and the 16 `jev-calls` receipts. The result SHA-256 is `7a424f9ffb3f365855dd4dcb6fa0e0fc340b6cc32fd1eb5a81e3bcbe9fe492aa`. Use `MANIFEST.json` to verify every ZIP member before relying on it.
4. Inspect `evidence/m09-ac-repeated-20260922-r3` as a sealed A/C-only diagnostic. Its unequal-budget predecessor produced the earlier 86% Graph context increase; do not carry that claim forward. R3's L-01 failures omitted URL-shortener facts. Keep R2 and R3 unchanged.
5. Inspect R7-R12 only to reconstruct process and harness failures. R8 had duplicate unbound answer calls. R9 stopped on an installed Jev binding mismatch. R11 timed out after a delayed relay. R12 dispatched one lane before its request existed. Do not aggregate these partial runs with R13 or retry their lanes.
6. Inspect the D-01 installed canary and the focused regression receipts in the roadmap. The focused and consumer checks had 180 passes and one skip; the historical broad benchmark suite had 27 errors and one failure in frozen successor hash validation. Determine whether each red check is a current defect, a historical binding check, or a test defect. Do not rewrite sealed evidence merely to make it green.

## Questions to answer

1. Rebuild the R13 table from raw receipts. Confirm pass counts, actual Direct/Graph routes, selector fallback reasons, mean end-to-end wall time, serialized answer-request bytes, Jev attempts/reranks/source acceptance, retry count, and reported token/cost data. State each metric definition and each unavailable field.
2. Explain why all 16 C/D trials selected Direct. Trace graph candidates, verified relationships, Direct-preservation guard, context selection, and installed output for representative S-01, D-01, L-01, and M-02 trials. Distinguish a useful Graph candidate that cannot fit from a graph with no useful relationship gain.
3. Trace D-01 and L-01 failures through public question, candidate pool, selected context, final answer, independent grade, and source. Classify each cause as retrieval, answer, Jev, harness, execution integrity, measurement, or environment. Do not label product failures as harness failures.
4. Decide what the evidence establishes about Jev. R13 reports 16 observed Jev calls, 16 reranks, and 16 source validations, with 447,264 reported input and 12,448 output tokens. Answer/grader token and all monetary cost data are unavailable. In particular, explain why accepted Jev reranks did not repair D-01 and L-01.
5. Audit the entire M09 process. Name the earliest point where each preventable failure could have been caught, the minimum durable correction, and which controls caused unnecessary delay. Separate execution-custody defects from product defects. Do not add more benchmark versions, boards, or gates without a concrete failure they prevent.
6. Assess whether the current candidate satisfies the product-adoption gate. A completed four-configuration policy study with 0/16 actual Graph routes is not a measured Graph-route advantage. State whether M09 can close as a negative policy study and what separate, source-verified experiment would be needed for an actual Graph route claim.

## Deliverables

First, return a detailed audit with a concise executive verdict, a chronology, a corpus-by-arm result table, exact evidence pointers and hashes, root causes with confidence levels, contradictions or missing evidence, and a prioritized implementation plan. Include a decision table that separates harness repair, product repair, measurement repair, and no change. Cite exact files and trial IDs. Challenge weak assumptions in the roadmap and PR #18 description.

Then create the smallest useful set of **draft PRs**, each from a fresh branch based on `codex/retrievel-0.2.0-rc1`. Use one coherent defect or product hypothesis per PR. Each PR must state the observed failure, actual caller and installed path, source change, focused tests, installed CLI canary result, regression risk, and the next evidence needed. Do not force Graph selection, add grader-only facts, add benchmark-specific exceptions, or weaken the Direct fallback guard to improve a score. Do not rerun a full provider benchmark until a changed source hypothesis passes a public-question canary on D-01, L-01, and one unaffected case. Keep PRs unmerged for Codex Parent review. If GitHub write access is unavailable, provide exact reviewable diffs and draft PR bodies instead of claiming PR creation.
