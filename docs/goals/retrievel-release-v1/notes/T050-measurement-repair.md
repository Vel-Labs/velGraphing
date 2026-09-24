# T050 Measurement Repair

Date: 2026-09-21
Status: Graph/off production-path canary and clean-export release validation passed. Graph/on fixture replay passed. The observed/live Graph/on controller path has subprocess-contract simulation coverage only. It has no live adapter or provider coverage.

## Candidate and scope

- Worktree: `codex/retrievel-0.2.0-rc1`, starting commit `c92ee975f7f931eb96880817ccc4a44a33d05091`.
- Replay-only continuation base: `e6cbb3812f1174b68fe84716664609da16633c01`.
- Observed/live controller continuation base: `64271e3e1c06aa3f29432eabc24a7d8985b7b466`.
- Packaged candidate SHA-256: `112a9b2d30057a12654c0a7237aa76aae011de2e7d22e91a6bd83803c9fd2107`.
- Packaged Graph Find adapter SHA-256: `3370c1dea98f3b778f628a7dc100cc8c638d3a419464439d1639c295a58aa0fe`.
- The controller stages the manifest-listed plugin bytes under the ignored run root. Graph/off trials invoke that installed `graph_find.py` once during `Trial.prepare`.
- Graph Find supplies the candidate set, selected source-bound spans, snapshot identity, and child-process diagnostics. The controller binds the candidate-set and package hashes, records each scan and memory read, and converts returned spans into the existing answer evidence payload.
- Direct retrieval now runs inside `Trial.prepare`. Its dynamic candidate packet feeds Jev and selection.
- Graph/on uses the installed Graph Find command with a request-bound replay file staged under the ignored run root for fixture replay. The observed/live continuation now uses the same installed command with explicit caller approval and a bounded call ledger.
- Replay validation binds the approved request hash, requires `execution=replay`, `status=reranked`, zero attempted calls, source revalidation, a reranked fresh selection, and preserved required candidates. It stores request size and replay token counts only in the source-free replay observation. Provider token fields remain empty because replay makes no provider call. Overall model-call coverage stays incomplete.
- Observed/live Graph/on requires a planned Jev call, a caller-owned `LiveJevBudget`, and the exact pool preview hash. It reserves once before launching the installed adapter. The child receives only the minimal process environment plus `TYPESAFE_API_KEY`; the key is not stored in argv, process receipts, or trial observations. The controller validates the request binding, live execution, attempted-call/network consistency, snapshot/package/span bindings, and reranked or safe baseline selection before it completes the call-ledger receipt. The source-free observation records request bytes, provider usage when reported, elapsed time, and attempted calls. The parent provider phase and provider durations remain missing. Overall model-call coverage stays incomplete.
- Historical freeze and preflight files were not changed. The historical Graph Find binding remains pinned to its original hash. Default Graph Find output remains unchanged unless `--diagnostics` is supplied.
- In the earlier Graph/off and replay-only validation, no network call or credential access occurred.

## Files changed

- `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `scripts/benchmarks/four_arm_study_v1.py`
- `tests/skills/test_portable_skills.py`
- `tests/benchmarks/test_four_arm_study_v1.py`
- `docs/goals/retrievel-release-v1/notes/T050-measurement-repair.md`

## Validation

- The final timer correction ends child `graph_build` after the returned `Graph(records, edges)` is constructed. The interval includes snapshot construction, source records, typed relation derivation, and final graph validation. It remains labeled with the installed subprocess clock. The parent `cold_graph_build` phase remains missing.
- A retained `execute_trial` Graph/off test runs exactly one installed Graph Find process, one answer process, and one independent grader process. The answer rejects a poisoned frozen-pool sentinel and requires the fresh source marker. The grader passes only when that marker reaches its input. Model-call coverage and usage remain incomplete.
- The production Graph/on replay test runs an installed preview before the measured trial to build the exact request-bound fixture response. The measured D/on trial runs one installed Graph Find process, one answer process, and one grader process. It records zero attempted Jev calls, a reranked source-revalidated observation, and preserved required candidates. The answer rejects the frozen-pool sentinel. A mismatched replay hash fails before another child process starts. The replay child receives no network flags and its environment omits `TYPESAFE_API_KEY`.
- The requested benchmark test command passed after this continuation: 28 tests ran, 24 skipped because private witness custody or frozen corpus lanes are unavailable. No network call or credential access occurred.
- The observed/live production `execute_trial` test converts an installed replay result into a live-shaped payload and intercepts the installed Graph Find child. It uses a fake key and makes no provider call. This is controller/subprocess-contract simulation, not patched-transport or live-adapter coverage. The interceptor allows only the expected Graph Find, answer, and grader commands. Any unexpected child or unhandled `--allow-network` command fails the test. It checks exact argv/hash/request-size bindings, one Graph Find child, one answer, one grader, reranked fresh evidence, required candidates, source-free usage receipts, and a consumed budget receipt. Aggregate provider usage remains unavailable because the parent provider phase is not complete. Its child-failure case keeps `reserved_unknown_if_consumed` and launches no retry.
- Test-development incident: an initial observed-path run used an interceptor tied to the earlier run-root adapter path. `execute_trial` staged a different adapter path, so one child reached the real installed Graph Find CLI with a synthetic test key and `--allow-network`. The child entered the live request path and returned a provider fallback. This initiated one provider request attempt. No real key was intentionally retrieved, logged, persisted, or passed to the child. The initial `patch.dict` test setup may have transiently copied the parent environment for restoration; whether it contained a real key is unknown. This attempt is not accepted as benchmark evidence. The final test uses an isolated environment and matches the adapter installed in that run root. Unexpected children and unhandled network-enabled commands now fail closed. Treat the earlier attempt as a test-harness safety defect.
- The worktree manifest writer refused the ignored plugin `.pyc`. An export from tracked HEAD with only the authorized Graph Find source change overlaid was built under ignored `.velgraphing-local`. The projector and manifest write/verify passed for 87 files and candidate `112a9b2d...`. Only the generated release manifest was copied back. The ignored bytecode was not changed.
- After the final timer correction, the focused benchmark file passed: 28 tests passed, 24 skipped. Skips require private witness custody or frozen corpus lanes. The single `graph_find_diagnostics` test passed.
- Commands used the declared shared virtualenv: `PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python -m unittest discover -s tests/skills -p test_portable_skills.py -k graph_find_diagnostics` and `PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python -m unittest discover -s tests/benchmarks -p test_four_arm_study_v1.py`.
- The contaminated worktree still contains ignored test bytecode. Parent therefore validated the exact commit from an automatically removed clean tracked export under `.velgraphing-local`; no ignored source-tree file was changed or copied into the export.
- Exact-candidate clean suite: scaffold 11 passed; core 284 passed; adapters 18 passed; skills 38 passed; benchmarks 193 passed with 25 expected private-data skips; parity 10 passed.
- Exact-candidate package verification passed for 87 files and candidate `112a9b2d...`.
- Independent Luna re-audit of commit `c7301d83b3dd92d676e48bbc86ae00403c52feca` returned `ACCEPT`. It confirmed full child graph-build timing, the production `execute_trial` path, no frozen-pool evidence leakage, one Graph Find process, one answer process, one independent grader process, a separate child clock domain, and no fabricated parent `cold_graph_build` phase.
- `git show --check` passed for the bounded commits.

## Remaining boundary

This is a local process-boundary canary, not a live model or accepted Jev result. Fixture replay and subprocess-contract simulation do not establish live adapter behavior, provider quality, usage completeness, or comparative benchmark results. The test-development incident above is retained as a safety boundary. No historical result or freeze was rewritten.
