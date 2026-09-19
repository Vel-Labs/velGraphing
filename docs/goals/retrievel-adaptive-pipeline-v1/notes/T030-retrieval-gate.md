# T030 Retrieval Gate Receipt

Date: 2026-09-19

Status: Gate 2 passed at the registered retrieval-only decision point. The result does not show positive graph value. T030 remains active for Parent review. No answer, grader, provider, or network call ran.

## Frozen inputs

- Candidate artifact: `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-ranked-candidates-v2-d03c804.json`
- Candidate SHA-256: `1a3b7ddcef5660a3aed1c4fa2b03c7474e42de8041b4abde6ca051616c0c1c17`
- Selector commit: `d03c80479b84bc00da145f7ead432e5da5ab23d5`
- Labels: `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-span-labels-v4-independent.json`
- Labels SHA-256: `3117d53481275d077553c3ac377684d177d17e5e235392463ae75ca47e9487ba`
- Result: `benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-retrieval-eval-v4-d03c804.json`
- Result SHA-256: `2736b4bab9dc1e85bed6171cb7b0f1c1f4fb09418d16a2a5427ae564704e233b`
- Candidate SHA-256 after evaluation remained unchanged.
- Snapshot digests match the registered corpus freeze. The four materialized source-lane directories were not present in this worktree. Span bytes, source file digests, and UTF-8 offsets reuse the prior independent byte-level adjudication of these same snapshot identities. The evaluator validated label schema, candidate snapshot bindings, and span bounds against the frozen candidate source rows. It does not independently read source bodies.

## Evaluation

The evaluator ran with `k=4,6,12` and byte budgets `8192,16384,24576`. Gate 2 uses `k=12`, `24576` bytes.

Gate 2 status: `pass`. Reasons: none. At the decision point, typed-graph critical-span recall did not fall below Direct for any graph-expected task. Source failures and authority failures were zero. All critical labels were known.

`positive_graph_value` is `false`. Typed-graph and edge-disabled recall deltas were zero for every task. This is a retrieval-span overlap diagnostic. It is not semantic answer correctness, graph/Jev speed, or an answer-quality result. Semantic fact recall and NDCG remain null.

| Task | Direct overlap / critical | Typed graph overlap / critical | Typed graph, no edges overlap / critical |
|---|---:|---:|---:|
| C-01 | 0.20 / 0.00 | 0.20 / 0.00 | 0.20 / 0.00 |
| C-02 | 0.40 / 0.00 | 0.40 / 0.00 | 0.40 / 0.00 |
| S-01 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| L-01 | 0.20 / 0.00 | 0.20 / 0.00 | 0.20 / 0.00 |
| M-01 | 0.25 / 0.00 | 0.25 / 0.00 | 0.25 / 0.00 |
| M-02 | 0.50 / 0.50 | 0.50 / 0.50 | 0.50 / 0.50 |

S-01 is reported separately. It has full overlap and single-candidate span-group recall on all three routes. This does not establish semantic answer correctness.

The accepted candidate-freeze receipt records 72 candidates and zero relationship supports in each route: Direct, tag index, typed graph, typed graph without edges, and typed graph without expansion. The evaluation independently found no useful edge-enabled difference on any of the six tasks.

## Commands and validation

The initial evaluator invocation failed before evaluation because Python could not import `packages` from the script directory. It wrote no output. The successful invocation added the worktree root to `PYTHONPATH`:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" python3 scripts/benchmarks/time_to_correct_retrieval_eval_v4.py --candidates "$PWD/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-ranked-candidates-v2-d03c804.json" --expected-candidates-sha256 1a3b7ddcef5660a3aed1c4fa2b03c7474e42de8041b4abde6ca051616c0c1c17 --labels "$PWD/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-span-labels-v4-independent.json" --output "$PWD/benchmarks/velgraphing-time-to-correct-v4/.inputs/t030-retrieval-eval-v4-d03c804.json" --k 4 6 12 --byte-budgets 8192 16384 24576
```

`jq` confirmed the v4 label schema and six task IDs before evaluation. The successful evaluator exit was zero and reported `provider_calls: 0`. Candidate, label, and result hashes were checked after evaluation.

## Next gate and remaining risk

Parent review of this retrieval-only result is next. Gate 2 safety passed, but the candidate earns no edge-related retrieval advantage. This result does not authorize answer or grader lanes, a live Jev call, a graph-value claim, or promotion. The materialized lanes were absent in this worktree, so source-byte verification was reused from the earlier adjudication rather than repeated here.

## Files changed

- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T030-retrieval-gate.md`
