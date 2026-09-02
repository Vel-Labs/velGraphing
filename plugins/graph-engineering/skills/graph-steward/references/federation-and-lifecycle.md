# Federation And Lifecycle

## Hierarchy

The workspace uses a federated graph of graphs.

```text
project graph -> folder graph -> workspace collective graph
```

Each arrow means “the parent may index an approved filtered export.” It does
not mean “the parent owns or can rewrite the child.”

An organization-only folder does not need a graph. Add a folder graph when the
folder owns useful cross-child relationships such as package consumption,
capabilities, goals, sources, or shared policy references.

## Registry Versus Graph Data

The federation registry stores:

- child identity and namespace;
- owner and authority reference;
- contained profile and export locators;
- definition version, profile digest, and export digest;
- lifecycle and ingest mode;
- allowed types and sensitivity ceiling;
- validation reference and validator identity.

The registry should not store:

- copied child records;
- secrets or source payloads;
- runtime credentials or provider state;
- child acceptance decisions;
- scheduler or service configuration.

## Admission Decision

Admission needs all of these:

1. Child graph owner and stable namespace.
2. Current graph profile.
3. Deterministic filtered export.
4. Default-deny allowlists.
5. Sensitivity ceiling.
6. Profile and export SHA-256 or equivalent identities.
7. Full profile and export structural verification with the named validator.
8. Child-owner authority reference.
9. Parent-owner registry authority.
10. Cross-graph impact review when an existing child changes.

A proposal or validation pass is not admission.

## Cross-Graph Relations

Cross-graph edges belong to the lowest common parent that owns the relation.

Examples:

- A `40_Code` folder graph can own `package_consumed_by` between two projects.
- A `50_Agents` graph can own `skill_routes_to` between a skill and a worker
  contract.
- The workspace graph can own `capability_owned_by` between a shared capability
  and a project.

The edge must cite its evidence and both child node locators. It must not change
the meaning or lifecycle of either child node.

## Drift Classes

- **Content drift:** Export digest changed.
- **Definition drift:** Profile, schema, or graph version changed.
- **Ownership drift:** Owner or authority reference changed.
- **Namespace drift:** IDs or namespace changed.
- **Policy drift:** Allowlists or sensitivity changed.
- **Source drift:** Canonical source reference is stale or missing.
- **Validator drift:** Current tooling no longer accepts prior evidence.

Content or definition drift normally moves `admitted` to `stale`. Trust,
authority, namespace collision, or leakage risk moves it to `quarantined`.

## Impact Checks

Before removal, retirement, namespace change, or type deletion, identify:

- parent cross-graph edges that reference affected IDs;
- downstream views and queries;
- goals, receipts, reports, or skills that cite the child;
- replacement or tombstone behavior;
- whether the change is breaking.

Do not delete child sources. Retirement changes federation state only.

## Security

- Resolve declared paths and prove containment before reading.
- Use regular files. Reject symlink escapes where the runtime can detect them.
- Verify digests before admission or refresh.
- Enforce record and edge provenance.
- Enforce exportability, type allowlists, and sensitivity.
- Treat graph structure as security-relevant input.
- Quarantine unknown or unauthorized structural writes.
- Keep secrets and sensitive payloads outside exchange records.

## Proof Boundary

Registry validation proves only that local registry structure passes the current
validator. Export verification proves only that the inspected files match the
declared local policy. Neither proves a live database, index, query service,
background refresh, project acceptance, or external action.
