---
name: graph-find
description: Find bounded, source-verified repository pointers for a prompt. Return graph results when evidence is sufficient and defer to authoritative source when it is incomplete.
---

# Graph Find

Run `scripts/graph_find.py` with an explicit absolute Git repository root and a
prompt. The adapter reads only Git-tracked, regular UTF-8 files. It builds the
verified `Graph` and `SourceSnapshotV4` in memory. It derives only uniquely
resolved Python `from module import name` edges, static relative JavaScript
named imports to direct named exports, and relative Markdown links to headings.
It then invokes the existing `graph_find` seam. It does not write, call a
network or provider, persist an index, or return source bodies.

```sh
python3 -B scripts/graph_find.py --root /path/to/repository --prompt "find token refresh"
```

The JSON result contains ranked hits, exact source pointers, and optional
`relationship_supports`. Each relationship support contains source and target
coordinates for one verified `imports` or `links_to_heading` edge. It is
navigation metadata only. It does not change seed ranking, evidence, context,
proof obligations, fallback paths, or byte budgets. Ambiguous and unbound
relations remain unresolved. Here, unchanged seed ranking means that
edge-enabled, edge-disabled, and expansion-disabled runs inside source-bound
mode use the same exact, sparse, and wiki seed route. Enabling source-bound mode
does not preserve the legacy graph-channel route. In source-bound mode,
`expand_one_hop: false` suppresses relationship support; it does not restore
legacy graph scoring or legacy one-hop mutation. `route: graph`
means the verified graph evidence met the retrieval threshold. `route: defer`
means the evidence is incomplete; use the listed fallback paths with a direct
source read. `fail_closed: true` means an authentication or custody boundary
blocked the result. A graph result is a navigation aid. Repository source remains
authoritative.

For a `change-impact` intent, relationship support can include one bounded
incoming edge from a selected definition to its verified importer. The support
keeps the original edge orientation and labels its direction. It does not alter
seed ranking, evidence, fallback paths, or byte budgets. The importer becomes
optional context only when ranked-context explicitly consumes the support.
Other intents keep outgoing-only relationship support, and no support expands a
second hop.

Use `--ranked-context plan` only when source context is explicitly requested.
This opt-in path builds Direct and relationship-expanded candidates from the
same verified retrieval. It uses the graph route only when source-witnessed
relationship candidates add evidence and required evidence remains preserved.
It then returns bounded source context. The default command remains body-free. `preview`, `replay`, and
`evaluate` add optional Jev processing. Preview and replay are offline.
Evaluate still requires both `--allow-network` and the exact
`--approve-request-sha256` from preview. Missing, stale, malformed, or
unqualified Jev output retains the verified baseline or defers.

```sh
python3 -B scripts/graph_find.py --root /path/to/repository \
  --prompt "find token refresh" --ranked-context plan
```

The root must be the canonical repository root. Symlink aliases and path
escapes are rejected. Secret-like tracked paths are excluded before any byte
read and reported by count only. Invalid-UTF-8 files remain unsupported and
are counted. If file or total-byte caps skip supported text, the result sets
`scan_complete: false`, uses `route: defer`, and reports
`repository_scan_incomplete`. The command fails when no usable source remains.
File and total-byte limits are explicit CLI controls with safe defaults.
