# Minimal Repair (in this PR)

The brief constrained this PR tightly: "Prefer a benchmark-owned monotonic event trace using `time.monotonic_ns()`, not a general telemetry framework." The repair therefore is **harness-only** and lives in `benchmarks/velgraphing-time-to-correct-v1/`, with a small stdlib-only harness, a per-arm rollup script, and a focused unit test. No canonical core file is changed.

## Files added

```
benchmarks/velgraphing-time-to-correct-v1/
  README.md                    protocol, retention rules, freeze contract
  event-trace.md               monotonic event schema (one JSONL line per event)
  protocol.md                  four-arm repeated-trial design
  freeze.example.json          frozen-input contract shape (no live numbers)

scripts/benchmarks/
  velgraphing_time_to_correct_v1.py     stdlib-only harness
  velgraphing_time_to_correct_trace.py  schema validator and per-arm rollup

tests/benchmarks/
  test_velgraphing_time_to_correct_v1.py  fixture-driven tests (zero provider calls)
```

## Files not changed (intentionally)

- `packages/core/{jev,retrieval,selection,navigation_v5}.py` — no demonstrated defect.
- `plugins/graph-engineering/commands/*.toml` — no demonstrated defect.
- `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py` — no demonstrated defect.
- `benchmarks/velgraphing-corpus-pilot-v1/{freeze,result,packets}.json` — sealed.
- `benchmarks/held-out-comparison-stable-r2/`, `benchmarks/multi-turn-readme-benchmark-v2/` — sealed.
- `benchmarks/project-scaffold-live-canary-v1/result.json` — sealed.
- `benchmarks/velgraphing-shipped-interface-v1/scores.json` — sealed.
- `benchmarks/velgraphing-corpus-pilot-v1/README.md` — only its wording can be updated; the freeze, packets, and result must not be rewritten.
- `README.md`, `docs/INDEX.md`, `AGENTS.md` — unchanged.

## What the harness measures

Twelve fields, one monotonic clock, no inference, no self-report. See `event-trace.md` for the full schema.

1. `task_accept_ms` — wall around `graph_find` (or `direct` discovery) for graph vs direct arms.
2. `graph_build_or_load_ms` — separated into `:cold` (first invocation of `graph_find.py`) and `:warm` (second invocation, where applicable).
3. `discovery_ms` — wall around the lane's own discovery phase.
4. `jev_prepare_ms` — wall around `jev.evaluate(replay=...)` prepare step.
5. `jev_provider_call_ms` — wall around the transport step (replay only; recorded as `skipped` for off/shadow).
6. `jev_revalidate_ms` — wall around `evaluate`'s second prepare.
7. `answer_dispatch_ms` — wall around the lane's answer phase.
8. `grade_ms` — wall around the grader subprocess.
9. `repair_attempt_n_ms` — one event per repair attempt under a fixed repair budget.
10. `first_pass_correctness` — value from the grader's first pass (`1.0`, `0.5`, `0.0`, `-1.0`).
11. `time_to_correct_ms` — wall from `task_accept` to the first pass whose `first_pass_correctness >= 1.0` AND whose `critical_errors == 0` AND whose `unsupported_material_claims == 0`. If no such pass occurs under the repair budget, the row is `censored` and `time_to_correct_ms` is `unknown`.
12. `active_execution_ms` — sum of non-queue, non-approval phases.
13. `queue_approval_ms` — sum of approval waits (e.g. Jev preview → evaluate).
14. `user_visible_wall_ms` — wall around the full task as observed by the harness subprocess. **Always recorded** by the harness itself; if the parent operator does not log it, the harness still has it.

## Censored-row retention

Every attempt produces a row, regardless of outcome. A row is `censored: true` when:

- `user_visible_wall_ms` is unavailable (only possible if the harness subprocess is killed before completing), OR
- `time_to_correct_ms` is unavailable because the repair budget was exhausted without a passing answer.

Censored rows are kept and counted. The aggregate report refuses to claim a wall-clock effect when the censored-row fraction per arm exceeds the threshold declared in `freeze.json` (default 0.25).

## Repair budget

The harness enforces a fixed repair budget per task:

- Default: `repair_budget: 2` (the initial answer plus up to two repair attempts).
- Configurable in `freeze.json` per benchmark.
- Each repair attempt is an independent `grade` event; the first pass that satisfies the rubric terminates the loop and records `time_to_correct_ms`.

The brief asked for "first-pass correctness and time-to-correct under a fixed repair budget." This is the implementation.

## Component-removal tests

The harness supports `--without-jev`, `--without-graph`, and `--without-fallback` flags that short-circuit the corresponding phase and record the removal as an event. See `benchmark-design.md` for the design and `tests/benchmarks/test_velgraphing_time_to_correct_v1.py::test_component_removal_jev_only` for the test.

## Validation

The harness is tested with deterministic replay fixtures. No live provider call is made. The harness refuses to start if `TYPESAFE_API_KEY` is set in the environment without `--allow-network`. The schema validator (`velgraphing_time_to_correct_trace.py`) rejects malformed events at write time, not after the run.

## Provider calls

Zero. The audit confirms this; the harness enforces it. The harness script raises on `TYPESAFE_API_KEY` set unless `--allow-network` is passed; the unit tests do not pass `--allow-network`.
