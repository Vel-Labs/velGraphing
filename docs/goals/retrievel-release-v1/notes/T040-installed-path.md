# T040 Installed-Path Verification

Date: 2026-09-21
Status: complete, including one approved synthetic installed-package live smoke.

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

This command was not run during the original T040 slice. A later T090 release
qualification ran the same unchanged request under the operator's subsequent
live-call authority. See the retained result below. Any changed packet or
preview still needs its own bound approval.

## T090 installed-package live-smoke result

T090 reinstalled the current `0.2.0-rc.1` package into a fresh isolated
`CODEX_HOME`. The installed preview reproduced the exact request SHA-256
`747673913325bd4d5992f6c05c38cfaf123e76adc8f55bfa0e5f5bc66a42d829`
and request size of 3,816 bytes. It contained only the three synthetic source
files listed above.

The installed runtime made one approved shadow-mode call. It returned
`shadow / advisory_only`, resolved `jev-1.13.0`, revalidated the source, and
preserved required candidate `c2`. The provider observation reported 1,300
input tokens, 49 output tokens, and 312.823 milliseconds. It remained
non-authority-bearing and insufficient by design.

The replacement proof is under
`.velgraphing-local/t040-installed-live-r8/`. Its receipt binds the live
response to current package candidate
`112a9b2d30057a12654c0a7237aa76aae011de2e7d22e91a6bd83803c9fd2107`,
all 87 manifest files, installed manifest SHA-256
`3e6389bd70b2de2ef2e59bab1197d881f5f40bc23914391802235fcc3e5a6099`,
and installed runtime SHA-256
`7daba616d59be40efc4a61f7d3561587316b0bf476e9182cbf041fdc712c9c09`.
The live observation reported 1,300 input tokens, 49 output tokens, and 297.637
milliseconds. The receipt SHA-256 is
`ab7d4ef2e709f4ac6374d76b4752ee0863ba5c0fd01c4209feb4ecfb9175c06e`.

Codex then removed the isolated plugin and marketplace, confirmed that the
isolated plugin inventory was empty, and removed the exact temporary
`CODEX_HOME`. No credential value was read or written. The earlier unbound R7
smoke remains diagnostic only and is superseded by this R8 receipt.

## Cleanup and remaining risk

Codex removed the test plugin and local marketplace. The isolated plugin list
was empty, and the marketplace list reported no marketplaces. Codex then
removed the exact temporary `CODEX_HOME`; the path no longer exists. The
worktree was clean after cleanup and before adding this note.

The original validation was focused on the packaged candidate, installed CLI
state, and installed runtime. T090 later ran the repository-wide suite and
package qualification. The Desktop command-picker reload remains unverified;
the installed CLI command files and runtime path are verified.
