# T020 Offline Canary Preparation

Date: 2026-09-19

Status: prepared only. T020 remains active. No provider call was made.

## Candidate

- Public case: `S-01`
- Route: `direct`
- Context budget: `1536` bytes
- Frozen candidate count: `12`
- Baseline selected count: `2`
- Baseline omitted count: `10`
- Accepted planner decision: `jev_call_could_affect_selection=true`
- Planner reason: `jev_observation_missing`
- Frozen candidate artifact SHA-256: `d147df356e72aa6588d0840ea32940b6db5d5dae975acf2b218e3d4cfc697ae9`
- Frozen source snapshot SHA-256: `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`

The planner proof imported `core` from a disposable copy of the plugin runtime. It did not import the canonical package path.

## Frozen Preview

- Model: `jev-1.13.0`
- Mode: `rerank`
- Rubric: `evidence-usefulness-v1`
- Packet path: `benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/s01-direct-packet.json`
- Packet SHA-256: `15bbc92207505751bbf4ad662c655b1eaa05c1437d7820e8bae7572d41605bda`
- Preview path: `benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/s01-direct-preview.json`
- Preview SHA-256: `75c5be6624b46fe554e70bc99bc4895b1dd6125563227d7292845104d74be126`
- Candidate-set SHA-256: `d425a74efe400934d0c29f15e5ab4ce9dd1dbf741e31aa74be075e5f8ce98d9a`
- Query SHA-256: `62cf41752a1ad335882aa8c9cf194e2bf2c4754a09a57973b5c1cb539c8620c9`
- Source-set SHA-256: `31b043e89c1e00c87c7eb6defabce1c7ad53e523badaa8da64379865cacf5b27`
- Request SHA-256: `8c7e59cf671e37ac07792af33baf00d6b5f1deea180aca76a44d6b3fc0c1eb84`
- Request bytes: `15869`
- Verified source bytes: `43619`

The preview used the existing Jev adapter. It was offline. It did not inspect a key or contact a provider.

## Cost And Call Boundary

- Maximum calls for this canary: `1`
- Retry count: `0`
- Timeout: `10` seconds
- Estimated cost: unknown because no applicable current price basis is present in the frozen artifacts
- Maximum cost: `$1.00`, the existing aggregate cap
- Calls made: `0`
- Observed cost: `$0.00`

Do not replace the unknown estimate with an invented amount. Confirm the applicable price basis before the provider call.

## Prepared Live Command

Run only after explicit provider-call authority and price-basis confirmation:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH='benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/graph-engineering/runtime' \
python3 'benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/graph-engineering/runtime/core/jev.py' evaluate \
  'benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/s01-direct-packet.json' \
  --root '../../benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4/thealgorithms-python' \
  --model 'jev-1.13.0' \
  --mode rerank \
  --timeout 10 \
  --allow-network \
  --approve-request-sha256 '8c7e59cf671e37ac07792af33baf00d6b5f1deea180aca76a44d6b3fc0c1eb84' \
  > 'benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/s01-direct-live-result.json'
```

Run the command from the `retrievel-adaptive-pipeline` worktree root. The existing adapter performs at most one attempted call and has no retry loop.

## Validation Boundary

- The installed-path planner selected a case where reranking can change the retained subset.
- The adapter generated the frozen preview from verified public source spans.
- Focused selector, portable runtime, and V4 Jev tests: `28` passed.
- Source-package parity tests: `10` passed.
- Frozen packet and preview hashes matched this receipt.
- `git diff --check`: passed.
- No canonical package source changed. No projection was required.
- The provider response, usage, charge, reranked selection, and answer effect remain unknown.
- T020 must not complete until the authorized live result and cost receipt exist.

The first parity run failed because the focused tests wrote ignored Python bytecode caches into package source trees. The caches were task-generated harness artifacts. After their removal, the same parity suite passed with `PYTHONDONTWRITEBYTECODE=1`. This was a harness-environment failure, not a product or package-parity defect.

## Files Changed

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T020-offline-canary-prep.md`

Ignored local preparation artifacts remain under `benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/`.
