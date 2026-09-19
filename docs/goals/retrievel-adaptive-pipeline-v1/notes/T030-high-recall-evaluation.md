# T030 High-Recall Retrieval Evaluation Receipt

Date: 2026-09-19

Status: the frozen high-recall candidate artifact has one independently labeled,
post-hoc span-overlap evaluation. The private D-01 four-arm canary is complete.
Its local artifact remains private. T030 remains active for retrieval and
context redesign. The Parent accepted the bounded offline source-semantics
repair. No answer-validation, provider-performance, or promotion claim is
supported.

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
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/benchmarks/time_to_correct_retrieval_eval_v4.py \
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
- The private relational canary does not establish product correctness.
- T030 remains active for answer validation. No T040 work is authorized by
  this receipt.

## Private D-01 Canary Closure

- Private result SHA-256:
  `bd03bd9944c55c142b1fc00773f1253f79dd4442213c3ab2b31c098b94313286`.
- The artifact remains ignored and private under the provider terms boundary.
- Arm outcomes, grades, provider behavior, selected evidence, usage, and timing
  are not tracked in this public receipt.
- This receipt makes no speed, quality, token, cost, ranking,
  provider-comparison, or promotion claim.

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
T030 remains active for answer validation. No live rerun or T040 work is
authorized.

## Parent Acceptance And Independent Audit

The Parent accepted candidate commit
`dc0fbcd4397e997645de49d831a8c6608f2f3df2` for the bounded offline repair.
The strict detached audit passed with a clean checkout. It confirmed:

- Two-pass projector idempotence.
- Source and package parity for 87 files.
- Package candidate SHA-256:
  `48b65ed3ba9d83e63b724ce2afb395f2fbda156d29adb1b9a194bd9c6564d941`.
- Exact `npm test`: 513 passed and 1 expected skip.

This acceptance covers only the offline code, package, retrieval, and source
semantics. It does not accept an answer, provider result, speed result, or T030
completion.

## Private Observation Replay Gate

The private artifact retains identity data for an exact replay check. The
tracked plan binds the private result and frozen preview hashes without
publishing arm outcomes or provider behavior.

Exact replay is not available. The sealed run has no complete canonical
`velgraphing-jev-observation-v1` envelope. Call receipts and the selected result
prefix do not reconstruct the full ordered observation or prove its complete
source-set and query binding. The replay check therefore failed closed.

No provider, network, credential, answer, grader, or model lane ran during this
check. The next path must remain private, hash-bound, and separately authorized.

The original run remains non-replayable because its complete observations were
not retained.

## Successor Live Confirmation Plan

The private successor was bounded by the tracked plan and aggregate cost cap.
Its arm outcomes, grades, provider behavior, selected evidence, usage, and
timing remain only in ignored local artifacts. No public performance claim is
supported. T030 remains active.

## Private Confirmation Result And Validator Repair

The fresh private confirmation completed. Its result SHA-256 is
`44fc6a9b6f3cade340906195b60105d187be1185975406bd9f12e330d46f10d2`.
Integration validation found a probability-sum compatibility failure in the
canonical adapter. The artifact remains ignored and private. Arm outcomes,
grades, provider behavior, selected evidence, usage, and timing are not tracked
in this public receipt. No product or provider performance claim is established.

TypeSafe's current [Score documentation](https://docs.typesafe.ai/primitives/score)
requires probabilities to sum to 1 and defines the score as the
probability-weighted mean. It does not specify a machine-precision tolerance.
The adapter therefore uses an explicit `0.011` sum tolerance as a local
validation policy. This accepts totals of `0.99` and `1.01` despite binary
floating-point representation. It rejects totals of `0.98` and `1.02`. Exact
keys, finite values in `[0, 1]`, weighted-score
consistency, candidate membership, required IDs, source revalidation, and
fallback behavior remain strict. This policy does not claim that TypeSafe has
a two-decimal response contract.

The smallest private successor is prepared but not executed. It revalidates
and replays the exact private observation with SHA-256
`33bd29d232f461583292ab14a640c2417a7eb55aa254ad43c3571883e2702a76`,
makes one new bounded integration call with zero retries, and runs one fresh
answer lane and one fresh grader lane. The ignored run root is
`$CHECKOUT/.velgraphing-local/retrievel-d01-d-repair-v1`.

With `CHECKOUT` set to this checkout, `PYTHON` set to the trusted project
interpreter, and `LANES_ROOT` set to the retained public corpus lanes, the
controller command is:

```text
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/benchmarks/time_to_correct_dependency_v4.py confirm-d --candidates "$CHECKOUT/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-dependency-behavior-canary-79adf45.json" --questions "$CHECKOUT/benchmarks/velgraphing-time-to-correct-v4/thealgorithms-dependency-behavior-canary-questions.json" --manifests-root "$CHECKOUT/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests" --lanes-root "$LANES_ROOT" --preview "$CHECKOUT/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-dependency-behavior-jev-preview-51e2dc7.json" --run-root "$CHECKOUT/.velgraphing-local/retrievel-d01-d-repair-v1" --answer-argv-json "$CHECKOUT/.velgraphing-local/retrievel-d01-d-repair-v1/answer-argv.json" --grader-argv-json "$CHECKOUT/.velgraphing-local/retrievel-d01-d-repair-v1/grader-argv.json" --replay-observations-root "$CHECKOUT/.velgraphing-local/retrievel-d01-confirmation-v1" --output "$CHECKOUT/.velgraphing-local/retrievel-d01-d-repair-v1/result.json"
```

The aggregate authorization is now six calls: five complete and one planned.
The one-call incremental worst-case envelope is USD `0.005505024`. The
aggregate worst-case envelope is USD `0.033030144`. The remaining allowance is
USD `0.966969856`. These are authorization bounds, not observed cost. T030
remains active.

### Exact Candidate Identity

The numeric repair parent is commit
`3d4a979eae1db6a3d682caec1249c5e67d7bfbe4`. The final validation candidate is
its direct child with commit subject
`test(jev): close confirm-d validation gaps`. The final child SHA is recorded in
the Parent handoff and is independently recoverable from Git history. This
parent-plus-direct-child identity avoids an impossible self-hash in this file.

### Exact Validation Commands

```text
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest tests.core.test_jev tests.benchmarks.test_time_to_correct_dependency_v4
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest tests.core.test_jev tests.core.test_ranked_context_selection tests.benchmarks.test_time_to_correct_jev tests.benchmarks.test_time_to_correct_jev_v4 tests.benchmarks.test_time_to_correct_dependency_v4 tests.scaffold.test_projection_contract
mkdir -m 700 "$CLEAN_ROOT"
rsync -a --exclude .git --exclude .velgraphing-local --exclude __pycache__ --exclude '*.pyc' "$CHECKOUT/" "$CLEAN_ROOT/"
(cd "$CLEAN_ROOT" && PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest tests.parity.test_source_package_parity)
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/package/project_portable_plugin.py --root "$CLEAN_ROOT"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/package/verify_source_package_parity.py --root "$CLEAN_ROOT" --write-manifest
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/package/verify_source_package_parity.py --root "$CLEAN_ROOT"
git diff --check
```

`CLEAN_ROOT` is a fresh disposable copy under the checkout-local ignored
validation area. The active checkout contains ignored private run artifacts in
`.velgraphing-local` and ignored Python bytecode under `packages/core`. The
official verifier fails closed on the bytecode path with
`private_or_machine_path`. The clean copy excludes both ignored trees. It does
not remove or modify the retained private artifacts.

### Validator Repair Validation

- Focused adapter and D-only controller tests: `72` passed.
- Known Jev, selection, benchmark, controller, and projection consumers: `119`
  passed.
- Parity tests in a clean disposable copy: `10` passed.
- Source-package parity: `87` files with candidate SHA-256
  `b8a9d02d2b33f4d44565ac85a86b7f6fe30a460cad442cf2a3e93a110ca60d0e`.
- Two projector runs produced the same package diff SHA-256
  `a239e98de166ee70c9368794c74b0eca963a17015717291833db3308ba2c93df`.
- The offline D-01 preflight reproduced the frozen request, pool, and source
  bindings. The private successor preparation passed its hash and argv checks.
- `git diff --check` passed.
- The full repository suite was not run. Caller discovery mapped the shared
  parser and its known consumers to the focused and consumer checks above.
- No provider, credential, answer, grader, or model lane ran for this repair.

### Validator Repair Files

- `packages/core/jev.py`
- `plugins/graph-engineering/runtime/core/jev.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `scripts/benchmarks/time_to_correct_dependency_v4.py`
- `tests/core/test_jev.py`
- `tests/benchmarks/test_time_to_correct_dependency_v4.py`
- `tests/benchmarks/test_time_to_correct_jev_v4.py`
- `benchmarks/velgraphing-time-to-correct-v4/dependency-behavior-canary-plan.json`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`

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
