# Actual Flow Diagram (VelGraphing installed command path)

This is the *current* end-to-end flow inside the installed VelGraphing path, with each phase's owner and what timing data exists today.

```
                                                                              ┌─────────────────────────────────────────┐
                                                                              │ Parent operator (human or parent agent) │
                                                                              │  - freezes questions, rubrics, snapshots │
                                                                              │  - owns approval of Jev request hash     │
                                                                              │  - owns provider key custody             │
                                                                              └────────────────┬────────────────────────┘
                                                                                               │
                                                                                               │ packet (freeze.json, packets.json)
                                                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Answer lane (fresh host-native worker, no inherited history)                                                   │
│                                                                                                                 │
│  ┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐                   │
│  │ Arm A or C: graph_find  │    │ Arm A or B: direct       │    │ Arm B or D: Jev          │                   │
│  │ scripts/graph_find.py    │    │ ls / read / search       │    │ capture / preview /      │                   │
│  │ --root <corpus_root>     │    │ (host-native)            │    │ evaluate (parent owns)   │                   │
│  └──────────────┬───────────┘    └──────────────┬───────────┘    └──────────────┬───────────┘                   │
│                 │                               │                               │                               │
│  packages/core/retrieval.py  │ no graph artifacts         │ packages/core/jev.py                                  │
│   - build_repository_tag_index (graph-find in-mem) │ │   - prepare (reads every captured source span)        │
│   - compile_prompt (8-20 facets)                    │ │   - evaluate (one provider call, or replay)          │
│   - retrieve (RRF over 4 channels, 1-hop expansion) │ │   - revalidate source spans after inference         │
│   - graph_find returns GraphFindResult              │ │   - returns suggested_order (a permutation)         │
│   (no internal timing emitted)                      │ │   (elapsed_ms only on the evaluate call)             │
│                 │                               │                               │                               │
│                 ▼                               ▼                               ▼                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐                   │
│  │ Lane composes answer using:                                                            │                   │
│  │  - direct source reads (own choice), or                                                │                   │
│  │  - graph_find hits (pointers) → exact source spans (graph-find does NOT read them),    │                   │
│  │    or                                                                                  │                   │
│  │  - Jev suggested_order (same set as baseline, possibly permuted)                       │                   │
│  │  - selection.py:580-696 select_documents() returns whole documents, not ordered bytes  │                   │
│  └───────────────────────────────┬────────────────────────────────────────────────────────┘                   │
│                                  │                                                                            │
│                                  ▼                                                                            │
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐                   │
│  │ Lane emits JSON with: route, task_id, arm, source_snapshot_sha256,                     │                   │
│  │   required_fact_coverage, source_support, model_visible_context_bytes, source_ops,      │                   │
│  │   cold_graph_build_ms, warm_graph_load_ms, retrieval_ms, fallback_reads_and_bytes,      │                   │
│  │   answer_ms, total_wall_ms, jev_calls_tokens_latency, proof_and_authority_errors        │                   │
│  │   → 11/12 fields are SELF-REPORTED by the lane; 1 (required_fact_coverage) is graded. │                   │
│  └───────────────────────────────┬────────────────────────────────────────────────────────┘                   │
└──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Independent grader (outside the answer lane)                        │
│  - applies rubric from freeze.json:142-147                          │
│  - returns: required_fact_score, required_fact_max, recall,         │
│    critical_facts_exact, unsupported_material_claims,               │
│    critical_errors, source_support                                  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
                        result.json (sealed)
```

## Where timing is missing

The diagram above shows the only places where time is currently captured:

1. Inside `packages/core/jev.py:353,399` — `evaluate()` records `elapsed_ms` for the entire Jev call (prepare + transport + parse + revalidate). This is the *only* monotonic timing in the canonical core.
2. Nowhere else. `graph_find.py`, `retrieval.py`, `selection.py`, and the answer lane emit no monotonic event trace.

The pilot result confirms this: `total_wall_ms` is `unknown` for almost every row, and the per-phase fields (`cold_graph_build_ms`, `warm_graph_load_ms`, `retrieval_ms`, `answer_ms`) are mostly `unknown`.

## What the harness changes

The new harness (`scripts/benchmarks/velgraphing_time_to_correct_v1.py`) wraps each phase in `time.monotonic_ns()` and emits a JSONL event stream. The phases map directly to the boxes in the diagram. See `minimal-repair.md` and `event-trace.md` for the schema.

## What Jev actually adds in the current path

Tracing the boxes for arm D:

1. Phase 1 (fresh lane) runs `graph_find` to get a shortlist.
2. Phase 1 captures explicit spans, prepares the packet, previews the request, and computes `request_sha256`. The lane does not answer.
3. The lane stops and waits for parent operator approval of the request hash.
4. Parent operator invokes `packages/core/jev.py evaluate` (one call), which:
   - prepares the request again (re-reads all captured source spans to verify digests; this is *additional* source-read work that the graph-find command did not have to do, because the spans were passed in already);
   - calls the provider (or runs the replay fixture);
   - parses the response;
   - re-reads the source spans a third time to verify they did not change during inference.
5. Parent operator returns the Jev observation/order to the same lane.
6. The lane revalidates exact sources and answers.

Total Jev-added work, even in the off path: zero (the lane does not call Jev when `mode=off`).
Total Jev-added work in the shadow path: zero (off by default; lane must opt in).
Total Jev-added work in the rerank path: at minimum one additional prepare+transport+parse+revalidate cycle. The rerank path **cannot** reduce source reads because it preserves every candidate (`packages/core/jev.py:384-389`). It can only change which candidate the lane reads first.

The first-read change can matter *only* if the lane would otherwise read more candidates than it needs to before finding a passing answer. There is no current measurement of this. The harness in this PR measures it.

## Why a "pure reordering" cannot reduce time-to-correct by itself

For Jev-on to reduce time-to-correct, three conditions must hold:

1. The lane reads enough candidates to find a passing answer that Jev-on would have surfaced earlier.
2. The lane would otherwise read past that candidate before stopping.
3. The candidate ordering produced by Jev matches what the lane actually consumes in the answer phase.

Condition 3 is the structural problem: `selection.py:580-696` `select_documents()` returns **whole documents** in `auth_ids` order, not ordered bytes. The byte-level order is set by `_verified_spans` (`packages/core/retrieval.py:1596-1744`), which sorts by `(critical?, authority_class_priority, documentation_only?, span_size, record_id, byte_start, byte_end)`. The Jev score is the *input* to the fused counter at `retrieval.py:1085-1111`, but the byte-level span order is dominated by obligation authority. A Jev reorder that pushes a low-authority span up the RRF list does not move it into the answer context unless its obligation moves.

This is the structural reason a rerank cannot reduce source reads by itself in the current path. The deferred redesigns (not in this PR) include "consume Jev order in span selection" and "make selection.py byte-ordered, not record-ordered." Neither is in scope here.
