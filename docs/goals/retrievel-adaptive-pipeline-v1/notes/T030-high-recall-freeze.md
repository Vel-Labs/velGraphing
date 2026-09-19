# T030 High-Recall Freeze Receipt

Date: 2026-09-19

Status: high-recall six-task artifact frozen. The separate relational canary
freeze failed strict validation. T030 remains active. No label, oracle, answer,
grader, provider, credential, or network lane ran.

## Repair Candidate

- Repair commit: `38eb61ed76990abab8189f084428fb50afb037c3`.
- Prompt compounds now expose non-required identifier parts. Existing
  underscore, camel-case, and digit identifier requirements remain unchanged.
- `as`, `in`, `it`, and `using` no longer consume prompt facets.
- Repository-vocabulary terms are selected across prompt clauses before the
  remaining lexical terms consume the 20-facet cap.
- Channel scoring keeps the strongest facet when several facet kinds share one
  canonical value.
- The six-task successor uses the existing Jev hard envelope as a high-recall
  preselection pool: 64 candidates, 32,768 aggregate excerpt bytes, and 4,096
  bytes per candidate. The later serialized answer-selection budget remains
  16,384 bytes.
- The historical candidate artifact, result, protocol receipts, and prior
  hashes remain unchanged.

## High-Recall Artifact

- Path: `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-high-recall-ranked-candidates-38eb61e.json`.
- Study: `velgraphing-v4-six-task-high-recall-v1`.
- Selector commit: `38eb61ed76990abab8189f084428fb50afb037c3`.
- SHA-256: `42d14d8daa02c92a2483f68f67b0d37d8fed2116779c6496a61a6b78159eaa24`.
- Size: `1015173` bytes.
- Runs: 30, from six tasks by five routes.
- Route totals: direct `302/0`; tag index `302/0`; typed graph `302/0`;
  typed graph without edges `302/0`; typed graph without expansion `302/0`.
  Each pair is candidates/relationship candidates.
- Every route has six runs. Per-run candidate counts range from 20 to 64.
- Every route materializes `183579` aggregate excerpt bytes across its six
  runs. Per-run controls remain bounded by 32,768 bytes.
- Source snapshots: CPython
  `c9f10e2dd66e033dbaeb89ad22d8d95c3b8cec7d4eadb4b96fed6cc8ae572908`;
  Engineering Handbook
  `594aa47760172eba049e18c5f3a2f602a7b96b73a315756876955d7be81cd402`;
  OpenChain
  `7b06041a211f9365686f934eb7f37a0646f65ac4866d6837e37714ffb1e7679b`;
  TheAlgorithms Python
  `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.
- A separate source-free validator confirmed the schema, study identity,
  selector commit, registry hash, matrix, controls, source identities, and
  typed-primary invariants.
- Label-free S-01 inspection found four `sorts/quick_sort.py` candidates. The
  range 253-1299 is a complete, parseable `quick_sort` function unit of 1,046
  bytes.

## Relational Canary Stop

- Intended path:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-relational-canary-38eb61e.json`.
- Study: `velgraphing-v4-relational-canary-v1`.
- The generator completed source scanning and candidate construction, then the
  source-free evaluator rejected the artifact with
  `relational_canary_support_mismatch`.
- The exclusive output was not written. The intended path does not exist.
- No retry, prompt change, target injection, ranking redesign, or weaker
  validator followed this new signature.

## Validation

- Focused core and benchmark checks: 123 passed.
- Core consumer suite: 265 passed.
- Benchmark consumer suite: 156 passed with one expected skip.
- Skill consumer suite: 35 passed after removing generated Python cache files.
- Parity tests: 10 passed.
- Portable projection ran twice with the same state.
- Source-package parity passed for 87 files with candidate SHA-256
  `929232e9594b0469dc13c1c335061f85fcb2fe68cce40fed4e1cf9e48cf37652`.
- `git diff --check` passed before the repair commit.
- The repository virtual environment did not contain PyYAML. Ruby's standard
  YAML parser validated the updated state file instead.

## Files Changed In The Repair Commit

- `packages/core/retrieval.py`
- `plugins/graph-engineering/runtime/core/retrieval.py`
- `plugins/graph-engineering/runtime/.projection-state.json`
- `plugins/graph-engineering/.codex-plugin/release-manifest.json`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py`
- `tests/core/test_retrieval.py`
- `tests/benchmarks/test_time_to_correct_ranked_candidates_v4.py`
- `tests/benchmarks/test_time_to_correct_retrieval_eval_v4.py`
- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `benchmarks/velgraphing-time-to-correct-v4/relational-canary-questions.json`

## Next Gate

Parent review owns the next decision. Independent label evaluation remains
blocked because the exact relational-canary freeze did not validate. Preserve
the high-recall artifact as oracle-blind evidence. Any canary repair requires a
new bounded hypothesis and a new selector commit.
