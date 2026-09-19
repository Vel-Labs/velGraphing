# T030 Candidate Unit Repair Receipt

Date: 2026-09-19

Status: fresh oracle-blind candidate freeze complete. T030 remains active. No provider, answer, grader, label, or oracle lane ran.

## Result

- The product retrieval path now builds ranked candidates from every bounded matched-facet occurrence.
- Code units, Markdown sections, and prose paragraphs use existing source-unit boundaries. Oversized units use a bounded UTF-8 window without a completeness claim.
- Required candidates come only from caller-declared proof-obligation evidence. Every obligation-bearing evidence item is exact, first, position-locked, and independent of retrieval hits. Invalid or over-budget required evidence fails closed.
- Optional complete units rank before equally matched bounded fallback units. Bounded incomplete units remain eligible.
- Candidate identity, ordering, custody, and limits are deterministic. The materializer takes explicit candidate, aggregate-byte, and unit-byte budgets bounded by the TypeSafe hard limits of 64, 32768, and 4096.
- Candidate retention interleaves retrieval hits. A noisy first source cannot consume the full cap before a later hit.
- Relationship support uses an authenticated graph edge and both endpoint coordinates. Forged and duplicate support fails closed. Parent and child candidate ranges must contain the source and target coordinates.
- The V4 generator now uses one snapshot, index, facet set, retrieval routine, and explicit candidate budget for all routes. Direct remains edge-free. Graph expansion remains source-bound. Candidate schema v2 records limits of 12 candidates, 24576 aggregate bytes, and 4096 bytes per unit; `TaskSpec.node_budget` controls retrieval only.
- The prior S-01 live artifact remains historical and invalid for candidate-quality claims.

## Frozen Candidate Artifact

- Controlled local relative path: `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-ranked-candidates-v2-d03c804.json`
- Selector commit: `d03c80479b84bc00da145f7ead432e5da5ab23d5`
- Candidate schema: `velgraphing-ranked-candidates-v4-bound-v2`
- Artifact SHA-256: `1a3b7ddcef5660a3aed1c4fa2b03c7474e42de8041b4abde6ca051616c0c1c17`
- Artifact size: `586175` bytes
- Run count: `30`
- Candidate budgets: `12` candidates, `24576` aggregate bytes, and `4096` bytes per unit in every route.
- Per-route totals: Direct `72/0`, tag index `72/0`, typed graph `72/0`, typed graph without edges `72/0`, and typed graph without expansion `72/0`, expressed as candidates/relationship supports.
- Source snapshots: CPython `c9f10e2dd66e033dbaeb89ad22d8d95c3b8cec7d4eadb4b96fed6cc8ae572908`; engineering handbook `594aa47760172eba049e18c5f3a2f602a7b96b73a315756876955d7be81cd402`; OpenChain `7b06041a211f9365686f934eb7f37a0646f65ac4866d6837e37714ffb1e7679b`; TheAlgorithms Python `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.
- S-01 contains one exact complete `quick_sort` function candidate from `sorts/quick_sort.py`. Its source-bound range is `1046` bytes. AST and canonical complete-unit checks passed. This proves substantive candidate materialization only, not answer correctness.

The first clean freeze attempt at selector `094d8e962c99a07fda0f30c20aa58edab0ec578e` failed before artifact write. The root cause was an optional lexical match from an extensionless source that the Jev packet contract correctly rejects as `unsupported_source_type`; the materializer had hidden that reason as a custody mismatch. Commit `d03c80479b84bc00da145f7ead432e5da5ab23d5` now skips only optional Jev-incompatible source types. Required incompatibility still fails closed with a distinct error.

## Validation

- Changed-behavior core, planner, generator, and evaluator tests: 44 passed.
- Affected core consumers: 94 passed. Benchmark consumers: 153 passed with 1 skipped. Skill consumers: 35 passed.
- Full declared suites: scaffold 11, core 259, adapters 18, skills 35, benchmarks 153 with 1 skipped, and parity 10. All passed.
- Validation uses the repository venv at `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python` because this worktree intentionally has no local `.venv`.
- Portable projector ran twice with the same projection state.
- Source-package parity passed for 87 files.
- Portable runtime imported `ranked_candidates_from_retrieval`.
- `git diff --check` passed.
- The new regression failed before the fix and passed after it. Focused materializer, planner, generator, and evaluator tests: `125` passed.
- Post-repair consumer suites: core `260` passed; benchmarks `153` passed with one expected skip; skills `35` passed.
- Post-repair projection was idempotent. Package parity passed for `87` files with candidate SHA-256 `36b9747c636dc8df904b582f123b4758eddf0fc0f0e66af04ed684300b7a2099`.
- The generator ran once after the clean repair commit and wrote one exclusive ignored file. Its own strict validator passed before write.
- A separate source-free `validate_candidates` pass confirmed the schema, selector commit, 30-run matrix, identical route budgets, source snapshot bindings, and common-primary invariants.
- A source-bound, label-free S-01 check confirmed the exact complete function range and parsed function body. It printed no source content.

Generation command, with local roots supplied by the operator environment:

```text
PYTHONDONTWRITEBYTECODE=1 "$REPO_VENV" scripts/benchmarks/time_to_correct_ranked_candidates_v4.py \
  --questions benchmarks/velgraphing-corpus-pilot-v1/corpus/questions.json \
  --manifests-root benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests \
  --lanes-root "$LANES_ROOT" \
  --output benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-ranked-candidates-v2-d03c804.json
```

## Remaining Gate

Parent must review and accept this source-free freeze before any answer, grader, label, oracle, or provider lane. The zero relationship-support totals are an observed candidate fact, not a graph-quality conclusion. Keep T030 active until the authorized study result is reviewed and accepted.

## Files Changed

- `packages/core/__init__.py`
- `packages/core/retrieval.py`
- `plugins/graph-engineering/runtime/core/__init__.py`
- `plugins/graph-engineering/runtime/core/retrieval.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py`
- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `packages/core/selection.py`
- `plugins/graph-engineering/runtime/core/selection.py`
- `tests/core/test_retrieval.py`
- `tests/core/test_retrieval_pr9_helpers.py`
- `tests/core/test_ranked_context_selection.py`
- `tests/benchmarks/test_time_to_correct_ranked_candidates_v4.py`
- `tests/benchmarks/test_time_to_correct_retrieval_eval_v4.py`
- `tests/benchmarks/test_time_to_correct_jev_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-candidate-unit-repair.md`
