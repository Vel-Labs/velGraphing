---
name: graph-find
description: Find source-verified repository evidence for a prompt. Deliver bounded source text with exact references, or report unresolved evidence and defer to authoritative source.
---

# Graph Find

For an explicitly requested build/inspect/expand/source-read sequence, use the
[offline tool loop](references/tool-loop.md). Live Jev action selection remains
unverified. The existing one-shot command below keeps its current contract.

Run `scripts/graph_find.py` with an explicit absolute Git repository root and a
prompt. The adapter reads only Git-tracked, regular UTF-8 files. It builds the
verified `Graph` and `SourceSnapshotV4` in memory. It derives only uniquely
resolved Python `from module import name` edges, static relative JavaScript
named imports to direct named exports, and relative Markdown links to headings.
It then invokes the existing `graph_find` seam. It does not write, call a
network or provider, or persist an index. The default result contains pointers only.


```sh
python3 -B scripts/graph_find.py --root /path/to/repository --prompt "find token refresh" --deliver
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

The default JSON result contains ranked hits and exact source pointers. Add
`--deliver` to include the selected source text. The delivery output includes
source paths, source hashes, byte ranges, excerpt hashes, delivered context
bytes, source bytes read, snapshot bytes retained, and unresolved evidence.
Source bytes read include invalid UTF-8 files and any cap probes. These byte
counts are not model tokens. `--byte-budget` is one shared content budget for
the Graph context and all follow-up source text. The follow-up projection uses
only the remaining budget. `delivered_total_bytes` and `remaining_byte_budget`
report the combined content charge. `follow_up.source_bytes` counts source file
bytes within its documents. `follow_up.envelope_bytes` counts the serialized
follow-up projection, including its metadata; it is a separate measure and is
also limited by the remaining budget. Do not add source bytes to envelope bytes.
`route: graph` means the retrieval threshold was met. `route: defer` means the
public route remains conservative. If scan exclusions or limits forced that
route, `retrieval_route` and `retrieval_reason` preserve the underlying retrieval
result, and `scan_caveats` records the scan condition. A scan caveat does not
explain a retrieval no-match. Evidence completeness is not assessed by routing
or delivery; `omissions.completeness_assessment` is always `not_assessed`.

For a controlled source scope, repeat `--exclude-path-prefix <git-path>` for
each Git path or directory tree to exclude. Matching uses whole path components
and runs before source reads. The result reports each configured prefix and the
number of excluded files. Any deliberate exclusion sets `scan_complete: false`
and keeps the public `route: defer`, even when retrieval selected and delivered
evidence. Read `retrieval_route`, `retrieval_reason`, and `scan_caveats` to keep
the retrieval result separate from this conservative route. Apply the same
leading path prefixes to every comparison arm, including ordinary direct search.

Use `--follow-up-path <git-path>` only when a path is an explicit bounded read
request. The command reads that tracked path from the same admitted snapshot and
returns the full file only when its serialized source context fits the remaining
shared `--byte-budget`. Repeat the option for multiple paths, up to
`--maximum-results`. An unavailable, excluded, unsupported, or over-budget path
returns `route: defer` with a reason. The request scans and admits the same
bounded source set first, so acquisition bytes remain separate from delivered
text bytes. Secret paths are excluded before reads. A graph result is a
navigation aid. Repository source remains authoritative.

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
It then returns bounded source context. The default command remains body-free. Use ranked-context separately from
`--deliver` and `--follow-up-path`; each mode has its own budgeted output contract.
`preview`, `replay`, and `evaluate` add optional Jev processing. Preview and replay are offline.
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

## Named complete-source recovery

A question that names a supported source file can return
`named_source_recovery.needs_recovery: true`. Read the target status, actual
candidate paths, source hash and `next_build`. Compound and hidden filenames
are supported within the admitted corpus. A basename can match several paths.
Do not invent a unique path or a source hash for an ambiguous target.

When complete named source is still missing, the adapter can withhold selected
context before delivery. Withheld text has no delivered-byte charge. For an
explicit same-request follow-up, it can release that unemitted reservation and
retry the existing snapshot-local projection once. It keeps the original
budget. Already delivered bytes are never refunded. Inspect the actual
delivery fields and recovery status; withholding does not prove an answer.

For one uniquely admitted pending target, a receiving caller can pass
`remaining_byte_budget` to the offline native tool. Bind the scoped `next_build`
to the handoff snapshot. Read the complete file node returned by that build.
Preserve prior delivered charges. Follow the
[receiving contract](references/tool-loop.md).

The source-only RetrieVEL operator implements the bounded receiving path for
up to sixteen uniquely admitted targets in one inherited allowance. It rejects
ambiguous targets; optional import recovery requires one pending target. It is
separate from the installed plugin and does not produce an answer. See the
operator guide at `scripts/operators/retrievel/OPERATOR_GUIDE.md` in a
source checkout for launch paths, interpreter, receipts and reopening.
Explicit full-path recovery uses a separate question and retains the original
refusal. It is not automatic candidate selection.
