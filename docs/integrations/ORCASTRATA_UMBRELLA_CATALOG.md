# Orcastrata Umbrella Catalog Intake

This guide supports three integration paths:

| Path | Use it when | Starting point |
| --- | --- | --- |
| Use [Orcastrata Max](https://github.com/Vel-Labs/orcastrata-max) | You want its umbrella view of repository, GoalBuddy, and WorkGraph references. | Export its canonical umbrella catalog and pass it to the VelGraphing adapter. |
| Build a compatible producer | Your orchestrator can emit the same closed JSONL contract. | Follow the contract and validation rules below. |
| Build a related adapter | Your data has different meaning or fields. | Reuse the provenance and fallback model, but define a new `artifact_type` and schema version. |

## Status

VelGraphing implements a consumer-owned, navigation-only Orcastrata adapter at
`adapters/orcastrata-umbrella-catalog/`. The producer contract is
`assets/contracts/umbrella-catalog-v1.md` in the Orcastrata package. Its machine
fixtures are `assets/templates/umbrella-catalog-v1-schema.json` and
`assets/templates/umbrella-catalog-v1-{valid,invalid}.json`.

The adapter is optional. It runs only when a catalog is supplied. It does not
start Orcastrata, inspect unrelated projects, or change repository state.

## Ownership

- Orcastrata owns catalog generation and source validation.
- GoalBuddy owns lifecycle and acceptance truth.
- WorkGraph owns dependency, readiness, scope, validation, and evidence truth.
- VelGraphing owns consumer admission, graph mapping, retention, and federation.
- GitHub is a synchronized collaboration surface. It is not execution truth.

The adapter must never write graph conclusions or lifecycle state back to
Orcastrata, GoalBuddy, WorkGraph, or GitHub.

## Required Intake

Consume the canonical JSONL generation. Do not parse the generated Markdown
view. Require exact `artifact_type: orcastrata_umbrella_catalog_v1` and
`schema_version: 1`. Validate the closed schema, record count, unique umbrella
identities, record digests, and catalog digest before mapping any record.

When producer sources are available, resolve each projection inside the
admitted source root and match its raw receipt and projection digests. Also
match the graph and board digest bindings to the receipt. V1 does not publish the
source paths or digest rules required to recompute the underlying WorkGraph and
GoalBuddy board digests. These checks prove digest consistency, not source
authentication. The adapter therefore keeps every mapped record
ineligible, marks freshness unknown, and requires direct source fallback for
consequential claims. Apply the stricter producer or consumer sensitivity rule.
Reject an exportable restricted record.

## Build A Compatible Producer

A compatible producer must implement the exact V1 meaning. Do not use the
Orcastrata `artifact_type` for data with different semantics.

1. Emit one canonical UTF-8 JSON object followed by one newline.
2. Set `artifact_type` to `orcastrata_umbrella_catalog_v1` and
   `schema_version` to `1`.
3. Sort records by `umbrella_id` and keep each identity unique.
4. Calculate each `record_sha256` from the canonical record without its
   `record_sha256` field.
5. Calculate `catalog_sha256` from the canonical `records` array.
6. Preserve provenance, sensitivity, exportability, tag owner, and tag source
   fields without reinterpretation.
7. Keep projection and receipt paths relative to one admitted source root.
8. Bind each projection, graph, board, and raw receipt digest as required by
   the producer contract.

Use the
[`valid.jsonl`](../../adapters/orcastrata-umbrella-catalog/fixtures/valid.jsonl)
and
[`invalid.jsonl`](../../adapters/orcastrata-umbrella-catalog/fixtures/invalid.jsonl)
fixtures as small conformance examples. The
[`adapter.py`](../../adapters/orcastrata-umbrella-catalog/adapter.py)
implementation is the reference consumer. Its
[`test suite`](../../tests/adapters/test_orcastrata_umbrella_catalog_adapter.py)
shows the admission and stale-data boundaries.

## Minimum Graph Mapping

Map each admitted record to the smallest useful project-owned graph:

| Catalog field | VelGraphing meaning |
| --- | --- |
| `umbrella_id` | Stable `Umbrella` node identity |
| `references.github_repository` | `Repository` node reference |
| `references.projection` | Producer source reference |
| `references.goalbuddy_owner` | Canonical lifecycle-owner reference |
| `references.workgraph_id` | Canonical dependency-owner reference |
| `tags` | Discovery metadata with class, value, owner, and source preserved |
| `digests` | Provenance bindings; never confidence scores |
| `evidence_state` | Producer evidence state; never consumer acceptance |
| `sensitivity`, `exportable` | Input to the stricter local export policy |

Use typed `derived_from`, `describes`, and `evidenced_by` edges where the source
supports them. Do not infer authority, completion, or dependency edges from a
tag or catalog presence alone.

## Freshness And Failure

The catalog is a snapshot and has no tombstones. Missing records do not prove
deletion or closure. On a missing source, digest mismatch, unknown version,
ambiguous identity, or absent required field:

1. Use an authorized direct read of GoalBuddy, WorkGraph, the projection, or
   GitHub and cite that source.
2. Otherwise return `defer`.

Keep the last valid generation only as a stale navigation snapshot. Never use
it for routing, merge, closure, or acceptance without fresh direct validation.

## Adapter Acceptance

Before admission, test the producer's valid and invalid fixtures plus one stale
source and one unknown-version case. Compare direct and catalog-assisted answers
on the same frozen source. Require no regression in fact recall or source
location, zero stale consequential answers, and no increase in unsupported
claims. Record tokens, cost, latency, and source reads only when the runtime
reports them.

Federation admission, background refresh, and AOL adoption are separate tasks.
This adapter grants none of them.
