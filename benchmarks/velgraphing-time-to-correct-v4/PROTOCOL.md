# Time-to-correct v4: qualification protocol, not an executed benchmark

Status: **draft, blocked on Gates 1–3 and a registered v4 runner**.
Source candidate: `6931f0ffa72bd27f79f5515bd669404dbc4667d0`.
No v4 result is asserted. No live call is authorized by this document.

## What changes, and what stays sealed

The v1, v2 and v3 freezes and results remain untouched. V3 is the fixed-packet,
no-fallback retrieval stress test. V4 is a separately registered adaptive product
experiment. A patched core must never be run under the original v3 candidate
identity. Record a new commit, source-package manifest, source snapshots, rubric
identity, candidate artifact and exact request hashes.

The implemented local slice repairs two source-window/tag-cap helpers, supplies
a post-hoc evaluator, and adds a bounded source-bound edge seam. The public
scanner derives only uniquely resolved Python `from module import name` and
relative Markdown heading-link edges. The core exposes at most one verified
`RelationshipSupport` per selected seed. This metadata does not change ranking,
evidence, context, obligations, fallback paths, or budgets. Ambiguous or unbound
relations do not produce support. This ranking statement applies to the
edge-enabled, edge-disabled, and expansion-disabled arms inside source-bound
mode. Those arms use the same exact, sparse, and wiki seed route. It does not
claim that source-bound mode preserves the legacy graph-channel route. Within
source-bound mode, `expand_one_hop: false` suppresses `RelationshipSupport`; it
does not restore legacy graph scoring or legacy one-hop mutation. This
slice does **not** implement an adaptive
selector or the live v4 runner. It has no benchmark result and no promotion
claim.

## Retrieval-only development run

Run the six existing tasks only as development cases. Freeze ranked candidate
artifacts before mounting evaluation labels. The selector may receive question,
caller scope, source bytes and deterministic adapters. It must not receive
`graph_expected`, acceptable spans, critical facts, oracle paths, or label files.
The evaluator runs in a different invocation after selection has ended. A hash
binds artifacts, but does not itself prove that the earlier process was isolated.

Compare `direct`, `tag_index`, `typed_graph`, `typed_graph_no_edges`, and
`typed_graph_no_expansion`. Preserve the same queries, source snapshots, seed
budgets and final byte budgets for the ablations. Remove the actual edges, not
just an observation counter. Keep S-01 visible individually.

Generate the frozen ranked-candidate artifact with
`scripts/benchmarks/time_to_correct_ranked_candidates_v4.py`. Run it without an
oracle or label mount. It verifies each materialized lane against its source
manifest and emits exactly six questions by five routes. Every run records the
closed seed, budget, edge, and expansion controls. The three typed arms use the
same exact, sparse, and wiki seeds. Only `typed_graph` can append an optional,
whole source-bound relationship target after its parent seed has retained
primary evidence. The generator emits no source bodies and makes no provider,
answer-model, grader, or scoring call. Its output belongs under an ignored
`.inputs` path and binds the clean selector commit.
The artifact also binds the canonical committed question-registry digest. Each
run records its corpus and prompt digest, but never the prompt text. The
evaluator requires the exact registered six-task mapping. It reconstructs each
`SourceSnapshotV4` from the canonical, non-empty source rows and rejects a
claimed snapshot digest that does not match those rows.

`derived_edge_count` records the edges extracted from the source snapshot.
`active_edge_count` records the edges passed to retrieval. The edge-enabled and
expansion-disabled typed arms require both counts to match. The edge-disabled
arm requires `active_edge_count: 0`. Direct and tag-index runs require both
counts to be zero.

The generator accepts one new regular-file output directly under the benchmark
`.inputs` directory. It rejects path traversal, symlinks, other destinations,
non-ignored destinations, and overwrite. It requires a clean selector checkout
before generation and verifies the tracked and untracked status after writing
the ignored artifact.

Candidate budgets: K in 4, 6 and 12. Evidence budgets: 8,192, 16,384 and 24,576
bytes. Report exact serialized model-visible bytes separately from excerpt bytes.
The evaluator's budgeted prefixes are diagnostics, not deployable answer packets;
a prefix that excludes a required candidate is explicitly reported, never used
as a valid answer packet.

Use `scripts/benchmarks/time_to_correct_retrieval_eval_v4.py` after generating the
ranked artifact. Its schemas are strict and its public test fixture demonstrates
all fields. The CLI requires an independently recorded candidate SHA-256:

```sh
python3 scripts/benchmarks/time_to_correct_retrieval_eval_v4.py \
  --candidates /absolute/path/to/frozen-ranked-candidates.json \
  --expected-candidates-sha256 "$PREVIOUSLY_RECORDED_CANDIDATE_SHA256" \
  --labels /absolute/path/to/independently-adjudicated-span-labels.json \
  --output /absolute/path/to/new-retrieval-result.json \
  --k 4 6 12 --byte-budgets 8192 16384 24576
```

Do not calculate the expected hash from an artifact that the evaluator or labeler
has just rewritten. The evaluator refuses overwrite of an existing output file.

### Label conversion and interpretation

The original oracle lists facts and line spans, but does not bind each critical
fact to an acceptable span. Convert line coordinates against the verified frozen
UTF-8 bytes in the independent evaluator lane, not in retrieval. For reproducing
the 19-span diagnostic, use one label group per listed span. Set `critical: null`
until an independent adjudicator establishes a complete critical-group mapping.
Alternative spans for the same supporting obligation belong in one group rather
than inflating the denominator. Retain all source paths and source digests.

Measure overlap recall and single-candidate containment separately. Neither is
semantic fact recall. The supplied evaluator returns semantic recall and NDCG as
null because span intersections do not justify those labels. It reports first
overlapping rank, reciprocal rank, unique source paths, repeated-range byte
fraction, missing required IDs in diagnostic prefixes, and supplied measured
source/time/error counters. It does not invent missing timings or revalidate
source bodies itself. The generating route must independently verify source
bytes and document that verification.

Gate 2 rejects any graph-expected task with lower critical-span recall than the
qualified Direct baseline or with a new source/authority failure. Unknown critical
labels do not pass this gate. A positive graph claim additionally requires a
useful difference from edge removal on predeclared relationship fixtures and
held-out tasks. Equal edge-enabled/disabled output is not proof of graph value.
The evaluator emits the explicit `velgraphing-gate-2-v1` decision at the
registered point K=12 and 24,576 bytes. It reports per-task edge-enabled versus
edge-disabled recall deltas. A safety pass can still report
`positive_graph_value: false` when no useful edge difference exists.

## Candidate labels and replay

Label relevance, direct usable evidence, facet contribution, contradiction, and
source-instruction risk outside all model inputs. Preserve `unknown` and labeler
disagreement. Do not derive semantic labels just from overlapping byte ranges.
Existing v3 observations can evaluate `evidence-usefulness-v1` only when the exact
request and source binding are available. A changed state, rubric, model or
question invalidates that replay. The public source-free score summaries are not
complete replay envelopes for new packets.

No held-out reliability measurement exists in this handoff. Confidence is not
called calibrated. An atomic rubric is a research proposal in the canonical
report, not a new supported transport contract or an activated routing policy.

## Conditional two-task canary

Tasks: **C-02 and M-01**. C-02 preserves a known passing Graph/off development
control. M-01 exercises non-code, authority-sensitive evidence. It is also a
useful skeptical control: its oracle support is concentrated in a single FAQ,
so a typed graph must earn its overhead rather than rely on the graph-expected
label. L-01 is held back until its question/rubric alignment is adjudicated.

Design: four arms, one trial per task/arm, eight answer lanes and eight independent
grader lanes. This is a rejection canary, not a stochastic performance claim.
Counterbalance task/arm launch order and blind answer/grader model-visible
identities to arm labels in a separately versioned host envelope. Retain those
identities only in controller receipts.

Provisional exact caps, to be frozen at the material candidate:

| Budget | Cap |
|---|---:|
| Seed candidates before deterministic expansion | 6 |
| Final pre-Jev shortlist candidates | 12 |
| Excerpt bytes per candidate | 2,048 |
| Aggregate pre-Jev excerpt bytes | 24,576 |
| Serialized TypeSafe request bytes | 131,072 |
| Final answer excerpt bytes | 16,384 |
| Graph expansion steps | 1 |
| Additional caller-allowlisted fallback pass | 1, within the same 12-candidate/24,576-byte shortlist caps |
| Live Jev requests | **at most 4**, B and D on each task |
| Jev retries / second-state judgments | **0 / 0** |
| Answer calls / independent grader calls | **8 / 8** |
| Answer repairs or model retries | **0** |
| Provider timeout per call | 10 seconds |
| Answer timeout per lane | 180 seconds |
| Grader timeout per lane | 120 seconds |
| Total controller wall deadline per trial | 600 seconds, including approval |

Pin `jev-1.13.0`, record the resolved model, and initially retain the existing
`evidence-usefulness-v1` rubric. A changed atomic rubric requires its own offline
label qualification before a new canary freeze. Pin the same native answer and
grader model/reasoning as the retained control only if the host can actually
provide them; otherwise stop and register a new comparison, never silently
substitute a model. The requested control is `gpt-5.6-sol`, medium reasoning.

These are count, byte and deadline caps, not token or dollar guarantees. The
native host does not currently expose validated answer/grader token budgets in
the audited path. Record token usage as null unless genuine host receipts expose
it. Do not infer tokens from byte counts. Total cost therefore remains unknown
until usage and applicable prices are available.

Pair A/B and C/D at the **pre-Jev shortlist**. Final packets may differ after
explicit budgeted selection; this is the intended successor treatment. Required
candidate IDs are caller/source-derived, always included and position-locked;
Jev never invents or removes them. Missing required content or insufficient budget
means bounded fallback or defer, not truncation or an optimistic sufficiency flag.
Provider failure restores the verified baseline selection, with a fresh source
check before answer. A source failure never licenses answering from stale bytes.

### Approval readiness checklist

There is no approval-ready request packet in this handoff. All four exact provider
request hashes are currently null. Only after all of the following may the local
Parent request fresh operator approval for the four exact previewed requests:

1. Gate 1 typed-edge/source/allowlist/staleness fixtures and observable edge-removal proof pass.
2. Gate 2 six-task critical-label retrieval evaluation passes, S-01 separately reported.
3. Gate 3 exact-rubric candidate labels/replay qualify the intended use, or the canary is explicitly limited to exploratory judgment collection rather than promotion.
4. Canonical tests, consumers, full suite, two-pass projection and source-package parity pass at one final commit.
5. Candidate/source/rubric/model bindings and all four preview hashes are frozen.

A no-op request is skipped and its quota is not reassigned. No live provider,
answer or grader execution is performed by the files in this handoff.

## Held-out confirmation

Register at least two untouched questions in each of five strata: cross-file code
API/dependency behavior, many-small-file exact lookup, cross-document synthesis,
long single-document/book hierarchy, and mixed-authority policy interpretation.
Keep held-out oracle and candidate labels inaccessible during development. Do not
reuse these six development tasks to claim generalization.

A planning baseline is ten tasks, four arms and three paired repetitions:
120 answer lanes, 120 grader lanes, and at most 60 Jev calls. This is **not an
approved budget** and is not launched by this protocol. Estimate variability from
the canary/host measurements before freezing an adequately powered sample size;
three repetitions alone do not guarantee sufficient power.

Counterbalance order, retain all failures and censored deadlines, report
per-stratum quality and latency distributions, and separate cold and warm modes.
Preserve the original all-registered-trials pass requirement for reporting an
arm-level mean TTC, or preregister any additional estimator with a different name.
Report user-visible answer availability and independent validation completion as
separate timestamps, plus approval, queue, provider, retrieval, expansion, fallback,
answer and grader intervals. Do not add overlapping phase durations as wall time.
