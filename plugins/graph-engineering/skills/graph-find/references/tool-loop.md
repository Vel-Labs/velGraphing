# Offline graph tool loop

Use `scripts/graph_tools.py` beside `graph_find.py`. Pass the canonical repository root. Send one JSON action per input line. Read one response per output line. The process retains one admitted snapshot and one shared content budget. It does not write, run arbitrary commands, call a provider or create an index.

```sh
python3 -B scripts/graph_tools.py --root /absolute/repository --byte-budget 32768
```

The actions are:

- `{"op":"build","intent":"natural task","limit":2}` creates directory, file and source-unit nodes for task-ranked files. Optional `scope` narrows initial construction inside the admitted corpus.
- `{"op":"inspect","limit":4,"offset":0}` lists built nodes and paged global candidates. It reports unbuilt files. Optional `query` and `scope` change inspection only.
- `{"op":"expand","query":"natural recovery question","limit":2}` constructs additional task-ranked files beyond the current graph. It is lexical recovery, not a relation claim.
- `{"op":"expand","id":"file:returned/path.py","limit":2}` follows statically resolved local Python imports. Every edge has a hash-bound import-statement witness. Dynamic imports, other languages and calls remain unsupported.
- `{"op":"read","id":"returned-node-id"}` returns the complete selected unit or file if the remaining shared budget fits. Fully covered repeats return no text. Source is checked again before delivery. Bytes are not model tokens.

Complete-unit invariant: a unit node is admitted only when the exact admitted bytes establish its complete bounds. Python uses the byte parser, including UTF-8 BOM/encoding declarations; existing JavaScript uses its maintained grammar; JSON requires a validated container; Markdown supports plain ATX sections only. Invalid anchors, parse failures, missing parsers, unsupported formats and unestablished structures produce `unresolved_unit` nodes, never a line-window fragment labelled as a complete unit. Reading an unresolved node defers with `complete_unit_unavailable`, no text or content charge, and a `fallback_obligations` entry naming the complete file node. A complete-file read remains explicit and subject to the same budget and freshness checks. In the obligation API, unavailable units retain unresolved obligation IDs and source fallback paths; they receive no partial proof credit. Ordinary navigation continues to deliver bounded snippets and has no complete-unit claim.

Bind replay actions to the returned `snapshot_sha256`, `head` and `branch`. Any supplied mismatch defers. Unknown fields, unknown nodes, invalid paths, changed source, branch changes and exhausted budgets defer. A new session is required after source or Git identity changes. Read and expansion stay inside the original admitted corpus. Excluded paths cannot be recovered by a tool action.

Limits: 32 actions, 64 files per operation, 512 graph nodes, 128 KiB source text per response, 512 KiB response envelope and 2 MiB accumulated response envelopes. Content budget exhaustion stops a source delivery before its freshness read. Initial acquisition is separately bounded by the existing scanner and is not stopped by the delivery budget. Overlapping complete units can repeat bytes; fully covered units are deduplicated. Inspect before choosing a larger parent unit.

`status: ok` means that the operation ran. `sufficient` and `authority_bearing` stay false. Completeness remains unassessed, including after recovery. A recorded offline decision driver proves this contract and source safety. It does not prove that Jev can request useful actions or that the graph improves answers. The approved live Jev transport must be integrated and evaluated separately.

## Receiving a named-source handoff

Validate the one-shot handoff before starting the native process. The original
limit, delivered context and source charges must conserve the remaining
allowance. Verify any already delivered document bytes and hashes. Every pending
target must be uniquely admitted and carry an exact path, source hash and
scoped build action. The source-only RetrieVEL receiving client has a
32,768-byte ceiling and accepts up to sixteen unique targets. It refuses
ambiguity; optional import recovery accepts one pending target only.

Start this native tool with the inherited remaining allowance, not a new full
budget. Bind the build to the handoff snapshot. Read its returned complete file
node. Native success is an observed operation status; validate the response
before accepting its text.

The reviewed receiver checks all five native budget fields as nonnegative
integers, excluding booleans. The limit stays equal to the inherited allowance.
Delivery plus remaining must conserve it. Delivery and step counters cannot
decrease; remaining cannot increase. The step ceiling stays 32. Successful
delivery increments must equal received UTF-8 text bytes. A failed response can
retain a larger claimed debit; do not refund it.

For each successful complete-file read, hash the received UTF-8 text. Compare
it with the selected admitted node, reported source hash and excerpt hash.
Require complete bounds from zero to the actual byte length and matching
integer `result.byte_count`. Check the primary handoff digest when the path
matches its target. These checks precede the receiver's text cache. Its final
primary target-path check remains after caching and before another request.
Imported files depend on the native admission witness. Consistent producer
forgery and continuous runtime origin are outside this proof.

Retain raw responses, attempted actions, received bytes, costs and native
identity before validation. Record raw budgets separately from accepted
budgets, and accepted source separately from attempted reads. On contradiction,
stop further requests and preserve the charged evidence. A receipt's exit 0
means that the requested source actions completed. It does not mean that a
cited answer, native evaluator or provider comparison ran.

The task-owned receiver compares its two existing invoked-source observations
before reporting completion. That detects an observed change, not continuous
interpreter, import or bytecode authenticity. Standalone Guided and Direct
record observations without that same enforcement. One optional import hop
uses a cached, hash-checked syntactic Python import witness; importer freshness
at derivation remains unproved. Full malformed-response handling and earlier
receipt-write/cleanup/hash error windows retain their documented limits.

Use a fresh output directory. Preserve a failed handoff. For an ambiguous
basename, inspect its actual candidate paths and issue a separate explicit
full-path question. Do not silently choose a path or reset a charged session.
Stop the foreground receiver with Ctrl-C once and allow owned cleanup. Reopen
the saved JSONL and receipt under the recorded revision and snapshot identity.
Reopening retained evidence is not a fresh source admission or an answer run.
