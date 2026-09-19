# T020 Installed Live Canary Receipt

Date: 2026-09-19

Status: complete. The existing live result was consumed locally. No additional provider call was made.

## Candidate And Installation

- Public case: `S-01`
- Route: `direct`
- Context budget: `1536` bytes
- Frozen candidate count: `12`
- Frozen candidate artifact SHA-256: `d147df356e72aa6588d0840ea32940b6db5d5dae975acf2b218e3d4cfc697ae9`
- Frozen source snapshot SHA-256: `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`
- Model: `jev-1.13.0`

The planner and selector imported `core` from the disposable installed plugin runtime. They did not import the canonical package path.

## Artifact Bindings

- Packet SHA-256: `15bbc92207505751bbf4ad662c655b1eaa05c1437d7820e8bae7572d41605bda`
- Preview SHA-256: `75c5be6624b46fe554e70bc99bc4895b1dd6125563227d7292845104d74be126`
- Candidate-set SHA-256: `d425a74efe400934d0c29f15e5ab4ce9dd1dbf741e31aa74be075e5f8ce98d9a`
- Query SHA-256: `62cf41752a1ad335882aa8c9cf194e2bf2c4754a09a57973b5c1cb539c8620c9`
- Source-set SHA-256: `31b043e89c1e00c87c7eb6defabce1c7ad53e523badaa8da64379865cacf5b27`
- Approved request SHA-256: `8c7e59cf671e37ac07792af33baf00d6b5f1deea180aca76a44d6b3fc0c1eb84`

The installed selector verified the request, candidate, query, source-set, packet-order, and source-snapshot bindings. It revalidated source bytes before it used the observation.

## Acceptance Result

- The accepted planner reported that a Jev call could affect selection.
- The installed selector accepted the exact bound observation.
- The selector applied the advisory rerank and changed optional membership.
- All required evidence remained present. This candidate had no required candidate IDs.
- The final serialized context stayed within the frozen byte budget.
- The provider response remained advisory and non-authoritative.

The final selected spans were thin header and doctest metadata. They did not contain the requested mutation behavior, recursive partition logic, or base-case evidence. T020 therefore proves live transport, binding, source revalidation, budget enforcement, and selection effect only. It does not prove evidence usefulness, answer correctness, benchmark superiority, general retrieval quality, or product performance.

T030 must repair the candidate units before any four-arm public-corpus run. The current thin first-span candidates are not suitable benchmark inputs.

## Usage And Cost

- Calls made: `1`
- Retry count: `0`
- Aggregate goal cap: `$1.00`
- Budget status: under cap, detailed accounting local only

Detailed usage and cost accounting remain in ignored local artifacts. This tracked receipt makes no public provider performance claim.

## Legal And Publication Boundary

Current TypeSafe customer terms prohibit publication of provider benchmark or performance information. Keep the live response and installed selection detail ignored and local. Do not publish provider usage, scores, distributions, ranking detail, candidate identity, latency, or comparative performance claims from this canary.

The detailed local artifacts remain under `benchmarks/velgraphing-time-to-correct-v4/.inputs/t020-offline-canary/`. This tracked receipt records only the bounded acceptance and accounting facts needed for lifecycle continuity.

## Validation

- Installed planner and selector binding checks: passed.
- Source revalidation: passed.
- Required-evidence preservation: passed.
- Frozen context budget: passed.
- Focused selector, portable runtime, and V4 Jev tests: `28` passed.
- Source-package parity tests: `10` passed.
- Goal-state transition field check: passed.
- Ignored artifact hashes: matched.
- `git diff --check`: passed.
- No canonical package source changed. No projection was required.

## Files Changed

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T020-offline-canary-prep.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
