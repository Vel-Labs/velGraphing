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

The bounded private v2 integration completed. Its result SHA-256 is
`b40d84af3b05d43adcb7bf70130762e8e644f87a1c401cb1bc0b633bbbd11a37`.
The frozen acceptance did not pass. Detailed arm behavior, provider metrics,
selected evidence, and grading details remain only in ignored local artifacts.
This receipt does not reinterpret the frozen grade or establish TTC.

The existing v2 files are sealed by source-free inventory
`result-seal.json`. Its SHA-256 is
`313038939aab0fe2882335d97520a48892e8cbcff166fbcebf3ec47656ad63c8`.
The seal binds 11 pre-existing files by relative path, size, and SHA-256. It
does not modify the completed result. Structural validation confirmed canonical
JSON, exact schema and result identity, sorted unique paths, regular non-symlink
files, exact sizes, and every file hash.

The aggregate authorization is now six calls, all complete. No call is planned.
The final incremental worst-case envelope was USD `0.005505024`. The
aggregate worst-case envelope is USD `0.033030144`. The remaining allowance is
USD `0.966969856`. These are authorization bounds, not observed cost. T030
remains active pending a separate read-only question/rubric alignment audit.

### Exact Candidate Identity

The numeric repair parent is commit
`3d4a979eae1db6a3d682caec1249c5e67d7bfbe4`. The final validation candidate is
commit `3fad08c698f2c8f4c6d47fad8dec0b63f9c0cc1d`. The final recovery candidate
is commit `afaf40ec8b444e5f7ce3a71b29eb2c0d863c69fc`. The final seal candidate is
its direct child with commit subject `chore(jev): seal private v2 result`. The
final child SHA is recorded in the Parent handoff and is independently
recoverable from Git history. This exact chain avoids an impossible self-hash
in this file.

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

- Focused adapter and D-only controller tests: `74` passed.
- Known Jev, selection, benchmark, controller, and projection consumers: `121`
  passed.
- Parity tests in a clean disposable copy: `10` passed.
- Source-package parity: `87` files with candidate SHA-256
  `b8a9d02d2b33f4d44565ac85a86b7f6fe30a460cad442cf2a3e93a110ca60d0e`.
- Two projector runs produced the same package diff SHA-256
  `a239e98de166ee70c9368794c74b0eca963a17015717291833db3308ba2c93df`.
- The private v2 seal and closed plan passed exact hash, inventory, structure,
  and authorization checks.
- `git diff --check` passed.
- The full repository suite was not run. Caller discovery mapped the shared
  parser and its known consumers to the focused and consumer checks above.
- No network, provider, credential, answer, grader, or model lane ran while
  sealing the completed artifact.

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

## Luna Successor Blind-Review Repair (R2, Superseded by R3 Plan)

The blind review returned `REVISE`. This repair resolves each finding without
running the study. S-01 now asks for a source citation and requires
`sorts/quick_sort.py`. It states that `quick_sort` removes a randomly selected
pivot from the input list and that the final mutated list contents are not
deterministic. L-01 now requires citations to both named chapters and separates
case-study assumptions from scalability guidance. M-02 now asks for one
process-documentation choice and one training choice, requires both named
sources, and scores the documented reference slides or LFC193/LFC194 courses.
D-01 is unchanged.

The repaired freeze binds:

- rubric repair commit
  `a14e1de9cdc93047b4ace523b594cd9f468d0c42`;
- ignored candidate SHA-256
  `9f4f1a7c6f4ea466b594c17b8a4181e8df2188f231f93e4bf261fe7c7be17e61`;
- ignored preview SHA-256
  `8cb17603172f1aa4f9faa82ca605ef564db812735c623d40278dd193196769a9`;
- canonical question registry SHA-256
  `61bae17c65b3c6bae59563dabe9d59dc1b0fa801dd44fe1034a34e21c368d4af`;
- canonical rubric manifest SHA-256
  `e1e9665d7136a260ee63f8db46bb833675f396777f9c2dd1c1fff4b50d8b6094`;
- source-free plan SHA-256
  `f0a52844278b3746f37a8c96c65766ca45504f8ed71e0d83af94259a1728ee09`;
- r2 offline preflight receipt SHA-256
  `7e9c94381f85f23f7081a058f0c130fb77f431a05cfa5afb8fa05b43f010a815`.

The final offline preflight regenerated all source-bound inputs and passed. The
M-02 pool and request hashes changed. The other task bindings remained stable.
All B/D selections can still change membership, so eight Jev calls remain
planned. The focused controller checks passed `9` tests. The mapped benchmark,
host, calibration, Jev, and selector suite passed `186` tests. No provider,
model, credential, network, push, or pull-request action ran.

T030 remains active. The blind-review findings are repaired. Parent exact
candidate audit is the current gate.

### Blind-Review Repair Files Changed

- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json`
- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json`
- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`
- `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py`
- `scripts/benchmarks/time_to_correct_luna_successor_v4.py`
- `tests/benchmarks/test_time_to_correct_luna_successor_v4.py`
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

## HISTORICAL/SUPERSEDED: Initial Luna Four-Task Successor Freeze (R1)

This retained block records the initial R1 freeze. Its hashes, run root, and
review gate are not active. The R2 blind-review section above records the
rubric correction. The R3 lane-identity section below records the active
offline freeze.

T030 now has a new study identity:
`velgraphing-v4-luna-four-task-successor-v1`. It does not rescore or replace any
prior question, rubric, result, or model comparison. The four tasks are S-01
exact lookup, D-01 relational retrieval, L-01 synthesis, and M-02 heterogeneous
documents. Each task has Direct/off, Direct/Jev, Graph/off, and Graph/Jev arms.
The answer and independent grader identities are both `gpt-5.6-luna` at medium
reasoning. Absolute model performance is not comparable with the prior Sol
study.

The successor rubric manifest enforces one benchmark-only rule: every required
fact maps to an explicit prompt ask. Incidental facts remain diagnostic. D-01
requires the imported `quick_sort` identity, accurate ascending pivot and
partition behavior, recursive recombination, and duplicate preservation. Its
base case is diagnostic. L-01 no longer scores batch-allocated IDs or buffered
Kafka as required. S-01 and M-02 passed the same explicit-ask mapping check.

The source-free plan is
`benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`, SHA-256
`15b73de20c36f54e4b82d713a9310204b0ce22354128082e59bff404dcbfed06`.
It binds:

- selector and preview adapter commit
  `717f378103f692586647ded6d45fe7c699ba77d5`;
- ignored candidate SHA-256
  `a3b39fea1d189d92e1dd1751e16f64642147383310fa23c41bb8c69449f4ec30`;
- ignored 16-arm preview SHA-256
  `c1c77f0eeb155fdc8ebfde0a407f8f63658313ee36722908660fef1512457d7a`;
- question registry SHA-256
  `3524233a83084a4aacc475eb8678ebb735f6de45fc55ed9795b557302bf702ef`;
- rubric manifest SHA-256
  `9cd4e4c191f2fb1932103f11a544e14f5bdabf83c8271a88bc49f4bcd1a43299`;
- all three source snapshot hashes, the balanced 16-trial dispatch order, exact
  per-arm pool and request hashes, limits, and stop rules.

Offline regeneration reproduced every frozen source-bound candidate, control,
snapshot, and pair identity. Retrieval timing is measured output and is not a
candidate identity field. The offline preview contains all 16 arms. Every B/D
request can change final answer membership, so all eight B/D calls remain
planned. A/C stay treatment-off. No call was eligible for the no-effect skip.
The goal authorization is now 14 calls: six complete and eight planned. The
aggregate worst-case envelope is USD `0.077070336`, leaving USD `0.922929664`
under the existing USD 1 cap. These are authorization bounds, not observed
cost.

The fresh ignored run root is
`$CHECKOUT/.velgraphing-local/retrievel-t030-luna-successor-v1`. Its offline
preflight receipt SHA-256 is
`845da0d220df9ac78b6b3f31be5e89226b2f37a66ea7d97ec0d1f758c1088d18`.
The controller can execute all 16 trials through the existing answer and grader
handoff boundaries and records the existing TTC phases. It rejects answer or
grader model substitutions when host usage identifies the model. The tracked
plan remains `live_authorized=false`; T030 remains active at Parent and blind
rubric review.

The final offline preflight passed after using the retained v4 materialized
public-corpus lane. It regenerated 20 route/task candidate records, validated
16 arm previews, verified paired pools, revalidated source snapshots, enforced
required-evidence preservation, and recorded eight planned Jev calls with zero
retries. The focused controller and host checks passed `17` tests. The mapped
host, generator, preview, legacy controller, calibration, Jev, and selector
consumers passed `185` tests. The full repository suite was not run because the
change is confined to benchmark registration and execution seams; the mapped
suite exercises each changed shared caller. No provider, Luna, answer, grader,
credential, network, push, or pull-request action ran.

### Luna Successor Files

- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json`
- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json`
- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`
- `scripts/benchmarks/time_to_correct_luna_successor_v4.py`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py`
- `scripts/benchmarks/time_to_correct_jev_v4.py`
- `scripts/benchmarks/time_to_correct_host.py`
- `tests/benchmarks/test_time_to_correct_luna_successor_v4.py`
- `tests/benchmarks/test_time_to_correct_host.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`

## Luna Successor Lane Identity Repair (R3, Accepted Candidate)

The exact-candidate audit found that null usage did not prove the Luna/medium
lane. R3 fixes the host boundary without changing sealed historical response
contracts. The successor run command now requires one canonical, source-free
lane manifest. It must contain exactly 32 entries: one answer lane and one
grader lane for each frozen trial. Every entry binds the trial, role, unique
Codex thread, `gpt-5.6-luna`, medium reasoning, canonical argv, and argv hash.
Missing or extra entries, thread reuse, wrong lane identity, and argv hash
drift fail before trial acceptance. Parent will create and bind the actual
threads in this manifest. No thread exists yet.

The successor adds `execution_identity` to each answer and grader output
contract. The host requires exact model, reasoning, role, trial, and thread
identity even when usage is null. Null usage remains unavailable telemetry.
The host does not invent token counts or cost. Legacy controllers keep their
existing output shapes because strict identity is opt-in at the host boundary.

The active R3 freeze binds:

- candidate SHA-256
  `9f4f1a7c6f4ea466b594c17b8a4181e8df2188f231f93e4bf261fe7c7be17e61`;
- preview SHA-256
  `8cb17603172f1aa4f9faa82ca605ef564db812735c623d40278dd193196769a9`;
- lane manifest contract SHA-256
  `46e2e18a102b376cee5df40e7ba205c305a415a37e4e025addc39dc73319b4be`;
- source-free plan SHA-256
  `c9ea95114d6da4cbc36c7c19f6d4d625a1b3122a6542c22e0881ce82076141f8`;
- r3 offline preflight receipt SHA-256
  `08a8583a1945c851473303e466fec9884f04a101c596994501007f4f63e4d3f1`.

The offline preflight regenerated the frozen source-bound inputs and passed.
It retained eight planned Jev calls and made zero provider calls. The focused
host and successor checks passed `22` tests. The mapped benchmark, host,
calibration, Jev, and selector suite passed `190` tests. JSON and YAML
structure checks and `git diff --check` passed. No provider, model, credential,
network, thread, push, or pull-request action ran.

T030 remains active. Parent exact-candidate reaudit is the current gate.

### R3 Files Changed

- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`
- `scripts/benchmarks/time_to_correct_host.py`
- `scripts/benchmarks/time_to_correct_luna_successor_v4.py`
- `tests/benchmarks/test_time_to_correct_host.py`
- `tests/benchmarks/test_time_to_correct_luna_successor_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`

## Luna Successor Live Authorization (R3, Superseded by Clean R4 Restart)

Parent accepted the exact Luna successor candidate at commit
`57ff3e4d7446761336ceb10193598796d96cf993`. The independent Luna audit result
was `PASS`. The tracked plan now has `live_authorized=true` and status
`live_authorized_lane_manifest_pending`.

This transition changes no candidate, preview, question, rubric, lane contract,
dispatch, limit, stop rule, or provider budget. The authorized plan SHA-256 is
`768760e48fd16e8a1d0830f9b8be3f31977f314cc3d700ce24acdfd94416c1df`.
The frozen candidate, preview, and lane contract hashes remain:

- `9f4f1a7c6f4ea466b594c17b8a4181e8df2188f231f93e4bf261fe7c7be17e61`;
- `8cb17603172f1aa4f9faa82ca605ef564db812735c623d40278dd193196769a9`;
- `46e2e18a102b376cee5df40e7ba205c305a415a37e4e025addc39dc73319b4be`.

The current gate is live-lane preparation. The 32 Luna answer and grader
threads and their canonical lane manifest do not exist yet. No provider,
model, credential, network, thread, Jev, benchmark, push, or pull-request
action ran during this transition. Live authorization covers the private local
result only. Public provider results still require separate permission.

After Parent creates and validates the 32-entry lane manifest, the exact
controller command is:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python scripts/benchmarks/time_to_correct_luna_successor_v4.py run --candidates /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-ranked-candidates-a14e1de.json --questions /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json --rubrics /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json --manifests-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests --lanes-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4 --preview /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-jev-preview-a14e1de.json --run-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r3 --lane-manifest /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r3/lane-manifest.json --output /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r3/result.json
```

Authorization-only validation passed `10` focused tests. The strict plan loader
and source-bound preflight accepted `live_authorized=true`, retained eight
planned Jev calls, and reported zero provider calls. JSON, YAML, and diff
structure checks passed.

### R3 Authorization Files Changed

- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`
- `scripts/benchmarks/time_to_correct_luna_successor_v4.py`
- `tests/benchmarks/test_time_to_correct_luna_successor_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`

## R3 Infrastructure Failure and Clean R4 Restart (R4 Attempt, Superseded by R5)

The R3 live run stopped fail-closed. A-S-01 completed. B-S-01 then returned an
incorrect `execution_identity.thread_id` after one Jev call completed. The
controller reported `successor_systemic_trial_failure` and wrote no result.
Parent classified this as a harness or operational lane-identity defect. It is
not product or provider-quality evidence.

The ignored R3 run root is preserved as excluded infrastructure-failure
evidence. R4 does not overwrite, reuse, replay, or retry its B-S-01 Jev call.
R4 starts in the fresh private run root
`$CHECKOUT/.velgraphing-local/retrievel-t030-luna-successor-r4`. The frozen
candidate, question, rubric, preview, dispatch, retrieval, selection, and lane
identity contract are unchanged. The R4 plan remains `live_authorized=true`,
records zero R4 provider calls, plans all eight R4 Jev calls, and permits zero
retries within R4.

The cumulative authorization ledger now records seven completed prior Jev
calls and eight planned R4 calls. The aggregate authorized count is `15`. At
USD `0.005505024` per worst-case call, the prior envelope is USD `0.038535168`,
the R4 incremental envelope remains USD `0.044040192`, the aggregate envelope
is USD `0.08257536`, and USD `0.91742464` remains under the USD 1 cap. These
values are authorization bounds, not observed cost.

The R4 tracked plan SHA-256 is
`a7953a1b37fdbf0afdfc257f86b0dfa00206c2c242d3775966256481a86763a9`.
After Parent creates and validates a fresh 32-entry R4 lane manifest, the exact
controller command is:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python scripts/benchmarks/time_to_correct_luna_successor_v4.py run --candidates /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-ranked-candidates-a14e1de.json --questions /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json --rubrics /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json --manifests-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests --lanes-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4 --preview /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-jev-preview-a14e1de.json --run-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r4 --lane-manifest /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r4/lane-manifest.json --output /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r4/result.json
```

R4 validation passed `10` focused tests. The authorization-aware source-bound
preflight retained the lane contract hash, eight planned calls, and zero R4
provider calls. A canonical comparison excluding only `call_authorization` and
`run_root` matched the accepted R3 plan. JSON, YAML, and diff structure checks
passed.

No lane, thread, credential, network, Jev, provider, model, benchmark, push, or
pull-request action ran while preparing R4. Private execution authorization
does not change the separate public-results permission boundary.

### Clean R4 Restart Files Changed

- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`
- `scripts/benchmarks/time_to_correct_luna_successor_v4.py`
- `tests/benchmarks/test_time_to_correct_luna_successor_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`

## R4 Protocol Boundary and Resumable R5 Restart (R5 Attempt, Superseded by R6)

R4 completed eight trials and four R4 Jev calls. It then stopped fail-closed at
C-L-01 because an identity-correct answer omitted evidence citations. The
controller wrote no result. The ignored R4 run root remains unchanged and is
excluded as a protocol or harness-boundary attempt. It is not provider-quality
evidence.

The changed hypothesis is narrow. A missing citation is answer quality and must
reach the independent grader. A citation that names an ID outside the delivered
evidence remains an authority error and still fails at the host boundary. The
host keeps missing-citation rejection as its backward-compatible default. The
Luna successor alone opts out of that missing-citation error.

R5 reuses `save_completed_trial`, `load_completed_trials`, and the calibration
resumability guard. It writes one canonical receipt after each terminal trial.
On restart, it skips only receipts whose full trial identity and answer and
grader lane identities and candidate-set binding match the current frozen run. It refuses receipt
conflicts and any unreceipted trial directory before new trial work. The Jev
ledger remains capped at eight R5 calls and permits zero retries.

The fresh private R5 run root is
`$CHECKOUT/.velgraphing-local/retrievel-t030-luna-successor-r5`. The cumulative
authorization ledger records `11` completed prior Jev calls: six before the
successor, one in R3, and four in R4. R5 plans eight calls, for `19` aggregate
authorized calls. At USD `0.005505024` per worst-case call, the prior envelope
is USD `0.060555264`, the R5 incremental envelope is USD `0.044040192`, the
aggregate envelope is USD `0.104595456`, and USD `0.895404544` remains under
the USD 1 cap. These are authorization bounds, not observed cost.

The R5 plan remains `live_authorized=true`, records zero R5 provider calls, and
keeps the frozen candidate, question, rubric, preview, dispatch, models,
limits, retrieval, selection, and lane identity contract unchanged. Its
SHA-256 is
`f6ea7a86c46a8f09ea2520061460407ce22c245ccf76c61e5f63a7353245c6fa`.

After Parent creates and validates a fresh 32-entry R5 lane manifest, the exact
controller command is:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python scripts/benchmarks/time_to_correct_luna_successor_v4.py run --candidates /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-ranked-candidates-a14e1de.json --questions /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json --rubrics /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json --manifests-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests --lanes-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4 --preview /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-jev-preview-a14e1de.json --run-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r5 --lane-manifest /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r5/lane-manifest.json --output /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r5/result.json
```

Focused host and successor checks passed `24` tests. The mapped host,
successor, persistence, calibration, retrieval, Jev, and selector consumers
passed `230` tests. Authorization-aware source-bound preflight retained `11`
prior calls, eight planned R5 calls, `19` aggregate calls, zero R5 provider
calls, and the frozen lane contract hash. JSON, YAML, and diff structure checks
passed.

No lane, thread, credential, network, Jev, provider, model, benchmark, push, or
pull-request action ran while preparing R5. Private execution authorization
does not change the separate public-results permission boundary.

### Resumable R5 Restart Files Changed

- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`
- `scripts/benchmarks/time_to_correct_host.py`
- `scripts/benchmarks/time_to_correct_luna_successor_v4.py`
- `tests/benchmarks/test_time_to_correct_host.py`
- `tests/benchmarks/test_time_to_correct_luna_successor_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`

## R5 Transport Encoding Failure and R6 Restart (Current)

R5 stopped after A-S-01. The grader produced semantically valid JSON whose
nested `execution_identity` keys were not in canonical order. Strict handoff
transport rejected the response as `response_invalid`. A-S-01 was persisted as
`measurement_error`, no R5 Jev call occurred, and no result was written. The
ignored R5 run root remains unchanged and is excluded transport-encoding
evidence. It is not product or provider-quality evidence.

The shared handoff `respond` command now has an explicit `--normalize-json`
option. The option reads at most 1 MiB from stdin or from a regular, no-follow
draft file inside the selected lane. It rejects invalid UTF-8, invalid JSON,
non-object JSON, duplicate keys, non-finite numbers, and oversized input or
canonical output. It then serializes with the existing `canonical()` function
and publishes through the existing `write_response` path. Without the option,
`respond` still requires already-canonical bytes. Host schema, execution
identity, citation authority, source, and package checks are unchanged.

R6 retains the R5 completed-trial persistence, resumability, and
missing-citation grading behavior. It changes only the fresh private run root
to `$CHECKOUT/.velgraphing-local/retrievel-t030-luna-successor-r6`. The plan
keeps `11` prior calls, eight planned calls, `19` aggregate calls, zero retries,
and zero R6 provider calls. The prior, incremental, aggregate, and remaining
authorization envelopes remain USD `0.060555264`, USD `0.044040192`, USD
`0.104595456`, and USD `0.895404544`. The R6 plan SHA-256 is
`93a62286e76df28804550248a9052e91500373ca398ea0cd937c6a363a6ff43d`.

After Parent creates and validates a fresh 32-entry R6 lane manifest, the exact
controller command is:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python scripts/benchmarks/time_to_correct_luna_successor_v4.py run --candidates /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-ranked-candidates-a14e1de.json --questions /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-questions.json --rubrics /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/luna-successor-rubrics.json --manifests-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests --lanes-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4 --preview /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-luna-successor-jev-preview-a14e1de.json --run-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r6 --lane-manifest /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r6/lane-manifest.json --output /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r6/result.json
```

For the A-S-01 grader lane, the exact normalized publish command is:

```sh
/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python scripts/benchmarks/time_to_correct_handoff.py respond --run-root /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r6 --trial-id A-S-01 --attempt 0 --lane grader --response-file /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-adaptive-pipeline/.velgraphing-local/retrievel-t030-luna-successor-r6/trials/A-S-01/attempt-0/grader/draft-response.json --normalize-json
```

Focused handoff, host, and successor checks passed `50` tests. The mapped
handoff, host, successor, persistence, calibration, retrieval, Jev, and
selector consumers passed `233` tests. Authorization-aware source-bound
preflight retained `11` prior calls, eight planned R6 calls, `19` aggregate
calls, zero R6 provider calls, and the frozen lane contract hash. JSON, YAML,
plan-identity, and diff structure checks passed.

No lane, thread, credential, network, Jev, provider, model, benchmark, push, or
pull-request action ran while preparing R6. Private execution authorization
does not change the separate public-results permission boundary.

### R6 Files Changed

- `benchmarks/velgraphing-time-to-correct-v4/luna-successor-plan.json`
- `scripts/benchmarks/time_to_correct_handoff.py`
- `scripts/benchmarks/time_to_correct_luna_successor_v4.py`
- `tests/benchmarks/test_time_to_correct_calibration.py`
- `tests/benchmarks/test_time_to_correct_luna_successor_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-high-recall-evaluation.md`

## R16 Operational Timeout Closeout

Hard stop: no R17 and no R16 rerun. The R16 controller stopped
`successor_systemic_trial_failure`. Its terminal `completed/C-M-02.json`
receipt records `measurement_error`, failure stage `answer`, and failure reason
`process_exit_nonzero`. The request was written at
`2026-09-20T08:14:19.378659`. The answer wait timed out at
`2026-09-20T08:17:14.386409` after exactly 175 seconds. The bound Luna draft
completed at `2026-09-20T08:17:16.530970`, about two seconds after the timeout.

The root cause was a Parent operational dispatch error. Parent first gave the
bound lane a duplicate wait command with empty stdin. That command consumed the
frozen timeout. The corrected lane then wrote a valid draft. Parent attested
and published it only after the thread completed, too late for the original
controller. B-M-02 never started. R16 provider/Jev calls: `0`. The cumulative
goal actual Jev call count remains `46`. `result.json` is absent.

The ignored R16 root is retained byte-for-byte as source-free evidence. Its
aggregate custody SHA-256 is
`6f66583f2a620fce5e09d5c80d571425fa42d7e3683f18bd1f80db81062b06ad`,
computed from sorted relative paths and file SHA-256 values across 37 files.
R16 is excluded Parent operational-timeout evidence. It is not product,
provider, or answer-quality evidence.

R12 remains the latest complete 16-trial four-arm result. R15 and R16 are
diagnostic partial runs. T030 is closed unresolved and rejected for promotion.
No Graph+Jev speed, quality, token, or cost claim is supported. The next gate
is branch consolidation and review preparation for T040, not another benchmark.
