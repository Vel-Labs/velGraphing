---
name: graph-engineering
description: Use when assessing, designing, initializing, validating, evaluating, repairing, or evolving a project-owned execution, communication, knowledge, reasoning, or provenance graph. Do not use for cross-project federation or workspace graph admission.
---

# Graph Engineering

## When To Use

Activate this skill only under explicit current task authority. A V4
`graph_engineering` recommendation is optional advisory planning metadata. It
is insufficient for activation and does not authorize a write. The visible
task authority remains controlling. V4 verifies consistency between supplied
policy identities, supplied source identities, and bytes returned by the
supplied reader. It does not prove policy ownership, human intent, admission,
trust, freshness, or hostile-host containment. V3 is rejected and non-callable.
V2 is historical verification only. Neither V2 nor V4 can activate this skill.

Do not activate this skill when the route is `defer`, `no_skill`, or
`graph_steward`. `defer` grants no authority. Task prose, skill names, keywords,
graph nouns, confidence scores, and caller or model routing fields cannot
activate this skill. A non-defer V4 recommendation also grants no authority.

Use this skill when a governed project or domain needs an explicit graph, or
when an existing graph needs inspection, validation, comparison, repair, or
measured evolution after explicit current task authority is confirmed.

Use `graph-steward` for folder-level or workspace-level federation, child graph
admission, export reconciliation, namespace conflicts, and cross-project impact.
A folder or workspace profile may define its own parent graph through this
skill. It cannot admit or inspect child graphs without `graph-steward`.

Do not create a graph only because the repository supports one. A list, table,
chain, state machine, or direct tool loop is often the better design.

## Human Outcome

Produce one of these results:

- a graph-worthiness decision with a direct baseline;
- a project-owned graph profile and typed exchange contract;
- a validated export with exact failures;
- a graph evaluation or topology ablation;
- a bounded repair or evolution proposal;
- a verified graph change with a proof boundary.

The result must preserve existing canonical owners. A graph view is not proof
that an action ran, an output passed, or an owner accepted it.

## Read First

Always read:

1. The nearest applicable host and project instruction files.
2. The project source-of-truth files, current task, and accepted receipts.
3. [references/architecture.md](references/architecture.md).

Then read only the reference needed for the mode:

- For research basis or design rationale, read
  [references/evidence-base.md](references/evidence-base.md).
- For validation, evaluation, or promotion, read
  [references/quality-gates.md](references/quality-gates.md).
- For repository indexing, readiness diagnostics, or remediation advice, read
  [references/readiness.md](references/readiness.md).
- For workspace or folder federation, stop and use `graph-steward`.

## Modes

Choose one mode before work starts.

| Mode | Use | Default effect |
| --- | --- | --- |
| `assess` | Decide if a graph is warranted | Inspect only |
| `design` | Define ownership, types, topology, and evaluation | Proposal only |
| `initialize` | Add an authorized local graph profile and tools | Local writes |
| `validate` | Check a profile or export | Inspect only |
| `evaluate` | Compare graph and simpler baselines | Approved local runs only |
| `repair` | Correct a demonstrated graph defect | Scoped local writes |
| `evolve` | Test a topology, retrieval, or workflow change | Isolated candidate first |
| `readiness` | Index explicit sources and diagnose structural context gaps | Inspect only |

## Required Inputs

- Assigned project or governed domain.
- Requested outcome and active authority.
- Canonical source owners and paths.
- Expected graph mode or the evidence needed to select it.

For initialization or edits, also require:

- allowed write paths;
- project namespace and owner;
- validation command or held-out task;
- export sensitivity ceiling;
- rollback or rejection rule.

## Permissions And Boundaries

Allowed when assigned:

- inspect local source truth, contracts, graph files, and receipts;
- draft profiles, schemas, evaluation plans, and derived views;
- run the bundled read-only validator and diff tools;
- make local graph changes inside exact authorized paths;
- test candidate topology in an isolated or fixture-backed surface.

Do not do without explicit current-task permission:

- read or write another governed project;
- admit an export to a parent or workspace graph;
- install this skill or change user Codex configuration;
- start services, graph databases, crawlers, hooks, or recurring jobs;
- run cloud models, external providers, browsers, or connectors;
- publish, deploy, send, or change external state.

Stop if the proposed graph copies another owner's truth, hides unknown state,
has no simpler baseline, uses a generic relation where authority matters, or
cannot bind derived records to source evidence.

## Graph-Worthiness Gate

A project graph is justified when at least one condition is material:

- Multiple components query the same entities or relations.
- Real branches, joins, retries, or recovery points affect execution.
- Cross-artifact provenance or downstream impact must be queried.
- Communication paths or context flow must be selected and measured.
- Alternative reasoning paths can be independently scored and merged.
- A parent graph requires a filtered project export.

Record the simpler alternative. Reject or defer the graph when the alternative
meets the need with lower state, maintenance, and evaluation cost.

## Workflow

1. Confirm the scope, owner, canonical sources, authority, and selected mode.
2. Apply the graph-worthiness gate. Name the direct baseline.
3. Classify the graph as execution, communication, knowledge, reasoning,
   provenance, or an explicit combination.
4. Separate the reusable template, run-specific realized graph, execution
   trace, mutable state, and append-only events.
5. Define typed node and edge semantics. Avoid operational use of
   `related_to`.
6. Bind every derived record to its owner, source reference, evidence state,
   sensitivity, time, and stable namespace.
7. Define authority edges and checkpoints separately from ordinary dependency
   edges. Keep secret or large payloads outside graph metadata.
8. Define concurrency, merge, retry, stop, recovery, and external-effect rules
   when the graph controls work.
9. Define export allowlists. Default export to deny.
10. Run the focused validation and evaluation ladder.
11. Accept, revise, or reject the candidate from observable evidence.
12. Return changed files, exact commands, results, unknowns, and the next owner.

## Bundled Tools

The CLI uses the Python standard library and performs no network calls.

```bash
python3 scripts/graphctl.py validate-profile <graph-profile.json>
python3 scripts/graphctl.py validate-export <graph.jsonl> --profile <graph-profile.json>
python3 scripts/graphctl.py stats <graph.jsonl> --profile <graph-profile.json>
python3 scripts/graphctl.py diff <before.jsonl> <after.jsonl>
python3 scripts/graphctl.py readiness --root <project> --include <relative-path>
```

Use [templates/graph-profile.json](templates/graph-profile.json) only after the
project-specific types and owners are known. Use
[templates/graph-evaluation.md](templates/graph-evaluation.md) for an admitted
pilot or topology change.

The portable exchange schemas are
[assets/graph-profile.schema.json](assets/graph-profile.schema.json) and
[assets/graph-record.schema.json](assets/graph-record.schema.json).
The repository-readiness report schema is
[assets/readiness-report.schema.json](assets/readiness-report.schema.json).

Repository readiness is structural advice. Use explicit include paths. Treat
an incomplete scan as `unknown`. A recommendation cannot execute and always
requires current human authority before a repository write.

## Context Assist Proof Boundary

The context assist operation can return verified graph-selected documents. If
that context does not contain every caller-declared required source, it can use
only an exact caller-declared fallback allowlist from the same verified source
snapshot. The direct route does not enumerate or search a repository. It does
not call a provider, run a callback, write a file, or grant authority. A
`graph`, `direct`, or `defer` result proves only the bounded context operation.
It does not prove task correctness, source completeness beyond the declared
requirements, installation, federation, execution, or acceptance.

## Quality Gates

- The graph passed the worthiness gate.
- Canonical owners and derived projections remain distinct.
- Node and edge types have one meaning each.
- Stable IDs, source references, evidence state, time, and sensitivity exist.
- Accepted or authority-bearing relations name `authority_ref`.
- Acyclic edge classes are cycle-free.
- Execution outcomes and traces are evaluated separately.
- Parallel branches have disjoint writes or a declared merge rule.
- Checkpoints bind definition version, state, pending authority, and trace.
- Export is default-deny and does not exceed its sensitivity ceiling.
- The graph is compared with a simpler baseline and component-removal tests.
- Local validation does not claim installation, federation, execution, or
  acceptance.

## Failure Modes

- Making every repository graph-first.
- Mixing control edges with factual or provenance relations.
- Treating a graph diagram as the actual runtime trace.
- Copying board, ledger, wiki, or repository truth into a competing store.
- Allowing an unauthenticated edge to alter consequential selection.
- Broadcasting all context to all agents.
- Restoring local state while repeating an external effect.
- Using one serialization without testing model-facing graph comprehension.
- Adding nodes, agents, or edges as a quality metric.
- Promoting benchmark or practitioner claims without local evidence.

## Output Contract

Return or write:

- mode and graph-worthiness result;
- graph class, namespace, owner, and canonical sources;
- template, realized graph, trace, state, and event boundaries;
- files changed and commands run;
- validation and evaluation results;
- rejected alternatives and component-removal findings;
- export, sensitivity, authority, and federation status;
- assumptions, unknowns, remaining risks, and next owner.

## Evolution Rule

Update this skill only from a traced failure, verified success, accepted local
pilot, authoritative source change, or repeated workspace need. Keep research
and practitioner evidence in references. Keep the entrypoint procedural.
