# T030 Candidate Unit Repair Receipt

Date: 2026-09-19

Status: implementation and fixture proof complete. T030 remains active. No public-corpus benchmark or provider call ran.

## Result

- The product retrieval path now builds ranked candidates from every bounded matched-facet occurrence.
- Code units, Markdown sections, and prose paragraphs use existing source-unit boundaries. Oversized units use a bounded UTF-8 window without a completeness claim.
- Required candidates come only from caller-declared proof-obligation evidence. Required overflow fails closed.
- Candidate identity, ordering, custody, and limits are deterministic. Limits are 64 candidates, 4096 bytes per candidate, and 32768 bytes in aggregate.
- Candidate retention interleaves retrieval hits. A noisy first source cannot consume the full cap before a later hit.
- Relationship support uses an authenticated graph edge and its target coordinate. The coordinate is expanded through the same bounded source-unit routine and stays optional and parent-bound.
- The V4 generator now uses one snapshot, index, facet set, task budget, retrieval routine, and candidate materializer for all routes. Direct remains edge-free. Graph expansion remains source-bound.
- The prior S-01 live artifact remains historical and invalid for candidate-quality claims.

## Validation

- Focused core, planner, generator, and evaluator tests: 122 passed.
- Full discovery with system Python: scaffold 11 passed; adapters 18 passed; skills 35 passed; benchmarks 153 passed with 1 skipped; parity 10 passed.
- Core discovery: 254 passed and 3 failed because the optional JavaScript parser is unavailable in this checkout. The failures report `javascript_parser_unavailable` and do not touch this change.
- The configured `npm test` command did not run because `.venv/bin/python` is absent. The equivalent discovery suites ran with `python3`.
- Portable projector ran twice with the same projection state.
- Source-package parity passed for 87 files.
- Portable runtime imported `ranked_candidates_from_retrieval`.
- `git diff --check` passed.

## Remaining Gate

Freeze a fresh, label-isolated offline candidate artifact from the repaired committed selector before any public-corpus study. Keep T030 active until the Parent reviews and accepts that artifact and the authorized study result.

## Files Changed

- `packages/core/__init__.py`
- `packages/core/retrieval.py`
- `plugins/graph-engineering/runtime/core/__init__.py`
- `plugins/graph-engineering/runtime/core/retrieval.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `tests/core/test_retrieval.py`
- `tests/core/test_retrieval_pr9_helpers.py`
- `tests/benchmarks/test_time_to_correct_ranked_candidates_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-candidate-unit-repair.md`
