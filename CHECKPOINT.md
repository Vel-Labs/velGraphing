# RetrieVEL local checkpoint — October 3, 2026

Resume here. This checkout contains the accepted complete-unit tool loop and the
offline repository build/search implementation. Compatibility version is 0.1.6.
Older pending-adoption sections in `docs/reviews/2026-10-03-checkpoint-and-closeout.md`
record historical review stages. The accepted successors are now integrated.

The local checkpoint follows `ea0ecc3cd453727b634f083e7e858afaa7779d20` on
`checkpoint/retrievel-20261003`. Use `git log -1` to identify this checkpoint.
There is no upstream for this branch. No push, merge, release or installation is
part of this checkpoint.

## What is usable

- Source-bound complete units preserve physical UTF-8/BOM/CRLF bounds. An
  unsupported or unestablished unit defers with a complete-file fallback.
- Offline build creates a saved map of file, Python symbol and static local
  import views. Search returns metadata pointers that require current source
  reads. The tool loop shares the same import resolver.
- The approved source/runtime composition has a 90-member clean package identity:
  `8373af5e0cc81bd0aaf0096b376178894fff1ff64d28944ecd3bae8f05d15a45`.
  Runtime projection and package inventories are deterministic tracked outputs.
  Operational state and local maps are outside this checkpoint.

## One workflow

Run from the checkout root with the existing isolated base interpreter. Choose
a new output path; build refuses to overwrite an existing map.

```sh
retrievel_root="$PWD"
retrievel_output_dir="$(mktemp -d)"
retrievel_py=/opt/homebrew/opt/python@3.14/bin/python3.14
retrievel_cli="$retrievel_root/plugins/graph-engineering/skills/graph-engineering/scripts/graphctl.py"
"$retrievel_py" -I -B "$retrievel_cli" retrievel-build \
  --root "$retrievel_root" --include . --namespace velgraphing \
  --output "$retrievel_output_dir/map.json"
"$retrievel_py" -I -B "$retrievel_cli" retrievel-search \
  --map "$retrievel_output_dir/map.json" \
  --query _read_verified_source_bytes --limit 3
```

Inspect the returned `packages/core/routing_v4.py` function to understand source
reader authentication. Check current source and span hashes before relying on
saved pointers. The validated build exposed 224 files, 1,318 symbols and 67 import
edges. These are navigation results, not proof of complete evidence or benefit.
Both commands exit normally. Ctrl-C stops an active command. No service remains.

## Evidence and remaining limits

Validation is reused from exact integrated source pins: 8 build checks pass,
11 complete-unit checks pass in the existing project virtualenv, real-repository
base-Python build/search pass, and a clean copy of the live 214 pinned files passes
strict 90-member package parity. The earlier 78 retrieval checks and 243 core
checks remain accepted evidence for their recorded source scopes. No test
campaign was rerun merely to make this Git checkpoint.

Base Python lacks the optional JavaScript grammar; one JavaScript-positive unit
check fails there. The same full unit suite passes in the project virtualenv.
Portable loading through that virtualenv still has a `packages.core`/`core`
model-type collision. Canonical strict parity intentionally refuses the ignored
cache with `private_or_machine_path`; the cache was preserved.

Installed/native command identity, evaluator adoption, matched retrieval science
and answer-quality/cost gains remain unproved. The expired trial stays expired.
Ground overlap is architectural context only. Direct source fallback remains
necessary for missing evidence; the historical enforcement-body diagnosis is
not replaced by the new map's file counts.

The optional Jev frontier pilot is prepared locally outside the repository.
Automatic approval review rejected external dispatch before execution because
the exact repository-derived transmission scope needs user authorization.
No rejected dispatch was retried. Jev transmission, prior browser restrictions
and native payload gates remain outstanding. This note grants no network,
browser, installation or provider authority.

Next: choose one bounded repository task, verify current source, and use direct
fallback when needed. Resolve the portable import-policy limitation before
claiming native loading. Run optional discovery and later packing/answer
comparisons only under their exact approved payload and execution scopes.
