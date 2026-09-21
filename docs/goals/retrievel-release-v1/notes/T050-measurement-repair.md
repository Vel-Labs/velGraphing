# T050 Measurement Repair

Date: 2026-09-21
Status: Graph/off production-path canary passed; the full focused skills suite is blocked by ignored bytecode in the worktree.

## Candidate and scope

- Worktree: `codex/retrievel-0.2.0-rc1`, starting commit `c92ee975f7f931eb96880817ccc4a44a33d05091`.
- Packaged candidate SHA-256: `112a9b2d30057a12654c0a7237aa76aae011de2e7d22e91a6bd83803c9fd2107`.
- Packaged Graph Find adapter SHA-256: `3370c1dea98f3b778f628a7dc100cc8c638d3a419464439d1639c295a58aa0fe`.
- The controller stages the manifest-listed plugin bytes under the ignored run root. Graph/off trials invoke that installed `graph_find.py` once during `Trial.prepare`.
- Graph Find supplies the candidate set, selected source-bound spans, snapshot identity, and child-process diagnostics. The controller binds the candidate-set and package hashes, records each scan and memory read, and converts returned spans into the existing answer evidence payload.
- Direct retrieval now runs inside `Trial.prepare`. Its dynamic candidate packet feeds Jev and selection.
- Graph/on remains fail-closed with `installed_graph_find_jev_path_incomplete`. Preview, approval, and final reranked selection telemetry are not implemented in this slice.
- Historical freeze and preflight files were not changed. The historical Graph Find binding remains pinned to its original hash. Default Graph Find output remains unchanged unless `--diagnostics` is supplied.
- No network call or credential access occurred.

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
- The worktree manifest writer refused the ignored plugin `.pyc`. An export from tracked HEAD with only the authorized Graph Find source change overlaid was built under ignored `.velgraphing-local`. The projector and manifest write/verify passed for 87 files and candidate `112a9b2d...`. Only the generated release manifest was copied back. The ignored bytecode was not changed.
- After the final timer correction, the focused benchmark file passed: 28 tests passed, 24 skipped. Skips require private witness custody or frozen corpus lanes. The single `graph_find_diagnostics` test passed.
- Commands used the declared shared virtualenv: `PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python -m unittest discover -s tests/skills -p test_portable_skills.py -k graph_find_diagnostics` and `PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.venv/bin/python -m unittest discover -s tests/benchmarks -p test_four_arm_study_v1.py`.
- Focused portable-skill suite: 32 tests; 1 failure and 1 error because `scripts/__pycache__/graph_find.cpython-314.pyc` appears as an unexpected package resource and is not UTF-8. The changed diagnostics test passed alone. The ignored `.pyc` was left untouched.
- The earlier full six-suite run was on the prior candidate, before this follow-up. Scaffold: 11 passed. Core: 284 passed. Adapters: 18 passed. Skills: 38 passed. Benchmarks: 193 passed, 25 skipped. Parity reported 3 failures and 8 errors because ignored `packages/core/__pycache__/*.pyc` entered its scan input. No full suite was rerun for this bounded follow-up.
- `git diff --check` passed before this follow-up commit.

## Remaining boundary

This is a local process-boundary canary, not a live model or Jev result. Graph/on Jev remains incomplete. The prior full release check was not green because parity encountered ignored bytecode. No historical result or freeze was rewritten.
