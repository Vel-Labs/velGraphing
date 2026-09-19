# Time-to-correct v4: qualification protocol, not an executed benchmark

Status: **T030 has positive isolated edge-retrieval evidence and a frozen
offline dependency-canary Jev preview. Parent review is the next gate. No live
call is authorized.**
Historical PR9 source candidate: `6931f0ffa72bd27f79f5515bd669404dbc4667d0`.
No semantic answer correctness, time, token, Jev, promotion, or product result
is asserted.

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

The frozen artifact uses the incompatible
`velgraphing-ranked-candidates-v4-bound-v2` schema. The incompatible v1
artifact remains historical and is not a valid input to a fresh study. Each candidate has exactly
`id`, `path`, `source_sha256`, `byte_start`, `byte_end`, `required`,
`record_id`, and `relationship_parent_candidate_id`. The candidate ID is the
bare 64-character lowercase SHA-256 of its canonical coordinate object. It has
no prefix, so the same exact ID is valid in the existing Jev packet contract.
The artifact hash binds the record and relationship metadata. Each primary
candidate names the exact authenticated source record
for its path and digest and has a null parent. Only a `typed_graph`
relationship target can have a parent. It names the retained earlier primary
candidate ID, uses `RelationshipSupport.target_record_id`, and is optional.
The generator rejects missing or mismatched Graph records before it writes the
artifact. The evaluator rejects the old schema, extra fields, inconsistent
record bindings, and self, missing, late, required, or chained relationship
targets before it reads labels. It does not read source bodies.
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

Each control row records `candidate_limit`,
`candidate_aggregate_byte_budget`, and `candidate_unit_byte_budget`. The
evaluator requires identical values across every route and rejects values above
the TypeSafe hard limits. `seed_limit` remains the retrieval-node limit. It is
not a candidate-pool budget.

## Registered T030 successor freezes

The historical six-task production study and its candidate artifact remain
unchanged. Four successor oracle-blind study identities use the same bound-v2
schema:

- `velgraphing-v4-six-task-high-recall-v1` uses the existing tracked six-task
  question registry. Every route binds a preselection ceiling of 64 candidates,
  32,768 aggregate excerpt bytes, and 4,096 bytes per candidate. This is a
  high-recall pool. It does not increase the later 16,384-byte serialized answer
  selection budget.
- `velgraphing-v4-relational-canary-v1` uses the tracked registry at
  `relational-canary-questions.json`. Its only task is `R-01` on the Engineering
  Handbook with prompt `What belongs in content/dsa/editorials versus
  content/dsa/patterns?`. The registry SHA-256 is
  `14e6ded1ecc1248109db9c1bda7c432278fdb5427e1c0f402850bc370594ccc3`.
  The prompt does not contain the target heading identifier. The generator
  requires the unique source-derived `links_to_heading` edge from
  `README.md` bytes 6504-6542 to `STYLE_GUIDE.md` bytes 13402-13425. Only the
  edge-enabled typed route may emit its optional relationship candidate. This
  study is retained as rejected historical evidence because its freeze emitted
  no relationship candidate. It is not candidate-addition proof.
- `velgraphing-v4-thealgorithms-import-canary-v1` uses the tracked registry at
  `thealgorithms-import-canary-questions.json`. Its only task is `I-01` on the
  frozen TheAlgorithms snapshot with prompt `How does the benchmark_sorts module
  prepare timing cases?`. The registry SHA-256 is
  `f5ed4f7a2f5cda04ff55c91cb5226ea4e81cf763eb3c48418adb82a6eb5eba95`.
  The prompt does not name `quick_sort`. The generator requires 16 derived
  edges and the unique source-bound `imports` edge from
  `repo:sorts/benchmark_sorts.py` bytes 1246-1256 to
  `repo:sorts/quick_sort.py` bytes 253-1296. Every route binds 64 candidates,
  32,768 aggregate excerpt bytes, and 4,096 bytes per candidate. Its independent
  post-freeze span labels gave every route identical acceptable and critical
  overlap. It is retained as mechanics-only evidence and rejected for positive
  graph value.
- `velgraphing-v4-thealgorithms-dependency-behavior-canary-v1` uses the tracked
  registry at `thealgorithms-dependency-behavior-canary-questions.json`. Its
  only task is `D-01` on the frozen TheAlgorithms snapshot. The registry
  SHA-256 is
  `a6006da0d7b2787a7fbb17e6f5a3f54d5a6409b170962c86e28f44b5bfa47897`.
  The prompt identifies the dependency by its import position after
  `merge_sort`; it does not name `quick_sort`. The generator requires the same
  16 derived edges and exact source-bound `imports` edge. Every route binds 64
  candidates, 32,768 aggregate excerpt bytes, and 4,096 bytes per candidate.

The evaluator accepts these identities only with their exact question hashes,
five-route matrices, controls, source snapshots, and typed-primary invariants.
The active dependency-behavior canary requires 16 derived edges, one typed
relationship candidate, no relationship candidates in the four controls,
exact control candidate identity, and source and target candidate ranges that
contain the registered coordinates. The typed route may displace exactly one
optional control candidate when its relationship child fills the 64-candidate
ceiling. It must preserve every required candidate. Unit fixtures test behavior
but do not register benchmark authority.

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

## Current retrieVEL dependency preview

The offline dependency-canary Jev preview is frozen at adapter commit
`51e2dc70916ecdbe9f90fff8d5a44a4b5f22c714`. It contains exactly D-01/B/direct
and D-01/D/typed_graph. Both source-bound pre-Jev pools passed fresh candidate,
registry, manifest, snapshot, source-byte, relationship, and request validation.
Both baseline decisions report that a Jev order could change final membership.
The requests use at most 64 candidates, 32,768 aggregate excerpt bytes, 4,096
bytes per candidate, 131,072 serialized request bytes, and a 16,384-byte final
answer selection budget. The tracked source-free plan permits at most two Jev
calls and zero retries, but records `live_authorized: false` and zero executed
provider calls.

The source-bearing preview and exact request bindings remain under the ignored
`.inputs` boundary. The answer subprocess receives only the question,
instructions, and normalized `id`, `path`, and `excerpt` evidence. The grader
receives only the answer and required, critical, and acceptable-span rubric
lists. The controller retains all identity, hash, treatment, score, relation,
ledger, provider, and receipt metadata outside both model payloads. This preview does not qualify model
usefulness or authorize a provider, answer, or grader call. Parent review is the
next gate. The historical PR9 candidate, preview, request hashes, four-call
plan, and approval-readiness record below remain non-applicable to retrieVEL.

### D-01 four-arm controller candidate

`scripts/benchmarks/time_to_correct_dependency_v4.py` is the exact D-01
controller candidate. A/B independently regenerate and verify the same Direct
pool. C/D independently regenerate and verify the same typed-graph pool.
Generation uses the current scanner and retrieval path; loading the frozen
candidate artifact is identity validation, not retrieval timing. Each observed
trial uses the existing monotonic `Trial`, zero repairs, the two-call Jev ledger,
the existing Jev prepare/evaluate boundary, the ranked-context selector, and the
allowlisted answer/grader subprocess boundary.

The controller records cold graph construction, candidate discovery, retrieval
including expansion, Jev preparation, provider execution, source revalidation,
response validation, fallback, context composition, answer generation, and
independent grading. The root trial interval remains the all-in wall clock.
Returned provider and model usage is retained. Unavailable tokens or cost stay
null. Selected spans are normalized to the same treatment-free answer evidence
schema for all four arms.

The source-only preflight regenerated all four pools from the pinned lane. A/B
matched at pool SHA-256
`3c4a9ea12b9f6d49dfe14b791dbe465d72a7948fad95144059ebe55b9a1a71e2`.
C/D matched at pool SHA-256
`efa862132c59426bd823aa86e15eebfc43a1aa01923f28aa4a8536be7c1e6c58`.
Both frozen request hashes matched, and B/D both remained selection-sensitive.
The tracked v2 plan binds these pools, the candidate, registry, selector,
snapshot, preview, models, rubrics, requests, caps, and zero-retry policy.

Observed execution is fail-closed while `live_authorized` is false. No provider,
answer-model, or grader-model call ran. The remaining gate is Parent approval of
an explicit tracked plan change to live authorization and the exact local answer
and grader lane commands. This candidate is not a benchmark result.

## Historical PR9 offline Jev preview freeze

The plan in this section is retained as historical PR9 data. It is not the
current retrieVEL plan and is not authority for a live call.

After the bound candidate artifact is committed and frozen, use
`scripts/benchmarks/time_to_correct_jev_v4.py` to prepare exactly four local
records in this order: C-02/B/direct, C-02/D/typed_graph, M-01/B/direct, and
M-01/D/typed_graph. The adapter revalidates the candidate artifact hash, strict
schema, registered questions, route controls, manifests, Graph records, source
snapshots, and source bytes. It uses the direct Graph for B and the edge-enabled
typed Graph for D. It converts the bound rows without ID remapping.

Each record calls only `jev.prepare` with `jev-1.13.0` and the canonical
`evidence-usefulness-v1` question contract. It then calls
`select_ranked_context` with no Jev observation and a 16,384-byte serialized
selection budget. The result must remain baseline ordered, source revalidated,
non-fail-closed, and preserve every required candidate. The shortlist remains
within 12 candidates and 24,576 excerpt bytes. The prepared request remains
within 131,072 bytes.

The adapter writes one exclusive canonical source-bearing artifact directly
under the ignored v4 `.inputs` directory. It includes the full candidate packet,
the exact ordered bound rows with record and relationship metadata, the full
prepared request, verified lane identity, baseline selection, and a source-free
index of hashes, byte counts, relationship counts, and selected IDs. Validation
requires the externally supplied candidate artifact hash plus the exact selector
and adapter commits, and always requires the registered production question
registry hash. It records
`provider_calls: 0` and `model_usefulness_qualified: false`. Preview generation
does not call `jev.evaluate`, read a key, use a transport, access labels, or
qualify Gate 3. Without an exact real replay, a future canary remains
exploratory.

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
| Excerpt bytes per candidate | 4,096 |
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

### Historical PR9 approval-readiness record

The frozen local plan was approval-ready for PR9 operator review. It is not
applicable to retrieVEL and is not live authorized. Historical approval
readiness means only that the exact request bytes, hashes, source bindings,
model, rubric, and four-call cap were frozen. It does not qualify Jev usefulness
or authorize a provider, answer, or grader call.

The ignored source-bearing preview is `.inputs/jev-v4-preview-06db3f1.json`, SHA-256
`0005d6c26523ab2da431eb5172f89f1aa077ce28d4c1b55ca1a10cd6ab71d6a9`.
The four provider request bindings are:

| Trial | Request SHA-256 |
|---|---|
| B-C-02 | `f0e48067a35d38e88b06c136e8aea7285af239e9a876deb65e23ab9ebf6026bf` |
| D-C-02 | `cb88c899dc6b2752aff978eac7b568da2f740c461d4969d282a2a2431de64ad9` |
| B-M-01 | `55a5fdcb9c20dd26fb90fec7896aab857acd14b709ae6e8a6949ccf3a496d8e7` |
| D-M-01 | `a2d81d30d5af32d0b0041fdba1e1abbc6dc173ac7056e3b2c9e63af7ce1ee16f` |

The historical PR9 Parent could request fresh operator approval only after
confirming:

1. Gate 1 typed-edge/source/allowlist/staleness fixtures and observable edge-removal proof pass.
2. Gate 2 six-task critical-label retrieval evaluation passes, S-01 separately reported.
3. Gate 3 remains explicitly limited to exploratory judgment collection. These four requests cannot support promotion.
4. Canonical tests, consumers, full suite, two-pass projection and source-package parity pass at one final commit.
5. Candidate/source/rubric/model bindings and all four request hashes match the frozen plan and preview artifact.

The historical tracked plan keeps `live_authorized=false`,
`promotion_eligible=false`, and
the hard provider cap at four. A no-op request is skipped and its quota is not
reassigned. No live provider, answer or grader execution is performed by these
files.

### Final repository validation receipt

Candidate `e3af84719b87896d56640d8210c0f426f7b760bf` was checked in the fresh
detached `$VALIDATION_WORKTREE`. `$VENV_PYTHON` was the existing project virtual
environment's Python executable. The six suite commands below are the exact
sequence in `package.json`'s `npm test` script.

Commands:

```text
cd "$VALIDATION_WORKTREE"
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" scripts/package/project_portable_plugin.py
git status --porcelain=v1 --untracked-files=all
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" scripts/package/project_portable_plugin.py
git status --porcelain=v1 --untracked-files=all
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" scripts/package/verify_source_package_parity.py
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" -m unittest discover -s tests/scaffold
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" -m unittest discover -s tests/core
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" -m unittest discover -s tests/adapters
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" -m unittest discover -s tests/skills
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" -m unittest discover -s tests/benchmarks
PYTHONDONTWRITEBYTECODE=1 "$VENV_PYTHON" -m unittest discover -s tests/parity
```

Results: both projector passes exited zero and left the worktree clean. Package
parity returned `{"candidate_sha256":"0e17875d87498c04016df2c8de28d3d8dc3a4ee61e7fbec60c0826bfb0bcf4d1","files":87}`.
The six suites ran 11, 249, 18, 34, 128 and 10 tests. Total: 450 run,
449 passed, one expected skip in `tests/benchmarks`, and zero failures or errors.
The final `git status --short` output was empty. This receipt covers repository
validation only. It does not authorize a live call or qualify Gate 3 promotion.

Structural binding candidate `f806ee83885a9c6917992c91fd70e6a56229c67b`
was checked in a separate fresh detached worktree. JSON validation passed, all
six focused Jev-v4 preview and canary-plan tests passed, `git diff --check`
passed, and package parity returned the same 87-file candidate SHA-256
`0e17875d87498c04016df2c8de28d3d8dc3a4ee61e7fbec60c0826bfb0bcf4d1`.
The worktree remained clean. This protocol-only receipt does not invalidate the
product, package, or structural checks because no runtime-consumed file changed.

This receipt supersedes the pre-successor Gate 1 and Gate 2 status in
`docs/reviews/velgraphing-pr9-frontier-audit-2026-09-18/report.md`. It does not
rewrite that historical PR9 audit.

Gate 1 passed on the final validated candidate. The source-bound relationship
implementation is commits `f98d38b808bf983cde29c9e5f846c31a9b0e2fc0`,
`e6bfa4d916cc1a916e824f8bdef85f6d220c6c29`, and
`f16aa09949ddfec5c264556706c6c476ff4a70dd`. The full-suite pass includes the
source-coordinate, ambiguous/unsupported relation, package-valid import,
allowlist, stale-source, and authenticated-record fixtures. It also includes
`test_typed_routes_keep_primary_seeds_and_only_enabled_adds_support`, which
holds seeds constant and proves that disabling edges removes relationship
support, and `test_zero_edge_fixture_keeps_all_typed_candidates_identical`.

Gate 2 passed at `k=12` and a 24,576-byte shortlist budget. The frozen labels
SHA-256 is `37a2050454c0359eefbe47e3d9420df4b11318a01aae40921610e65b63ef8ca2`.
The candidate artifact SHA-256 is
`d147df356e72aa6588d0840ea32940b6db5d5dae975acf2b218e3d4cfc697ae9`.
The source-free retrieval result SHA-256 is
`7e0cd1b9e9582f4e087992fa8f7c40450454c0aa0373ea475bab97b048fa83a5`.
Its decision is `pass`. S-01 is the only task with a positive edge-enabled
critical and acceptable overlap-recall delta, both `1.0`. C-01, C-02, L-01,
M-01, and M-02 each have delta `0.0`. This limited result does not establish a
general graph advantage.

The historical PR9 preview artifact and four request hashes are frozen above.
They are non-applicable to retrieVEL and grant no live-call authority. Its artifact
SHA-256 is `0005d6c26523ab2da431eb5172f89f1aa077ce28d4c1b55ca1a10cd6ab71d6a9`.
The retained v3 result seal is
`916c5e766b9152df5dac21b3cf3fec0116002dfee8d4f6c68eec9885bf94fd96`.
Remaining historical PR9 risks are unchanged: Gate 3 is exploratory only, and
usefulness and promotion are not qualified. Current retrieVEL work returns to
the offline dependency-canary Jev preview gate above.

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
