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

One monotonic clock, no inferred or self-reported timing. See `event-trace.md` for the schema.

1. `task_accept` — start of the frozen row.
2. `jev_*` — canonical Jev replay evaluation and source revalidation for Jev-on rows.
3. `answer_dispatch_*` — wall around the frozen answer subprocess.
4. `grade_*` — wall around the frozen grader subprocess and its observed grade object.
5. `repair_attempt_n_*` — attempts under the fixed repair budget.
6. `first_pass_correctness` — boolean derived from the first observed grader result.
7. `time_to_correct` — wall from row start to the first observed passing grade.
8. `active_execution` — sum of observed Jev, answer, and grader subprocess phases.
9. `queue_approval` — `null`; this harness does not own approval waits.
10. `user_visible_wall` — wall around the full frozen row.

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

The harness is tested with deterministic Jev replay fixtures and real caller-supplied answer/grader subprocesses. No live provider call is made. The harness refuses to start if `TYPESAFE_API_KEY` is set. If either frozen command is absent, the row fails closed and is retained as censored. The schema validator (`velgraphing_time_to_correct_trace.py`) rejects malformed events at validation time.

## Provider calls

Zero. The audit confirms this; the harness enforces it. The harness script raises when `TYPESAFE_API_KEY` is set, and the tests use only deterministic Jev replay.
