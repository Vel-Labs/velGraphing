# T050 Measurement Repair

Date: 2026-09-21
Status: Graph/off production-path canary and clean-export release validation passed; Graph/on remains incomplete.

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
- The contaminated worktree still contains ignored test bytecode. Parent therefore validated the exact commit from an automatically removed clean tracked export under `.velgraphing-local`; no ignored source-tree file was changed or copied into the export.
- Exact-candidate clean suite: scaffold 11 passed; core 284 passed; adapters 18 passed; skills 38 passed; benchmarks 193 passed with 25 expected private-data skips; parity 10 passed.
- Exact-candidate package verification passed for 87 files and candidate `112a9b2d...`.
- Independent Luna re-audit of commit `c7301d83b3dd92d676e48bbc86ae00403c52feca` returned `ACCEPT`. It confirmed full child graph-build timing, the production `execute_trial` path, no frozen-pool evidence leakage, one Graph Find process, one answer process, one independent grader process, a separate child clock domain, and no fabricated parent `cold_graph_build` phase.
- `git show --check` passed for the bounded commits.

## Remaining boundary

This is a local process-boundary canary, not a live model or Jev result. Graph/on Jev remains incomplete. No historical result or freeze was rewritten.
