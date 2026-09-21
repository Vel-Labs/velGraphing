# T240 symbol-aligned change impact

## Decision

Accept the intent and relationship ordering repair. Continue to T250 before a
provider call because the exact verified relationship cannot yet enter the
capped shortlist.

## Repair

- Natural language `changes` now maps to the existing `change-impact` intent.
- Change-impact retrieval still prefers incoming before outgoing supports.
- Within each direction, an already-verified edge whose seed-coordinate symbol
  exactly matches a canonical prompt facet wins before the prior stable edge
  order.
- Non-impact retrieval remains outgoing-only.
- One support per selected seed, sensitivity, custody, byte caps, count caps,
  and deterministic fallback are unchanged.

Commit: `4d6263ab2ec787b9d8ad82e9502762142e9d2d6b`.

## Validation

- Targeted regressions: 3 passed.
- Retrieval, helper, JavaScript, and ranked-selection consumers: 119 passed.
- Portable, Jev, and parity checks in a clean copy: 47 passed.
- Two projector runs produced projection-state SHA-256
  `ab60f4efbf311d8db50d3b3411fbd74b374b95f7acfe375b4ee4356cdbaf13b8`.
- Package candidate SHA-256:
  `892f990b357bc5a8abd0a1200f095f5bd6193800eeb71873c9c738ae76afe3b9`.

The installed public preflight selected incoming `derive_source_relations`
supports for both canonical and runtime retrieval source. No provider or model
call occurred.

## Exact blocker

The verified Python declaration coordinate spans the entire
`derive_source_relations` function: 12,702 bytes. Candidate units are capped at
4,096 bytes. The candidate builder correctly refuses to claim that a bounded
excerpt contains the full edge coordinate, so no relationship child survives
and the ranked planner selects Direct.

The selector custody contract and 4,096-byte cap are correct. The relation edge
needs a precise declaration-name anchor instead of a whole-function coordinate.
The candidate builder can then expand a bounded source unit around that exact
verified anchor.

## Files changed

- `packages/core/retrieval.py`
- `plugins/graph-engineering/runtime/core/retrieval.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `tests/core/test_retrieval.py`
- `tests/skills/test_portable_skills.py`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T240-symbol-aligned-impact.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
