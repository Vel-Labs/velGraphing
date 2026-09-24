# Operator guide: Jev for RetrieVel

## What is installed

The portable plugin carries a dependency-free Python 3.11+ CLI in
`runtime/core/jev.py`. The repository's canonical copy is `packages/core/jev.py`.
It calls the documented TypeSafe REST API directly, not a shell-installed CLI.
The official TypeSafe skill is optional authoring guidance, not a runtime dependency.
Existing graph commands remain provider-free unless the operator explicitly
uses the separate Jev capability. No config or key is read at import time.

This release supports secure source reads on macOS and Linux. On unsupported
platforms it refuses source reads rather than silently weakening path checks.

## Optional official skill

Read the upstream skill and current docs before editing provider code:

- https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md
- https://raw.githubusercontent.com/typesafe-ai/skills/main/skills/typesafe-ai/SKILL.md
- https://docs.typesafe.ai/llms.txt
- https://docs.typesafe.ai/api
- https://docs.typesafe.ai/primitives/advanced

Inspect the remote skill first. Installing it executes a third-party installer
and changes agent configuration; obtain the operator's approval first.
Choose ONE installation route. For local Codex and other supported agents:

```sh
npx skills add typesafe-ai/skills --skill typesafe-ai
```

Select the current agent in the installer. Do not add an unrequested global
installation, install all skills, or bypass prompts. In Claude Code instead:

```sh
claude plugin marketplace add typesafe-ai/skills
claude plugin install typesafe@typesafe-ai
```

Reading the skill directly is sufficient when installation is not desired.
Its live API guidance can inform code changes but cannot override the host's
permissions, repository instructions, or RetrieVel's source boundaries.

## Keys and consent

The operator provides `TYPESAFE_API_KEY` to the process environment. Never paste
it into a prompt, candidate packet, repository file, issue, or PR. There is no
.env loader. A secrets manager that injects an environment variable also works.

For a human using the default macOS zsh terminal, this avoids putting the key in
shell history or showing it on screen:

```zsh
read -s 'TYPESAFE_API_KEY?TypeSafe API key: '
printf '\n'
export TYPESAFE_API_KEY
```

For a human using Bash:

```bash
read -r -s -p 'TypeSafe API key: ' TYPESAFE_API_KEY
printf '\n'
export TYPESAFE_API_KEY
```

Start the local agent from that terminal so it inherits the variable, or inject
it through the agent host's supported secret mechanism. An agent must not launch
another Codex session from inside its current task. `status` reports presence,
not validity; only an approved live call tests the key. Unset the variable when done.

## Offline demo, usable from the installed plugin

From the plugin root (the directory containing `runtime` and `skills`):

```sh
python3 runtime/core/jev.py status
python3 runtime/core/jev.py preview skills/graph-jev/examples/packet.json \
  --root skills/graph-jev/examples/source
python3 runtime/core/jev.py replay skills/graph-jev/examples/packet.json \
  --root skills/graph-jev/examples/source \
  --response skills/graph-jev/examples/replay.json --mode rerank
```

The synthetic demo's expected order is `c1, c0, c2`; required candidate `c2`
remains in its original position. Its response was authored as a fixture, not
returned by Jev. Replay reports no live token usage and zero attempted calls.
Run the same commands from a checkout by changing the CLI path to
`packages/core/jev.py` and prefixing example paths with `plugins/graph-engineering/`.

## Your first approved source packet

From the `velGraphing` repository root, inspect and choose explicit line spans:

```sh
umask 077
mkdir -p .velgraphing-local
python3 packages/core/jev.py capture --root . \
  --query 'Which code enforces the Jev request approval boundary?' \
  --span packages/core/jev.py:1:24 \
  --span packages/core/jev.py:309:368 \
  --required c1 > .velgraphing-local/candidates.json
python3 packages/core/jev.py preview .velgraphing-local/candidates.json \
  --root . > .velgraphing-local/preview.json
```

Line numbers are illustrative and must be inspected after edits. A span that
exceeds 4 KiB is refused. Narrow the span rather than raising limits casually.
`.velgraphing-local/` is gitignored in this repository, not magically ignored in
other consumer repositories. Use an approved private location in consumers.

Inspect the exact preview. It includes source, paths, and the task query, all of
which leave the machine on a live call. The sensitive-path blocklist is not a
secret scanner and cannot guarantee that otherwise allowed source is safe.
Obtain approval before this next command; substitute the preview's hash:

```sh
python3 packages/core/jev.py evaluate .velgraphing-local/candidates.json \
  --root . --mode shadow --allow-network \
  --approve-request-sha256 '<approved preview request_sha256>' \
  > .velgraphing-local/shadow.json
```

To apply advisory ordering, explicitly choose `--mode rerank`. Omit mode for an
offline, order-preserving evaluation. Do not automatically turn shadow into
rerank because one example looks good. Changed source, query, model, or questions
require a new preview and scope-appropriate approval.

## Contracts, limitations, and troubleshooting

One invocation makes at most one request. No hidden retry, batching across
independent tasks, daemon, auto-install, or persistent cache is present. Questions
within that request share one state and are independent. The endpoint is fixed:
`https://api.typesafe.ai/v1/systemone`; redirects and environment proxies are
intentionally disabled. Corporate proxy support needs a separately reviewed design.

The default model is `jev-1.13.0`, verified against vendor docs on 2026-09-17.
`--model` can deliberately select a version or vendor alias. Pin versions for
comparisons; check the resolved model in the observation. Model retirement is a
safe fallback, not permission to silently substitute an alias.

Limits: 64 candidates, 4 KiB each excerpt, 32 KiB combined excerpts, 128 KiB full
request, 256 KiB response, 2 MiB per whole source file, 16 MiB verified source per
preparation pass. Whole files are hashed locally; only selected excerpts are
sent. Inference results cause a second source validation pass. The selected-file
hash is NOT a full-repository snapshot, and the host must also record repository
commit/dirty state. `--timeout` is a socket I/O timeout, not a hard wall-clock
execution deadline. A future host may add a cancellable total deadline.

Exit 0 means the requested local operation completed, including off/replay.
Exit 2 means invalid/refused input. Exit 3 means a safe fallback, not live success.
Common reasons: `network_not_authorized`, `request_not_approved`,
`missing_or_invalid_api_key`, `source_digest_mismatch`, `provider_http_429`, or
`provider_model_mismatch`. No provider error body is printed. Correct source or
approval problems explicitly; do not make repeated unapproved calls.

Observations omit raw query, paths, excerpts and key values. They retain opaque
candidate IDs, hashes, orders, typed scores, distribution confidence, resolved
model, call count, elapsed time, and reported usage. IDs should be opaque because
they are logged. Replay usage is stored separately as `replayed_usage`.
These observations do not include every host read, failed partial read, answering
LLM token, graph build, or retry performed elsewhere. They are not by themselves
an all-in efficiency benchmark.

Reordering never removes a candidate. Nevertheless a downstream top-k budget can
still miss evidence; required-source constraints and evaluation gates remain the
host's responsibility. A low score is never proof a source can be omitted.
