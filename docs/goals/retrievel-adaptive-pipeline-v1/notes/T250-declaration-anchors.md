# T250 declaration-anchor and installed-canary receipt

## Outcome

T250 passed. Python relation targets now use exact declaration-name byte
coordinates. This keeps long functions eligible for the existing 4,096-byte
candidate limit without changing source authority, relation types, or selection
caps.

The final installed-path canary also passed. The Graph route retained the
incoming `derive_source_relations` relationship through one live Jev rerank.
This proves the integrated mechanism once. It does not prove benchmark value or
general performance.

## Candidate

- Product commit: `fbfa54b0d1f223a073e67753ea1b3cd958d48baa`
- Package candidate SHA-256:
  `6adb2850258ed178376b6d63c2dcaae04457844cefec6a38411a5bfe2166c19e`
- Release manifest SHA-256:
  `f4707718b982951441cc7f7062c6aab1fa5a24c28613d65da4cd6929d979d351`
- Installed root:
  `/Users/steven/Workspace/.velgraphing-local/t250-codex-home-6adb2850`
- Public source commit: `3bad9cb75235752140ad32519f76638d4c366427`
- Public source snapshot:
  `dbd9ff89fbb78774322abfd035e17597ba378b925c88670f8a7dd57e399e492a`

## Changed product files

- `packages/core/retrieval.py`
- `plugins/graph-engineering/runtime/core/retrieval.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `tests/core/test_retrieval.py`
- `tests/skills/test_portable_skills.py`

## Validation

- Two exact declaration-anchor regressions passed.
- The 120-test retrieval, ranking, portable, Jev, and parity consumer set
  passed.
- The clean 47-test portable, Jev, and parity set passed.
- The projector was idempotent across two runs.
- The installed preflight selected the Graph route and retained an incoming
  relationship child under the unchanged unit cap.
- The preview was reproduced byte for byte by Parent.
- An independent Luna audit passed with no blocking finding. It confirmed the
  merged product ancestry, generic production logic, exact source custody, and
  parent-child integrity.

The audit could not rerun the official parity command in this checkout because
ignored `__pycache__` directories are present. It independently checked all 39
tracked projections, the 87-file release inventory, manifest digests, version,
and package candidate. The earlier clean detached-worktree parity run remains
the official parity evidence for this exact product candidate.

## Live canary

- Prompt: `what changes if derive_source_relations changes`
- Candidate-set SHA-256:
  `ce3050a60d77ab22e42b6b06bcb7cdc92d860762e183b3e92cc455220fc5cdd3`
- Query SHA-256:
  `b67053997ffb5df0622bbbad2040e1c39dfca9acd5caf1b73765b00494cbbf49`
- Source-set SHA-256:
  `5e982696c9aa0eebf7c927075c100e0480a65e7005860d2fd0b23219e2e0d712`
- Request SHA-256:
  `50abef8bb625b830b77ce84e091635496ef4fd1f9bb713095243a35b095a3cc0`
- Preview SHA-256:
  `f8b05643271718c143feabf4ce658bf401c4c0af899ecfebbb45e1629802f82b`
- Live observation SHA-256:
  `1ec697a0924ba4d564ba6a51d4289c22d94e4f56f63e007bd150c356354d1893`
- Provider: `jev-1.13.0`
- Calls: 1
- Retries: 0
- Provider latency: 716.937 ms
- Provider usage: 24,747 input tokens and 682 output tokens
- Source revalidation: passed
- Final serialized context: 32,587 of 32,768 bytes
- Final excerpt bytes: 19,766

The selected relationship child
`aecfe644ecfcffa1148c4cfc9113e77fff7da280a8749d2231502ba1f7d071c6`
retained parent
`e024313556c32edc294c95ad8252b9b09b5528530c1438306c3506f1af388b2c`.
Both remained in final selection after Jev reranking.

## Budget

The 88,532-byte request reserves USD `0.003718344` at the conservative
USD 0.042 per million input-byte rule. The aggregate conservative commitment is
USD `0.327947781`. The remaining USD 1 limit is USD `0.672052219`. Actual
provider billing remains unavailable.

## Proof boundary

This receipt proves one exact installed Graph plus Jev path with source custody,
relationship retention, and safe reranking. It does not prove answer
correctness, wall-clock improvement, context reduction, cost reduction, or
cross-repository generalization. A fresh final-candidate four-arm study is still
required.
