# T030 High-Recall Retrieval Evaluation Receipt

Date: 2026-09-19

Status: the frozen high-recall candidate artifact has one independently labeled,
post-hoc span-overlap evaluation. The private D-01 four-arm canary is complete.
All four correctness grades failed. T030 remains active for retrieval and
context redesign. No promotion claim is supported.

## Bound Inputs

- Candidate artifact:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-high-recall-ranked-candidates-38eb61e.json`.
- Candidate SHA-256:
  `42d14d8daa02c92a2483f68f67b0d37d8fed2116779c6496a61a6b78159eaa24`.
- Independent labels:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-span-labels-v4-independent.json`.
- Label SHA-256:
  `3117d53481275d077553c3ac377684d177d17e5e235392463ae75ca47e9487ba`.
- Selector commit: `38eb61ed76990abab8189f084428fb50afb037c3`.

## Evaluation Command

```text
PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python scripts/benchmarks/time_to_correct_retrieval_eval_v4.py \
  --candidates benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-high-recall-ranked-candidates-38eb61e.json \
  --expected-candidates-sha256 42d14d8daa02c92a2483f68f67b0d37d8fed2116779c6496a61a6b78159eaa24 \
  --labels benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-span-labels-v4-independent.json \
  --output benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-high-recall-retrieval-eval-38eb61e.json \
  --k 4 6 12 24 32 64 \
  --byte-budgets 8192 16384 24576 32768
```

The evaluator used exclusive file creation. It validated the candidate hash
before decoding labels. It produced 720 source-free diagnostic rows.
The high-recall evaluation itself made no provider, answer, grader, credential,
or network call.

## Result Artifact

- Path:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-high-recall-retrieval-eval-38eb61e.json`.
- SHA-256:
  `57dd7134764c73628274323137d0b9e5961a43feca0a139c328dd862c4bd2b49`.
- Size: `681444` bytes.
- Provider calls: `0`.
- Gate 2 status: `not_applicable`.
- Gate 2 reason: `production_study_required`.

## Registered Point

The registered high-recall point is K=64 with a 32,768-byte prefix budget.
Direct, typed graph, and typed graph without edges produced the same values.

| Task | Acceptable span overlap | Critical span overlap |
| --- | ---: | ---: |
| C-01 | 0.60 | 0.50 |
| C-02 | 0.80 | 1.00 |
| S-01 | 1.00 | 1.00 |
| L-01 | 0.00 | 0.00 |
| M-01 | 0.75 | 0.50 |
| M-02 | 0.50 | 0.50 |

Every registered Direct, typed graph, and no-edge row recorded zero source
failures and zero authority failures. Edge-enabled and no-edge equality means
this evaluation shows no positive graph value.

The macro critical span-overlap value is 0.5833. The prior frozen macro value
at K=12 and 24,576 bytes was 0.25. This is a descriptive increase in path/range
overlap from about 0.25 to about 0.58. It is not semantic correctness, graph
value, Jev value, token reduction, speed, promotion, or product acceptance.

## Remaining Boundary

- Semantic fact recall and candidate NDCG remain unknown.
- The evaluator did not independently revalidate candidate source bytes.
- The evaluator does not prove prior oracle isolation by itself.
- The private relational canary completed but failed correctness in every arm.
- T030 remains active for Parent review. No T040 work is authorized by this
  receipt.

## Private D-01 Canary Closure

- Private result SHA-256:
  `bd03bd9944c55c142b1fc00773f1253f79dd4442213c3ab2b31c098b94313286`.
- All source, model, context, and answer-boundary coverage completed.
- All four correctness grades failed.
- Two permitted Jev calls were consumed. No retry ran.
- The evidence remains private and internal under the provider terms boundary.
- Timing was contaminated. This receipt makes no speed, quality, token, cost,
  ranking, provider-comparison, or promotion claim.
- The live authorization is closed. The next gate is retrieval and context
  redesign with offline proof before any broader live run.

## Offline Source-Semantics Repair

The bounded offline repair is complete. Ranked selection still records selected
candidate IDs and Jev telemetry in effective rank order. Model-visible spans now
keep the first-seen file-group order and exact byte order within each file.
Each span includes source coordinates, source identity, and the existing direct
relationship-parent marker.

Relationship parents and direct children now enter or leave optional context as
one bundle. A required parent adds one deterministic direct child. If that
required bundle does not fit, selection uses the existing fail-closed path.
Required IDs do not change. Invalid or stale Jev observations still use the
verified baseline.

The D-01 answer boundary now preserves the allowed source metadata. It tells the
answer lane to infer source adjacency only from matching paths and byte
coordinates. Arm, treatment, provider, score, and request fields remain outside
the model-visible payload.

Validation:

- Focused core, answer-boundary, D-01, and Jev tests: 45 passed.
- Known retrieval, graph-core, candidate-generator, and retrieval-evaluator
  consumers: 165 passed.
- The frozen D-01 preview passed legacy compatibility validation.
- The portable projector was idempotent after the canonical projection.
- Package parity passed for 87 files with candidate SHA-256
  `48b65ed3ba9d83e63b724ce2afb395f2fbda156d29adb1b9a194bd9c6564d941`.
  The parity check used a clean disposable copy because an ignored bytecode
  cache in the worktree is outside the package contract.
- No provider, model, network, credential, answer, or grader call ran.

This is retrieval and context-composition proof only. It does not prove answer
correctness, performance, provider value, promotion, or product acceptance.
T030 remains active for Parent review. No live rerun or T040 work is authorized.

## Files Changed

- `packages/core/selection.py`
- `plugins/graph-engineering/runtime/core/selection.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `scripts/benchmarks/time_to_correct_host.py`
- `scripts/benchmarks/time_to_correct_jev_v4.py`
- `scripts/benchmarks/time_to_correct_dependency_v4.py`
- `tests/core/test_ranked_context_selection.py`
- `tests/benchmarks/test_time_to_correct_host.py`
- `tests/benchmarks/test_time_to_correct_dependency_v4.py`
- `tests/benchmarks/test_time_to_correct_jev_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
