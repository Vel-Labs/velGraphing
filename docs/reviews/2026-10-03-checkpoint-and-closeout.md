# RetrieVEL local checkpoint and resume — October 3, 2026

RetrieVEL and Relay are the active focus projects. This note records a local source checkpoint, not an installation, publication, release or scientific acceptance.

## Source identity and preserved work

Canonical home: `graph-engineering`. Product: VelGraphing / RetrieVEL. Compatibility package: `graph-engineering` 0.1.6.

Checkpoint branch: `checkpoint/retrievel-20261003`. Original branch: `codex/retrievel-baseline-delivery-20260929`. Original HEAD: `07f79841019cc5c36841a19b36a75b66a6882622`. The original branch reference stays at that HEAD. No remote action is part of this checkpoint.

| Artifact | SHA-256 |
| --- | --- |
| Canonical and projected retrieval | `9e8e69a5560c219a7659509a0560999153494338a35e1ba0cbcad16f367dcb2d` |
| Reviewed 89-member package candidate | `858d1739ae857f5dd010c8529389147f1a77ad2843fd5fde86d1ff29218e531a` |
| Release-manifest raw file | `a1760167f3f6fb4773d358efb698a856888c97f77951c040a764e8c608aea4bd` |

The checkpoint includes four overlapping groups across 16 existing source/test/generated paths:

- A: older offline graph tool-loop skill, reference, script and tests. Preserve this as WIP. Its original author and broader acceptance remain unresolved. Inclusion does not grant new acceptance.
- B: delivery separator admission repair and its UTF-8 regression.
- C: reviewed JSON/anchor containment, progressive separators, distinct public exports and typed invalid-UTF8 rejection, with source/tests and owning projections.
- D: reviewed intent-trigger preservation and unique-tag cap, with four regressions and owning projections.

B precedes C; D depends on C. The final package also contains A. Generated runtime source and metadata are retained as the reviewed source/package consistency unit. Runtime data, caches, raw query output, evaluator work and trials are excluded.

Do not hand-edit projected runtime. Any future source change needs the owning projector and manifest tools for its intended composition. See [source ownership](../architecture/SOURCE_OWNERSHIP_AND_PORTABILITY.md).

## Reused evidence and practical limits

Accepted source is byte-bound to retained 75 retrieval tests, 240 core tests, independent SOL High review and strict clean 89-file package parity. These are reused results, not new checkpoint test runs. All 209 maintained inputs matched the accepted candidate before checkpointing. Earlier four-repair acceptance is retained.

Canonical whole-tree parity intentionally refuses ignored bytecode with `private_or_machine_path`. No cache cleanup or verifier relaxation is authorized by this note.

The retained real-repository question is `Where are source-package parity and retrieval provenance enforced?`. The original and isolated repaired-engine comparison both returned authenticated context, but current enforcement-body coverage was **0/5**. No query ran after canonical integration. Direct source fallback is required. Routing and delivery do not assess completeness. Lower context bytes do not prove cost, quality or speed benefit.

Installed plugin loading, native evaluator adoption and matched science remain unproved. The expired trial remains expired. Ground overlap is architecture context, not integration authority.

## One meaningful navigation workflow

Use an explicitly authorized dogfood session. Python >=3.11 and Git are required. No server or provider is needed. From the canonical repository root:

```sh
retrievel_output="$(mktemp -d /tmp/retrievel-dogfood.XXXXXX)"
GIT_OPTIONAL_LOCKS=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false \
python3 -B plugins/graph-engineering/skills/graph-find/scripts/graph_find.py \
  --root "$PWD" \
  --prompt 'Where are source-package parity and retrieval provenance enforced?' \
  --deliver --byte-budget 16000 --maximum-results 6 \
  > "$retrievel_output/context.json"
printf 'Retain locally: %s/context.json\n' "$retrievel_output"
```

Inspect paths, byte ranges, hashes, omissions and budget counters. Follow useful pointers, then read the current bodies directly:

- `scripts/package/verify_source_package_parity.py`: `verify`, `build_manifest`, `_verify_projection`.
- `packages/core/routing_v4.py`: `_read_verified_source_bytes`.
- `packages/core/retrieval.py`: `_validate_retrieval_custody`, `_verified_spans`, `GraphFindResult.to_delivery_dict`.

Record one useful pointer and each missing enforcement group. Do not execute historical manifest-writing examples from retrieved text. Keep source-containing result JSON local. The process exits on completion; Ctrl-C stops it. There is no daemon or persistent index to stop. `/tmp` is not durable storage.

## Next bounded closeout

Verify the actual installed package identity and all 89 member hashes before a separately authorized installed-command canary. The README installer targets `main`; that does not prove this checkpoint is installed. A package script run alone does not establish installed command resolution.

Then run one unchanged question/options canary through the actual installed command. Authenticate output and document missing bodies. The parent/user chooses the acceptance boundary: authenticated navigation with disclosed direct fallback, or the stronger frozen oracle requiring all five complete current enforcement-body groups in delivered context. Preserve 0/5 until new evidence establishes another result.

Do not start tuning, install a package, renew a trial or invoke a provider from this note alone. New work needs current source identity and the necessary scope/authority. Remote backup, merge and release remain separate decisions.
