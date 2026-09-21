# Four-arm end-to-end protocol

## Historical frozen matrix

Tasks are S-01 exact lookup, D-01 relational dependency and duplicate behavior,
L-01 synthesis, and M-02 heterogeneous documents. Arms are:

| Arm | Retrieval | Jev |
| --- | --- | --- |
| A | Direct | Off |
| B | Direct | On |
| C | Graph | Off |
| D | Graph | On |

The dispatch order uses a balanced arm rotation and is fixed in `freeze.json`.
Each dispatch uses one fresh answer lane and one fresh grader lane. Lane reuse
and inherited conversation history are forbidden.

The sealed labels above remain historical. Successor metadata uses the precise
comparison contract:

| Arm | Successor comparison role | Jev |
| --- | --- | --- |
| A | Edge-disabled frozen-shortlist baseline | Off |
| B | Edge-disabled frozen-shortlist baseline | On |
| C | Relationship-enabled frozen-shortlist arm | Off |
| D | Relationship-enabled frozen-shortlist arm | On |

## Evidence and treatment boundaries

All corpus sources are public and pinned by commit, manifest, and snapshot
digest. Direct and Graph use the same source authority and caller-allowlisted
exact-source fallback. Graph can add only source-verified relationship context.
Jev can reorder only the frozen verified shortlist. It cannot add evidence,
remove required evidence, recover evidence excluded before pool creation, or
grant authority. In D-01, the relationship-enabled pool added source-verified
imported-dependency context; Jev recovered that evidence after baseline final
selection omitted it.

Answer lanes receive only the question, answer instructions, selected source
evidence, and the answer response contract. They do not receive rubrics,
oracles, treatment labels, arm names, route names, provider metadata, or scores.
Successor graders receive only the answer, the required-fact rubric, the
answer evidence-ID-to-source-path map, and the grader response contract. They
return one decision per required fact. They do not receive the question,
source bodies, treatment labels, arm names, route names, or provider metadata.

The L-01 Kafka and batch-ID fact is diagnostic. It is not required. D-01
requires a duplicate-specific fact. Its base-case fact is diagnostic because
the public question does not ask for it. C-02 is absent.

The successor rubric accepts any M-02 process-documentation choice supported
by cited Small Company Playbook evidence. L-01, M-02, and S-01 citation checks
resolve cited evidence IDs through the supplied source-path map. The sealed
historical rubric remains unchanged.

The successor overlay is offline only. The sealed historical bundle can be
validated and inspected, but it cannot prepare, qualify, freeze lanes, or run
through the current controller. A new successor freeze and fresh lane manifest
must bind the current controller, host, rubric, and grader contract before any
execution command is eligible.

The successor TTC contract adds a deterministic pre-answer source-completeness
check. It uses only selected evidence identities and a frozen private fact-witness
map. The map is a benchmark diagnostic. It is not a production routing input.
Each required fact is satisfied only when all of its frozen witness IDs are in
the selected context.

The concrete witness map, candidate identities, source paths, and byte ranges
live only in the ignored canonical witness-custody artifact. Successor validation,
lane freeze, and execution require its explicit path. The tracked contract binds
the canonical custody hash, witness-map hash, and fallback-allowlist hash. A
missing, redirected, symlinked, noncanonical, or changed custody artifact fails
closed.

If a witness is missing, every arm uses the same exact-source allowlist and the
same frozen task snapshot. The controller can append the missing allowlisted
spans once. The final evidence context must not exceed 16,384 bytes. An unresolved
witness, changed source identity, or oversized context stops the trial before
answer dispatch. The answer receives only the normal question, evidence, and
citation instruction. The independent grader receives the evidence-ID-to-path
map and returns one decision for each required fact.

This study and its sealed result are `oracle_assisted_fallback_ttc`. The result
can describe TTC only under this frozen oracle-assisted fallback contract. It
cannot support Direct, Graph, Jev, or comparative retrieval-performance claims.

Historical and successor validation are separate commands. `validate` reports
the historical scope. `validate-successor-overlay` reports the offline
successor scope and its bound implementation identities.

## Jev budget and skip rule

There are at most eight Jev calls, one for each B and D dispatch. There are no
retries. A Jev dispatch can be skipped only when the offline
`select_ranked_context` preflight records
`jev_call_could_affect_selection: false`. A provider failure consumes the call
and preserves baseline shortlist order.

The phase-2 prepare command recomputed that proof from each frozen pool and
source snapshot through `select_ranked_context`. Every B and D pool can change
final membership, so all eight calls remain planned and no skip is frozen. A
future stale or changed pool must fail closed. A reason string or
caller-supplied digest is not proof.

## Phase-2 pool freeze

The prepare command uses the current merged product seams. The shipped
Git-tracked scanner verifies each manifest lane. The relation seam derives only
source-witnessed edges. Direct retrieval runs without graph expansion. Graph
retrieval runs with source-bound expansion. Both routes use the same snapshot,
prompt, retrieval node limit, candidate limits, and final context limit.

Each pool permits at most 64 candidates, 32,768 aggregate excerpt bytes, and
4,096 bytes per candidate. Final context is limited to 16,384 bytes. The
tracked preflight records source-free identities and eligibility summaries.
Candidate paths, ranges, excerpts, selected context, and Jev request bodies
remain in the ignored local artifact.

D-01 has one verified import relationship candidate from the caller module to
the imported dependency implementation. L-01 has one verified document-heading
relationship candidate. S-01 and M-02 have no supported relationship delta for
these prompts and frozen sources. Their Graph candidate sets equal their Direct
candidate sets. This is an observed product result, not a benchmark quality or
performance conclusion.

## Timing and usage

The controller must record complete user-visible wall time and wall time with
operator approval removed. It must separately record discovery, graph build,
graph load, source capture, provider, selection and context composition,
answer, grading, operator approval, and fallback or repair time.

The result must record accepted correctness, first-pass correctness, request
bytes, context bytes, and answer, grader, and provider input, output, and cache
usage where the host reports them. Provider cost is recorded only when the
provider reports it. Every unavailable value is null with an explicit
missingness reason and failure class. Source bytes are never converted into
token estimates.

Each successor result also binds the current controller and host, successor
rubric and grader contract, source snapshots, pool hashes, verifier and fallback
hashes, custody hash, request-byte set, and lane manifest. It records attempt,
answer, grader, and verified-fallback counts. The fallback interval measures the
actual verifier on every successor trial and includes any exact-span append.
`fallback_invocations` remains zero for verification-only work and one when the
allowlist appends evidence. The result records wall time, confirmed TTC, and
explicit usage missingness. One answer call and one independent grader call are
allowed per dispatch. Answer repair is forbidden.

## Phase-3a stop boundary

Phase 3a provides a thin serial adapter over the phase-2 pools. It uses the
current public selection API, canonical answer and grader handoff, terminal
receipts, resumable custody, the eight-call ledger, and a private result seal.
Fixture qualification covered all four treatment shapes, restart, baseline
fallback, telemetry, and zero external calls. It did not import or run the
historical T030 continuation controller.

T300 froze 16 fresh Luna answer thread IDs, 16 fresh Astra grader thread IDs,
all 32 exact host argv arrays, the absolute Python executable, and the R6
manifest hash. Parent sends each exact request inline. Parent retains each raw
assistant response, validates its identity and role contract, and serializes an
equivalent canonical lane draft before the existing attestation flow. Parent
must retain the exact
request-byte set, eight-call cap, total USD reservation, manifest hash, and
Python executable. No lane or provider call is authorized by this package.

Provider performance details remain private unless separate provider permission
authorizes publication. This restriction applies to future results as well as
provider-specific timing, quality, token, and cost comparisons.

## Private host-attested execution boundary

The strict controller R8 through R10 transport did not complete. The answer
model returned an empty response once and malformed identity-envelope JSON
twice. No provider call occurred in those attempts. The tracked successor
contract is pending and does not bind an abandoned lane manifest.

An operator-authorized private diagnostic then completed the eight approved
provider calls, 16 fresh answer calls, and 16 fresh blind grader calls. It used
the same frozen pools, custody, exact source checks, selection policy, models,
call cap, and no-retry rule. The model returned semantic content only. Parent
recorded task identity and turn duration. The private result measures a sum of
selection, provider, answer-turn, and grader-turn intervals. It does not measure
queue time or complete user-visible wall time. Answer-model and grader-model
token usage were unavailable.

The diagnostic also exposed a grading limit. The frozen grader sees rubric
facts and an evidence-ID-to-path map, but it does not see source bodies. It can
score required facts and citation paths. It cannot reliably decide whether an
extra cited claim is supported by source text. A fact-only diagnostic may show
this difference, but it must not replace the frozen acceptance result.

The private source-aware regrade preserves the original result and reuses its
retained answers. Each fresh grader receives the answer, frozen rubric, and
only the exact source records cited by that answer. It receives no question,
arm, route, provider observation, or treatment metadata. Parent retains the
exact grader request, raw response, parsed response, thread identity, and
duration. This regrade can diagnose correctness. It cannot repair or complete
the original timing and model-usage measurements.
