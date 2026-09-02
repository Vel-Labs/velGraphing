---
name: graph-benchmark
description: Compare a source-bound Graph-assisted route with direct repository use under a frozen, read-only benchmark. Use for measured effectiveness, not setup or mutation.
---

# Graph Benchmark

Read the nearest instruction files, [the Graph Engineering skill](../graph-engineering/SKILL.md), and [Graph Audit](../graph-audit/SKILL.md). Keep the repository read-only.

## Workflow

1. Freeze representative questions, required facts, repository snapshot, model and reasoning level, route controls, and write restrictions before either route runs.
2. Run fresh Direct and Graph-assisted lanes against the same snapshot and question order. Use two host-native worker lanes in parallel with no inherited conversation history. Do not invoke `codex`, `codex exec`, or another Codex CLI process from a shell. The Graph-assisted lane may use only source-bound fallback allowed by the caller.
3. Record required-fact coverage, model-visible context bytes, repository operations, graph build and load cost, fallback reads, wall-clock time, prohibited writes, proof errors, and authority errors.
4. Separate cold-build, warm-load, retrieval, fallback, and answer costs. Do not convert local source bytes into model-token cost.
5. Report Direct, Graph-assisted, and percentage change in one table. Mark answer quality `unscored` when no independent required-fact rubric exists.
6. Accept an improvement only when required-fact coverage does not decline and safety errors do not increase. Otherwise report a rejection or an unresolved result.

The Parent task owns the freeze, lane dispatch, scoring, and final comparison.
Each worker returns its answer and only metrics that its host exposes. Mark a
metric `unknown` when the host does not expose it. If host-native workers are
unavailable, stop with `fresh_lane_execution_unavailable`; never substitute a
nested CLI run or reuse the Parent answer as a lane.

Use [the benchmark report template](templates/benchmark-report.md) for retained
or published results. Keep every standard metric row and write `unknown` when
the host did not expose a value. Add task-type-specific checks under quality;
do not force writing, design, or implementation tasks into one synthetic score.

Use `scripts/graphctl.py readiness` only for structural readiness. It does not
measure answer quality. Do not modify the repository, install components,
publish results, or claim installation, federation, adoption, or acceptance.
