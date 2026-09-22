# T070 execution approval transition

## Status

Materialized the explicit final user re-ack into the successor artifacts. No
nested task, answer, grader, Jev, or provider call ran. No credential or
network access occurred. `execution_ready` is true. No commit was created.

Candidate HEAD before this transition: `067b6d27f36260c6c1fa7b7289016a68244748dd`.

```text
verified custody and pool -> frozen manifest -> exact final user re-ack materialized
                                      no tasks created; live_lanes_created = 0
```

## Financial authority

The operator supplied this TypeSafe account snapshot:

- Total authorized budget: USD `1.0000`.
- Spend reported to date: USD `0.0969` across 108 calls and 2,371,440 tokens.
- Remaining authorized budget: USD `0.9031`.
- Maximum additional spend for this batch: USD `0.9031`.
- Source status: operator-provided; not provider-verified by this process.

The eight-call cap and zero-retry rule are separate batch controls. Request
bytes identify the frozen request set. They do not estimate cost. The earlier
USD 1.00 additional-spend value is superseded.

The historical request-byte `total_reservation_usd` of USD `0.359789241` is
retired and historical-only. It is not spend, was not charged, must not be
subtracted again, and is not attributable to the operator-reported account-level
USD `0.0969`. Successor planning uses USD `0.9031` remaining and maximum
additional spend, with the separate eight-call and zero-retry batch controls.

The successor freeze status is `ready_after_final_user_reack`. The exact
request hash, eight-call cap, approved maximum additional spend, lane manifest
hash, and Python executable matched the frozen values. The v1 schema has no
approval-receipt field, so the transition is bound by its ready status,
cleared re-ack list, and regenerated freeze/preflight hashes only.

## Frozen lane plan

- Run root: `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.velgraphing-local/velgraphing-four-arm-study-v1/retrievel-0.2.0-rc1-t070-r1`.
- Python executable: `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python`.
- Canonical lane-name mapping: `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.velgraphing-local/velgraphing-four-arm-study-v1/retrievel-0.2.0-rc1-t070-r1/lane-bindings.json`.
- Lane-name mapping SHA-256: `8957d586f1c931757a40a825ba38cda43fe4c6adf5c05cd7bb4d9de33f81432e`.
- Frozen lane manifest: `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.velgraphing-local/velgraphing-four-arm-study-v1/retrievel-0.2.0-rc1-t070-r1/lane-manifest.json`.
- Manifest SHA-256: `57d444a0a8ea252433e5d69140c9677685878c9956576dd55a1c2df05406a0fa`.
- Entry counts: 32 total; 16 Luna answer lanes and 16 Astra grader lanes.
- Naming pattern: `t070_r1_luna_answer_<trial-id>` and
  `t070_r1_astra_grader_<trial-id>`. Convert trial letters to lowercase and
  trial-ID hyphens to underscores.
- All 32 planned identifiers are unique and follow the frozen dispatch order.

The manifest's `thread_id` field stores a canonical collaboration `task_name`,
not an opaque host-issued thread ID. Before response capture or attestation,
Parent must verify that `spawn_agent` returned a `task_name` that exactly
matches the planned manifest name. Keep any opaque host ID separate. A
mismatch stops capture and attestation; any corrected name requires a new
manifest and final re-ack for its new hash. No task was created for this freeze.

## Bound artifacts

- Request-byte-set SHA-256: `80b3411f0d30600bc302a59debe36fe66734e4aceca0da6afdae303dc096af94`.
- Per-batch Jev cap: 8 calls; retries: 0.
- Maximum additional provider spend: USD `0.9031`.
- Successor freeze SHA-256: `a442afb5fea8529e2979435dd09877207c2a9ba30d53f0c85198c622a7bd86d0`.
- Successor preflight SHA-256: `23a14866597f20a204ffc6df598bd62ccb1269e2d48364c2c4eef63d82160e66`.
- Ignored pool artifact SHA-256: `3721b7378848d024e073cfa67bce44249b62551835ce236c22837119fee16d7b`.
- Controller SHA-256: `92c4783c4f81b5768e26394119947199207bea278b675f29038fc37f2343c930`.
- Successor rubric canonical SHA-256: `91799682531977718ffe75cce4b0674b7b4193f54cb528d7475f431fdd913083`.
- Successor rubric file SHA-256: `d20a63a1a46f3d5e855862fe9b3fa36c6859178506de5a6900f67553d6b75e35`.
- Successor TTC contract canonical SHA-256: `87ac7ef1ad996052f856564ff02b96db4e43843f3086741607971c47b0ded8da`.
- Successor TTC contract file SHA-256: `d25290d05f1719d4082e16fca036c09b1ae7138ccfa287ba63ccc2959b796ef9`.
- Contract status: `ready_after_final_user_reack`.
- Remaining re-ack fields: none.

## Validation

- `freeze-successor --refresh` against
  `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4`: passed after validating all three bound source snapshots. It bound the updated controller, reservation reconciliation, account snapshot, request set, and pool hashes. It recorded zero executed calls and zero retries.
- `prepare-successor-execution` against pinned local v4 lanes: passed in the
  earlier T070 preparation and regenerated the ignored pool file. This refresh
  left that file unchanged; `freeze-successor --refresh` rederived the pools
  from the pinned lanes and matched the same bound pool SHA.
- `freeze-lanes --refresh` with the specified run root, Python path, updated
  bindings, pool, and custody: passed. It replaced the prior planned-name
  manifest and froze 32 unique canonical task names; it created no tasks.
- `approve-successor` with the exact user-approved request hash, eight-call cap,
  USD `0.9031` maximum additional value, manifest hash, and Python executable:
  passed. It made no calls and changed only the successor contract, freeze, and
  preflight artifacts.
- `validate-successor-overlay`: passed. It reports eight planned Jev calls,
  the frozen manifest hash, zero live lanes created, and `execution_ready: true`.
- Historical `validate --lane-manifest`: passed. Direct binding checks passed:
  32 names match their answer/grader bindings exactly, are unique, and use only
  lowercase ASCII letters, digits, and underscores. The contract SHA matches
  the regenerated manifest.
- Focused benchmark tests: 33 passed, 2 skipped. Coverage now checks the
  approval transition, mismatch no-write behavior, canonical task-name rule,
  refresh overwrite guard, manifest semantics, and historical-reservation
  reconciliation.
- `git diff --check`: passed.
- GoalBuddy `state.yaml` syntax check with Ruby YAML: passed.
- `run --help`: passed; it exposes `--approved-max-additional-provider-spend-usd`.
- `git diff --exit-code` for historical `freeze.json` and `preflight.json`: passed; both remain unchanged.
- Historical `freeze.json` and `preflight.json` diff check: passed; both remain unchanged.
- Historical `freeze.json` and `preflight.json`: unchanged.
- Package parity was attempted but refused with `private_or_machine_path` on
  an ignored `__pycache__` path in the checkout inventory. No package files
  changed; this is a parity-harness/environment issue, not a T070 artifact
  result.

## Files changed

- `benchmarks/velgraphing-four-arm-study-v1/PROTOCOL.md`
- `benchmarks/velgraphing-four-arm-study-v1/successor-rubrics.json`
- `benchmarks/velgraphing-four-arm-study-v1/successor-ttc-contract.json`
- `benchmarks/velgraphing-four-arm-study-v1/successor-freeze.json`
- `benchmarks/velgraphing-four-arm-study-v1/successor-preflight.json`
- `scripts/benchmarks/four_arm_study_v1.py`
- `tests/benchmarks/test_four_arm_study_v1.py`
- `docs/goals/retrievel-release-v1/notes/T060-study-freeze.md`
- `docs/goals/retrievel-release-v1/notes/T070-study-execution.md`
- `docs/goals/retrievel-release-v1/state.yaml`

The ignored T070 run root contains the updated `lane-bindings.json` and
regenerated `lane-manifest.json`. The board file had pre-existing local
changes and now also records this approval transition.

## Launch repair after two refused starts

The first start refused a stale successor lane state. The second start exposed
`single_answer_grade_required`. No answer, grader, Jev, or provider call ran in
either attempt.

The second message masked the actual preparation failure. Direct inspection of
the returned trial showed `answer_evidence_order_invalid`. The selector chose
11 of 64 source-bound candidates, but the answer packet still contained all 64.
The answer composer correctly refused the inconsistent packet before dispatch.

Commit `06cd219` repairs the packet boundary. The verified fallback now returns
only the selected shortlist plus any required fallback witnesses. It also
preserves the recorded preparation failure instead of replacing it with the
generic answer-and-grade postcondition.

The replacement ignored run root is
`.velgraphing-local/velgraphing-four-arm-study-v1/retrievel-0.2.0-rc1-t070-r2`.
Its lane manifest SHA-256 is
`290be76aa609690572523ce9feb198e5d485dcab36b2a0333a5bdc2bd83b6c65`.
The refreshed successor freeze SHA-256 is
`fdad0cdd6bb6e051ec0a71454747d759524006c0c2c3a255aa8dfc5813265a08`.
The refreshed successor preflight SHA-256 is
`e9b60becc853988033ea353d0d823994562525f103845b55366b595b0924b1f4`.
The request-byte-set SHA-256 and eight-call, zero-retry controls did not change.

Validation after the repair:

- Actual 64-candidate S-01 Direct pool reduced to the exact 11-candidate answer
  packet with matching order.
- Focused benchmark suite: 33 passed and 2 expected machine-local skips.
- Successor overlay: passed with `execution_ready: true`.
- Historical bundle plus replacement lane manifest: passed.
- Provider, answer, grader, and Jev calls: zero.

## Contract-invalid lane continuation repair

The live R2 execution completed `A-S-01` at 5/5 and retained `B-S-01` at 4/5.
The `B-S-01` Jev path returned a safe fallback with
`provider_or_adapter_error`, zero reported attempted calls, and no retry.

The `C-S-01` answer lane then returned
`velgraphing-response-contract-v1` where the frozen response contract required
`velgraphing-answer-output-v1`. Parent retained the exact invalid response. It
did not rewrite the field or request an unapproved answer repair. The R2
controller stopped because it could not retain a contract-invalid lane as a
failed trial and continue.

The R3 repair records a completed model call before response-contract
validation. Invalid response or usage telemetry remains a failed trial, with
usage marked unavailable when needed. A failed trial now returns to the serial
controller for retention and successor dispatch. A passing trial still requires
exactly one answer call and one grader call. No retry rule changed.

R3 uses fresh task names and the ignored run root
`.velgraphing-local/velgraphing-four-arm-study-v1/retrievel-0.2.0-rc1-t070-r3`.
Its lane manifest SHA-256 is
`0a11bb06ca7477cdb9c6dc18fc49022ac7215867cb509b02f928a88e47357c69`.
Focused host and four-arm validation passed 52 tests with 2 expected
machine-local skips. The request set, eight-call cap, and zero-retry rule remain
unchanged.

## R3 diagnostic result and R4 repair

R3 completed all 16 trials and sealed result SHA-256
`1e3142100f038773fda391f16576fc913421086a46bd71aca0c57382c73fb231`.
It made 13 answer calls, 10 grader calls, and 4 provider calls. Three trials
passed. Three early lanes exceeded the 120 or 180 second handoff ceiling. Three
answer lanes returned an invalid response schema. Seven independently graded
answers failed the rubric.

R3 does not support an arm comparison. All four Direct plus Jev trials failed
before provider dispatch. Direct discovery bound the benchmark canonical JSON
hash. The Jev adapter then bound the same candidate array with its newline-
terminated canonical JSON hash. The binding guard correctly rejected the
second unequal hash as `attempt_binding_changed`. The adapter reported a safe
`provider_or_adapter_error` fallback with zero attempted calls. All four Graph
plus Jev trials used the Jev hash first and reached the provider.

The R4 repair uses the Jev canonical candidate hash for Direct discovery. It
does not weaken the binding guard. The lane handoff ceiling is now 600 seconds
for answers and graders. Actual completion time remains measured; the higher
ceiling only prevents a slow Parent dispatch from becoming a false timeout.

The ignored R4 run root is
`.velgraphing-local/velgraphing-four-arm-study-v1/retrievel-0.2.0-rc1-t070-r4`.
Its 32-entry manifest SHA-256 is
`e6ab860654c138dc93b8815a2d539e816e59b2c75dbce12778e015e69da2cb39`.
Its launcher SHA-256 is
`5eecf413c334ef83b0e3c34a678da6b3f9e4f51dadcc41ec353085ed9dcdddaa`.
The successor overlay is execution-ready. The request set, eight-call cap,
zero-retry rule, source snapshots, candidate pools, questions, and rubrics are
unchanged.

R4 validation before launch:

- Direct discovery followed by the real Jev evaluator and an injected local
  transport completed as `reranked` with one attempted call and matching
  candidate and request bindings.
- The Jev timing and four-arm contract suites passed 44 tests. Two tests skipped
  because this worktree does not contain the optional path-local lane override.
- `validate-successor-overlay` passed with `execution_ready: true` and no
  remaining re-ack fields.
- Successor freeze SHA-256:
  `c0908969c9e3aa39e6f0c058bcf05817aeb8b24ddaa1a8c468ea5668029033cb`.
- Successor preflight SHA-256:
  `71a70fc83e65f46d99bc8d84b2bd48a8d0984fa2a95a3d25facea3a2509b9577`.
- No R4 answer, grader, Jev, or provider call has run.

## R4 sealed execution

R4 completed all 16 frozen trials. It made 16 answer calls, 16 independent
grader calls, and 8 live Jev calls. It made no retry. The source-free result is
`closed` and `observed`. Its SHA-256 is
`e78ddf4a33a1be4132725da9f7f1247d34b34c0f51b7c4f194e603df74abb6ce`.

The result passed 12 of 16 trials:

- Direct, Jev off: 3 of 4.
- Direct, Jev on: 2 of 4.
- Graph, Jev off: 4 of 4.
- Graph, Jev on: 3 of 4.

Graph plus Jev and Direct without Jev each passed 3 of 4. Their all-trial mean
wall times were 245.373 seconds and 247.663 seconds. Graph plus Jev was 0.9%
faster on that narrow aggregate. On the three tasks that both arms passed, the
mean confirmed time to correct was 253.281 seconds and 258.358 seconds. Graph
plus Jev was 2.0% faster. The task-level wall-time changes were not consistent:
-29.9%, +2.8%, +33.9%, and -3.2% for S-01, D-01, L-01, and M-02.

The Jev evaluator itself took 0.509 to 0.929 seconds. Answer and grader time
dominated wall time. Graph plus Jev reduced mean answer-request bytes by 6.0%
against Graph without Jev, but its mean answer request remained 75.9% larger
than Direct without Jev. The Graph Jev request was equal to the Direct Jev
request on two tasks and larger on two tasks. This result does not show general
packet compression.

Direct plus Jev retained complete provider usage: 111,816 input tokens and
3,112 output tokens across four calls. Graph plus Jev retained the evaluator
elapsed time and request bytes, but not provider token usage. Its usage state is
`model_call_incomplete`. Answer and grader token usage is unavailable for every
arm. The result therefore does not support an all-model token or cost claim.

One C-M-02 answer capture double-encoded the already completed model JSON. The
Parent removed that single transport quoting layer, validated the unchanged
object against the frozen response contract and execution identity, and
submitted it without another model or provider call. This was a transport
normalization, not a retry.

The result classification is `oracle_assisted_fallback_ttc`. It supports only
the frozen-contract TTC comparison. It does not establish general Direct,
Graph, or Jev retrieval performance. The next audit must address the missing
Graph-plus-Jev provider usage and the larger Graph answer context before any
release claim.
