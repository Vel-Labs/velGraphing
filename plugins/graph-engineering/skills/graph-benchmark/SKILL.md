---
name: graph-benchmark
description: Compare a source-bound Graph-assisted route with direct repository use under a frozen, read-only benchmark. Use for measured effectiveness, not setup or mutation.
---

# Graph Benchmark

Read the nearest instruction files, [the Graph Engineering skill](../graph-engineering/SKILL.md), and [Graph Audit](../graph-audit/SKILL.md). Keep the repository read-only.

## Workflow

1. Freeze representative questions, required facts, repository snapshot, model and reasoning level, route controls, and write restrictions before either route runs.
2. Run fresh Direct and Graph-assisted lanes against the same snapshot and question order. The Graph-assisted lane may use only source-bound fallback allowed by the caller.
3. Record required-fact coverage, model-visible context bytes, repository operations, graph build and load cost, fallback reads, wall-clock time, prohibited writes, proof errors, and authority errors.
4. Separate cold-build, warm-load, retrieval, fallback, and answer costs. Do not convert local source bytes into model-token cost.
5. Report Direct, Graph-assisted, and percentage change in one table. Mark answer quality `unscored` when no independent required-fact rubric exists.
6. Accept an improvement only when required-fact coverage does not decline and safety errors do not increase. Otherwise report a rejection or an unresolved result.

Use `scripts/graphctl.py readiness` only for structural readiness. It does not
measure answer quality. Do not modify the repository, install components,
publish results, or claim installation, federation, adoption, or acceptance.
