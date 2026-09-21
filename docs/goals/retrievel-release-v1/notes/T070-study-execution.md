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
- Lane-name mapping SHA-256: `e0f4306296e7c5ed7d5f5c6f7017fc32705af191cf7b00b9b50f0054542a8ad3`.
- Frozen lane manifest: `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.velgraphing-local/velgraphing-four-arm-study-v1/retrievel-0.2.0-rc1-t070-r1/lane-manifest.json`.
- Manifest SHA-256: `c164f76c2e5a995661be6f534eb38e4b364c57e8592844da5f6e21fde7632382`.
- Entry counts: 32 total; 16 Luna answer lanes and 16 Astra grader lanes.
- Naming pattern: `T070-r1-Luna-answer-<trial-id>` and `T070-r1-Astra-grader-<trial-id>`.
- All 32 planned identifiers are unique and follow the frozen dispatch order.

The manifest contains planned task-name identifiers. It does not contain
opaque IDs returned by task creation because no task was created. If execution
requires actual host thread IDs, Parent must replace the planned values, freeze
a new manifest, and request re-ack for its new hash before execution.

## Bound artifacts

- Request-byte-set SHA-256: `80b3411f0d30600bc302a59debe36fe66734e4aceca0da6afdae303dc096af94`.
- Per-batch Jev cap: 8 calls; retries: 0.
- Maximum additional provider spend: USD `0.9031`.
- Successor freeze SHA-256: `647bfac827ee4e419bc28d9ccb9a58c8b306fed0828608d76ad1ec9b981291d1`.
- Successor preflight SHA-256: `442582de7241c84cde93c38efb0151cb2d77a9561ae0510b2ece164bd54d2f45`.
- Ignored pool artifact SHA-256: `3721b7378848d024e073cfa67bce44249b62551835ce236c22837119fee16d7b`.
- Controller SHA-256: `b68ffd10fc733df0eb21475657c6338b5be0d966da9f7d646357f415290c6177`.
- Successor rubric canonical SHA-256: `f851ba07b55cf9e520527021fc737f1f11f59803d29e24e60a771b0328c35f69`.
- Successor rubric file SHA-256: `9f2a2acf353a3dce56e648145c862a63daf2b4ea545689efa3635f5840cd1bae`.
- Successor TTC contract canonical SHA-256: `7f283dce4adfb8e0cd366df38f0b7311e9ddcec8a7c72f606b671952ad9dacf2`.
- Successor TTC contract file SHA-256: `4a715c8538428f276de93deea4e0eb0f9213809aaf2b88b02b8fbdf31dea09fe`.
- Contract status: `frozen_pending_final_user_reack`.
- Remaining re-ack fields: request-byte-set hash; eight-call cap; total budget; operator-reported spend-to-date; maximum additional spend; manifest hash; Python executable.

## Validation

- `freeze-successor --refresh` against
  `/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4`: passed after validating all three bound source snapshots. It bound the updated controller, reservation reconciliation, account snapshot, request set, and pool hashes. It recorded zero executed calls and zero retries.
- `prepare-successor-execution` against pinned local v4 lanes: passed in the
  earlier T070 preparation and regenerated the ignored pool file. This refresh
  left that file unchanged; `freeze-successor --refresh` rederived the pools
  from the pinned lanes and matched the same bound pool SHA.
- Earlier T070 `freeze-lanes` with the specified run root, Python path,
  bindings, pool, and custody: passed. It froze 32 unique manifest entries.
- `validate-successor-overlay`: passed. It reports eight planned Jev calls,
  the frozen manifest hash, zero live lanes created, and `execution_ready: false`.
- Direct manifest validation from T070: passed; 32 entries, 32 unique planned
  IDs, 16 answer lanes, and 16 grader lanes. This refresh preserved its SHA.
- Focused benchmark tests: 31 passed, 2 skipped. Coverage now checks the
  frozen-manifest status and the historical-reservation reconciliation.
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
- `docs/goals/retrievel-release-v1/state.yaml`: corrected the superseded T060
  budget summary and T070 re-ack requirements.

The ignored custody copy and regenerated pool remain local. The ignored T070
run root contains only `lane-bindings.json` and `lane-manifest.json`.
