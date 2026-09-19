# T010 Receipt: Integrated Product Seam

Date: 2026-09-19

## Candidate

- Starting commit: `52dc69199a68a7a61595f9e6aa608feed0cfc58c`
- Branch: `codex/retrievel-adaptive-pipeline`
- Release candidate SHA-256: `1cba106d4485716abdb429435ce30accffafb09d80fcddbe91cac76f4e1d5223`
- Validation tier: full. The public core result type and portable package API changed.

## Result

T010 adds one product-owned planner before final ranked-context selection. The planner accepts caller-built Direct and Graph candidate tuples. It selects Graph only when Graph adds an optional relationship candidate with an earlier primary parent, preserves each required Direct candidate exactly, and binds the relationship to an authenticated `GraphEdge`. The edge must match both record IDs and carry verified source coordinates for the current snapshot. Fabricated candidate relationship metadata keeps the Direct route.

The selector now reports whether optional Jev judgment can change the selected source-bound context under the current byte budget. It requests no judgment when Jev is off, all optional candidates fit, fewer than two optional candidates can compete, or changing their order cannot change the selected set. A missing, unqualified, invalid, or no-effect observation keeps the verified baseline. Applying a valid observation is a second explicit selector invocation. It requires caller qualification and matching request, candidate, query, and source bindings.

Jev eligibility compares candidate orders under the exact provider-bound serialization shape with a reserved 64-character request digest. It compares an applied result to the provider-bound baseline order. Request-binding overhead therefore cannot count as a Jev selection effect. Identical ordering always retains the original verified baseline membership.

The baseline does not require or fabricate an approval hash. Successful baseline context uses `graph-ranked-context-baseline-v1` and omits the provider-only field. The existing `graph-ranked-context-v1` contract retains its full approval digest and is emitted only when a bound Jev observation changes selection. The planner and decision telemetry omit raw query and source content. The public seam is `plan_ranked_context` plus `select_ranked_context`. No provider call was added to `/graph-find`.

## Files Changed

- `packages/core/selection.py`
- `packages/core/__init__.py`
- `plugins/graph-engineering/runtime/core/selection.py`
- `plugins/graph-engineering/runtime/core/__init__.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `tests/core/test_ranked_context_selection.py`
- `tests/skills/test_jev_skill.py`
- `scripts/benchmarks/time_to_correct_jev_v4.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T010-receipt.md`

## Validation

- Focused selector: `python -m unittest tests.core.test_ranked_context_selection -v` -> 16 passed, including exact 922, 923, and 924 byte boundaries.
- Direct consumers: core Jev, retrieval, Jev V4, ranked candidates V4, and frontier modules -> 177 passed across corrected commands.
- One initial consumer command named the absent module `tests.benchmarks.test_ranked_candidates_v4`. This was a command error. The actual module `tests.benchmarks.test_time_to_correct_ranked_candidates_v4` then passed 7 tests.
- Portable runtime: `python -m unittest tests.skills.test_jev_skill -v` -> 6 passed, including import of `core.plan_ranked_context` from `runtime`.
- Projection: `scripts/package/project_portable_plugin.py` -> success. A second run produced the same diff SHA-256.
- Package parity: manifest write and verify -> candidate `1cba106d4485716abdb429435ce30accffafb09d80fcddbe91cac76f4e1d5223`, 87 files.
- Parity tests: `python -m unittest tests.parity.test_source_package_parity -v` -> 10 passed.
- Full suite: the six `unittest discover` groups from `npm test`, using the repository root virtual environment -> 480 passed, 1 skipped.
- `git diff --check` -> passed.

## Boundaries And Remaining Risk

- Provider calls: 0. Observed provider cost: USD 0.00.
- No network, key, deployment, push, pull request, or live provider canary was used.
- The planner consumes already-built candidates. It does not create Direct or Graph candidates.
- `relationship_parent_candidate_id` alone has no routing authority. Graph routing also requires an authenticated coordinate-bound edge. The selector then verifies candidate source identity, graph record, source bytes, and parent ordering before selection.
- T010 does not define a confidence threshold. The caller must explicitly qualify an observation. T020 and T030 own live-canary evidence and any measured threshold decision.
- The retained PR10 frontier remains benchmark history. This implementation does not treat it as the product seam.
