---
name: graph-audit
description: Measure whether Graph Engineering helps on a repository by comparing a source-bound graph-assisted route with direct repository use. Use for read-only readiness checks or paired effectiveness audits, not setup or repository mutation.
---

# Graph Audit

Keep the repository read-only. Read the nearest instruction files, then read
[the Graph Engineering skill](../graph-engineering/SKILL.md). Use its bundled
`scripts/graphctl.py`; do not copy the graph runtime into the target repository.

## Readiness Check

For a structural check, run `graphctl.py readiness` against explicit include
paths. Use `--policy-status complete` only when the scan covers the complete
declared repository scope. Report missing anchors, broken references, source
identity, and whether the result is `ready`, `not_ready`, or `unknown`.

Readiness measures repository structure. It does not measure answer quality or
prove that graph navigation is useful.

## Effectiveness Audit

Use a paired audit when the user asks whether the graph improves agent work:

1. Freeze one to three representative repository questions before either route
   runs. Prefer user-provided questions and required facts. Otherwise label
   answer quality `unscored`.
2. Run fresh Direct and Graph-assisted lanes with the same model, reasoning
   level, question, repository snapshot, and write restrictions.
3. The Direct lane uses ordinary repository tools. The Graph-assisted lane
   starts with graph navigation and may use source-bound fallback when its own
   evidence is incomplete.
4. Record only observable values: required-fact coverage, model-visible source
   context, repository tool operations, graph/index build cost, fallback reads,
   wall-clock time, prohibited writes, and proof or authority errors.
5. Show Direct, Graph-assisted, and percentage change in one table. Separate
   cold-build cost from warm reuse. Do not call a result an improvement when
   required-fact coverage declines or safety errors increase.

Stop after the comparison. Do not modify the repository, install components,
or publish results unless the user separately authorizes that action.

## Output

Return the repository snapshot, questions, route controls, result table,
verdict, important caveats, and exact commands or tools used. Say `unscored`
when no independent required-fact rubric exists.
