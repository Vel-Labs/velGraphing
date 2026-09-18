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
| `task_accept` | First event for a (trial, task, arm) | `freeze_sha256`, `corpus_root` (project-relative) |
| `graph_build_or_load:cold` | First `graph_find.py` invocation | `subprocess_ms`, `exit_code`, `stdout_sha256`, `stderr_sha256` |
| `graph_build_or_load:warm` | Subsequent `graph_find.py` invocation | same as above |
| `discovery_start` | Lane begins discovery | `mode` (`graph` or `direct`) |
| `discovery_end` | Lane ends discovery | `mode`, `hits`, `hits_count`, `fallback_paths_count` |
| `jev_prepare_start` | First call to `jev.evaluate` | `mode` (`off`/`shadow`/`rerank`), `candidates_count` |
| `jev_prepare_end` | After `evaluate`'s prepare step | same as above + `prepare_ms` |
| `jev_provider_call_start` | Transport call (live or replay) | `endpoint`, `transport` (`live`/`replay`/`injected`), `model` |
| `jev_provider_call_end` | After transport returns | `provider_call_ms`, `input_tokens`, `output_tokens`, `attempted_calls` |
| `jev_revalidate_end` | After `evaluate`'s second prepare | `revalidate_ms`, `source_changed` (bool) |
| `answer_dispatch_start` | Lane begins writing its answer | `phase_1_pass_correctness` if previously graded |
| `answer_dispatch_end` | Lane emits its JSON | `answer_ms`, `answer_text_sha256` |
| `grade_start` | Grader subprocess begins | `grader_id` |
| `grade_end` | Grader subprocess ends | `grade_ms`, `required_fact_score`, `required_fact_max`, `required_fact_recall`, `critical_facts_exact`, `unsupported_material_claims`, `critical_errors`, `source_support` |
| `repair_attempt_n_start` | Lane begins repair attempt N | `attempt_index` |
| `repair_attempt_n_end` | Lane ends repair attempt N | `attempt_index`, `first_pass_correctness` (1.0/0.5/0.0/-1.0) |
| `first_pass_correctness` | After first grade | `value` (1.0/0.5/0.0/-1.0) |
| `time_to_correct` | After the first pass that satisfies the rubric | `time_to_correct_ms` (or `null` if censored) |
| `active_execution` | Once per row | `active_execution_ms` |
| `queue_approval` | Once per row | `queue_approval_ms` |
| `user_visible_wall` | Once per row | `user_visible_wall_ms` |
| `component_removal` | When a component-removal flag is passed | `removed` (`jev`/`graph`/`fallback`) |
| `terminal_reason` | Once per row | `reason` (`pass`/`fail_no_pass_under_budget`/`fail_censored`/`fail_invalid_response`/`fail_provider_error`/`fail_fallback_unavailable`) |

## Time-to-correct

`time_to_correct_ms` is computed from `task_accept.t_monotonic_ns` to the `t_monotonic_ns` of the first `grade_end` event whose `required_fact_recall == 1.0` AND `critical_facts_exact == true` AND `unsupported_material_claims == 0` AND `critical_errors == 0`. If no such event occurs under the repair budget, the row is `censored` and `time_to_correct_ms` is `null`.

## Active execution vs user-visible wall

`active_execution_ms` is the sum of:

- `graph_build_or_load:cold` (if present)
- `graph_build_or_load:warm` (if present)
- `discovery_*` delta
- `jev_*` deltas (if present)
- `answer_dispatch_*` delta
- `grade_*` delta

`user_visible_wall_ms` is the wall around the entire task as observed by the harness subprocess. It includes `queue_approval_ms`.

`queue_approval_ms` is the sum of waits that the harness observes but does not control (e.g. Jev preview → evaluate approval).

These three fields are deliberately independent so that double-counting is detectable.

## Schema stability

This schema is versioned as `velgraphing-time-to-correct-event-v1`. Changes require a freeze bump and a new schema version. The validator (`scripts/benchmarks/velgraphing_time_to_correct_trace.py`) rejects events whose `schema_version` does not match.

## Why JSONL

JSONL is append-only, line-oriented, and trivially diffable. It survives partial-run truncation (each line is self-contained). The validator reads the file line by line and never holds more than one event in memory, so a truncated file produces a clear "last_event_truncated" error rather than a corrupt parse.

## Why `time.monotonic_ns()` and not `time.time()`

`time.monotonic_ns()` is monotonic, unaffected by NTP adjustments, unaffected by daylight-saving, and nanosecond-resolution. `time.time()` is wall-clock and can move backward; we never want a backward event to flip a "passed under budget" verdict into "censored."
