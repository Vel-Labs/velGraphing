# Benchmark Evidence

This directory retains only compact evidence for the two benchmark results
reported in the project README. The 696 MB internal research archive contained
more than 100 stopped or superseded harness generations, source snapshots,
traces, responses, and indexes. Those files were development history, not the
public benchmark product.

## Retained Results

| Directory | Scope | Verdict |
| --- | --- | --- |
| `held-out-comparison-stable-r2/` | One-turn Direct versus Hybrid comparison | Rejected |
| `multi-turn-readme-benchmark-v2/` | Two related turns across three repositories | Rejected |

Each directory contains its final `freeze.json`, `result.json`, and
`result-seal.json`. These files preserve the reported result identity. They do
not reproduce the removed private or machine-specific execution corpus.

## Public Benchmark Direction

A future public benchmark must use the shipped product interface. It should
freeze user-selected questions, run equivalent Direct and Graph-assisted
routes, measure fact coverage and source context, separate cold-build from
warm-reuse cost, and report fallback and safety behavior. Do not restore the
old numbered harness chain.
