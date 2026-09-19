# T030 Candidate Unit Repair Receipt

Date: 2026-09-19

Status: implementation and fixture proof complete. T030 remains active. No public-corpus benchmark or provider call ran.

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

## Validation

- Changed-behavior core, planner, generator, and evaluator tests: 44 passed.
- Affected core consumers: 94 passed. Benchmark consumers: 153 passed with 1 skipped. Skill consumers: 35 passed.
- Full declared suites: scaffold 11, core 259, adapters 18, skills 35, benchmarks 153 with 1 skipped, and parity 10. All passed.
- Validation uses the repository venv at `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python` because this worktree intentionally has no local `.venv`.
- Portable projector ran twice with the same projection state.
- Source-package parity passed for 87 files.
- Portable runtime imported `ranked_candidates_from_retrieval`.
- `git diff --check` passed.

## Remaining Gate

Freeze a fresh, label-isolated offline candidate artifact from the repaired committed selector before any public-corpus study. Keep T030 active until the Parent reviews and accepts that artifact and the authorized study result.

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
