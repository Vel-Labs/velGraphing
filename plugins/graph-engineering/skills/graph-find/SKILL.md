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
verified `Graph` and `SourceSnapshotV4` in memory, then invokes the existing
`graph_find` seam. It does not write, call a network or provider, or persist an
index.

```sh
python3 -B scripts/graph_find.py --root /path/to/repository --prompt "find token refresh" --deliver
```

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

The reviewed task-owned source client implements that bounded receiving path.
It is separate from the installed plugin. It rejects ambiguous or multiple
pending targets and does not produce an answer. Its operator bundle supplies
the exact launch paths, interpreter, receipts and reopening instructions.
Explicit full-path recovery uses a separate question and retains the original
refusal. It is not automatic candidate selection.
