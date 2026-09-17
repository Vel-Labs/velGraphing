# VelGraphing public product V1

## Objective

Turn the current VelGraphing alpha into a source-verified repository navigation
release candidate that a new user can install, use, audit, and benchmark.

## Completion proof

1. The installed package exposes `/graph-find` and invokes the supported
   retrieval runtime.
2. Graph exports do not contain complete repository source bodies.
3. A disposable-repository lifecycle passes: install, start, find, edit,
   update, find, audit, benchmark, and uninstall.
4. Repository scope, secrets, binaries, large files, dependencies, rollback,
   security reporting, contribution, change history, and CI are documented and
   checked.
5. A frozen public benchmark compares Direct, graph-only, graph-assisted, and
   graph-assisted-with-fallback through the shipped interface.
6. One independent audit accepts the frozen release candidate.

## Scope

- Allowed writes: this repository only.
- Allowed commands: local tests, builds, package projection, disposable local
  installation, benchmark execution, and explicitly authorized Orcastrata
  model calls.
- Network: allowed for the user-authorized provider calls and release research.
- Publishing, pushing, GitHub writes, and consumer-repository writes: not
  authorized by this goal.

## Product boundary

The graph routes an agent to evidence. Repository source remains authoritative.
The broker reads exact source spans. The system can abstain or select direct
source when graph evidence is stale, incomplete, ambiguous, or high risk.

## Direct baseline

The direct baseline uses ordinary repository listing, search, and exact source
reads without a graph index.

## Non-goals

- Vector database.
- Daemon or background service.
- Cloud-hosted index.
- Cross-repository federation.
- Autonomous hooks.
- New parser languages without benchmark evidence.
- Public release or social post.

## Task sequence

| Task | Result |
|---|---|
| T010 | Map the smallest `/graph-find` and source-pointer integration seam. |
| T020 | Implement and validate `/graph-find`. |
| T030 | Independently audit Gate 1. |
| T040 | Remove source bodies from graph exports and preserve exact-source resolution. |
| T050 | Prove the clean installed lifecycle and freshness behavior. |
| T060 | Close privacy, scope, bootstrap, CI, security, contribution, and rollback gaps. |
| T070 | Freeze the shipped-interface public benchmark. |
| T080 | Execute, score, and interpret the benchmark. |
| T090 | Freeze and independently audit the release candidate and public claims. |
| T999 | Parent lifecycle closeout and final inventory. |

## Stop and redesign rule

After two failures with the same signature and no changed hypothesis, stop the
repair loop. Run an adversarial Orcastrata review and choose a new bounded
design. Do not weaken source authority, privacy, or benchmark comparators to
obtain a passing result.
