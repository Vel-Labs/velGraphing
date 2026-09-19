# T030 TheAlgorithms Canary Receipt

Date: 2026-09-19

Status: the import canary is closed as mechanics-only evidence and rejected for
positive graph value. The dependency-behavior canary has independent labels,
source revalidation, a positive isolated edge-retrieval result, and a frozen
offline Jev preview. T030 remains active at Parent review. No answer, grader,
provider, credential, network, product-core, or live host lane ran.

## Import Canary Outcome

- Study: `velgraphing-v4-thealgorithms-import-canary-v1`.
- Candidate artifact:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-import-canary-afb32bf.json`.
- Selector commit: `afb32bfbbc4aa0e6339a6d795fb1861680cc600a`.
- Candidate SHA-256:
  `76e469b6a10d063c3fca7443100c43635df37a424454185193d7a31d57930a7e`.
- Context-isolated labels:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-import-canary-labels-pristine.json`.
- Evaluator-compatible label SHA-256:
  `96c777d5b6133b7caf24da4d216d46647a93e726dcd3993d76eb894b452ea61b`.
- Pre-Phase-B label SHA-256:
  `346b01ee56204f2a9aba33eb5af734adb9e5d103c8a13fcf2abfdca9c13b6097`.
  Only `schema_version` changed after this hash. The evaluated label artifact is
  schema-compatible, but it is not byte-pristine.
- Result:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-import-canary-eval-pristine.json`.
- Result SHA-256:
  `d318c1723f0babffc1733edc85b4da8c809cb6f346b0a9e1135a3c85199771d0`.
- Provider calls: `0`.

At K=64 and 32,768 bytes, every route had acceptable span-group overlap 1.0,
critical span-group overlap 1.0, zero source failures, and zero authority
failures. Typed Graph versus typed Graph without edges had delta 0.0. The
result confirms candidate-addition mechanics but no positive graph value. It
does not establish semantic fact recall. The evaluator did not independently
revalidate source bytes and did not prove prior oracle isolation.

## Dependency-Behavior Freeze

- Study: `velgraphing-v4-thealgorithms-dependency-behavior-canary-v1`.
- Implementation commit: `79adf45e8ff245c7e90701ea172d8de269228f83`.
- Registry:
  `benchmarks/velgraphing-time-to-correct-v4/thealgorithms-dependency-behavior-canary-questions.json`.
- Registry SHA-256:
  `a6006da0d7b2787a7fbb17e6f5a3f54d5a6409b170962c86e28f44b5bfa47897`.
- Prompt SHA-256:
  `9f78389e75c8157d2aeb78891ee35a80a51337b8f9de8ac1837b10834d71ef59`.
- The prompt does not name `quick_sort`.
- Frozen source snapshot: TheAlgorithms Python
  `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.
- Graph binding: 16 derived edges and one authenticated `imports` relation from
  `repo:sorts/benchmark_sorts.py` bytes 1246-1256 to
  `repo:sorts/quick_sort.py` declaration bytes 253-1296.
- Controls: 64 candidates, 32,768 aggregate excerpt bytes, and 4,096 bytes per
  candidate.
- Artifact:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-dependency-behavior-canary-79adf45.json`.
- Artifact SHA-256:
  `8a75f792aefbabe5679fdfb934e440f723649a5993cb46196d63a437486c9ce7`.
- Artifact size: `215148` bytes.

| Route | Candidates | Excerpt bytes | Relationship candidates |
| --- | ---: | ---: | ---: |
| Direct | 64 | 29,055 | 0 |
| Tag index | 64 | 29,055 | 0 |
| Typed graph | 64 | 30,036 | 1 |
| Typed graph without edges | 64 | 29,055 | 0 |
| Typed graph without expansion | 64 | 29,055 | 0 |

The four control arrays are identical. The target path is absent from Direct
and from the 63 typed primary candidates. The typed primaries equal Direct
minus exactly one displaced optional candidate. That candidate is
`sorts/benchmark_sorts.py` bytes 39-104 and is 65 bytes. Every required
candidate remains. The retained parent is bytes 1217-1256. The relationship
child is bytes 253-1299 and covers the registered target declaration.

## Dependency-Behavior Evaluation

- Context-isolated labels:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-dependency-behavior-labels-pristine.json`.
- Label SHA-256:
  `ca9b6fa14e18a71fd3c92b8b6062b1b369a7a3fa8c81863115964180554f5400`.
- Result:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-dependency-behavior-eval-pristine.json`.
- Result SHA-256:
  `dac799a64e9d5dab95ef71b86bdb22f8038bed1a831a9e58a8edc9f3ca5af7ca`.
- Candidate SHA-256:
  `8a75f792aefbabe5679fdfb934e440f723649a5993cb46196d63a437486c9ce7`.
- Provider calls: `0`.
- Gate 2: `not_applicable`, reason `production_study_required`.

| Route | Acceptable overlap | Critical overlap | Source or authority failures |
| --- | ---: | ---: | ---: |
| Direct | 1/3 | 1/3 | 0 |
| Tag index | 1/3 | 1/3 | 0 |
| Typed graph | 3/3 | 3/3 | 0 |
| Typed graph without edges | 1/3 | 1/3 | 0 |
| Typed graph without expansion | 1/3 | 1/3 | 0 |

At K=64 and 32,768 bytes, typed Graph has a strict acceptable and critical
overlap delta of `+0.666667` against the no-edge arm. The dependency import
overlaps first at rank 60 in every route. The two target-behavior groups first
appear at rank 61 only in typed Graph. This supports the isolated retrieval
hypothesis. It does not establish semantic answer correctness, time, token, Jev,
promotion, or product claims.

## Independent Source Revalidation

- Authorized lane:
  `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4/thealgorithms-python`.
- Lane HEAD: `a381578994d545e44f26afabbd2303746a2dc358`.
- Snapshot SHA-256:
  `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.
- All 149 manifest-selected sources and all 320 candidate rows were
  revalidated against current bytes, lengths, hashes, and ranges.
- Selected-source differences: `0`.
- The lane has 1,521 staged deletions. All are outside the selected manifest.
  This result proves the selected-source boundary only. It does not claim
  global lane cleanliness.

## Offline Dependency Jev Preview

- Adapter commit: `51e2dc70916ecdbe9f90fff8d5a44a4b5f22c714`.
- Source-bearing ignored artifact:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-dependency-behavior-jev-preview-51e2dc7.json`.
- Artifact SHA-256:
  `ac771f605821c720e9a8d6d3e31de56bee6309c0258f1336de4662465ee4c761`.
- Artifact size: `378614` bytes.
- Records: exactly D-01/B/direct and D-01/D/typed_graph.
- Request bytes: `109650` for B and `110662` for D.
- Both records report `jev_call_could_affect_selection: true`.
- Both records passed candidate, registry, manifest, snapshot, source-byte,
  relationship, request-hash, request-byte, and baseline-selection validation.
- Tracked source-free plan:
  `benchmarks/velgraphing-time-to-correct-v4/dependency-behavior-canary-plan.json`.
- Maximum Jev calls: `2`. Retries: `0`. Executed provider calls: `0`.
- Live authorization: `false`.

The source-bearing request bodies, candidate identities, source coordinates,
and provider details remain in the ignored artifact. The tracked plan contains
only hashes, limits, and authority boundaries. The preview does not qualify Jev
model usefulness and is not authority for a live call.

## Model-Payload Allowlist Repair

The answer and independent-grader subprocess inputs now use exact semantic
allowlists. Answer input contains only the question, instructions, and normalized
`id`, `path`, and `excerpt` evidence. Grader input contains only the answer and
the required-fact, critical-fact, and acceptable-span rubric lists. The grader
does not receive the frozen rubric hash. The controller attaches that identity
to the returned grade before validation.

The D-01 host test injected run, trial, arm, route, Jev treatment/status,
request and response hashes, source hashes, scores, probability, confidence,
relationship, call-ledger, provider, and controller-receipt data. Exact
subprocess standard-input assertions proved that none reached either model. The
same assertions proved that the D-01 question, citation instruction, normalized
source evidence, answer, and rubric facts remained.

Focused host and Jev preview tests passed `16/16`. The calibration consumer
tests passed `23/23`. The three changed Python modules passed `py_compile`, and
`git diff --check` passed. No provider, answer-model, or grader-model call ran.

## D-01 Four-Arm Controller Candidate

The exact offline controller candidate is
`scripts/benchmarks/time_to_correct_dependency_v4.py`. It reuses the existing
ranked-candidate generator, ranked-context selector, Jev prepare/evaluate
functions, `LiveJevBudget`, monotonic `Trial`, and allowlisted host boundary.
It does not add a provider adapter or alter product retrieval, Jev, or selection
code.

The real source-only preflight passed against the pinned TheAlgorithms lane:

- A/B Direct pool SHA-256:
  `3c4a9ea12b9f6d49dfe14b791dbe465d72a7948fad95144059ebe55b9a1a71e2`.
- C/D typed-graph pool SHA-256:
  `efa862132c59426bd823aa86e15eebfc43a1aa01923f28aa4a8536be7c1e6c58`.
- B request SHA-256:
  `b63f730ae2e2290a3ab964c170c851c205b6ba28f1df53b9679ea25009a14277`.
- D request SHA-256:
  `ae0bde087faf70dd31d77f6887f5975d98bbe52996e37eb41c98f1ef7b4e47c3`.
- B and D `jev_call_could_affect_selection`: `true`.
- Final answer budget: `16384` bytes.
- Aggregate Jev cap: `2`; retries and repairs: `0`.
- Provider, answer-model, and grader-model calls executed: `0`.
- Live authorization: `false`.

Offline fixtures prove pair identity, treatment-blind model payloads, required
evidence retention, C relationship-child omission, valid D relationship-child
selection, provider fallback to the verified baseline, the two-call ledger cap,
zero retries, stop gates, and complete phase accounting. The focused controller,
host, and preview set passed `21/21`. The full benchmark suite passed `166/166`
with one expected skip. Changed Python modules passed `py_compile`, and
`git diff --check` passed.

The controller records all-in monotonic wall time plus graph construction,
candidate discovery, retrieval/expansion, Jev preparation/provider/revalidation,
response validation, fallback, context composition, answer, and independent
grade phases. Genuine returned usage is retained. Missing token or cost data
stays null. This is an implementation and preflight receipt, not a live result.

### D-01 controller acceptance repair

The controller now binds each trial to restricted lane state SHA-256
`ea86c846cf76908cca63090dccb6db497e4bc98ab5c20cd208b675109462f39d`.
That digest includes the commit, full index, porcelain status, untracked-path
inventory, and selected source snapshot. It includes the pinned staged
deletions and makes no clean-lane claim.

The scanner callback, selection reader, and Jev wrapper now record bytes from
actual source reads. Metadata replay no longer counts as a source operation.
Source coverage fails when any scanner, selection, or Jev read path bypasses its
observer. Source capture and source revalidation remain observed phases. The
four-arm controller stops successor arms when answer or grader model-call
coverage is incomplete, or when answer context-delivery coverage is incomplete,
even if the rubric grade passes.

The execution entry point accepts canonical A/B/C/D argv JSON files only from a
private direct child of this checkout's ignored `.velgraphing-local` root. It
invokes subprocess argv without a shell. It atomically creates `result.json` and
writes up to two `jev-calls/*.json` ledger receipts under the same run root. The
tracked plan still has `live_authorized: false`, so the command stops before it
reads lane commands or starts a provider, answer, or grader process.

Controller preflight elapsed time is recorded separately with
`ttc_allocation: separate_not_in_arm_ttc`. Each Trial wall interval is all-in
only for its arm after preflight. The two pinned Jev calls are far below the
current listed-price $1 allowance. Aggregate accounting now binds one completed
T020 call plus at most two planned D-01 calls. Under the protocol's conservative
price and request-cap rule, the authorization envelope is `$0.016515072` and
the remaining authorization is `$0.983484928`. Provider-reported cost remains
null, actual usage remains ignored/local, and no observed-cost or performance
claim is supported. The protocol retains the price sources and TypeSafe public
benchmark restriction. Comparative Jev results still require separate provider
permission before public pull-request publication.

The focused controller tests passed `9/9`. The scanner, host, and preview
consumer tests passed `25/25`. The full four-arm fixture confirmed paired pool
identity, two Jev calls, zero repairs, ordered completion, and a stop before C/D
after either a systemic B failure or incomplete B coverage. The real offline
preflight matched both pool and request pairs, confirmed B/D selection
sensitivity, and reported zero provider calls. The full benchmark suite ran
`170` tests: `169` passed and one expected test was skipped.

## Validation

- Focused generator and evaluator tests: 35 passed.
- Full benchmark suite: 158 passed with one expected skip.
- Both changed Python scripts passed `py_compile`.
- The offline dependency preview passed strict self-validation at generation.
- Both answer and grader test subprocesses rejected any leaked controller or
  treatment identity in their actual standard input.
- Both registry hashes, exact rows, prompt hash bindings, and `quick_sort`
  exclusions passed.
- In-memory mutation tests reject wrong edge counts, changed control identity
  or count, target-as-primary candidates, parent and child coordinate changes,
  invalid displacement, and required-candidate loss.
- A source-only check confirmed the exact import binding and that the target
  implementation contains the behavior needed by the question.
- The fresh artifact passed strict schema, artifact-hash, source-snapshot,
  five-route, control, candidate-identity, byte-count, edge-count, parent, and
  child invariants. It also passed exact displacement and required-candidate
  retention checks.
- `git diff --check` passed before the implementation commit.
- The context-isolated import labels and result match their delegated hashes.
- The dependency-behavior labels, result, candidate binding, route metrics,
  strict delta, first-overlap ranks, and zero provider-call count match their
  delegated hashes and source-free result.
- Independent source revalidation passed for all 149 selected sources and 320
  candidate rows. The staged-deletion exclusion boundary was checked exactly.

## Preserved Negative Evidence

The Engineering Handbook study `velgraphing-v4-relational-canary-v1` remains
rejected historical evidence. Its attempted freeze failed with
`relational_canary_support_mismatch` because it emitted no relationship
candidate. The import canary is also now rejected for positive graph value.
Neither result is rewritten by the dependency-behavior freeze.

## Files Changed

Dependency-behavior implementation commit:

- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `benchmarks/velgraphing-time-to-correct-v4/thealgorithms-dependency-behavior-canary-questions.json`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py`
- `tests/benchmarks/test_time_to_correct_ranked_candidates_v4.py`
- `tests/benchmarks/test_time_to_correct_retrieval_eval_v4.py`

Receipt commit:

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

Current documentation-only update:

- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

Offline dependency preview implementation:

- `benchmarks/velgraphing-time-to-correct-v4/dependency-behavior-canary-plan.json`
- `scripts/benchmarks/time_to_correct_host.py`
- `scripts/benchmarks/time_to_correct_jev_v4.py`
- `tests/benchmarks/test_time_to_correct_host.py`
- `tests/benchmarks/test_time_to_correct_jev_v4.py`
- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

D-01 four-arm controller candidate:

- `benchmarks/velgraphing-time-to-correct-v4/dependency-behavior-canary-plan.json`
- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `scripts/benchmarks/time_to_correct_dependency_v4.py`
- `tests/benchmarks/test_time_to_correct_dependency_v4.py`
- `tests/benchmarks/test_time_to_correct_jev_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

D-01 controller acceptance repair:

- `benchmarks/velgraphing-time-to-correct-v4/dependency-behavior-canary-plan.json`
- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `scripts/benchmarks/time_to_correct_dependency_v4.py`
- `tests/benchmarks/test_time_to_correct_dependency_v4.py`
- `tests/benchmarks/test_time_to_correct_jev_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

D-01 observed-source and acceptance repair:

- `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `scripts/benchmarks/time_to_correct_dependency_v4.py`
- `tests/benchmarks/test_time_to_correct_ranked_candidates_v4.py`
- `tests/benchmarks/test_time_to_correct_dependency_v4.py`
- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

## Remaining Boundary

The dependency-behavior result proves positive isolated edge retrieval for this
registered question. It does not prove semantic answer correctness, time, token,
Jev usefulness, promotion, release readiness, or product acceptance. T030
remains active. Independent audit issued strict PASS at
`cd238e253b37111a6654fdde49d906b9af4b54bf`. Parent then authorized live
enablement preparation. The tracked plan now has `live_authorized: true`, while
`provider_calls_executed` remains `0` and goal `calls_made` remains `1`. Exact
answer and grader argv files are prepared only in the ignored private run root.
No lane, controller, provider, answer, or grader process ran during preparation.
The exact next gate is lane dispatch followed by controller execution. No
historical PR9 artifact or prior approval-readiness record authorizes a
different call or public result.

The first controller launch stopped in A after preparation and before handoff
request creation. Its Trial recorded `failure_stage: answer`,
`failure_reason: process_exit_nonzero`, and exit code `69`. The empty host
environment resolved relative `python3` to `/usr/bin/python3`, which was blocked
by the local Xcode-license gate. No D-01 provider or model call ran. The
controller now requires each lane command to name an absolute executable whose
resolved target is a real executable file. The preserved ignored argv files use
the existing Homebrew Python.

The next gate is a new controller execution; the failed launch is not a consumed
D-01 provider call.
