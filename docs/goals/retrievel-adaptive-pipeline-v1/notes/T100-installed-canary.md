# T100 installed Jev canary

Status: blocked on a process-level credential after safe fallback. No provider
call occurred. T110 offline freeze work can continue.

## Bound candidate

- Installed plugin: `graph-engineering@graph-engineering-local` version `0.1.6`.
- Installed command: cached `graph-find` from the disposable repository-local
  Codex home.
- Public source: the VelGraphing checkout at merged PR #15 content.
- Source snapshot SHA-256:
  `dbd9ff89fbb78774322abfd035e17597ba378b925c88670f8a7dd57e399e492a`.
- Prompt: `what changes if derive_source_relations changes`.
- Candidate-set SHA-256:
  `906dfbd7e427603d37296416582085b7e08272d8b5d978a4acb4c87225592ccb`.
- Query SHA-256:
  `b67053997ffb5df0622bbbad2040e1c39dfca9acd5caf1b73765b00494cbbf49`.
- Preview request SHA-256:
  `2a0a85a5a3ee886c44b9dd740362f22332ed38a7dd182125a1ee5fce19ee3e80`.
- Preview request bytes: `103460`.
- Model: `jev-1.13.0`.
- Network calls allowed by the invocation: one. Retries: zero.

The installed plan used the Graph route. It reported
`graph_adds_source_witnessed_relationship_candidates` and confirmed that one
Jev judgment could affect bounded context selection. A separate installed
offline check confirmed that the merged change-impact projection emits both
incoming and outgoing verified import support.

## Budget

The public TypeSafe price checked on 2026-09-20 is USD `0.042` per million
input tokens, with unmetered output. The existing goal ledger reserved USD
`0.005505024` per historical call. Forty-six prior calls therefore reserve USD
`0.253231104`. Treating each request byte as one input token gives this preview
a conservative maximum of USD `0.00434532`. A successful call would raise the
conservative aggregate to USD `0.257576424`, leaving USD `0.742423576` under
the USD 1.00 goal allowance.

## Attempt and fallback

The approved exact evaluate command was sent to the existing Terminal tab so
the credential would remain process-local. The installed adapter returned
`missing_or_invalid_api_key` before transport:

- attempted provider calls: `0`;
- network called: `false`;
- provider status: `fallback`;
- source revalidated: `true`;
- Jev source revalidated: `false`;
- final order source: `baseline`;
- selected baseline candidates: `7`;
- retry count: `0`.

The detailed preview and fallback result remain ignored and local. No source,
provider score, usage, latency, or comparative provider result is published.

## Resume condition

Resume T100 only in a process that already has a valid `TYPESAFE_API_KEY`.
Regenerate the preview and require all bound hashes above to remain identical
before the single evaluate call. If any identity changes, freeze a new canary
instead of reusing this approval hash.

## Files changed

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T100-installed-canary.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

