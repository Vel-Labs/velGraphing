# RetrieVel

RetrieVel, formerly VelGraphing, provides source-verified graph navigation for
coding agents. This directory is the portable plugin package boundary. The
compatibility package ID remains `graph-engineering`.

The `0.2.0-rc.1` release candidate contains six public commands:

- `/graph-find` returns bounded, source-verified pointers for a repository prompt.
- `/graph-start` prepares the smallest source-bound setup.
- `/graph-update` refreshes an existing graph after source changes.
- `/graph-audit` measures readiness or effectiveness.
- `/graph-benchmark` runs a frozen Direct versus Graph comparison.
- `/graph-jev` previews and tests optional Jev evidence reranking.

Graph Benchmark includes a reusable report template for multi-track quality,
efficiency, safety, cold-build, warm-session, and task-level evidence.
It can also prepare a sanitized RetrieVel issue draft and request explicit
operator approval before opening one upstream issue.

Advanced Graph Engineering and Graph Steward skills remain available. The
package also contains a generated host-neutral runtime projection.
The context assist operation supports a verified graph route, a bounded direct
route from a caller allowlist in the same verified source snapshot, and a
fail-closed defer route.

`/graph-find` scans only Git-tracked regular UTF-8 files under an explicit
canonical repository root. It builds the verified graph and source snapshot in
memory, returns JSON pointers without source bodies, and performs no writes,
network calls, provider calls, or persistence. Unsupported files are skipped
within the explicit file and total-byte caps and reported in scan metadata.
Secret-like paths are excluded before reads and reported by count only.
`route: graph` means the verified evidence met the retrieval threshold with a
complete supported scan. `route: defer` means source is still authoritative;
use the returned fallback paths for direct reads. Capped supported files force
`repository_scan_incomplete` with `scan_complete: false`. Sensitive-path
exclusion forces `sensitive_paths_excluded`.

Canonical source stays outside this directory. Generated runtime content under
`runtime/` is a package projection. It is not project truth.

The direct route does not enumerate or search a repository. It does not call a
provider, run a callback, or write. This source package does not prove task
correctness, installation, marketplace discovery, federation admission,
publication, consumer adoption, or AOL adoption.

The runtime also exposes source-grounded typed retrieval. It derives tags from
exact verified repository bytes. It compiles 8 to 20 prompt facets when the
prompt contains enough distinct evidence. It constrains supplied semantic
expansion to the repository vocabulary. It fuses exact, sparse, wiki, and graph
rankings and permits one typed graph hop. It returns verified byte spans or
`defer`. A direct read still requires the existing explicit caller allowlist.
Retrieval scores are not confidence, authority, or acceptance evidence.

The Graph Engineering skill also includes a read-only repository-readiness
command. It indexes only explicit include paths, reports structural gaps, and
emits advisory recommendations with `auto_apply: false`. It does not change a
repository or prove semantic quality.

Use `/graph-audit` for a read-only readiness check or paired Direct versus
Graph-assisted effectiveness audit. Use `/graph-start` for a setup preview;
repository writes require separate approval after that preview.

## Optional Jev module

[Jev for RetrieVel](skills/graph-jev/SKILL.md) is a separately invoked,
experimental source-bound reranker powered by TypeSafe. It is off by default;
no key, external skill, SDK, or network is required for ordinary graph use.
Users provide their own `TYPESAFE_API_KEY` and explicitly approve outbound source
scope. Shadow preserves the baseline; rerank only permutes optional candidates.
Every candidate remains present and required positions stay locked.

Read the [operator guide](skills/graph-jev/references/usage.md),
[advanced JSON guidance](skills/graph-jev/references/advanced.md), and
[four-arm evaluation protocol](skills/graph-jev/references/benchmark.md).
The included offline replay is synthetic, not a live Jev benchmark. No automatic
LLM-turn interception, graph mutation, permission decision, or quality claim is
introduced by this module. Existing direct-source behavior is unchanged.
