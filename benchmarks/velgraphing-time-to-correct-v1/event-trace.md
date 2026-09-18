# Event Trace Schema (VelGraphing Time-to-Correct v1)

The harness emits one JSON object per line. Each event carries:

```json
{
  "schema_version": "velgraphing-time-to-correct-event-v1",
  "event_id": "<uuid4-or-stable-id>",
  "trial_index": 0,
  "task_id": "C-01",
  "packet_id": "A-C-01",
  "arm": "A",
  "corpus_id": "cpython",
  "snapshot_sha256": "<64 hex>",
  "phase": "<see below>",
  "t_monotonic_ns": 1234567890,
  "status": "ok | skipped | failed | censored",
  "details": { ... phase-specific ... }
}
```

`details` is phase-specific. The list below is the closed vocabulary.

## Phases

| Phase | When | `details` keys |
| --- | --- | --- |
| `task_accept` | First event for a (trial, task, arm) | `freeze_sha256` |
| `graph_build_or_load:cold` / `:warm` | Reserved for a future caller-owned graph command seam | not emitted by this harness version |
| `discovery_start` / `discovery_end` | Reserved for a future caller-owned discovery command seam | not emitted by this harness version |
| `jev_prepare_start` | Canonical `jev.evaluate` begins | `mode` (`rerank`) |
| `jev_prepare_end` | Canonical Jev evaluation returns | `mode`, `canonical` |
| `jev_provider_call_start` | Deterministic replay evaluation begins | `transport` (`replay`) |
| `jev_provider_call_end` | Canonical Jev evaluation returns | `elapsed_ms`, `canonical_elapsed_ms`, `status`, `attempted_calls` |
| `jev_revalidate_end` | Canonical Jev source revalidation returns | `source_revalidated` |
| `answer_dispatch_start` | Frozen answer subprocess begins | `attempt_index` |
| `answer_dispatch_end` | Frozen answer subprocess returns | `attempt_index`, `exit_code`, `wall_ms`, output digests |
| `grade_start` | Frozen grader subprocess begins | `attempt_index` |
| `grade_end` | Frozen grader subprocess returns | `attempt_index`, `exit_code`, `wall_ms`, observed grade object |
| `repair_attempt_n_start` | Lane begins repair attempt N | `attempt_index` |
| `repair_attempt_n_end` | Harness ends attempt N | `attempt_index`, `reason` |
| `first_pass_correctness` | After an observed grade | `attempt_index`, `value` (boolean), `required_fact_recall` |
| `time_to_correct` | After the first pass that satisfies the rubric | `time_to_correct_ms` (or `null` if censored) |
| `active_execution` | Once per row | `active_execution_ms` |
| `queue_approval` | Once per row | `queue_approval_ms` |
| `user_visible_wall` | Once per row | `user_visible_wall_ms` |
| `component_removal` | When a component-removal flag is passed | `removed` (`jev`/`graph`/`fallback`) |
| `terminal_reason` | Once per row | observed reason such as `pass`, `fail_no_pass_under_budget`, `answer_lane_unavailable`, `grader_unavailable`, or `jev_error:<reason>` |

## Time-to-correct

`time_to_correct_ms` is computed from the task start to the first observed grade whose `required_fact_recall == 1.0` AND `critical_facts_exact == true` AND `unsupported_material_claims == 0` AND `critical_errors == 0`. If no such grade occurs under the repair budget, the row remains a failed, non-censored outcome. Missing replay, answer, grader, or timeout boundaries are censored.

## Active execution vs user-visible wall

`active_execution_ms` is the sum of:

- `jev_*` deltas (if present)
- `answer_dispatch_*` delta
- `grade_*` delta

`user_visible_wall_ms` is the wall around the entire task as observed by the harness process. It includes `queue_approval_ms`.

`queue_approval_ms` is currently `null` because this harness does not own an approval queue.

These three fields are deliberately independent so that double-counting is detectable.

## Schema stability

This schema is versioned as `velgraphing-time-to-correct-event-v1`. Changes require a freeze bump and a new schema version. The validator (`scripts/benchmarks/velgraphing_time_to_correct_trace.py`) rejects events whose `schema_version` does not match.

## Why JSONL

JSONL is append-only, line-oriented, and trivially diffable. It survives partial-run truncation (each line is self-contained). The validator reads the file line by line and never holds more than one event in memory, so a truncated file produces a clear "last_event_truncated" error rather than a corrupt parse.

## Why `time.monotonic_ns()` and not `time.time()`

`time.monotonic_ns()` is monotonic, unaffected by NTP adjustments, unaffected by daylight-saving, and nanosecond-resolution. `time.time()` is wall-clock and can move backward; we never want a backward event to flip a "passed under budget" verdict into "censored."
