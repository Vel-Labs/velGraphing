# Timing-Ownership Matrix

For each timing field the corpus pilot freeze asks for (`benchmarks/velgraphing-corpus-pilot-v1/freeze.json:100-117`), who owns the measurement today, and what category the field falls into. Categories: **observed** (measured by code), **self-reported** (answer-lane agent types the value), **inferred** (computed by code from other fields), **missing** (no field in result.json), **double-counted** (same underlying clock counted twice), **incomparable** (different definitions across arms).

| Field | Owner | Definition site | Category | Notes |
| --- | --- | --- | --- | --- |
| `route` | Answer lane | Self-declared in the JSON it returns | self-reported | Pilot does not verify the reported route against the actual arm in `freeze.json:arms`. |
| `task_id` | Answer lane | Self-declared | observed (from packet) | Bound by packet id at packet generation time. |
| `arm` | Answer lane | Self-declared | observed (from packet) | Bound by packet id at packet generation time. |
| `source_snapshot_sha256` | Answer lane | Self-declared | observed (must match packet) | In sealed result, `unknown` for many rows. |
| `required_fact_coverage` | Scorer | `freeze.json:143` (independent rubric scoring) | observed | Computed by an independent grader outside the answer lane. |
| `source_support` | Scorer | `freeze.json:144` | observed | Computed by the grader. |
| `model_visible_context_bytes` | Answer lane | Self-declared | self-reported | The lane is asked to count what it exposed to the model. Direct lanes cannot recover this if their host trace was truncated (live canary `limitations[2]`). |
| `source_operations` | Answer lane | Self-declared | self-reported | Same risk as above. |
| `cold_graph_build_ms` | Answer lane | Self-declared | self-reported | Not measured by `graph_find.py`; the lane is asked to time its own cold build. |
| `warm_graph_load_ms` | Answer lane | Self-declared | self-reported | Same as above. |
| `retrieval_ms` | Answer lane | Self-declared | self-reported | The `graph_find.py` CLI does not emit a timing field. The lane must time its own call. In the sealed result, retrieval_ms is a single number per row (`result.json` A-C-01 line 31), not per-phase. |
| `fallback_reads_and_bytes` | Answer lane | Self-declared | self-reported | A dict `{reads: int, bytes: int}`; only A-C-01 has non-zero values. |
| `answer_ms` | Answer lane | Self-declared | self-reported | "unknown" everywhere except inferred partials. |
| `total_wall_ms` | Answer lane | Self-declared | missing | **"unknown" for every arm B/D row and most others** (`result.json` B-* and D-* rows have `"total_wall_ms": "unknown"`). This is the headline time-to-correct field and it is uncensored-only-by-accident. |
| `jev_calls_tokens_latency` | Answer lane (B/D only) | Self-declared | self-reported | A dict `{calls, tokens, latency_ms}`. In sealed result, `calls: 0` and `latency_ms: 0` for B/D rows because the parent did not log them. |
| `proof_and_authority_errors` | Scorer | `freeze.json:145` | observed | Counted by the grader. |

## Where the audit draws the line

The brief asks for "which process owns each timing field, and which values are observed, inferred, self-reported, missing, double-counted, or incomparable." This matrix is the answer. The headline number:

- 0 of the 12 timing fields are observed by `graph_find.py` (the actual installed command).
- 1 of the 12 is partially observed (`retrieval_ms` is sometimes a number — but it is the lane's self-report, not the CLI's).
- 11 of the 12 are self-reported or missing.
- 0 are double-counted today, because none are observed twice. Once a monotonic event trace is added, double-counting becomes a real risk (e.g. `active_execution_ms` and `user_visible_wall_ms` overlap) and the schema must declare whether they are independent or nested.

## Comparison across arms

The pilot compares Jev-within-retrieval (`B-A`, `D-C`) and graph assistance (`C-A`, `D-B`). For a comparison to be valid:

- The owner of every field must be identical across arms.
- The definition of every field must be identical across arms.
- The measurement must be present in every row of every arm.

The sealed result fails all three conditions:

- `total_wall_ms` is `unknown` in 22/24 rows.
- `model_visible_context_bytes` is `unknown` in most arm A rows except A-C-01.
- `source_operations` is `unknown` in most rows.
- `cold_graph_build_ms` and `warm_graph_load_ms` are `unknown` in every row.

The pilot's `unknown_policy` (`freeze.json:162`) makes this *permitted* — but it also makes the comparison invalid for any claim about time or cost. The pilot verdict reflects this: `does_not_establish_wall_clock_savings`.

## What the new harness changes

`scripts/benchmarks/velgraphing_time_to_correct_v1.py` records events directly via `time.monotonic_ns()` at the point of measurement:

| Phase | Event | Owner |
| --- | --- | --- |
| Task acceptance | `task_accept` | Harness |
| Graph build (cold) | caller-owned | Not measured by this successor harness |
| Graph load (warm) | caller-owned | Not measured by this successor harness |
| Discovery (graph or direct) | caller-owned | Not measured by this successor harness |
| Jev prepare | `jev_prepare_start`, `jev_prepare_end` | Harness |
| Jev replay evaluation | `jev_provider_call_start`, `jev_provider_call_end` | Harness; canonical `evaluate(replay=...)`, no live provider |
| Jev revalidate | `jev_revalidate_end` | Harness |
| Answer dispatch | `answer_dispatch_start`, `answer_dispatch_end` | Harness (wall around the answer-lane subprocess) |
| Independent grade | `grade_start`, `grade_end` | Harness (subprocess around the grader) |
| Repair attempts | `repair_attempt_n_start`, `repair_attempt_n_end` | Harness (under fixed repair budget) |
| First-pass correctness | `first_pass_correctness:1.0/0.5/0.0/-1.0` | Harness (from grader output) |
| Time-to-correct | `time_to_correct_ms` | Harness (computed from grade events; `unknown` if censored) |
| Active execution | `active_execution_ms` | Harness (sum of non-queue phases) |
| Queue / approval | `queue_approval_ms` | Harness (sum of approval waits, e.g. between Jev preview and evaluate) |
| User-visible wall | `user_visible_wall_ms` | Harness (subprocess wall around the full task; `unknown` if the parent operator did not record it; the harness records it) |
| Terminal reason | `terminal_reason` | Harness (one of `pass`, `fail_no_pass_under_budget`, `fail_censored`, `fail_invalid_response`, `fail_provider_error`, `fail_fallback_unavailable`) |

The harness refuses to start if `TYPESAFE_API_KEY` is set. Missing replay, answer, or grader boundaries fail closed and remain in the summary.

## Censored-row retention

Every attempt produces a row, including failed and censored ones. A row is `censored: true` when a required replay, answer, or grader boundary is unavailable or times out. The aggregate report computes per-arm medians, IQRs, and pass rates with and without censored rows; the comparison report refuses to claim a wall-clock effect when censored-row fraction is above a documented threshold (default 0.25; configurable in `freeze.json`).
