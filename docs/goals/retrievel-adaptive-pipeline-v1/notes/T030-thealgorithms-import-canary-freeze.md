# T030 TheAlgorithms Canary Receipt

Date: 2026-09-19

Status: the import canary is closed as mechanics-only evidence and rejected for
positive graph value. The oracle-blind dependency-behavior canary is frozen.
T030 remains active for Parent review. No dependency-behavior label, oracle,
answer, grader, Jev, provider, credential, network, product-core, or host lane
ran.

## Import Canary Outcome

- Study: `velgraphing-v4-thealgorithms-import-canary-v1`.
- Candidate artifact:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-import-canary-afb32bf.json`.
- Selector commit: `afb32bfbbc4aa0e6339a6d795fb1861680cc600a`.
- Candidate SHA-256:
  `76e469b6a10d063c3fca7443100c43635df37a424454185193d7a31d57930a7e`.
- Context-isolated labels:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-import-canary-labels-pristine.json`.
- Evaluator-compatible label SHA-256:
  `96c777d5b6133b7caf24da4d216d46647a93e726dcd3993d76eb894b452ea61b`.
- Pre-Phase-B label SHA-256:
  `346b01ee56204f2a9aba33eb5af734adb9e5d103c8a13fcf2abfdca9c13b6097`.
  Only `schema_version` changed after this hash. The evaluated label artifact is
  schema-compatible, but it is not byte-pristine.
- Result:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-import-canary-eval-pristine.json`.
- Result SHA-256:
  `d318c1723f0babffc1733edc85b4da8c809cb6f346b0a9e1135a3c85199771d0`.
- Provider calls: `0`.

At K=64 and 32,768 bytes, every route had acceptable span-group overlap 1.0,
critical span-group overlap 1.0, zero source failures, and zero authority
failures. Typed Graph versus typed Graph without edges had delta 0.0. The
result confirms candidate-addition mechanics but no positive graph value. It
does not establish semantic fact recall. The evaluator did not independently
revalidate source bytes and did not prove prior oracle isolation.

## Dependency-Behavior Freeze

- Study: `velgraphing-v4-thealgorithms-dependency-behavior-canary-v1`.
- Implementation commit: `79adf45e8ff245c7e90701ea172d8de269228f83`.
- Registry:
  `benchmarks/velgraphing-time-to-correct-v4/thealgorithms-dependency-behavior-canary-questions.json`.
- Registry SHA-256:
  `a6006da0d7b2787a7fbb17e6f5a3f54d5a6409b170962c86e28f44b5bfa47897`.
- Prompt SHA-256:
  `9f78389e75c8157d2aeb78891ee35a80a51337b8f9de8ac1837b10834d71ef59`.
- The prompt does not name `quick_sort`.
- Frozen source snapshot: TheAlgorithms Python
  `5bafa4b7f64a981a61abb6be348436f6f18be31e0102c533b88269a9f9359f09`.
- Graph binding: 16 derived edges and one authenticated `imports` relation from
  `repo:sorts/benchmark_sorts.py` bytes 1246-1256 to
  `repo:sorts/quick_sort.py` declaration bytes 253-1296.
- Controls: 64 candidates, 32,768 aggregate excerpt bytes, and 4,096 bytes per
  candidate.
- Artifact:
  `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-thealgorithms-dependency-behavior-canary-79adf45.json`.
- Artifact SHA-256:
  `8a75f792aefbabe5679fdfb934e440f723649a5993cb46196d63a437486c9ce7`.
- Artifact size: `215148` bytes.

| Route | Candidates | Excerpt bytes | Relationship candidates |
| --- | ---: | ---: | ---: |
| Direct | 64 | 29,055 | 0 |
| Tag index | 64 | 29,055 | 0 |
| Typed graph | 64 | 30,036 | 1 |
| Typed graph without edges | 64 | 29,055 | 0 |
| Typed graph without expansion | 64 | 29,055 | 0 |

The four control arrays are identical. The target path is absent from Direct
and from the 63 typed primary candidates. The typed primaries equal Direct
minus exactly one displaced optional candidate. That candidate is
`sorts/benchmark_sorts.py` bytes 39-104 and is 65 bytes. Every required
candidate remains. The retained parent is bytes 1217-1256. The relationship
child is bytes 253-1299 and covers the registered target declaration.

## Validation

- Focused generator and evaluator tests: 35 passed.
- Full benchmark suite: 158 passed with one expected skip.
- Both changed Python scripts passed `py_compile`.
- Both registry hashes, exact rows, prompt hash bindings, and `quick_sort`
  exclusions passed.
- In-memory mutation tests reject wrong edge counts, changed control identity
  or count, target-as-primary candidates, parent and child coordinate changes,
  invalid displacement, and required-candidate loss.
- A source-only check confirmed the exact import binding and that the target
  implementation contains the behavior needed by the question.
- The fresh artifact passed strict schema, artifact-hash, source-snapshot,
  five-route, control, candidate-identity, byte-count, edge-count, parent, and
  child invariants. It also passed exact displacement and required-candidate
  retention checks.
- `git diff --check` passed before the implementation commit.
- The context-isolated import labels and result match their delegated hashes.

## Preserved Negative Evidence

The Engineering Handbook study `velgraphing-v4-relational-canary-v1` remains
rejected historical evidence. Its attempted freeze failed with
`relational_canary_support_mismatch` because it emitted no relationship
candidate. The import canary is also now rejected for positive graph value.
Neither result is rewritten by the dependency-behavior freeze.

## Files Changed

Dependency-behavior implementation commit:

- `benchmarks/velgraphing-time-to-correct-v4/PROTOCOL.md`
- `benchmarks/velgraphing-time-to-correct-v4/thealgorithms-dependency-behavior-canary-questions.json`
- `scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`
- `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py`
- `tests/benchmarks/test_time_to_correct_ranked_candidates_v4.py`
- `tests/benchmarks/test_time_to_correct_retrieval_eval_v4.py`

Receipt commit:

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-thealgorithms-import-canary-freeze.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`

## Remaining Boundary

The dependency-behavior freeze proves isolated, bounded graph candidate
addition for a question that requires imported dependency behavior. It does
not prove semantic correctness, answer quality, positive graph value, Jev
value, token reduction, speed, promotion, release readiness, or product
acceptance. T030 remains active. Parent review owns any later label or
evaluation step.
