# Benchmark Evidence

This directory retains only compact evidence for benchmark results. The 696 MB
internal research archive contained
more than 100 stopped or superseded harness generations, source snapshots,
traces, responses, and indexes. Those files were development history, not the
public benchmark product.

Benchmark directory names and frozen labels that use `velgraphing` are retained
historical identifiers. They do not define the current public display name.

## Retained Results

| Directory | Scope | Verdict |
| --- | --- | --- |
| `held-out-comparison-stable-r2/` | One-turn Direct versus Hybrid comparison | Rejected |
| `multi-turn-readme-benchmark-v2/` | Two related turns across three repositories | Rejected |
| `velgraphing-time-to-correct-v2/` | Four-arm, 24-trial time-to-correct calibration | Unresolved |
| `velgraphing-corpus-pilot-v1/` | Six-task, four-arm pipeline pilot; 24 scored packet rows | Sealed; does not establish wall-clock savings. Timing, answer tokens, and cost remain unknown. |
| `velgraphing-four-arm-study-v1/` | Four-task, four-arm pre-optimization baseline | Directional diagnostic evidence only. The strict result-v2 seal is pending; the private diagnostic is not a public performance result. |

The rejected comparison directories contain their final `freeze.json`,
`result.json`, and `result-seal.json`. The time-to-correct directory contains
its frozen calibration, retained result, and result report. These files preserve
the reported result identity. They do not reproduce the removed private or
machine-specific execution corpus.

The corpus pilot is a bounded pipeline result, not a universal knowledge-system
or corpus-generalization study. It rejects Jev promotion and does not support a
wall-clock-savings claim. The four-arm package is a retained pre-optimization
baseline. Its separate private host-attested run remains diagnostic evidence,
not a sealed public product-performance result. Neither package supports
general correctness, token, cost, or provider-performance improvement claims.

## Public Benchmark Direction

A future public benchmark must use the shipped product interface. It should
freeze user-selected questions, run equivalent Direct and Graph-assisted
routes, measure fact coverage and source context, separate cold-build from
warm-reuse cost, and report fallback and safety behavior. Do not restore the
old numbered harness chain.
