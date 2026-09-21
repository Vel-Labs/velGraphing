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
