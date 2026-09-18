# VelGraphing Time-to-Correct v1 (successor harness)

Status: **preparation complete; no live run yet.**

This directory is the bounded successor to the corpus pilot (`benchmarks/velgraphing-corpus-pilot-v1/`). Its purpose is to make the three hypotheses the audit separated measurable on the next run, without rewriting the sealed pilot evidence or changing canonical core files.

## What this harness does

1. Owns a monotonic event trace (`time.monotonic_ns()`) for every (question, arm) pair.
2. Enforces a fixed repair budget per task.
3. Retains censored and failed rows (no survivorship bias).
4. Runs four arms (A, B, C, D) with a seeded dispatch order.
5. Runs the canonical Jev implementation with deterministic replay fixtures; refuses to start when `TYPESAFE_API_KEY` is set.
6. Executes the caller-supplied frozen answer and grader commands. Missing commands fail closed as censored rows.
7. Supports component-removal tests (`--without-jev`, `--without-graph`, `--without-fallback`).

## What this harness does not do

- It does not choose or launch a host-native answer lane. It executes only the frozen command supplied by the caller and records the observed subprocess wall time.
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

The harness is a measurement instrument with explicit subprocess seams. The parent operator freezes the answer and grader commands. The commands receive JSON on stdin and return JSON on stdout. The harness does not invent a lane, answer, grade, or timing value.

For local development:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.benchmarks.test_velgraphing_time_to_correct_v1
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/velgraphing_time_to_correct_v1.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/velgraphing_time_to_correct_trace.py --help
```

For a future live run:

1. Freeze questions, rubrics, snapshots, and dispatch order in `freeze.json` (use `freeze.example.json` as the shape).
2. Set `answer_lane_boundary.answer_command` and `grader.command` to approved, reproducible commands.
3. Run the harness for each (question, arm) pair. It captures the JSONL event stream and per-row summary.
4. Validate the rollup with `velgraphing_time_to_correct_trace.py`.
5. Publish the rollup as `result.json` and seal it with a SHA-256 over the canonicalized scope.

## Privacy and portability

The harness does not record absolute source paths in event details. Freeze paths remain caller-owned execution inputs and must use portable placeholders or runtime-resolved values.

## What this harness replaces

The new event trace replaces self-reported answer timing with measurements at the Jev, answer-command, and grader-command boundaries. Graph discovery remains caller-owned. `proof_and_authority_errors` remains a grader outcome, not a timing field.
