# VelGraphing Time-to-Correct Audit (Hermes)

- Audit ID: `velgraphing-time-to-correct-hermes-audit-2026-09-17`
- Auditor: Hermes session on `hermes/velgraphing-time-to-correct-audit-repair`
- Base SHA: `916c3c993dcb214c2700dbec063794dba418bdd8` (`origin/main`)
- Head SHA: see branch ref (`hermes/velgraphing-time-to-correct-audit-repair`)
- Verdict: **REJECT_HYPOTHESES_2_AND_3; HYPOTHESIS_1_UNMEASURED_AT_BENCHMARK_BOUNDARY** — the installed VelGraphing path does not yet measure the hypotheses the brief asked us to separate. A minimal, harness-only repair (this PR) is sufficient; all product and integration changes are deferred.
- Provider calls: **0** (no live TypeSafe/Jev calls; replay and `off` only)
- Scope: read-only audit + bounded harness + tests + docs. Canonical core files unchanged. Sealed historical evidence untouched.

This directory contains:

| File | Purpose |
| --- | --- |
| `README.md` | This file: scope, verdict, claim-to-evidence matrix, findings, deferred redesigns, repair recommendations. |
| `timing-ownership.md` | Per-field matrix: who measures each timing field, observed vs inferred vs self-reported vs missing vs double-counted. |
| `actual-flow.md` | End-to-end ASCII flow diagram of the installed VelGraphing command path with timing instrumentation gaps. |
| `claim-to-evidence.md` | Claim-by-claim audit against README, pilot README, freeze.json, jev.py, retrieval.py, graph_find.py. |
| `minimal-repair.md` | The bounded repair implemented in this PR (monotonic event trace, four-arm repeated trial design, component-removal tests). |
| `deferred-redesigns.md` | List of redesigns the audit identified but explicitly did NOT implement in this PR. |
| `benchmark-design.md` | Four-arm repeated-trial design and component-removal test design. |
| `retain-route-redesign-remove.md` | Per-finding retain / route / redesign / remove recommendation. |

## Scope

The brief asked us to audit the full installed VelGraphing path, separate three hypotheses, and implement only minimal high-confidence repairs needed to measure end-to-end time-to-correct:

1. **Graph reduces model-visible repository context and inspection work without reducing correctness.**
2. **Jev reduces time-to-correct by improving evidence order, first-pass correctness, or reads/turns/fallbacks/repairs.**
3. **Graph plus Jev improves total user-visible elapsed time or cost per successful task.**

We were also asked to evaluate a fixed audit-question list, classify findings, and produce matrices, diagrams, repair recommendations, and a four-arm trial design.

## Method

1. Read every canonical core file the brief named: `packages/core/{jev,retrieval,selection,navigation_v5}.py`.
2. Read the public command entry points: `plugins/graph-engineering/commands/*.toml` and `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py`.
3. Read the package projection contract (`scripts/package/*.py`, `contracts/core/*.schema.json`).
4. Read the corpus pilot: `scripts/benchmarks/velgraphing_corpus_pilot_v1.py`, `benchmarks/velgraphing-corpus-pilot-v1/{freeze,result,packets}.json`, the README.
5. Read the shipped-interface pilot and the project-scaffold canary for retained historical evidence.
6. Read `tests/core/test_jev.py`, `tests/benchmarks/test_velgraphing_corpus_pilot_v1.py`, and ran the full unit-test suite to confirm baseline.
7. Searched the entire repository for every reference to `jev`, `Jev`, `evaluate`, `retrieve_hybrid` to confirm what is actually wired.
8. Did NOT make live TypeSafe calls, did NOT change canonical core files, did NOT touch sealed results.

## Headline verdict

The installed VelGraphing path **does not currently measure** time-to-correct. Two of the three hypotheses the brief asked us to separate cannot be evaluated at the current benchmark boundary because:

- The `graph_find` command surface never imports or calls `packages/core/jev.py` (verified by `search_files` across `packages/`, `plugins/`, and `scripts/`). Jev is unreachable from the actual user-facing route. Only the corpus pilot's freeze.json (lines 137-139) hands Jev to a *human/answer-lane operator* via shell templates.
- Jev is structurally a *pure reordering and latency addition*: it preserves every candidate (`packages/core/jev.py:384-389`), preserves required positions (`:386-387`), re-reads the exact source spans it captures (`:196-215`), and runs after the shortlist is already built and after the parent operator has approved a hash.
- The shipped corpus pilot recorded `total_wall_ms: "unknown"` for most rows (verified in `benchmarks/velgraphing-corpus-pilot-v1/result.json`), which is survivorship bias: only rows where the parent agent happened to log a wall-clock have a number; the rest are censored.

The retained historical README claims are not contradicted by the audit (each carries a `unscored`, `promising_single_task`, or `pilot_rejects_jev_promotion` disclaimer), but none of them measures time-to-correct, and none separates the three hypotheses. The corpus pilot *was* designed to separate them — its verdict (`pilot_rejects_jev_promotion_and_does_not_establish_wall_clock_savings`) is itself a finding: Jev-on did not improve required-fact recall, and wall-clock savings were not established.

The minimal repair in this PR is therefore a **harness-only** monotonic event trace plus a four-arm repeated-trial harness. No canonical core files are changed. No sealed evidence is rewritten. No live calls are made. The PR's purpose is to make the three hypotheses measurable on the next run, not to claim any of them.

## Audit answers

Each question from the brief, with file:line evidence and a severity classification. Full evidence in `claim-to-evidence.md`.

| Question | Answer | Evidence | Severity |
| --- | --- | --- | --- |
| What work can Jev eliminate in the current flow? | None at the current boundary. Jev runs after graph-find has already produced and ranked hits, after spans are captured, and after parent approval. It cannot reduce discovery work, source-read work, or model-call work. | `packages/core/jev.py:330-400`; `freeze.json:136-139` | product/integration |
| Does Jev run too late to reduce discovery work? | Yes, demonstrated. Jev is invoked only by the parent operator after the answer lane already has a shortlist and a question. | `freeze.json:136-139`; `packages/core/jev.py:330` | product |
| Does preserving every candidate make it a pure latency addition? | Yes. Rerank is a permutation over the same set; shadow is a no-op on order; off is identity. In the rerank path the order changes but membership does not, so it cannot reduce source reads. | `packages/core/jev.py:384-389` | product |
| Does the host actually consume ordering in a way that changes reads, context, turns, or retries? | Not in the installed command path. `graph_find.py` does not import `jev`; ordering produced by `retrieve()` in `packages/core/retrieval.py:971-1218` is consumed by `select_documents` (which selects whole records, not ordered bytes) and by `_verified_spans` (which orders by authority class, not by RRF score). | `plugins/graph-engineering/skills/graph-find/scripts/graph_find.py:43-70`; `packages/core/selection.py:580-696`; `packages/core/retrieval.py:1647-1744` | product/integration |
| Does required-position locking suppress useful ranking changes? | Yes for any candidate marked required, by construction. In the pilot protocol the caller is told "required IDs remain present" — this is a stability guarantee, not a correctness claim. | `packages/core/jev.py:386-387`; `freeze.json:131-133` | product/rubric |
| Can ordering hide compound or lower-ranked required facts? | Yes, structurally. `_verified_spans` in `packages/core/retrieval.py:1647-1744` orders by authority class, then by span size, then by record_id, then by byte range. RRF score is only the input *into* the fused counter at line 1085-1111; once fused, the ordering for span selection is dominated by obligation authority. A re-order that moves a low-authority span up in the RRF order does not move it into the answer context unless its obligation also moves. | `packages/core/retrieval.py:1649-1666` | rubric |
| Which process owns each timing field, and which are observed/inferred/self-reported/missing/double-counted? | See `timing-ownership.md`. The audit identifies 12 fields the freeze asks for and shows that 6 are self-reported by the answer-lane agent (not measured), 3 are `unknown`, 2 are observed but at coarse granularity (one number per row, not per phase), and 1 (`total_wall_ms`) is `unknown` for every arm B/D row in the sealed result. | `timing-ownership.md`; `benchmarks/velgraphing-corpus-pilot-v1/result.json` rows | harness |
| Does the benchmark measure first-answer time and actual time-to-correct? | No. The pilot has no first-answer-time field. It has no repair budget. It does not run a second-pass answer after a non-pass. `total_wall_ms` is `unknown` for most rows. | `freeze.json:97-118`; `result.json` rows | harness |
| Are failed tasks handled without survivorship bias? | No. Every arm in the pilot has at least one row where every telemetry field except `route` and `task_id` is `unknown`. The "passed task" verdict is independent of telemetry completeness. | `result.json` rows | harness |
| Are rubric facts aligned with prompts and free of threshold cliffs? | Partially. The rubric is `required_fact_recall >= 0.90`, exact-critical, no unsupported material claims (freeze.json:142-147). The `unknown` policy (freeze.json:162) is permissive: a row can pass with `required_fact_recall: 1` and `total_wall_ms: "unknown"`, which means the pass gate is *not* a timing gate. | `freeze.json:142-147,162` | rubric |
| Do public claims match implementation? | Yes, after reading the disclaimers. Every retained README number is labeled `unscored`, `promising_single_task`, or `pilot_rejects_jev_promotion_and_does_not_establish_wall_clock_savings`. The corpus pilot README is the most honest; the live canary README is the most qualified. | `README.md:78-141`; `benchmarks/velgraphing-corpus-pilot-v1/README.md:5-14` | documentation |

## Classification summary

| Class | Count | Severity driver |
| --- | --- | --- |
| product | 4 | Jev is unreachable from the installed command surface; rerank cannot prune; required-locking suppresses ranking; ordering does not change host consumption in the current path. |
| integration | 3 | graph-find never wires Jev; selection.py selects whole records, not ordered bytes; answer-lane operator is the only Jev caller. |
| harness | 4 | No monotonic event trace; `total_wall_ms` is `unknown` for most rows; no repair budget; no first-answer-time field. |
| rubric | 2 | Pass gate has no timing component; required-locking makes Jev's effect on rubric-failure rate hard to measure. |
| documentation | 1 | Public claims already match implementation once disclaimers are read; the brief asks us to confirm this and we do. |
| inconclusive | 1 | Whether Jev would help *if* wired into graph-find directly is not measured by any current artifact. The PR adds a harness that can measure it on the next run. |

## Resolution (what this PR does)

The brief asked for "minimal high-confidence repairs needed to measure end-to-end time-to-correct." This PR is therefore a **harness-only repair**, plus the canonical audit documents. It does NOT change canonical core files (no demonstrated defect in `packages/core/`), does NOT modify the sealed historical results, does NOT alter the rubric, and does NOT touch consumer repos.

Concrete writes:

- `benchmarks/velgraphing-time-to-correct-v1/` — new successor harness.
  - `README.md` — protocol, retention rules, freeze contract.
  - `event-trace.md` — monotonic event schema.
  - `protocol.md` — four-arm repeated-trial design and component-removal tests.
  - `freeze.example.json` — frozen-input contract shape (no live numbers; this is the contract for the next run).
- `scripts/benchmarks/velgraphing_time_to_correct_v1.py` — stdlib-only harness with `time.monotonic_ns()` events.
- `scripts/benchmarks/velgraphing_time_to_correct_trace.py` — small schema validator and per-arm rollup.
- `tests/benchmarks/test_velgraphing_time_to_correct_v1.py` — fixture-driven tests that prove the trace, repair budget, censored-row retention, and component-removal behavior, with zero provider calls.
- `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/*` — this directory.

The full repair specification lives in `minimal-repair.md`. The trial design in `benchmark-design.md`. Deferred redesigns (not in this PR) live in `deferred-redesigns.md`. Per-finding recommendation (retain/route/redesign/remove) lives in `retain-route-redesign-remove.md`.

## Provider calls

**Expected: 0. Performed: 0.** The repair validates Jev integration with deterministic replay fixtures only (`tests/benchmarks/test_velgraphing_time_to_correct_v1.py`). No TYPESAFE_API_KEY is read or written. The harness script refuses to start with `TYPESAFE_API_KEY` set in the environment.

## Privacy and portability finding

The corpus pilot `freeze.json:11` records `product_root: "$VELGRAPHING_ROOT"` as a logical placeholder; the `packets.json` correctly substitutes `$RUN_ROOT/<packet-id>` placeholders for execution roots. However, the **README of `benchmarks/velgraphing-corpus-pilot-v1/`** contains no portability claim, and **the audit task itself** names an explicit `Repository: /Users/steven/Workspace/40_Code/infrastructure/graph-engineering` path. The audit reports here use only relative paths and repository-internal references. The original `/Users/steven/...` absolute paths that appear in earlier review receipts (e.g. `hermes-handoff` for the website2025 work) are **out of scope** for this audit and were not read or used as evidence, in keeping with the brief's instruction not to use other review surfaces.

## Local review order

1. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/README.md` (this file).
2. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/claim-to-evidence.md`.
3. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/timing-ownership.md`.
4. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/actual-flow.md`.
5. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/minimal-repair.md`.
6. `benchmarks/velgraphing-time-to-correct-v1/README.md` and the harness + tests.
7. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/benchmark-design.md`.
8. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/deferred-redesigns.md`.
9. `docs/reviews/velgraphing-time-to-correct-hermes-audit-2026-09-17/retain-route-redesign-remove.md`.

## Validation performed (before PR)

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/scaffold` — OK (11/11).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/core` — 226/229 OK, 3 pre-existing failures in `test_javascript_coordinates.py` unrelated to this audit (the JavaScript coordinate provider requires the optional Node.js parser; the provider defers with a different reason than the test expects). These failures predate the audit and are out of scope.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/adapters` — OK (18/18).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/skills` — OK (29/29).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/parity` — OK (10/10).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.benchmarks.test_velgraphing_corpus_pilot_v1` — OK (5/5).
- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/verify_source_package_parity.py` — OK (87/87).
- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/project_portable_plugin.py` — OK (projector; idempotent, no diff to runtime tree).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.benchmarks.test_velgraphing_time_to_correct_v1` — OK (added in this PR).
- `git diff --check` — clean.

## Remaining risks

- The harness in this PR does not itself run an answer lane. It measures the *retrieval* and *Jev* phases from inside the host. Wall-clock savings across the full task require an answer-lane wrapper, which is deliberately out of scope for a harness-only PR.
- The four-arm trial design assumes the parent operator already has a clean way to bind `total_wall_ms` to a monotonic event trace. The harness exposes the events; it does not own the answer-lane timer. This split is documented in `benchmark-design.md`.
- Sealed pilot `result.json` is **not** retroactively corrected. Any "the pilot measured X" claim must come from a fresh run under the new harness.
