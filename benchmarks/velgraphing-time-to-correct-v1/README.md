# VelGraphing Time-to-Correct v1 (successor harness)

Status: **preparation complete; no live run yet.**

This directory is the bounded successor to the corpus pilot (`benchmarks/velgraphing-corpus-pilot-v1/`). Its purpose is to make the three hypotheses the audit separated measurable on the next run, without rewriting the sealed pilot evidence or changing canonical core files.

## What this harness does

1. Owns a monotonic event trace (`time.monotonic_ns()`) for every (question, arm) pair.
2. Enforces a fixed repair budget per task.
3. Retains censored and failed rows (no survivorship bias).
4. Runs four arms (A, B, C, D) with a seeded dispatch order.
5. Validates Jev integration with deterministic replay fixtures; refuses to start with `TYPESAFE_API_KEY` set unless `--allow-network` is passed.
6. Supports component-removal tests (`--without-jev`, `--without-graph`, `--without-fallback`).

## What this harness does not do

- It does not run the answer lane itself. It wraps a lane subprocess and times the wall around it.
- It does not make live TypeSafe calls. Jev is exercised via replay fixtures only.
- It does not rewrite sealed results.
- It does not change canonical core files.

## Files

| File | Purpose |
| --- | --- |
| `README.md` | This file. |
| `event-trace.md` | JSONL event schema. |
| `protocol.md` | Four-arm repeated-trial design and component-removal tests. |
| `freeze.example.json` | Frozen-input contract shape (no live numbers; this is the contract for the next run). |

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/benchmarks/velgraphing_time_to_correct_v1.py` | Stdlib-only harness. Emits a JSONL event stream and a per-row summary. |
| `scripts/benchmarks/velgraphing_time_to_correct_trace.py` | Schema validator and per-arm rollup. |

## Tests

| Test | Purpose |
| --- | --- |
| `tests/benchmarks/test_velgraphing_time_to_correct_v1.py` | Fixture-driven tests with zero provider calls. |

## How to use

The harness is *not* a runner. It is a measurement instrument. The parent operator decides what to put in the freeze, runs the answer lane, and feeds the events to the harness.

For local development:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.benchmarks.test_velgraphing_time_to_correct_v1
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/velgraphing_time_to_correct_v1.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/velgraphing_time_to_correct_trace.py --help
```

For a future live run:

1. Freeze questions, rubrics, snapshots, and dispatch order in `freeze.json` (use `freeze.example.json` as the shape).
2. Run the answer lane for each (question, arm) pair. Capture the JSONL event stream per task.
3. Append each row to a per-arm rollup.
4. Validate the rollup with `velgraphing_time_to_correct_trace.py`.
5. Publish the rollup as `result.json` and seal it with a SHA-256 over the canonicalized scope.

## Privacy and portability

The harness does not record absolute paths. Every path is the project-relative path from `freeze.json::corpus[*]::materialized_root`. The `/Users/steven/...` paths in this audit task's brief are not recorded; the audit confirms they appear in no sealed evidence.

## What this harness replaces

The 11 self-reported fields in `freeze.json:answer_lane_boundary:telemetry_return_schema` are replaced by 14 harness-measured fields (see `event-trace.md`). The 12th field, `proof_and_authority_errors`, remains grader-measured (it is a rubric outcome, not a timing field).
