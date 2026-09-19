# T030 TheAlgorithms Import Canary Freeze Receipt

Date: 2026-09-19

Status: the oracle-blind TheAlgorithms import canary is frozen. T030 remains
active for Parent review. No label, oracle, answer, grader, Jev, provider,
credential, network, product-core, or host lane ran.

## Bound Inputs

- Study: `velgraphing-v4-thealgorithms-import-canary-v1`.
- Implementation commit: `afb32bfbbc4aa0e6339a6d795fb1861680cc600a`.
- Registry:
  `benchmarks/velgraphing-time-to-correct-v4/thealgorithms-import-canary-questions.json`.
- Registry SHA-256:
  `f5ed4f7a2f5cda04ff55c91cb5226ea4e81cf763eb3c48418adb82a6eb5eba95`.
- Prompt SHA-256:
  `aa04023625c4eeab028cf841f6ceda62ec9ee553fd3b0111ac6929a42d7c078c`.
- The prompt does not name `quick_sort`.
- Frozen source snapshot: TheAlgorithms Python
  `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.
- Controls: 64 candidates, 32,768 aggregate excerpt bytes, and 4,096 bytes
  per candidate.
- Graph binding: 16 derived edges and one exact `imports` relation from
  `repo:sorts/benchmark_sorts.py` bytes 1246-1256 to
  `repo:sorts/quick_sort.py` bytes 253-1296.

## Frozen Artifact

- Path:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-import-canary-afb32bf.json`.
- Selector commit: `afb32bfbbc4aa0e6339a6d795fb1861680cc600a`.
- SHA-256:
  `76e469b6a10d063c3fca7443100c43635df37a424454185193d7a31d57930a7e`.
- Size: `156618` bytes.
- The path is ignored. The tracked checkout stayed clean after generation.

| Route | Candidates | Excerpt bytes | Relationship candidates |
| --- | ---: | ---: | ---: |
| Direct | 28 | 17,863 | 0 |
| Tag index | 28 | 17,863 | 0 |
| Typed graph | 29 | 18,909 | 1 |
| Typed graph without edges | 28 | 17,863 | 0 |
| Typed graph without expansion | 28 | 17,863 | 0 |

The four control candidate arrays are identical. The 28 typed primary
candidates are byte-for-byte identical to Direct. The target path is absent
from the primary candidates. The retained parent range is 1217-1256 and covers
the registered source bytes. The relationship child range is 253-1299 and
covers the registered target declaration bytes.

## Validation

- Focused generator and evaluator tests: 34 passed.
- Full benchmark suite: 157 passed with one expected skip.
- Both changed Python scripts passed `py_compile`.
- The registry hash, exact row, prompt hash binding, and `quick_sort` exclusion
  passed.
- The fresh artifact passed strict schema, artifact-hash, source-snapshot,
  five-route, control, candidate-identity, byte-count, edge-count, parent, and
  child invariants.
- `git diff --check` passed before the implementation commit.
- The first focused command used a nonexistent worktree-local virtual
  environment. The repository virtual environment then ran all checks. This
  was a harness-path error, not a product failure.

## Preserved Negative Evidence

The Engineering Handbook study `velgraphing-v4-relational-canary-v1` remains
rejected historical evidence. Its attempted freeze failed with
`relational_canary_support_mismatch` because it emitted no relationship
candidate. This new freeze does not rewrite that history.

## Files Changed

Implementation commit:

- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `benchmarks/velgraphing-time-to-correct-v4/thealgorithms-import-canary-questions.json`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py`
- `tests/benchmarks/test_time_to_correct_ranked_candidates_v4.py`
- `tests/benchmarks/test_time_to_correct_retrieval_eval_v4.py`

Receipt commit:

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

## Remaining Boundary

This freeze proves isolated graph candidate addition under the registered
canary. It does not prove semantic correctness, answer quality, Jev value,
token reduction, speed, promotion, release readiness, or product acceptance.
T030 remains active. Parent review owns any later label or evaluation step.
