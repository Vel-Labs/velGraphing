# RetrieVel

Source-verified graph navigation for coding agents.

RetrieVel is the public name for the product formerly called VelGraphing. It
helps an agent decide where to look, retrieves exact source spans, and keeps
repository source authoritative. The repository remains named `velGraphing`
through the 0.2.x line. The plugin and Python package ID remains
`graph-engineering`.

See [product identity and compatibility](docs/architecture/PRODUCT_IDENTITY_AND_COMPATIBILITY.md)
for stable identifiers and migration rules.

## Commands

| Command | Purpose |
| --- | --- |
| `/graph-find` | Find source-verified pointers for a repository prompt. |
| `/graph-start` | Inspect a repository and prepare the smallest useful graph setup. |
| `/graph-update` | Refresh an existing graph after source changes. |
| `/graph-audit` | Measure graph readiness and effectiveness. |
| `/graph-benchmark` | Compare Direct and Graph-assisted repository work. |
| `/graph-jev` | Configure, preview, and test optional Jev evidence reranking. |

The public display name is **RetrieVel**, formerly VelGraphing. The repository
name and plugin and Python package ID remain stable during this transition.

## Retrieval path

RetrieVel scans eligible Git-tracked source files and verifies source identity
and spans. It expands typed relationships only when source evidence supports
them. It selects a bounded, ranked context from verified spans. When graph
evidence is incomplete, it can use caller-declared direct-source fallback. If
the fallback is unavailable or incomplete, the route defers. Optional Jev can
rerank a verified shortlist. It cannot add evidence or grant authority.

These statements describe implemented behavior. They do not establish general
correctness, wall-clock, token, cost, or provider-performance improvements.
The retained four-arm result is directional diagnostic evidence only. The
corpus pilot does not establish wall-clock savings. See the
[benchmark evidence index](benchmarks/README.md) for the exact boundaries.

## Install

```sh
codex plugin marketplace add Vel-Labs/velGraphing --ref main
codex plugin add graph-engineering@graph-engineering-local
```

Start a new Codex task after installation so the command list reloads.

For local Python development, use a repository-local virtual environment. The
project requires Python 3.11 or newer and pins its parser dependencies.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
```

To remove the installed plugin, run:

```sh
codex plugin remove graph-engineering@graph-engineering-local
```

`/graph-find` does not create a repository index or other repository files, so
it has no graph data to roll back. If an explicitly approved setup command
writes project files, use the rollback list that command reports.

## Orchestration Adapters

RetrieVel includes an optional catalog adapter for
[Orcastrata Max](https://github.com/Vel-Labs/orcastrata-max). It converts the
canonical Orcastrata umbrella catalog into navigation context for umbrella,
repository, WorkGraph, and GoalBuddy references. Source remains authoritative.
Stale or incomplete catalog evidence returns `defer` or requires direct source
fallback.

You can also implement the same contract for another orchestration system. See
the [orchestration catalog integration guide](docs/integrations/ORCASTRATA_UMBRELLA_CATALOG.md)
for the JSONL contract, validation rules, minimum graph mapping, and failure
behavior.

## Optional Jev integration

Use `/graph-jev` to preview and test an optional Jev-powered evidence reranker.
Default graph behavior remains unchanged; no API key is required unless you
explicitly enable live Jev calls. You supply your own TypeSafe API key, approve
bounded source excerpts, and choose shadow or rerank. This is an experimental
integration, not a demonstrated efficiency improvement.

Start with the [operator guide](plugins/graph-engineering/skills/graph-jev/references/usage.md).
It includes the official TypeSafe skill setup, an offline demo, and advanced
JSON question-design guidance. For implementation and local testing, use the
[Codex handoff](docs/jev/CODEX_HANDOFF.md). Preserve the historical evidence below.

## Retained Evidence

The retained read-only evaluations rejected the Hybrid candidate under their
predeclared gates. These are bounded historical observations, not general
performance claims.

| Evaluation | Direct fact / critical recall | Hybrid fact / critical recall | Context | Verdict |
| --- | ---: | ---: | ---: | --- |
| Stable R2, one turn | 95.83% / 95.83% | 91.67% / 89.58% | Hybrid used 29.08% more | Rejected |
| V2, two related turns | 97.22% / 97.92% | 94.44% / 100.00% | Hybrid used 12.76% less | Rejected |

The V2 run used 12 persistent sessions and 24 answer turns across frozen GEO
extension, Project Scaffold, and AgentReady snapshots. Hybrid made 290 broker
operations versus 349 for Direct. No prohibited tool, proof error, authority
error, or performed repository write was recorded. Six fresh index builds
processed 15,278,122 bytes, so this run does not prove amortized savings.

See [benchmarks/README.md](benchmarks/README.md) and the retained compact result,
freeze, and seal files for the exact historical evidence boundary.

### Shipped-interface self-conformance benchmark

The September 2, 2026 shipped-interface run used three tasks, 19 required
facts, four routes, fresh Luna High answer lanes, and an independent Luna High
scorer.

| Route | Fact recall | Source-location recall | Difference from Direct | Meaning |
| --- | ---: | ---: | ---: | --- |
| Direct | 94.74% | 100.00% | Baseline | Direct missed one complete contract statement. |
| Graph only | 0.00% | 5.26% | -100.00% | Body-free pointers are a diagnostic, not a source-semantic answer. |
| Graph-assisted pointer reads | 10.53% | 10.53% | -88.89% | The selected spans were small but materially incomplete. |
| Graph-assisted targeted fallback | 89.47% | 100.00% | -5.56% | Fallback found every anchor but omitted two compound statements. |

The run was rejected. Targeted fallback scored 17/19 facts versus 18/19 for
Direct. One answer lane also created an unused temporary file, and one
pointer-read lane breached exact-range isolation before recovery. Direct byte
accounting was incomplete, so this run makes no context-reduction or speed
claim. Independent Grok and MiniMax reviews both recommended a harness-only
successor rather than a product retrieval change.

See
[`benchmarks/velgraphing-shipped-interface-v1/README.md`](benchmarks/velgraphing-shipped-interface-v1/README.md)
for the interpretation and exact evidence files.

### Live installed-command canary

A September 2, 2026 Project Scaffold canary used the published plugin, one
frozen question, a six-fact rubric, and fresh Luna High lanes. It is one task,
not a general performance claim.

| Metric | Direct | Graph-assisted | Difference | Meaning |
| --- | ---: | ---: | ---: | --- |
| Required-fact coverage | 3/6 (50.0%) | 5/6 (83.3%) | +66.7% | The graph route found two more required facts. |
| Total model input tokens | 541,842 | 222,907 | -58.9% | The graph route exposed much less total input. This is not source-byte accounting. |
| Final output tokens | 10,206 | 12,224 | +19.8% | The graph answer was longer. |
| Wall-clock time | 180.0 s | 208.2 s | +15.7% | The graph route was slower in this run. |
| Proof or authority errors | 0 | 0 | 0% | Neither answer crossed the source or authority boundary. |

The graph export validated before the run. Its cold in-memory build took
120.0 ms, warm load took 1.4 ms, and the bounded lookup took 0.03 ms. Direct
operation count and source-byte totals were not recoverable from the truncated
host trace, so this canary makes no tool-operation or source-byte claim. This
canary exposed a command defect: the workflow tried to start a nested Codex
process. Version 0.1.1 repairs the command to use fresh host-native worker
lanes. The historical measurements above remain unchanged.

See
[`benchmarks/project-scaffold-live-canary-v1/result.json`](benchmarks/project-scaffold-live-canary-v1/result.json)
for the frozen question, rubric, route controls, and limits.

## Source Layout

| Path | Purpose |
| --- | --- |
| `packages/core/` | Canonical graph, routing, retrieval, and source-coordinate code. |
| `contracts/` | Portable schemas and package projection contract. |
| `adapters/orcastrata-umbrella-catalog/` | Navigation-only Orcastrata catalog intake. |
| `plugins/graph-engineering/` | Installable Codex plugin and commands. |
| `scripts/package/` | Deterministic plugin projection and parity checks. |
| `tests/` | Current product, package, skill, and adapter tests. |

Generated plugin runtime files mirror canonical source. Run the projector after
an intentional source change.

## Validate

```sh
PYTHONDONTWRITEBYTECODE=1 npm test
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/verify_source_package_parity.py
```

## Boundaries

RetrieVel does not replace repository source, grant write authority, or prove
that an answer is correct. Graph scores are retrieval diagnostics, not
confidence or authority. Cross-project federation, background services,
publication, and consumer adoption require separate proof.

`/graph-find` reads only Git-tracked regular UTF-8 files under the explicit
repository root. It excludes secret-like paths before reading them. Binary,
unsupported, and over-limit files are skipped or cause a `defer` route when
the scan is incomplete. Graph exports contain source pointers and metadata,
not complete source bodies. The command keeps its graph in memory and performs
no network, provider, repository-write, or persistent-index operation.

## License

RetrieVel, formerly VelGraphing, is available under the Apache License 2.0.
See [LICENSE](LICENSE).
