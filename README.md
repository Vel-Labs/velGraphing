# VelGraphing

Source-verified graph navigation for coding agents.

VelGraphing helps an agent decide where to look, retrieves exact source spans,
and falls back to direct source when graph evidence is incomplete. Source files
remain authoritative. The graph is a derived navigation layer.

## Commands

| Command | Purpose |
| --- | --- |
| `/graph-start` | Inspect a repository and prepare the smallest useful graph setup. |
| `/graph-update` | Refresh an existing graph after source changes. |
| `/graph-audit` | Measure graph readiness and effectiveness. |
| `/graph-benchmark` | Compare Direct and Graph-assisted repository work. |

The public product name is **VelGraphing**. The compatibility plugin and Python
package ID remains `graph-engineering` for the `0.1.x` line.

## Install

```sh
codex plugin marketplace add Vel-Labs/velGraphing --ref main
codex plugin add graph-engineering@graph-engineering-local
```

Start a new Codex task after installation so the command list reloads.

## Current Evidence

The current read-only evaluations rejected the Hybrid candidate under their
predeclared gates. This is useful negative evidence, not a performance claim.

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

VelGraphing does not replace repository source, grant write authority, or prove
that an answer is correct. Graph scores are retrieval diagnostics, not
confidence or authority. Cross-project federation, background services,
publication, and consumer adoption require separate proof.
