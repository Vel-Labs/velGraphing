# Benchmark Design (four-arm repeated-trial + component-removal)

## Four-arm design

Identical to the corpus pilot (`freeze.json:87-92`):

| Arm | Retrieval | Jev | Hypothesis tested |
| --- | --- | --- | --- |
| A | direct | off | baseline |
| B | direct | on | Jev effect on direct retrieval |
| C | graph_assisted | off | graph effect |
| D | graph_assisted | on | graph + Jev effect |

The harness runs each question once in each arm. Dispatch order is a seeded permutation (default seed 20260917) declared in `freeze.json`. The harness records per-event timing for every arm and computes `time_to_correct_ms`, `first_pass_correctness`, `user_visible_wall_ms`, and the per-phase fields.

## Comparisons

Three planned comparisons:

1. **Jev within direct (B vs A):** measures whether rerank changes direct reads.
2. **Jev within graph-assisted (D vs C):** measures whether rerank changes graph-assisted reads.
3. **Graph assistance overall (C + D) vs direct (A + B):** measures whether the graph changes reads.

Each comparison reports:

- Median per-arm `time_to_correct_ms` (with IQR).
- Median per-arm `first_pass_correctness`.
- Median per-arm `user_visible_wall_ms`.
- Per-arm censored-row fraction.
- A **deliberately conservative** effect claim: "no effect" unless (a) the censored-row fraction per arm is below 0.25, (b) the IQRs do not overlap, (c) the effect direction is consistent across all rows, (d) `first_pass_correctness` does not decline.

## Repeated trials

For the first release of the harness, repeated trials mean: each (question, arm) pair is run exactly once. Multi-trial repetition (e.g. 3 runs per (question, arm)) is deferred (D4).

The harness records a `trial_index` field (default 0) so future multi-trial runs do not need a schema change.

## Repair budget

Default `repair_budget: 2` (initial + 2 repairs). Configurable in `freeze.json`. Repairs run in the same lane; each repair's `first_pass_correctness` is graded independently; the first pass that satisfies the rubric terminates the loop and records `time_to_correct_ms`.

## Component-removal tests

Three flags:

- `--without-jev`: short-circuits the Jev phase. The lane runs as if `arm.jev == "off"`. Records `component_removal: jev` event. Used to estimate the *cost* of running Jev in arms B and D.
- `--without-graph`: short-circuits the graph-find phase. The lane runs as if `arm.retrieval == "direct"`. Used to estimate the *benefit* of running graph-find in arms C and D.
- `--without-fallback`: short-circuits the fallback phase. Used to estimate the *benefit* of source-bound fallback when graph evidence is incomplete.

Component-removal rows are kept and counted. The aggregate report reports the effect of each removal across all arms.

## Censored-row policy

A row is `censored: true` when `user_visible_wall_ms` or `time_to_correct_ms` is `unknown`. The aggregate report refuses to claim a wall-clock effect when the censored-row fraction per arm exceeds `freeze.json::censored_row_threshold` (default 0.25). When the fraction is below the threshold, censored rows are still reported (count and reasons), but the median and IQR are computed over the non-censored rows.

## Repair-attempt budget exhausted rows

When `repair_budget` is exhausted without a passing answer, the row is `status: failed` with `terminal_reason: fail_no_pass_under_budget`. The row is **not** censored; the failure is a real outcome. The harness records `repair_attempts_used` and `final_pass_correctness`.

## Independent grading

The grader is a separate subprocess. It receives:

- The question and pinned corpus.
- The lane's final answer text.
- The lane's source pointers and excerpt digests.
- The rubric from `freeze.json:scoring`.

It returns:

- `required_fact_score`
- `required_fact_max`
- `required_fact_recall`
- `critical_facts_exact`
- `unsupported_material_claims`
- `critical_errors`
- `source_support`

The grader is **outside** the answer lane. The lane never sees the rubric. The grader never sees the lane's telemetry. This separation is what makes the pass rate comparable across arms.

## Schema stability

The schema for events is declared in `event-trace.md`. The schema for the per-arm rollup is declared in the schema validator (`scripts/benchmarks/velgraphing_time_to_correct_trace.py`). Changes to either require a freeze bump and a new `freeze.json` schema version.

## What the harness does NOT do

- It does not run the answer lane itself. It wraps a lane subprocess (e.g. a `codex exec` call, or a Codex-equivalent fresh-worker call) and times the wall around it. The lane subprocess is owned by the parent operator.
- It does not make live TypeSafe calls. Jev is exercised via replay fixtures only.
- It does not rewrite the sealed `result.json` from the prior pilot.
- It does not change `packages/core/`.

## Validation in this PR

- The unit test `tests/benchmarks/test_velgraphing_time_to_correct_v1.py` runs the harness against a synthetic corpus (3 small files, 3 questions, 4 arms) and asserts:
  - 12 rows produced (3 questions × 4 arms).
  - Every row has `task_id`, `arm`, `packet_id`, `time_monotonic_ns` deltas that are monotonically non-decreasing within a row.
  - The Jev-on arms have `jev_provider_call_ms > 0` when replay is used.
  - The Jev-off arms have `jev_provider_call_ms == 0` and `status: skipped`.
  - `total_wall_ms` is recorded for every row (no `unknown` for user-visible wall).
  - Censored rows are retained when the harness subprocess is killed before completion.
  - Component-removal rows are produced when `--without-jev` is passed.
  - No `TYPESAFE_API_KEY` is read.
