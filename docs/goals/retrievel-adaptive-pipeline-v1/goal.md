# retrieVEL adaptive pipeline V1

## Objective

Deliver one source-governed retrieval pipeline that selects Direct or Graph
retrieval, invokes Jev only when semantic reduction can change the answer
context, preserves required evidence, falls back safely, and measures complete
time to correctness.

The public product remains VelGraphing until the integrated result supports a
separate packaging or naming decision.

## Completion proof

1. One supported product entry point selects Direct or Graph retrieval from
   deterministic source-bound signals.
2. Jev is skipped when its result cannot change the selected context.
3. A valid Jev response can reduce optional answer context. Required evidence
   remains present and source-verified.
4. Invalid, unavailable, low-value, or stale Jev output retains the verified
   baseline or uses the declared Direct fallback.
5. End-to-end telemetry records retrieval, graph expansion, Jev, context
   selection, answer, validation, fallback, usage, cost, and wall-clock time.
6. A frozen public-corpus study compares Direct/off, Direct/Jev, Graph/off, and
   Graph/Jev across exact, relational, synthesis, and heterogeneous-document
   tasks.
7. The installable package matches canonical source and passes focused,
   consumer, full, parity, and installed-interface validation.
8. One independent audit accepts the final candidate or records a bounded
   rejection with no unsupported performance claim.

## Scope and authority

- Allowed writes: this repository only.
- Allowed commands: local inspection, tests, builds, package projection,
  disposable installation, benchmark execution, and Git operations required
  for an implementation branch and review pull request.
- Network: allowed for current TypeSafe documentation, approved public Git
  operations, and Jev calls within the provider budget below.
- Provider: TypeSafe Jev only, model pinned to `jev-1.13.0`.
- Aggregate Jev allowance: at most USD 1.00 for this goal.
- Provider source scope: public benchmark material only. Do not send private
  repository source.
- Do not access or print credentials. Use only an already available process
  environment credential.

## Product boundary

Repository source remains authoritative. Graph records are derived navigation
evidence. Jev supplies advisory semantic scores over materialized source spans.
Code owns routing, source revalidation, budgets, required evidence, fallback,
telemetry, and the final selection decision.

## Direct baseline

The Direct baseline uses the same source reader and source snapshot without
typed-neighborhood expansion or Jev judgment.

## Non-goals

- Raw-graph reasoning by Jev.
- New vector database, daemon, crawler, hook, scheduler, or cloud index.
- GNN training or a RepoHyper-scale implementation.
- A registry of versioned selection policies.
- Automatic consumer-repository changes.
- Performance claims from replay, fixtures, retrieval-only evaluation, or a
  provider response without end-to-end answers and grading.

## Milestones

| Task | Result |
| --- | --- |
| T010 | Implement one deterministic route and Jev-use decision at the existing source-bound selector seam. |
| T020 | Validate the integrated installed path and run the smallest useful live Jev canary within the aggregate allowance. |
| T030 | Freeze and run the four-arm public-corpus time-to-correct study with relationship strata. |
| T040 | Refine user documentation, package projection, examples, contribution guidance, and claims from measured evidence. |
| T050 | Run full validation, independent audit, push the candidate branch, and open the review pull request. |
| T999 | Parent lifecycle closeout, child inventory, final receipt, and completion audit. |

## Stop and redesign rule

After two failures with the same signature and no changed hypothesis, stop the
micro-repair loop. Change the architecture hypothesis or split the milestone.
Do not weaken source authority, required-evidence preservation, provider budget,
or benchmark comparators to obtain a passing result.

