# Claim-to-Evidence Matrix

Each row links a public or implicit claim to the exact implementation evidence that supports or refutes it.

## C1: "VelGraphing helps an agent decide where to look, retrieves exact source spans, and falls back to direct source when graph evidence is incomplete."

Source: `README.md:1-7`.

| Sub-claim | Evidence | Status |
| --- | --- | --- |
| Decides where to look | `packages/core/retrieval.py:971-1218` `retrieve()` returns ranked hits. | Supported |
| Retrieves exact source spans | `packages/core/retrieval.py:1596-1744` `_verified_spans()` returns `ContextSpan` with byte ranges, source SHA-256, and excerpt digests. | Supported |
| Falls back to direct source | `packages/core/retrieval.py:1439-1499` `retrieve_hybrid()` invokes `assist()` (selection.py:146-236) with a caller-declared fallback list. | Supported |
| Source files remain authoritative | `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py:18` `sys.dont_write_bytecode = True` plus `_scan` returning read-only `SnapshotReader`. The graph is built once per invocation and discarded. | Supported |

Verdict: claim matches implementation.

## C2: "`/graph-find` reads only Git-tracked regular UTF-8 files under the explicit repository root."

Source: `README.md:174-179`.

Evidence: `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py:135-281`:

- Line 135-147: `_git()` invokes `git -C root ls-files -z --cached` only.
- Line 156-183: `_read_regular()` opens with `O_RDONLY | O_NOFOLLOW`, requires `S_ISREG`, and rejects symlink components (line 124-132).
- Line 221-223: `_is_sensitive_path()` excludes `.env`, `secrets/`, `credentials/`, `id_*` keys before any byte read.

Verdict: claim matches implementation.

## C3: "Use `/graph-jev` to preview and test an optional Jev-powered evidence reranker."

Source: `README.md:64-72`.

Evidence:

- `plugins/graph-engineering/commands/graph-jev.toml:1-2` registers the command.
- `plugins/graph-engineering/skills/graph-jev/SKILL.md:14-72` describes the protocol.
- `packages/core/jev.py:449-494` implements `main()` with `status`, `capture`, `preview`, `evaluate`, `replay` subcommands.
- **No caller in `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py` imports `jev`.** Confirmed by `search_files` for `from .* jev` and `import jev` across `packages/`, `plugins/`, and `scripts/`. The only `packages/core/jev.py` reference outside the file itself and `tests/core/test_jev.py` is in `plugins/graph-engineering/runtime/core/jev.py` (the projector copy) and the corpus pilot templates.

Verdict: the *command* exists and is described honestly as experimental. The README line "Default graph behavior remains unchanged; no API key is required unless you explicitly enable live Jev calls" is consistent with `packages/core/jev.py:340-356` (off / shadow / rerank with explicit `allow_network=True`). The unstated implication that Jev is integrated into `/graph-find` is **not** supported by the code.

## C4: "This is an experimental integration, not a demonstrated efficiency improvement."

Source: `README.md:69-70`.

Evidence:

- `packages/core/jev.py:1-6` module docstring: "This module only suggests a permutation of an existing, source-bound shortlist. It never prunes candidates, proves sufficiency, executes graph actions, or grants permissions."
- `packages/core/jev.py:384-389`: optionals are sorted by score; required positions are not touched; final order is a permutation of baseline.
- Corpus pilot verdict (`benchmarks/velgraphing-corpus-pilot-v1/README.md:5-7`): `pilot_rejects_jev_promotion_and_does_not_establish_wall_clock_savings`.

Verdict: claim matches implementation and matches the most recent measured result.

## C5: Pilot claims about required-fact recall (Stable R2 and V2, shipped-interface, project-scaffold).

Source: `README.md:78-141`.

| Pilot | Required-fact recall claim | Source | Verdict |
| --- | --- | --- | --- |
| Stable R2 | "Direct 95.83% / 95.83%; Hybrid 91.67% / 89.58%; context +29.08%; Rejected." | `README.md:84` | Re-stated from `benchmarks/held-out-comparison-stable-r2/result.json`. Labeled "useful negative evidence, not a performance claim" (README.md:80). |
| V2 | "Direct 97.22% / 97.92%; Hybrid 94.44% / 100.00%; context -12.76%; Rejected." | `README.md:85` | Re-stated from `benchmarks/multi-turn-readme-benchmark-v2/result.json`. |
| Shipped-interface | "Direct 18/19; Graph only 0/19; Graph-assisted pointer reads 2/19; Graph-assisted targeted fallback 17/19." | `README.md:104-107` | Re-stated from `benchmarks/velgraphing-shipped-interface-v1/scores.json` and `README.md`. |
| Project-scaffold canary | "Direct 3/6; Graph-assisted 5/6; tokens -58.9%; wall +15.7%." | `README.md:128-132` | Re-stated from `benchmarks/project-scaffold-live-canary-v1/result.json`. |

Each of these has a `Verdict`, a `Limitations` block, or both. The shipped-interface `README.md` (`benchmarks/velgraphing-shipped-interface-v1/README.md`) records "The run was rejected." The canary records `verdict: promising_single_task` and `limitations: ["One question on one repository cannot support a general effectiveness claim.", ...]` (`result.json:87-93`).

Verdict: claims match implementation and disclaimers. The audit confirms there is **no inflation** in the README.

## C6: `time.monotonic_ns()` event trace will measure the three hypotheses.

Source: this audit (`minimal-repair.md`).

Evidence: the repair in `benchmarks/velgraphing-time-to-correct-v1/` emits one JSONL line per event with `event_id`, `phase`, `t_monotonic_ns`, `task_id`, `arm`, `packet_id`. The events listed in `event-trace.md` are: `task_accept`, `graph_build_or_load`, `discovery_start`, `discovery_end`, `jev_prepare_start`, `jev_prepare_end`, `jev_provider_call_start` (only on rerank with replay or live approval), `jev_provider_call_end`, `jev_revalidate_end`, `answer_dispatch_start`, `answer_dispatch_end`, `grade_start`, `grade_end`, `repair_attempt_n_start`, `repair_attempt_n_end`, `first_pass_correctness`, `time_to_correct` (computed from grade events), `active_execution_ms` (sum of phases minus queue time), `queue_approval_ms` (sum of approval waits), `user_visible_wall_ms` (recorded by parent). `total_wall_ms` in the prior pilot is replaced by these per-event fields.

Verdict: claim is supportable by the harness design and is tested by `tests/benchmarks/test_velgraphing_time_to_correct_v1.py`.

## C7: Failed tasks are not silently dropped.

Source: this audit.

Evidence: `scripts/benchmarks/velgraphing_time_to_correct_v1.py` keeps a row for every attempt, including `status: failed`, `terminal_reason: <reason>`, and `censored: true` when wall-clock is unavailable. The `tests/benchmarks/test_velgraphing_time_to_correct_v1.py::test_censored_row_is_retained` test asserts this.

Verdict: claim is enforced by the harness and tested.

## C8: Jev integration is validated with replay/deterministic fixtures only.

Source: this audit; brief instruction.

Evidence: `packages/core/jev.py:330-400` `evaluate()` accepts a `replay` parameter bound to a request-hash-keyed envelope. The harness invokes `evaluate(replay=...)` only. `tests/benchmarks/test_velgraphing_time_to_correct_v1.py::test_jev_replay_path_emits_provider_call_events` asserts no `TYPESAFE_API_KEY` is read and no transport other than the replay fixture is used. The harness script also raises if `TYPESAFE_API_KEY` is set in the environment.

Verdict: claim matches implementation and tests.
