# retrieVEL adaptive pipeline V1

## Objective

Deliver one source-governed repository graph and retrieval pipeline that helps
agents reach correct answers with less context and less wall-clock time.
Deterministic code owns graph truth, source custody, routing, budgets, and
fallback. Jev is an optional semantic judgment over verified source evidence.

The public product remains VelGraphing. `retrieVEL` names this adaptive
retrieval program until evidence supports a separate package decision.

## Current truth

- PR #11 is the product candidate. It is based on `main` and is mergeable with
  green Python 3.11 and 3.13 checks.
- PR #12 is the evidence candidate. It is stacked on PR #11 and is mergeable
  with green Python 3.11 and 3.13 checks.
- PR #11 must merge first. PR #12 must then target the merged `main`, retain
  evidence-only scope, pass CI, and merge second.
- T030 is closed unresolved. Its failures and partial results remain evidence.
  They do not prove Graph value, Jev value, or product performance.
- Forty-six live Jev calls occurred during the prior goal. None used the exact
  final installed PR #11 `graph-find --ranked-context evaluate` path.
- The Jev allowance is an aggregate USD 1.00 budget. It is not a fixed call
  count. Per-run call ceilings are safety controls only.

## Architecture direction

Use one canonical source-bound graph with multiple task projections.

1. Source and symbol nodes are the authoritative foundation.
2. Language adapters emit verified typed relations.
3. A shared relation contract keeps language outputs comparable.
4. Connector nodes represent source-witnessed interstitial identities such as
   APIs, commands, packages, schemas, tables, topics, and configuration keys.
5. Cross-language identity resolution links compatible symbols and connector
   identities without treating a model judgment as graph truth.
6. Coverage and unresolved reports expose what the graph can and cannot prove.
7. Incremental refresh updates only changed source-bound graph material.
8. Obsidian-style modes are projections over the same graph: global coverage,
   local task depth, backlinks or impact, connector or interface, answer
   evidence, and unresolved candidates.
9. Jev may classify task intent and rank optional neighborhoods or evidence.
   It cannot admit a node or edge without deterministic source witness.
10. End-to-end evaluation measures accepted correctness, complete wall-clock
    time, context discovery, answer production, all-model usage, and fallback.

## Completion proof

1. PR #11 and PR #12 land in the declared order with clean post-merge checks.
2. The installed product derives source-witnessed relations through a canonical
   core seam and reports supported, unresolved, and unsupported relation work.
3. At least two language families use the shared typed-relation contract, with
   explicit unsupported coverage instead of silent omission.
4. Connector identities remain derived and source-bound. Cross-language links
   are deterministic, explainable, and reversible.
5. The supported graph projections operate over one graph and preserve direct
   source fallback.
6. The exact installed product path completes a bounded live Jev canary within
   the aggregate USD 1.00 ledger. Required evidence and source membership remain
   valid under provider success, rejection, timeout, and malformed response.
7. A frozen public-corpus study compares Direct/off, Direct/Jev, Graph/off, and
   Graph/Jev on correctness, all-in wall time, context bytes, all-model usage,
   provider cost, retrieval coverage, and failure class.
8. Focused, consumer, full, projection-idempotence, package-parity, and
   installed-interface checks pass for the final candidate.
9. One independent audit accepts the final candidate or records a bounded
   rejection. No unsupported performance claim is published.

## Scope and authority

- Allowed writes: this repository only.
- Allowed commands: local inspection, tests, builds, package projection,
  disposable installation, benchmark execution, and required Git operations.
- Network: allowed for current public documentation, approved public Git
  operations, and TypeSafe Jev calls within the budget.
- Provider: TypeSafe Jev with the explicitly selected model and live contract.
- Aggregate Jev allowance: at most USD 1.00 for this goal. Record actual or
  conservative worst-case spend before each additional live batch.
- Provider source scope: public benchmark material only. Do not send private
  repository source.
- Do not access, print, or persist credentials. Use an approved process-level
  credential handoff only.

## Product boundary

Repository source remains authoritative. Graph records and connector nodes are
derived navigation evidence. Jev supplies advisory semantic judgment over
materialized source spans. Code owns graph admission, source revalidation,
budgets, required evidence, fallback, telemetry, and final context selection.

## Non-goals

- Jev admission of graph truth.
- A database, daemon, hook, scheduler, cloud index, or second repository crawler.
- A comprehensive language catalog in one change.
- A registry of speculative versioned selection policies.
- Automatic changes to consumer repositories.
- Performance claims from replay, fixtures, retrieval-only evaluation, or a
  provider response without end-to-end answer and grade evidence.

## Milestones

| Task | Result |
| --- | --- |
| T010 | Integrated deterministic route, selection, and optional Jev seam. |
| T020 | Installed binding canary; live transport history retained. |
| T030 | Prior four-arm evaluation closed unresolved and preserved. |
| T040 | Product and evidence candidates separated into PR #11 and PR #12. |
| T050 | Merge PR #11, retarget and verify PR #12, then merge PR #12. |
| T060 | Move relation derivation behind one core seam and expose coverage and unresolved reporting. |
| T070 | Add the next language-family relation adapter through the shared contract. |
| T080 | Add source-witnessed connector identities and bounded cross-language resolution. |
| T090 | Add global, local, impact, connector, evidence, and unresolved graph projections. |
| T100 | Run the exact installed live Jev canary under the aggregate dollar ledger. |
| T110 | Run and seal the redesigned end-to-end four-arm study. |
| T999 | Run the final audit and Parent lifecycle closeout. |

## Stop and redesign rule

After two failures with the same signature and no changed hypothesis, stop the
micro-repair loop. Change the architecture hypothesis or split the milestone.
Do not weaken source authority, required evidence, provider budget, or benchmark
comparators to obtain a passing result.
