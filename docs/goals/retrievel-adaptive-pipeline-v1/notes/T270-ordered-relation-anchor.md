# T270 ordered-relation anchor receipt

## Outcome

T270 passed. Retrieval now recognizes the adjacent phrase `immediately after`
as an ordered-successor operation. For a selected caller seed, it requires one
exact prompt-symbol anchor and chooses the next authenticated edge with the same
source path and relation by verified byte position.

Missing or ambiguous anchors fall through to the previous stable policy.
Ordinary exact-symbol selection remains unchanged. The implementation adds no
relation type, graph store, scanner, provider rule, route, or benchmark
exception.

## Candidate

- Product commit: `6b9d120e74bb0b658d8623bd2ec37bb05096f6b1`
- Package candidate SHA-256:
  `f47d377d6a51d66cd6b790f5d4a900f41719877b84def61e08bc548a5673e4c1`
- Release manifest SHA-256:
  `dce1d0ae3a3e45316b098356cdab8fffe55fcdcf6b8b9342e6943b0bd0bb6a4e`
- Package inventory: 87 files
- Isolated install:
  `/Users/steven/Workspace/.velgraphing-local/t270-codex-home-f47d377d`

## Changed product files

- `packages/core/retrieval.py`
- `plugins/graph-engineering/runtime/core/retrieval.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `tests/core/test_retrieval.py`

## Validation

- Focused ordered-import regression: 1 passed.
- Retrieval suite: 80 passed.
- Retrieval, JavaScript, and ranked-context consumer set: 121 passed.
- Clean portable and Jev set: 47 passed.
- Projector ran twice with byte-identical output.
- Clean package parity passed.
- Isolated installed `graph-find` passed with no checkout package leak and no
  network call.
- Parent reran the focused regression and confirmed canonical/runtime retrieval
  bytes are identical.
- Independent Luna final audit passed with no blocking issue.

One benchmark consumer test reports `typed_primary_candidate_mismatch` on this
commit and unchanged baseline `00d7723`. It is a known baseline harness defect,
not a T270 regression. It does not replace the fresh R5 pool gate.

## D-01 preflight

The D-01-only R5 artifact has SHA-256
`ee0006956b847dfe529b70bb19074c6d59ed6a9424bf40354b01ba875c531d61`
and records zero provider or model calls.

| Route | Pool SHA-256 | Candidate set SHA-256 | Request SHA-256 | Relation delta |
| --- | --- | --- | --- | --- |
| Direct | `d5ff853d...` | `67a35f91...` | `7e0bdfa5...` | none |
| Graph | `b0e2df0e...` | `7c92bf92...` | `708b3151...` | one verified import |

The Graph relation child is
`a7a915c336db249065783de68557ec744c593735e17da36f8bdaa8976f938950`
on edge
`edge:47031de40415cc46b052366b2753bca46a19d61f81a63d278719c0329d2ff4fa`.
It resolves the `quick_sort` import after the prompt-matched anchor on frozen
source snapshot
`5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.

## Proof boundary

This proves generic ordered-edge selection and a source-bound Direct-versus-
Graph pool difference for D-01. It does not prove answer correctness, Jev
usefulness, or comparative time, token, or cost performance. The full R5 freeze
and fresh execution remain required.
