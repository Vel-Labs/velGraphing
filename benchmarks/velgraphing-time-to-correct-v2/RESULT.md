# VelGraphing time-to-correct calibration v2 result

Status: closed. Verdict: unresolved.

The coordinator received 24 of 24 terminal trial receipts. The run does not
establish a time-to-correct advantage. Every arm has at least one non-passing
trial. The frozen policy requires all six registered trials in an arm to pass
before it reports a mean time to correct. All four mean TTC values are therefore
`null`.

## Arm result

| Arm | Passed | Mean terminal wall time (ns) | Mean TTC (ns) |
| --- | ---: | ---: | ---: |
| A | 4/6 | 154,546,435,819.5 | `null` |
| B | 1/6 | 196,382,884,930.83334 | `null` |
| C | 4/6 | 152,337,680,576.5 | `null` |
| D | 3/6 | 223,311,225,215.33334 | `null` |

The rates are lower bounds because nine trials ended in measurement errors.
Three other trials produced independently graded non-passing answers and ended
with `repair_budget_exhausted`. The machine-readable result preserves every
trial's terminal reason, first-pass value, terminal wall time, TTC, and relevant
failure stage.

## Jev provider result

Seven of the 12 planned Jev-on trials reached a live provider call. All seven
calls returned `reranked`. No call was retried. The five other Jev-on trials
terminated before a live call: `B-C-01`, `B-L-01`, `B-M-01`, `B-M-02`, and
`D-C-01`.

- Input tokens: 20,076
- Output tokens: 478
- Provider interval total: 2,793,315,084 ns
- Provider interval mean: 399,045,012 ns

These counts cover Jev only. Answer and grader usage has `unavailable`
provenance. All-in token totals and cost remain unknown.

## Evidence and revalidation

- Evidence-tree aggregate SHA-256:
  `9e4ca9e06572c0435816f20456f1fca495614282f37bc654e12106f0c7420b73`
- Coordinator source commit:
  `2c8151058f62edfadb464f5757129a64f872316d`
- Coordinator tracked tree: clean at execution
- Source lanes: all four revalidated unchanged after the run

The retained result excludes raw requests, source bodies, credentials, and
machine-specific paths. See [`result.json`](result.json) for exact trial rows,
provider-call hashes, source-lane identities, and null fields.

## Claim boundary

This is a retained observed run, not a promotion result. The closed coordinator
state proves receipt coverage. It does not convert host failures into correctness
failures. It also does not support an all-in token, cost, or time-to-correct
comparison.
