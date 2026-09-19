---
name: graph-find
description: Find bounded, source-verified repository pointers for a prompt. Return graph results when evidence is sufficient and defer to authoritative source when it is incomplete.
---

# Graph Find

Run `scripts/graph_find.py` with an explicit absolute Git repository root and a
prompt. The adapter reads only Git-tracked, regular UTF-8 files. It builds the
verified `Graph` and `SourceSnapshotV4` in memory. It derives only uniquely
resolved Python `from module import name` edges and relative Markdown links to
headings. It then invokes the existing `graph_find` seam. It does not write,
call a network or provider, persist an index, or return source bodies.

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

The root must be the canonical repository root. Symlink aliases and path
escapes are rejected. Secret-like tracked paths are excluded before any byte
read and reported by count only. Invalid-UTF-8 files remain unsupported and
are counted. If file or total-byte caps skip supported text, the result sets
`scan_complete: false`, uses `route: defer`, and reports
`repository_scan_incomplete`. The command fails when no usable source remains.
File and total-byte limits are explicit CLI controls with safe defaults.
