# T060 successor study freeze

## Result

Frozen a separate current-candidate successor study. The historical `freeze.json`,
`preflight.json`, sealed results, and GoalBuddy board remain unchanged. The
operator reports USD 1.0000 total authorized, USD 0.0969 spent across 108 calls
and 2,371,440 tokens, and USD 0.9031 remaining. This TypeSafe account snapshot
is operator-provided and not provider-verified. USD 0.9031 is the maximum
additional spend authority for this batch, not a cost estimate. The eight-call
cap and zero retries are separate batch controls. Request bytes identify the
frozen request set only. The historical byte-based `total_reservation_usd` of
USD 0.359789241 is retired and historical-only. It is not spend or a charge, is
not subtracted again, and is not attributable to the operator-reported
account-level USD 0.0969. Successor planning uses USD 0.9031 remaining and
maximum additional spend, plus the separate eight-call and zero-retry controls.

```text
pinned local v4 lanes -> successor freeze and preflight
                     -> regenerate ignored pools -> verify preflight SHA
                     -> fresh lanes and final user re-ack remain pending
```

The matrix contains S-01, D-01, L-01, and M-02 across arms A/B/C/D: 16 trials.
The preflight plans eight Jev calls. The offline execution-prep regenerated the
ignored pool artifact and verified its SHA-256 against the successor preflight.
It executed zero answer, grader, Jev, or provider calls and zero retries. It
created zero answer or grader tasks, zero live lanes, and no lane manifest.
Execution was not ready at T060 close. T070 later froze only the planned lane
manifest; it did not create nested tasks. See
[T070-study-execution.md](T070-study-execution.md) for the refreshed authority.

## Candidate and evidence bindings

- T060 worktree HEAD: `0992b65f12868cbc6bf5f7b21cfa4ac430241d4b`.
- T060 controller SHA-256: `515a1762712de5af558cf4364c7010295b985828031803493352eef2e3a781f9`.
- Package candidate SHA-256: `112a9b2d30057a12654c0a7237aa76aae011de2e7d22e91a6bd83803c9fd2107`.
- Release-manifest SHA-256: `3e6389bd70b2de2ef2e59bab1197d881f5f40bc23914391802235fcc3e5a6099`.
- Successor rubric SHA-256: `9a296e0a83f7d0fc17408679baa607743da1f79206d6cff4267c648a5cf506d8`.
- Successor TTC contract SHA-256: `c2b1ec7d5d8e7c3f447292fe3473d92d9ea639ea853bf7ddd274e88100b313b7`.
- Request-byte-set SHA-256: `80b3411f0d30600bc302a59debe36fe66734e4aceca0da6afdae303dc096af94`.
- Witness-custody canonical SHA-256: `e042c9ee45c7fcc9e36a7ad693b7f77106f12dd94f06756b9e8ae19e276be38b`.
- Source snapshots: engineering-handbook `594aa47760172eba049e18c5f3a2f602a7b96b73a315756876955d7be81cd402`; openchain-reference-material `7b06041a211f9365686f934eb7f37a0646f65ac4866d6837e37714ffb1e7679b`; thealgorithms-python `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.
- Account budget authority: USD `1.0000` total; operator-reported spend USD
  `0.0969` across `108` calls and `2371440` tokens; USD `0.9031` remaining and
  maximum additional spend. Source is operator-provided TypeSafe account truth;
  it is not provider-verified. Final user re-ack is pending.
- Original T060 successor freeze SHA-256, superseded by the T070 financial refresh: `36438e19c2e51a723825a921f3457e1127e1e5744424eb9526ab743a79bea56b`.
- Original T060 successor preflight SHA-256, superseded by the T070 financial refresh: `e9439a7ee7c173d41d93afb932a3a08d5342d667ac261def5ce8e8d8b6df88df`.
- T070 financial-refresh freeze/preflight hashes (`4db4a59625d4266657c2ee0b51301fa93244ccd5e7e8b2e861693620f00042c1` / `2fa8e9a7b26797c416f97c2d2b38da474725b2fa16843163efa588029ed22f04`) were superseded by the reservation/status refresh (`647bfac827ee4e419bc28d9ccb9a58c8b306fed0828608d76ad1ec9b981291d1` / `442582de7241c84cde93c38efb0151cb2d77a9561ae0510b2ece164bd54d2f45`), then the canonical task-name binding refresh (`ed86110272cb4d8dfad853245698b82a2daca1b6cd17fe341db7406fe98d2a5b` / `dffaf31f8dde051223b7ccf86f2b2b90fa5f271fb46693037e061cb415f0fdbf`).
- Current T070 manifest SHA-256: `57d444a0a8ea252433e5d69140c9677685878c9956576dd55a1c2df05406a0fa`; lane-name mapping SHA-256: `8957d586f1c931757a40a825ba38cda43fe4c6adf5c05cd7bb4d9de33f81432e`.
- Current T070 controller SHA-256: `505099f791674f3c007873429c5fa35f737c295cf6821be89122a7f127776a33`; successor rubric canonical SHA-256: `5bcdbf640ef88067db6162c7b937a9976b355c9cd933df2440c51793c16e4e6d`; TTC contract canonical SHA-256: `6ea6382a0b8c1be0135be410b2d3bb7dad66d025c78257f7a8fc98d456fd1305`.
- Regenerated ignored pool SHA-256: `3721b7378848d024e073cfa67bce44249b62551835ce236c22837119fee16d7b`.

The contract retains the oracle-assisted fallback TTC claim only. It grants no
Direct, Graph, Jev, or comparative retrieval-performance claim. Provider-specific
performance publication remains forbidden without separate permission. The
reported spend is account-level background, not attributed to this study. Final
user re-ack remains pending.

## Files changed

- `benchmarks/velgraphing-four-arm-study-v1/PROTOCOL.md`
- `benchmarks/velgraphing-four-arm-study-v1/successor-rubrics.json`
- `benchmarks/velgraphing-four-arm-study-v1/successor-ttc-contract.json`
- `benchmarks/velgraphing-four-arm-study-v1/successor-freeze.json`
- `benchmarks/velgraphing-four-arm-study-v1/successor-preflight.json`
- `scripts/benchmarks/four_arm_study_v1.py`
- `tests/benchmarks/test_four_arm_study_v1.py`
- `docs/goals/retrievel-release-v1/notes/T060-study-freeze.md`
- Ignored local custody copy at `.velgraphing-local/velgraphing-four-arm-study-v1/successor-ttc-witness-custody.json`; its source artifact was not changed.
- Ignored generated pool artifact at `.velgraphing-local/velgraphing-four-arm-study-v1/phase-2-pools.json`.

## Validation

- `freeze-successor` against the pinned local v4 lanes: passed; reproduced all
  three exact source snapshots, eight pool hashes, the frozen request-byte set,
  and the historical preflight hash.
- `prepare-successor-execution` against the pinned local v4 lanes: passed;
  regenerated the ignored pool file and verified its SHA-256 against
  `successor-preflight.json` before any lane manifest existed.
- `validate-successor-overlay`: passed; reported eight planned Jev calls and
  `execution_ready: false`.
- `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests/benchmarks -p 'test_four_arm_study_v1.py'`: passed, 31 tests, 2 skipped. The tests reject a stale pool before lane creation or live execution and keep historical reservation validation unchanged.
- `git diff --check`: passed.
- `git diff --exit-code HEAD -- benchmarks/velgraphing-four-arm-study-v1/freeze.json benchmarks/velgraphing-four-arm-study-v1/preflight.json`: passed; both historical artifacts are unchanged.
- `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/package/verify_source_package_parity.py`: earlier attempt refused with `private_or_machine_path`. This did not change package files. The manifest candidate identity is bound above, but full source/package parity was not verified in this worktree.

## Remaining gates

At T060 close, execution still required a unique 32-entry lane manifest and
final user re-ack. T070 froze a planned manifest but created no answer or
grader tasks. The regenerated T070 successor freeze reports
`frozen_pending_final_user_reack`; final re-ack remains the authority gate.
Re-ack still must confirm the request-byte-set
hash, eight-call cap, total authorized amount, operator-reported spend-to-date,
USD 0.9031 maximum additional spend, lane-manifest hash, and Python executable.
No provider, credential, network, or cloud-audit call was made. No commit was
created.
