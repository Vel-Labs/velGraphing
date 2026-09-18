# Protocol (VelGraphing Time-to-Correct v1)

The protocol is the four-arm repeated-trial design the audit recommends. It is identical in shape to the corpus pilot (`freeze.json:87-92`) but adds:

- A monotonic event trace.
- A fixed repair budget.
- Censored-row retention.
- Component-removal flags.
- Independent grading as a separate subprocess.

## Arms

| Arm | Retrieval | Jev | Hypothesis tested |
| --- | --- | --- | --- |
| A | direct | off | baseline |
| B | direct | on | Jev effect on direct retrieval |
| C | graph_assisted | off | graph effect |
| D | graph_assisted | on | graph + Jev effect |

The parent operator freezes the arm definitions in `freeze.json::arms`.

## Dispatch order

Seeded permutation. The seed is declared in `freeze.json::dispatch::seed`. The order is declared in `freeze.json::dispatch::order` as a list of `packet_id` values. Each `packet_id` is `<arm>-<task_id>`.

## Repair budget

Default `repair_budget: 2` (initial + 2 repairs). Configurable per benchmark in `freeze.json::repair_budget`. Repairs run in the same lane. The first pass that satisfies the rubric terminates the loop.

## Component-removal flags

Three flags, all default off:

- `--without-jev`: short-circuits the Jev phase. Records `component_removal: jev`. Used to estimate the cost of running Jev.
- `--without-graph`: short-circuits the graph-find phase. Records `component_removal: graph`. Used to estimate the benefit of graph-find.
- `--without-fallback`: short-circuits the fallback phase. Records `component_removal: fallback`. Used to estimate the benefit of fallback.

Component-removal rows are produced in addition to the regular arms. The aggregate report reports the effect of each removal across all arms.

## Censored-row policy

A row is `censored: true` when `user_visible_wall_ms` or `time_to_correct_ms` is `null`. The aggregate report refuses to claim a wall-clock effect when the censored-row fraction per arm exceeds `freeze.json::censored_row_threshold` (default 0.25).

## Independent grading

The grader is a separate subprocess. It receives:

- The question and pinned corpus.
- The lane's final answer text.
- The lane's source pointers and excerpt digests.
- The rubric from `freeze.json::scoring`.

It returns:

- `required_fact_score`
- `required_fact_max`
- `required_fact_recall`
- `critical_facts_exact`
- `unsupported_material_claims`
- `critical_errors`
- `source_support`

The grader is outside the answer lane. The lane never sees the rubric. The grader never sees the lane's telemetry.

## What the protocol does NOT do

- It does not require live provider calls. Jev is exercised via replay fixtures only.
- It does not change canonical core files.
- It does not rewrite sealed results.
- It does not impose a timing gate on the pass rate.

## What the protocol guarantees

- Every (question, arm) pair produces a row, including failed and censored ones.
- Every row has a `terminal_reason`.
- Every row has a monotonic event trace from `task_accept` to `terminal_reason`.
- Every Jev-on row has either `jev_provider_call_end` with `transport: live` or `transport: replay`. There is no third option.
- No row contains `TYPESAFE_API_KEY` or any HTTP body that echoes submitted source.
