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

Bind replay actions to the returned `snapshot_sha256`, `head` and `branch`. Any supplied mismatch defers. Unknown fields, unknown nodes, invalid paths, changed source, branch changes and exhausted budgets defer. A new session is required after source or Git identity changes. Read and expansion stay inside the original admitted corpus. Excluded paths cannot be recovered by a tool action.

Limits: 32 actions, 64 files per operation, 512 graph nodes, 128 KiB source text per response, 512 KiB response envelope and 2 MiB accumulated response envelopes. Content budget exhaustion stops a source delivery before its freshness read. Initial acquisition is separately bounded by the existing scanner and is not stopped by the delivery budget. Overlapping complete units can repeat bytes; fully covered units are deduplicated. Inspect before choosing a larger parent unit.

`status: ok` means that the operation ran. `sufficient` and `authority_bearing` stay false. Completeness remains unassessed, including after recovery. A recorded offline decision driver proves this contract and source safety. It does not prove that Jev can request useful actions or that the graph improves answers. The approved live Jev transport must be integrated and evaluated separately.
