---
name: graph-steward
description: Use when governing folder-level or workspace-level graph federation, child graph admission, export verification, namespace ownership, cross-graph relations, drift, quarantine, retirement, or impact analysis. Do not use to design a single project graph.
---

# Graph Steward

## When To Use

Activate this skill only under explicit current task authority. A V4
`graph_steward` recommendation is optional advisory planning metadata. It is
insufficient for activation and does not authorize a write. The visible task
authority remains controlling. V4 verifies consistency between supplied policy
identities, supplied source identities, and bytes returned by the supplied
reader. It does not prove policy ownership, human intent, admission, trust,
freshness, or hostile-host containment. V3 is rejected and non-callable. V2 is
historical verification only. Neither V2 nor V4 can activate this skill.

Do not activate this skill when the route is `defer`, `no_skill`, or
`graph_engineering`. `defer` grants no authority. Task prose, skill names,
keywords, graph nouns, confidence scores, and caller or model routing fields
cannot activate this skill. A non-defer V4 recommendation also grants no authority.

Use this skill for a folder graph or the workspace collective graph after
explicit current task authority is confirmed. Use it to inspect or maintain the registry of child
graphs, validate filtered exports, manage lifecycle state, reconcile drift, or
answer cross-project impact and ownership questions.

Use `graph-engineering` to assess, design, initialize, validate, evaluate, or
repair one project-owned graph.

Do not use this skill to crawl the workspace, rewrite child truth, execute a
child workflow, approve a project result, or flatten private project data.

## Human Outcome

Produce one of these results:

- a validated federation registry;
- a no-effect admission or ingest plan;
- a verified child export and digest;
- a quarantine, stale, or retirement recommendation;
- a cross-graph ownership or impact report;
- a scoped registry change with owner evidence.

The workspace graph remains a discovery and relationship layer. It does not
become the canonical owner of each child graph.

## Read First

1. The nearest applicable host and project instruction files.
2. The host's workspace or project index when one exists.
3. The active task, allowed paths, and accepted receipts.
4. [references/federation-and-lifecycle.md](references/federation-and-lifecycle.md).

When a child profile or export is in scope, also read that project's local
`graph-steward` or graph contract. For research and common record semantics,
use `../graph-engineering/references/evidence-base.md` and
`../graph-engineering/references/architecture.md`.

## Modes

| Mode | Use | Default effect |
| --- | --- | --- |
| `inspect` | Show registry, child status, owners, and gaps | Read only |
| `plan` | Compute admission, refresh, quarantine, or retirement actions | Read only |
| `verify` | Check registry, paths, digests, exports, and policy | Read only |
| `admit` | Add an authorized validated child export | Registry write only |
| `reconcile` | Resolve drift or namespace/type conflicts | Proposal first |
| `impact` | Query downstream or cross-project relationships | Read only |
| `retire` | Remove a child from active federation without deleting its source | Registry write only |

## Required Inputs

- Target folder or workspace graph ID.
- Federation registry path and owner.
- Current task authority.
- Workspace root.
- Requested lifecycle or query operation.

For admission or refresh, also require:

- child graph profile and filtered export;
- child namespace, owner, and definition version;
- profile and export digests;
- child owner authority reference;
- current validation reference and validator identity;
- allowed node and edge types;
- sensitivity ceiling;
- verification result.

## Permissions And Boundaries

Allowed when assigned:

- inspect registry, profiles, exports, digests, and source references;
- run bundled read-only registry planning and verification;
- draft admission, quarantine, retirement, or impact reports;
- edit the exact authorized federation registry;
- add parent-owned cross-graph relations with evidence and authority references.

Do not do without explicit current-task permission:

- inspect arbitrary child files not named by an approved export contract;
- generate or modify a child graph;
- change a child board, ledger, wiki, repository, or acceptance record;
- enable crawling, indexing, services, hooks, schedules, or heartbeats;
- install skills or modify user Codex configuration;
- use network, providers, credentials, browsers, connectors, or publishing;
- delete, move, or rename child source data.

Stop if a child has no owner, namespace, filtered export, authority reference,
contained path, digest, or current validation. Stop if federation would expose
data above the declared sensitivity ceiling or merge incompatible meanings.

## Federation Rules

1. Each child owns its namespace, profile, source truth, and export policy.
2. The registry records locators and admission state. It does not copy child
   payloads as authority.
3. Export defaults to deny. Admission uses explicit type allowlists.
4. Parent graphs may add cross-child relations only when the parent owns that
   relationship and cites evidence.
5. Parent relations that reference acceptance or approval must use
   `acceptance_ref` or `approved_by_ref`. The named owner remains authoritative.
6. A stale, quarantined, or retired child cannot be ingested as approved.
7. Digest or definition drift removes current verification. It does not update
   the child automatically.
8. Child failure is isolated. Other valid child graphs remain available.
9. Private or restricted child records do not become visible because a parent
   graph exists.
10. A successful registry check is not a live query, index, service, or
    operational acceptance result.

A proposal or validation pass is not admission. Admission requires the current
child-owner and parent-owner authority evidence defined below.

## Lifecycle

Use these states:

- `proposed`: locator and owner are known; validation is incomplete.
- `validated`: profile and export passed current structural checks.
- `admitted`: owner authority, digest, allowlists, and sensitivity passed.
- `stale`: source, definition, digest, or validation is no longer current.
- `quarantined`: trust, authority, security, schema, or leakage defect exists.
- `retired`: no longer included in active federation; source remains owned by
  the child.

Allowed progression:

```text
proposed -> validated -> admitted
validated | admitted -> stale | quarantined | retired
stale | quarantined -> validated only after new evidence
retired is terminal in the same registry entry
```

## Workflow

1. Confirm the target graph, registry owner, requested mode, and exact scope.
2. Validate the registry structure and namespace uniqueness.
3. In `plan`, compute actions without requiring or changing child files.
4. For each active child, resolve only the declared contained profile and export
   paths.
5. Verify lifecycle, ingest mode, authority, digest, type allowlists,
   sensitivity, namespace, and exportability.
6. Preserve `not_run`, stale, quarantined, retired, and unknown states.
7. For admission, require fresh child-owner authority and current validation.
8. Add cross-graph edges only under the parent namespace and owner.
9. Run impact checks for removals, type changes, or namespace changes.
10. Write only the authorized registry or report. Never repair child truth from
    the parent.
11. Return exact evidence, results, unknowns, and the next owner.

## Bundled Tools

The CLI uses the Python standard library. It performs no network calls and no
writes.

```bash
python3 scripts/stewardctl.py validate-registry <registry.json> --workspace-root <workspace-root>
python3 scripts/stewardctl.py plan <registry.json> --workspace-root <workspace-root>
python3 scripts/stewardctl.py verify <registry.json> --workspace-root <workspace-root>
```

Start proposals from
[templates/federation-registry.json](templates/federation-registry.json). Do
not reuse its placeholder IDs as live values.

Validate registry structure against
[assets/federation-registry.schema.json](assets/federation-registry.schema.json).

## Quality Gates

- Registry graph ID, namespace, owner, and workspace root are explicit.
- Child graph IDs and namespaces are unique.
- All resolved paths stay inside the assigned workspace root.
- Active paths are regular files and match the expected digest.
- The profile digest, definition version, owner, and current validation match.
- Parent allowlists and sensitivity only narrow the child export policy.
- `admitted` and `approved` appear together with `authority_ref`.
- Type allowlists and sensitivity ceilings pass.
- Exported records are namespaced, source-backed, and `exportable: true`.
- Stale, quarantined, retired, disabled, and proposed children do not ingest.
- Parent relations have a parent owner and do not copy child authority.
- Removal or schema changes include downstream-impact evidence.
- Unknown and `not_run` states remain visible.

## Failure Modes

- Treating the workspace graph as a universal database.
- Crawling children instead of consuming filtered exports.
- Letting a child write cross-project relations under another namespace.
- Keeping an admitted state after digest or definition drift.
- Hiding a disabled or failed child as an empty successful graph.
- Importing secrets, payloads, personal data, or restricted evidence.
- Treating an acceptance reference as the acceptance decision.
- Repairing a child from the parent registry.
- Claiming a plan or validation result is a live federated service.

## Output Contract

Return or write:

- mode, registry, graph ID, namespace, owner, and workspace root;
- child lifecycle, ingest, authority, digest, and verification states;
- planned or applied registry changes;
- cross-graph edges and their parent owner;
- commands and exact results;
- visible `not_run`, stale, quarantined, retired, and unknown states;
- files changed, assumptions, risks, and next child or parent owner;
- explicit install, index, service, network, publication, and acceptance status.

## Evolution Rule

Change federation policy only from an observed cross-graph defect, accepted
pilot, authoritative source change, or repeated workspace need. A child schema
change belongs to the child and `graph-engineering` first.
