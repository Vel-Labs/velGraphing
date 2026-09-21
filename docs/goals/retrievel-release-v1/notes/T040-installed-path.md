# T040 Installed-Path Verification

Date: 2026-09-21
Status: local installed-path checks complete; live provider smoke remains unapproved and unrun.

## Candidate and scope

- Repository: RetrieVel worktree on `codex/retrievel-0.2.0-rc1`.
- Starting commit: `9f06e8ae8e30776da0e7f5300bfc90724d621659`.
- Candidate: `graph-engineering` `0.2.0-rc.1`.
- Candidate SHA-256: `21f8b725d3f4f204d49f627cff31047bdf6bcd7c155b96ec61b80c3aba2bcad0`.
- The source-package parity check passed for 87 files before installation:
  `PYTHONDONTWRITEBYTECODE=1 /Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.venv/bin/python scripts/package/verify_source_package_parity.py`
  from the worktree root.
- Only this note is changed. No source, package, or parent-owned `state.yaml` file changed.

## Isolated installation

The Codex CLI was `/opt/homebrew/bin/codex`. The isolated `CODEX_HOME` was
`/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4`.
The presence-only shell check reported `TYPESAFE_API_KEY` absent. Every
behavior-test invocation unset that variable. No credential value was read.

The local marketplace resolved `graph-engineering@graph-engineering-local` to
version `0.2.0-rc.1`. Codex reported the plugin installed and enabled. The
installed directory was a real directory under the isolated home. All 87
manifest-listed file hashes matched the source candidate, and the installed
release manifest matched the source manifest. No `/Users/steven/Workspace`
path was embedded in the installed package. The installed plugin contains all
six command files, including `graph-jev`. Its `agents/openai.yaml` sets
`allow_implicit_invocation: false`.

The CLI installation used the local marketplace only. It did not install
dependencies. The isolated CLI state does not prove that a separate Codex
Desktop command picker has reloaded; that interface was not tested.

The install and removal commands used these exact paths:

```sh
env -u TYPESAFE_API_KEY CODEX_HOME='/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4' /opt/homebrew/bin/codex plugin marketplace add '/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1' --json
env -u TYPESAFE_API_KEY CODEX_HOME='/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4' /opt/homebrew/bin/codex plugin list --marketplace graph-engineering-local --available --json
env -u TYPESAFE_API_KEY CODEX_HOME='/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4' /opt/homebrew/bin/codex plugin add graph-engineering@graph-engineering-local --json
env -u TYPESAFE_API_KEY CODEX_HOME='/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4' /opt/homebrew/bin/codex plugin list --json
env -u TYPESAFE_API_KEY CODEX_HOME='/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4' /opt/homebrew/bin/codex plugin remove graph-engineering@graph-engineering-local --json
env -u TYPESAFE_API_KEY CODEX_HOME='/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4' /opt/homebrew/bin/codex plugin marketplace remove graph-engineering-local --json
rm -r -- '/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4'
```

## Installed runtime checks

Commands ran from the installed plugin root:

```sh
env -u TYPESAFE_API_KEY python3 runtime/core/jev.py status
env -u TYPESAFE_API_KEY python3 runtime/core/jev.py replay \
  skills/graph-jev/examples/packet.json \
  --root skills/graph-jev/examples/source \
  --response skills/graph-jev/examples/replay.json --mode rerank
env -u TYPESAFE_API_KEY python3 runtime/core/jev.py preview \
  skills/graph-jev/examples/packet.json \
  --root skills/graph-jev/examples/source | jq \
  '{request_sha256, request_bytes, rubric_version, query: .request.state.task.query, candidates: [.request.state.candidates[] | {id, path, excerpt_bytes: (.excerpt | length)}]}'
```

Status reported `api_key_present: false`, default mode `off`, and
`network_called: false`. Offline replay made zero calls. It suggested
`c1,c0,c2` from baseline `c0,c1,c2`; required candidate `c2` remained in its
original position. The observation contained hashes and opaque IDs, not the
query, source paths, excerpts, or API key.

Two fail-closed paths also passed. An approved-hash evaluation with the key
unset returned `fallback / missing_or_invalid_api_key`, made zero calls, and
preserved baseline order. A local malformed replay response returned
`fallback / provider_question_mismatch`, made zero calls, and preserved
baseline order. Both observations kept `authority_bearing` and `sufficient`
false. The malformed replay fixture was created only inside the temporary
home and was removed with that home.

The missing-key check used the preview hash with
`--mode rerank --allow-network --approve-request-sha256 "$preview_hash"`.
The key guard returned before any transport call. The malformed replay check
used the preview hash in a local replay envelope whose `answers` object was
empty. Both checks stayed local.

The test commands were:

```sh
preview_hash=$(env -u TYPESAFE_API_KEY python3 runtime/core/jev.py preview \
  skills/graph-jev/examples/packet.json --root skills/graph-jev/examples/source \
  | jq -r '.request_sha256')
env -u TYPESAFE_API_KEY python3 runtime/core/jev.py evaluate \
  skills/graph-jev/examples/packet.json --root skills/graph-jev/examples/source \
  --mode rerank --allow-network --approve-request-sha256 "$preview_hash"
env -u TYPESAFE_API_KEY python3 runtime/core/jev.py replay \
  skills/graph-jev/examples/packet.json --root skills/graph-jev/examples/source \
  --response '/Users/steven/Workspace/40_Code/infrastructure/graph-engineering/.worktrees/retrievel-0.2.0-rc1/.t040-codex-home.4vlUC4/malformed-provider-replay.json' \
  --mode rerank
```

## Synthetic live-smoke preview

The preview used only the packaged synthetic fixture:

- Query: `Find the cancellation implementation and its test.`
- Paths: `background.py`, `cancel.py`, and `test_cancel.py` under
  `skills/graph-jev/examples/source`.
- Three candidates; `c2` is required; excerpts total 184 bytes.
- Request size: 3,816 bytes.
- Preview request SHA-256: `747673913325bd4d5992f6c05c38cfaf123e76adc8f55bfa0e5f5bc66a42d829`.

From the installed plugin root, after operator approval of this exact data
scope and API spend, the intended first live command is:

```sh
python3 runtime/core/jev.py evaluate skills/graph-jev/examples/packet.json \
  --root skills/graph-jev/examples/source --mode shadow --allow-network \
  --approve-request-sha256 \
  '747673913325bd4d5992f6c05c38cfaf123e76adc8f55bfa0e5f5bc66a42d829'
```

This command was not run. No network or provider call occurred. A key, if later
available, is not approval. Any changed packet or preview needs new approval.

## Cleanup and remaining risk

Codex removed the test plugin and local marketplace. The isolated plugin list
was empty, and the marketplace list reported no marketplaces. Codex then
removed the exact temporary `CODEX_HOME`; the path no longer exists. The
worktree was clean after cleanup and before adding this note.

Validation was focused on the packaged candidate, installed CLI state, and
installed runtime. No repository-wide suite was run because product files did
not change. The live provider path, provider-side response, API usage, and
Desktop command-picker reload remain unverified.
