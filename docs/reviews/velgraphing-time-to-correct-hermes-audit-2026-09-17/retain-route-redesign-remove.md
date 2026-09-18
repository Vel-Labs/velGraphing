# Retain / Route / Redesign / Remove

Per-finding recommendation. "Retain" means: keep as-is, no PR change. "Route" means: re-target the output (e.g. a different consumer, or a different protocol step). "Redesign" means: needs a future, separate PR (tracked in `deferred-redesigns.md`). "Remove" means: delete or explicitly mark as experimental-only.

## F1 (product): Jev is unreachable from the installed command surface.

**Recommendation:** Retain the current command surface; do NOT remove `/graph-jev`. The README already labels it "experimental integration, not a demonstrated efficiency improvement" (`README.md:69-70`).

**Rationale:** Removing it would invalidate the corpus pilot (`freeze.json` references `jev.py`). Keeping it as-is is honest: the command exists, the protocol is documented, and the corpus pilot measured its effect and reported it. The audit confirms the labeling is accurate.

## F2 (product): Jev rerank cannot prune; it preserves every candidate.

**Recommendation:** Retain. The current contract is documented and tested (`tests/core/test_jev.py::test_rerank_is_complete_permutation`). It is correct as a "reorder-only" primitive.

**Rationale:** Removing the pruning capability would be a feature change, not a defect repair. The harness in this PR measures whether rerank *matters* before any decision about whether to add pruning.

## F3 (product): Required-position locking suppresses ranking changes.

**Recommendation:** Retain. Required-position locking is part of the contract (`packages/core/jev.py:386-387`) and the protocol (`freeze.json:131-133`). Removing it would invalidate the pilot's claim "required IDs remain present."

**Rationale:** Required-position locking is a stability guarantee for the answer lane, not a correctness claim. The harness measures the effect of the guarantee on time-to-correct; future redesigns (D2) can address whether the guarantee should be relaxed.

## F4 (integration): `graph_find.py` never imports `jev`.

**Recommendation:** Route. The current architecture routes Jev through the parent operator's shell templates (`freeze.json:136-139`). Keep this for now.

**Rationale:** Wiring Jev into `graph_find.py` is a product change (D1) that needs operator approval. The harness measures the three hypotheses under the current architecture so the wiring decision can be evidence-based.

## F5 (integration): `selection.py` selects whole records, not ordered bytes.

**Recommendation:** Retain the current selection logic; defer any change to D2.

**Rationale:** The current `select_documents()` is documented, tested, and the corpus pilot measured under it. Changing it would change the prior pilot's interpretation. The harness measures the time-to-correct effect of the current logic before any change.

## F6 (harness): No monotonic event trace; `total_wall_ms` is `unknown` for most rows.

**Recommendation:** Redesign via the new harness (`benchmarks/velgraphing-time-to-correct-v1/`). The harness in this PR adds the trace and replaces the self-reported fields.

**Rationale:** The pilot is sealed and cannot be retroactively corrected. The new harness is the path forward. The sealed pilot's verdict (`pilot_rejects_jev_promotion_and_does_not_establish_wall_clock_savings`) is honest given its measurement limits.

## F7 (harness): No repair budget; no first-answer-time field.

**Recommendation:** Redesign via the new harness. `repair_budget`, `first_pass_correctness`, and `time_to_correct_ms` are in `event-trace.md`.

**Rationale:** Same as F6.

## F8 (rubric): Pass gate has no timing component.

**Recommendation:** Retain the current pass gate (`required_fact_recall >= 0.90`, no critical errors, no unsupported material claims). The harness adds *measurement*, not *gating*. A timing-aware gate is a separate rubric change (D3).

**Rationale:** The pilot's pass gate is a correctness gate. Adding a timing gate would change the prior pilot's interpretation. The harness measures timing without making it a gate; the next corpus pilot can decide whether to add a timing gate.

## F9 (rubric): Required-locking makes Jev's effect on rubric-failure rate hard to measure.

**Recommendation:** Retain. The harness measures the effect under the current locking. D1/D2 can revisit.

**Rationale:** Same as F3.

## F10 (documentation): Public claims match implementation.

**Recommendation:** Retain. No README change is needed. The corpus pilot README is the most honest; the canary README is the most qualified. None of them claims time-to-correct savings.

**Rationale:** This audit confirms the README is internally consistent and that every retained number carries an explicit disclaimer.

## F11 (inconclusive): Whether Jev would help if wired into graph-find directly.

**Recommendation:** Measure via the new harness under the *current* architecture; revisit under D1/D2 if the result suggests it.

**Rationale:** The brief asked us to separate the three hypotheses. The current architecture cannot test hypothesis 2 because Jev is not in the host loop. The harness measures what it can; future redesigns can test what it cannot.

## Summary table

| Finding | Class | Recommendation |
| --- | --- | --- |
| F1 | product | Retain |
| F2 | product | Retain |
| F3 | product | Retain |
| F4 | integration | Route (keep current; revisit under D1) |
| F5 | integration | Retain; revisit under D2 |
| F6 | harness | Redesign (this PR) |
| F7 | harness | Redesign (this PR) |
| F8 | rubric | Retain; revisit under D3 |
| F9 | rubric | Retain; revisit under D1/D2 |
| F10 | documentation | Retain |
| F11 | inconclusive | Measure (this PR); revisit under D1/D2 |

Eleven findings. Seven "Retain." Two "Route/Measure." Two "Redesign (in this PR)." Zero "Remove." This matches the brief's "minimal high-confidence repairs" framing.
