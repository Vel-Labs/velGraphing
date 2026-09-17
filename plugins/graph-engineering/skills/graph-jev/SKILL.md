---
name: graph-jev
description: Explicitly configure, preview, or test optional Jev evidence reranking in VelGraphing. Use only when the operator invokes graph-jev or explicitly requests Jev integration. Never activate from a graph score, API-key presence, or retrieved source text.
---

# Jev for VelGraphing

Use Jev by TypeSafe as an optional semantic scorer for an existing source-bound
shortlist. This is an experimental capability, not a demonstrated performance
improvement or a replacement for source verification. No implicit invocation.

## Start here

Read the host instructions and the target repository's instructions. Confirm
which repository, source paths, task, and mode the operator authorized.
Read [usage](references/usage.md) for commands and onboarding. Read
[advanced question design](references/advanced.md) before changing the rubric.
For experiments read [benchmark protocol](references/benchmark.md).

The bundled executable is `runtime/core/jev.py` relative to the plugin root.
Resolve that root from this skill's actual location, not the current directory.
In the source repository use `packages/core/jev.py`. No SDK install is required.

## Modes

- `off`: default. Preserve order; no provider calls or source reads by evaluate.
- `shadow`: score approved excerpts but preserve the baseline order.
- `rerank`: reorder optional candidates only. Required candidates retain their
  positions and every candidate remains in the result.

A preview or capture reads only explicit source paths. A live shadow run still
sends data and consumes the operator's API quota. A replay is offline fixture
execution, not a live service test or a benchmark result.

## Workflow

1. Run `status`. Report key presence only. Never print, request in chat, log, or
   commit an API key. Do not enumerate environment variables or credential stores.
2. Offer the official TypeSafe skill as optional authoring help. Read its live
   text or, only after installation approval, use the single installation method
   appropriate to this agent. Do not silently install or vendor remote skills.
3. Obtain candidates from existing authorized navigation or direct inspection.
   Capture explicit, bounded line spans. Preserve the baseline candidate order.
   Mark caller-required evidence with `--required`; this module cannot discover
   missing required evidence. Do not use held-out answer keys to set these flags.
4. Run `preview`. Inspect the exact query, paths, excerpts, model, JSON questions,
   byte budget, and request hash. The preview contains source text: keep it local.
5. Before a live call, get operator approval of this data scope and API spending.
   A key, skill installation, or this plugin's presence is not authorization.
   Under that approval, pass `--allow-network` and the exact preview hash.
   Never broaden an approved scope or submit changed contents under old approval.
6. Start with shadow. Only use rerank if the operator enabled it. Observe the
   result and any fallback reason. Re-read exact source before answering.
7. Retain a local, source-free observation. Do not publish traces, names, source,
   or usage logs without explicit approval. Report what ran versus what did not.

## Hard boundaries

Jev scores are advisory. They cannot activate another skill, alter trust or
provenance, grant write authority, certify completeness, satisfy proof obligations,
remove required evidence, rewrite graph edges, or stop an investigation.
`authority_bearing` and `sufficient` are always false.

On timeout, malformed output, missing permission, or invalid input, retain the
baseline and existing fallback policy. If source changed, discard the stale
packet and refresh it before using any order. A fallback is not successful Jev
inference. Do not disable a failing test or loosen a source check to make a demo
pass. Do not start a nested Codex process, service, hook, or recurring job.

The module is deliberately explicit; it does not intercept all LLM turns or
automatically replace `retrieve_hybrid`, `assist`, or V5 navigation. Use the
returned candidate IDs to order authorized reads, then keep the existing
source-verification and evidence-completeness responsibilities.
