# Deferred Redsigns (not in this PR)

These are redesigns the audit identified as the natural next steps to make the three hypotheses answerable. Each is described, justified, and explicitly tagged "DEFERRED" so that future review knows it is on the list and not in this PR.

## D1: Wire Jev into the installed command surface

**Status:** DEFERRED. Requires product change.

**Why deferred:** The brief asks us to make time-to-correct measurable, not to ship a new product feature. Wiring Jev into `/graph-find` is a product decision that needs operator approval for live provider calls. The harness in this PR measures the three hypotheses under the current (Jev-as-external-protocol) architecture so we can answer the question first.

**If pursued:** Add a `jev` argument to `graph_find.py` that captures spans, calls `jev.evaluate(replay=...)` against an approved hash, applies the suggested order to the byte-level span selection in `_verified_spans`, and emits timing events. The harness would then run the wired version end-to-end and the three hypotheses become directly measurable against the host's actual reads, not against an external operator-mediated rerank.

## D2: Make `selection.py` byte-ordered instead of record-ordered

**Status:** DEFERRED. Requires product change.

**Why deferred:** Same as D1 — product change, not a harness change. The current `select_documents()` returns whole documents in `auth_ids` order; byte-level order in `_verified_spans()` is set by obligation authority, not by RRF score. A Jev reorder that pushes a low-authority span up the RRF list does not move it into the answer context unless its obligation also moves. This is the structural reason rerank cannot reduce source reads by itself.

**If pursued:** Replace `select_documents()` with a byte-ordered selection that consumes the suggested_order from Jev (when present), then the Jev score actually changes which bytes the lane reads first.

## D3: Add a `required-fact` rubric to the canary/pilot format

**Status:** DEFERRED. Requires rubric change.

**Why deferred:** The current rubric (`freeze.json:142-147`) is "exact 1.0, partial 0.5, absent_or_wrong 0.0, critical_error -1.0". A "required-fact" rubric would let the harness compute per-fact coverage and let the time-to-correct event terminate on a partial-fact improvement, not just on a full pass.

**If pursued:** Extend `freeze.json:scoring` with `required_facts_per_question`, an array of `{question_id, fact_id, criticality}` tuples, and update `tests/benchmarks/test_velgraphing_time_to_correct_v1.py` to assert the new shape.

## D4: Multi-question repeated trials

**Status:** DEFERRED. Requires corpus change.

**Why deferred:** The corpus pilot has 6 questions × 4 arms = 24 rows. For time-to-correct measurement, that is too few rows per arm to separate Jev-within-retrieval effects from graph-assistance effects with any confidence. The brief asks for "four-arm repeated-trial design," and the design lives in `benchmark-design.md`; the actual corpus extension (e.g. 30 questions per arm) is a separate corpus question.

**If pursued:** Add 24 more questions to the corpus pilot (12 across the existing four corpora plus 12 across two new ones), freeze them in `freeze.json`, regenerate `packets.json`, and rerun.

## D5: Cross-corpus Jev budget

**Status:** DEFERRED. Requires freeze change.

**Why deferred:** The current Jev budget is "one request per arm per task; six tasks and Jev-on arms use 12 total calls" (`freeze.json:122`). For time-to-correct measurement, this is the right shape (each call is one Jev invocation). But it does not allow measuring the effect of `max_candidates` (currently 6) on time-to-correct.

**If pursued:** Add `jev_max_candidates_grid: [3, 6, 9]` to `freeze.json:jev` and run the grid. Out of scope for this audit.

## D6: Move timing emission into canonical core

**Status:** DEFERRED. Requires core change.

**Why deferred:** The harness emits timing events today, which is sufficient for measurement. Moving `time.monotonic_ns()` events into `packages/core/` would be a wider change that would need its own audit (the AGENTS.md rule "do not add a ... scheduler" is relevant).

**If pursued:** Add a `TraceSink` protocol to `packages/core/models.py`, plumb it through `retrieve()`, `evaluate()`, and `compose_navigation_context()`, and document the schema in `contracts/core/`.

## D7: Replace the answer-lane self-report contract

**Status:** DEFERRED. Requires harness and answer-lane change.

**Why deferred:** The pilot asks the answer lane to self-report 11 of 12 timing fields, which the sealed result shows does not work in practice (most fields are `unknown`). The harness in this PR replaces 11 of those fields with harness-measured fields, so the self-report contract is no longer needed for the new benchmark. It is still in the old corpus pilot because that pilot is sealed.

**If pursued:** Update `freeze.json:answer_lane_boundary:telemetry_return_schema` to drop the self-reported fields and require only the answer-lane-emitted text. Out of scope for this audit.

## D8: Adversarial source-folder fixture

**Status:** DEFERRED. Requires corpus change.

**Why deferred:** The corpus pilot freezes one snapshot per corpus. For the four-arm trial to separate "Jev is reranking the wrong thing" from "Jev is reranking correctly but the host ignores it," we need at least one corpus where the Jev reorder would, in principle, surface a different byte first than the obligation-authority ordering does.

**If pursued:** Add an adversarial corpus where required facts are spread across high-authority and low-authority paths and the rubric is sensitive to which fact is found first. Out of scope for this audit.

## Summary

Eight deferred redesigns. Each is justified and tagged. None are implemented in this PR. The harness in this PR is sufficient to measure the three hypotheses on the *current* installed command path; the redesigns would let the same measurements be made on *improved* command paths and let product changes be evaluated with the same instrument.
