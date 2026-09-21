# T230 relationship retention and main integration

## Decision

Accept the shortlist repair and the required `origin/main` merge. Do not accept
the installed Graph plus Jev path as complete. The merged package retains two
verified relationship children before Jev, but the exact live rerank correctly
removes both because the graph selected unrelated outgoing imports.

## Git integration

- Shortlist repair commit:
  `8ea6938a625d117a174c101125c0910ba0709916`.
- Merge first parent:
  `8ea6938a625d117a174c101125c0910ba0709916`.
- Merge second parent:
  `3bad9cbfa618e4a39789298a52a8d03d2afdb8f2`.
- Merge commit:
  `77acbc6f45df6d564e0e0e9f13918c2a34bed04d`.

The GoalBuddy branch had recorded PRs #13 through #15 as accepted, but their
product commits were not ancestors of the branch. The merge now includes the
Python and Markdown relation seam, JavaScript static named imports, incoming
change-impact projection, later retrieval and selection fixes, and the T230
shortlist repair.

## Repair

`ranked_candidates_from_retrieval` now places non-required candidates that bind
validated relationship supports before unrelated optional candidates. Each
parent still immediately precedes its children. Required evidence, source
custody, Direct behavior, count caps, and byte caps are unchanged.

## Validation

- Focused and consumer retrieval, JavaScript relation, helper, and ranked
  selection tests: 118 passed.
- Full core integration: 281 passed.
- Benchmark-host preservation: 15 passed.
- Clean portable skill, Jev, and parity tests: 47 passed.
- Two projector runs produced identical projection state.
- Source-package parity passed for 87 files.
- Merged package candidate SHA-256:
  `653f74b1ed990af0e1383fa86a7475acf7d4eaf10649d3cc11539dcbb658ddff`.

## Installed preflight and live diagnostic

The fresh isolated install imported only its installed runtime. It analyzed
public `origin/main` commit `3bad9cb` at source snapshot
`dbd9ff89fbb78774322abfd035e17597ba378b925c88670f8a7dd57e399e492a`.
The planner selected Graph and retained two relationship children.

One exact provider call ran before the missing-main integration was discovered:

- request SHA-256:
  `dac5ff9fc094d7694d0bc96349420227ee993f5ddea5e409f5c77d715270d42e`;
- request bytes: `87,005`;
- status: `reranked`;
- model: `jev-1.13.0`;
- provider duration: `711.284` milliseconds;
- usage: 24,466 input tokens and 666 output tokens;
- calls: `1`;
- retries: `0`;
- source revalidation: passed.

The merged package reproduced the exact candidate, source, query, and request
hashes, so it consumed the same live observation without another provider call.
The installed selector applied the rerank, selected 32 candidates in 32,002
serialized bytes, and preserved parent-child integrity. It selected neither
relationship child.

## Remaining product defect

The four graph supports were outgoing imports for `SourceIdentityV4`,
`ContextSpan`, `is_authenticated_eligible`, and `_words`. They were not callers
or consumers of `derive_source_relations`.

Two deterministic causes remain:

1. `changes` does not map to the existing `change-impact` intent.
2. Incoming support selection takes the first stable edge for a seed instead
   of preferring the edge whose verified symbol matches the prompt.

The graph already contains verified `derive_source_relations` import edges.
The next task must select those existing edges before adding any new graph
model or relation type.

## Claim boundary

This task proves installed packaging, source-bound relationship retention, live
Jev transport, exact response binding, source revalidation, and safe selection.
It does not prove useful change-impact retrieval or Graph plus Jev performance.

## Files changed

- `packages/core/retrieval.py`
- `plugins/graph-engineering/runtime/core/retrieval.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `tests/core/test_retrieval.py`
- `benchmarks/velgraphing-time-to-correct-v4/PUBLIC_STATUS.md`
- `packages/core/__init__.py`
- `packages/core/javascript_coordinates.py`
- `packages/core/selection.py`
- `plugins/graph-engineering/runtime/core/__init__.py`
- `plugins/graph-engineering/runtime/core/javascript_coordinates.py`
- `plugins/graph-engineering/runtime/core/selection.py`
- `plugins/graph-engineering/skills/graph-find/SKILL.md`
- `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py`
- `tests/core/test_javascript_coordinates.py`
- `tests/core/test_ranked_context_selection.py`
- `tests/skills/test_portable_skills.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T230-relationship-retention.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
