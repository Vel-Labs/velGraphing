# T070 authority preparation

## Status

Prepared the successor authority package only. No nested task was created. No
answer, grader, Jev, or provider call ran. No credential or network access
occurred. `execution_ready` remains false. No commit was created.

Base HEAD: `ddb094cd01c3a7b2450a937203fc40f9a1bff290`.

```text
verified custody and pool -> frozen manifest with planned names -> final user re-ack pending
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

The regenerated successor freeze status is
`frozen_pending_final_user_reack`. The lane manifest is already frozen, so a
fresh lane manifest is no longer a pending gate. Final user re-ack remains
required before execution.

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
- Successor freeze SHA-256: `ed86110272cb4d8dfad853245698b82a2daca1b6cd17fe341db7406fe98d2a5b`.
- Successor preflight SHA-256: `dffaf31f8dde051223b7ccf86f2b2b90fa5f271fb46693037e061cb415f0fdbf`.
- Ignored pool artifact SHA-256: `3721b7378848d024e073cfa67bce44249b62551835ce236c22837119fee16d7b`.
- Controller SHA-256: `505099f791674f3c007873429c5fa35f737c295cf6821be89122a7f127776a33`.
- Successor rubric canonical SHA-256: `5bcdbf640ef88067db6162c7b937a9976b355c9cd933df2440c51793c16e4e6d`.
- Successor rubric file SHA-256: `66acba6c5cdec5c970f417ec457e39a40bdef31065611fa464f5e9de5d2b4cc2`.
- Successor TTC contract canonical SHA-256: `6ea6382a0b8c1be0135be410b2d3bb7dad66d025c78257f7a8fc98d456fd1305`.
- Successor TTC contract file SHA-256: `6395345ed8c299eea41d45a76e575d305da9423f84dd3e7507b45c54e73e32df`.
- Contract status: `frozen_pending_final_user_reack`.
- Remaining re-ack fields: request-byte-set hash; eight-call cap; total budget; operator-reported spend-to-date; maximum additional spend; manifest hash; Python executable.

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
- `validate-successor-overlay`: passed. It reports eight planned Jev calls,
  the frozen manifest hash, zero live lanes created, and `execution_ready: false`.
- Historical `validate --lane-manifest`: passed. Direct binding checks passed:
  32 names match their answer/grader bindings exactly, are unique, and use only
  lowercase ASCII letters, digits, and underscores. The contract SHA matches
  the regenerated manifest.
- Focused benchmark tests: 31 passed, 2 skipped. Coverage now checks the
  canonical task-name rule, refresh overwrite guard, manifest semantics, and
  historical-reservation reconciliation.
- `git diff --check`: passed.
- GoalBuddy `state.yaml` syntax check with Ruby YAML: passed.
- `run --help`: passed; it exposes `--approved-max-additional-provider-spend-usd`.
- Historical `freeze.json` and `preflight.json` diff check: passed; both remain unchanged.
- Historical `freeze.json` and `preflight.json`: unchanged.
- Package parity was not rerun. No package files changed; T060's parity result
  for the same package candidate remains the available evidence.

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

`docs/goals/retrievel-release-v1/state.yaml` had pre-existing local changes and
was not changed in this repair. The ignored T070 run root contains the updated
`lane-bindings.json` and regenerated `lane-manifest.json`.
