# VelGraphing adversarial audit: time-to-correct

Audit date: 2026-09-17 (America/Chicago). Audited base:
`916c3c993dcb214c2700dbec063794dba418bdd8`.
Work branch: `codex/velgraphing-time-to-correct-audit-repair`.

## Verdict and evidence boundary

**Do not promote either a Jev speedup or a graph-topology benefit from the six-task
pilot. Repair measurement before changing product selection.** The saved results
support a narrow ordering experiment with mixed rubric scores, not a general
quality regression, an all-in cost result, or a time-to-correct result.

The current public graph-find route constructs file records without edges. It
can test source indexing/ranking, but does not exercise the relationship traversal
hypothesis. Jev runs after discovery and exact capture. Reordering retained
candidates cannot undo that work or reduce their membership. It might still
improve first-pass answers or reduce subsequent repairs; the pilot did not measure
those effects repeatedly or record the necessary end-to-end timings.

This was a read-only source audit before implementing the benchmark repair.
Reviewed: the repository entry guides; all six command skills; the graph-find
adapter; canonical Jev, retrieval, selection and V5 navigation paths; pilot
preparation, questions, oracle, freeze and retained results; tests; projection
contract; and historical result boundaries. This is a caller/measurement audit,
not a claim to have executed every legacy or experimental product path.
No ignored inputs, private corpus checkout, credentials or live provider were
accessed. Retained grades were inspected, not independently regraded from raw
answers. The original local network clone failed on DNS. GitHub reads established
the exact base. The repair was later validated in an isolated worktree and by the
pull-request workflow. The original staging directory is not represented as the
operator's checkout.

## 1. Findings ordered by severity

Source links in this section are pinned to the audited base, not the repair.

### F01 / P1 / Benchmark-harness defect: no owner measures the full task

The pilot preparation script emits lane instructions and a requested telemetry
shape. It is not a dispatcher with a root stopwatch, answer-completion events,
independent grading events or a repair loop. A requested field is not an observed
measurement. The retained result explicitly leaves answer time, total wall time,
answer-model usage and cost unknown. One phase-local duration cannot fill them.

Evidence: [packet generation and instructions](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/scripts/benchmarks/velgraphing_corpus_pilot_v1.py#L276-L430),
[parent ownership expressed only as skill instructions](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/plugins/graph-engineering/skills/graph-benchmark/SKILL.md#L10-L30),
[retained unknowns and receipt boundary](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/result.json#L1580-L1665).

Resolution: a benchmark-owned monotonic controller now records acceptance,
attempts, answer dispatch/completion, independent grading, repairs and first pass.
A separate process boundary now accepts caller-supplied answer and grader commands
as argv arrays. It exchanges canonical JSON without a shell and bounds each child
process by the remaining trial deadline. The caller still supplies preparation.
This offline qualification is not a native Codex deployment and does not
reconstruct historical wall time.

### F02 / P1 / Integration defect in the experiment: topology and warm reuse are not exercised

The shipped CLI scans tracked files and returns `Graph(records)`. The Graph type
has an empty default edge tuple. The core can traverse supplied edges, but this
caller supplies none. It also rebuilds its scan and index per invocation; it does
not load a project graph created by graph-start or a persisted warm index.

Evidence: [scan and Graph construction](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/plugins/graph-engineering/skills/graph-find/scripts/graph_find.py#L219-L310),
[Graph edge default](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/packages/core/models.py#L116-L152),
[index rebuild and retrieval](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/packages/core/retrieval.py#L880-L982),
[edge traversal consumes the supplied edges](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/packages/core/retrieval.py#L1100-L1160).

Resolution: actual graph-path instrumentation records edge/record counts and cold
work, while marking warm load not applicable. No topology or caching redesign was
made. Before a topology claim, demonstrate nonempty source-bound edges actually
consumed and compare against the same retrieval path with edges removed.

### F03 / P1 / Integration limitation: Jev is too late to reduce discovery in this pilot

The frozen sequence is discover, capture, preview, parent Jev call, then revalidate
and answer. The evaluator preserves membership and locks required positions.
There is no mechanism here to retroactively avoid discovery, reduce the retained
source set, or suppress the already performed capture/preview work.

Evidence: [frozen Jev phases](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/freeze.json#L120-L210),
[evaluator and stable optional permutation](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/packages/core/jev.py#L330-L425).

Resolution: classify the benefit correctly, not change the product to manufacture
one. Pure ordering is not necessarily a *net latency loss*: generation length,
first-pass quality or repairs can change. But an upstream-read or membership-based
context saving is impossible in this particular sequence. A budgeted/streamed
reader or task-aware selection policy is a separate proposed experiment.

### F04 / P1 / Benchmark-harness defect: timing boundaries and attribution are inconsistent

Jev's `elapsed_ms` encloses preparation, response acquisition, response validation,
source revalidation and sorting. It is not provider-only latency. It excludes
preceding capture/preview, approval and the answering agent. Some result rows
repeat the same retrieval number in two phases. Summing those numbers or adding
the Jev envelope to all its child stages would double count.

Evidence: [evaluator clock boundary](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/packages/core/jev.py#L330-L425),
[duplicated phase telemetry and unknown all-in fields](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/result.json#L1080-L1420).

Resolution: one controller clock, nested span identities, inclusive interval unions,
separate waits and unattributed gaps. Isolated Jev qualification splits real
prepare/parse/revalidation code without modifying production. Replay has no
provider interval; a local response-copy fixture is labeled fixture, never live.

### F05 / P2 / Rubric defect: a compound, implicit detail creates a threshold cliff

L-01 asks for a cross-chapter explanation centered on read-path scaling, traffic,
caches and stateless scaling. One of five points bundles two additional design
mechanisms. These mechanisms can be relevant, but the question does not explicitly
request both. A half-point difference crosses the fixed 90% pass threshold.

Evidence: [L-01 question](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/corpus/questions.json#L20-L30),
[oracle and compound facts](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/corpus/oracle.json#L60-L100).

Resolution: preserve the sealed result and its gate. Before successor trials,
review question-to-fact alignment, make requested dimensions explicit and score
atomic facts independently. Report continuous fact recall and critical-fact
coverage alongside pass/fail. Do not remove the inconvenient point post hoc or
quietly lower the threshold to favor Jev.

### F06 / P2 / Inconclusive evidence: the ordering explanation is not causally established

Only one repetition per task/arm is retained. Dispatch is fixed A/B/C/D within
each task. Six of twelve Jev calls changed order. Saved rows contain opaque order
IDs, but not the complete rank-to-source-span-to-rubric mapping and original answers
needed to independently identify the omitted detail's position. The result records
parent-supplied grades; this audit did not read forbidden ignored artifacts to fill
that gap. A lower score following a changed order is not a causal explanation.

Evidence: [dispatch and grading contract](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/freeze.json#L100-L210),
[order-change summary and evidence boundary](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/result.json#L1500-L1665).

Resolution: proposed paired, counterbalanced repetitions with a frozen rubric and
privacy-safe candidate/span hashes. Keep raw answers and source mapping only in
an authorized private evidence store. The new trace does not manufacture a
historical source-position explanation.

### F07 / P2 / Benchmark-harness defect: source, context and token counters describe different things

Graph-find emits a body-free result while retaining an internal `context_bytes`
value. It is not the byte length of the actual serialized tool output or entire
model request. File scan bytes, repeated in-memory verification, exact source
reads and repeated model exposures must be distinct. In another helper, the byte
counter sums payloads but not the separators used when joining them.

Evidence: [body-free result serialization](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/packages/core/retrieval.py#L377-L417),
[context join accounting](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/packages/core/retrieval.py#L1370-L1441),
[scan and in-memory reader](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/plugins/graph-engineering/skills/graph-find/scripts/graph_find.py#L193-L310).

Resolution: record actual delivered UTF-8 bytes/hashes at the host boundary and
logical source-read receipts separately. Missing answer-model usage keeps net token
and cost claims unknown. The reported 50,834 Jev-side tokens are real retained
provider accounting, **not a measured 50,834-token net increase across all models**.
The latent helper counter semantics are not silently changed in this repair.

### F08 / P2 / Benchmark-harness defect: answer correctness does not clear process warnings

The result retains a graph scan of a README disallowed by lane instructions,
several capture/command errors, and a fallback adding an explicitly requested
chapter missing from the graph shortlist. Correctly supported final answers do
not erase those process issues or their unmeasured recovery costs.

Evidence: [recorded warnings, fallback and read counts](https://github.com/Vel-Labs/velGraphing/blob/916c3c993dcb214c2700dbec063794dba418bdd8/benchmarks/velgraphing-corpus-pilot-v1/result.json#L1180-L1420).

Resolution: keep process errors separate from the final grade, and include their
work in the root interval. Align the successor's mounted scope and tool scope
before running. Do not claim all process or authority questions were independently
resolved merely because the retained material-claim score is clean.

### F09 / P3 / Portability-privacy review item: preserve historical originals

The assignment flags absolute home-directory paths in historical artifacts.
`audit_pilot_receipts.py` reports tracked historical JSON file/line locations
without reproducing the private values. Its CI output is the location receipt.
Do not rewrite a sealed artifact just to remove a path. Any later sanitization
needs a separate derived view, preserved original digest, explicit redaction map
and changed publication policy. No historical artifact is modified here.

## 2. Actual public execution flow

```text
/graph-start -> skill -> graphctl readiness -> approved project-local setup
/graph-update -> skill -> declared project update or rebuild preview -> validate
/graph-audit -> skill -> structural check or Parent-dispatched fresh worker audit
/graph-benchmark -> skill -> Parent-owned freeze/dispatch/grade instructions

/graph-find -> installed Python adapter
    -> Git-tracked scan -> in-memory source snapshot + Graph(records, edges=())
    -> tag index -> prompt facets -> retrieve -> possible obligation-based retry
    -> body-free ranked pointers -> host exact reads / declared fallback

/graph-jev -> explicit skill / CLI
    -> already discovered exact candidate packet -> preview -> operator approval
    -> evaluate: prepare -> request or replay -> validate -> source revalidation
    -> optional permutation with required slots locked -> host reads/answers

answer generation and independent grading: native host / Parent, not graph core
benchmark process seam: caller-owned answer command -> separate grader command
core assist / retrieve_hybrid: separate caller-owned fallback APIs
V5 navigation: separate bounded API, not the graph-find CLI entry point
package projector: canonical core/contracts/adapters -> portable runtime copies
```

Start/update skills describe project-owned lifecycle operations; they do not
establish a persisted runtime-index lifecycle consumed by the tested graph-find
adapter. Graph-only output is navigation evidence, not an answer or sufficiency
proof. The audit leaves these source/authority boundaries intact.

## 3. Claim-to-evidence matrix

| Claim | Status for the retained pilot | Reason |
| --- | --- | --- |
| Jev was called 12 times with recorded usage | Proven as retained provider receipts | Bookkeeping is inspectable; no call repeated in this audit. |
| Every final answer retained critical facts/source support | Recorded, not independently regraded here | Raw answer/grade evidence was outside the inspected public receipt. |
| Jev reduced retained candidate membership | Contradicted | Permutation preserves membership. |
| Jev avoided discovery already performed before its call | Impossible under current sequence | It runs afterward. |
| The public CLI exercised graph-edge traversal | Contradicted | Its Graph has no edges. |
| The CLI amortized a warm persisted index | Impossible under current CLI path | It builds each invocation; no warm loader is called. |
| Graph ranking can reduce what the host elects to read | Mechanism exists; pilot effect unmeasured | Body-free pointers plus targeted reads; host exposure not fully captured. |
| Ordering can improve first-pass correctness or repairs | Plausible mechanism; inconclusive evidence | Single trials, mixed scores, no fixed repair experiment. |
| Jev reduced end-to-end elapsed time or successful-task cost | Unmeasured | Missing answer/total timing and model usage. |
| The new offline qualification proves a real speedup | Contradicted | It proves instrumentation/control behavior only. |

## 4. Timing ownership matrix

| Quantity | Old owner/evidence | Successor owner and exact boundary |
| --- | --- | --- |
| Task acceptance to terminal result | Missing | Controller monotonic root interval |
| Cold scan/record/index build | Mostly missing | Isolated actual graph adapter + index wrappers |
| Warm graph load | No such CLI call | Not applicable, not a claimed zero-cost warm run |
| Discovery/retrieval | Lane-reported, boundaries uncertain | Controller-owned call spans; compound CLI scopes documented |
| Capture/preview | Outside Jev elapsed | Host wraps actual source_capture/preparation call |
| Jev preparation | Included in composite elapsed | First actual prepare call |
| Provider round trip | Not separately observed | Host-owned transport span; offline fixture clearly typed |
| Response validation / source revalidation | Included in composite elapsed | Actual parse call / second prepare call |
| Queue / operator approval | Missing | Separate controller start/finish spans when observable |
| Answer generation | Missing | External answer process dispatch to completion; native hidden queue stays unmeasured |
| Independent grade | Parent-supplied score, no duration | Separate external grader process, timed by the controller |
| Repairs | Not performed under a fixed budget | Bounded attempts, all earlier work retained |
| First passing answer | Missing | Retrospective answer completion and separate grade confirmation |
| CPU time | Not measured | Still not measured; active wall is not CPU time |

Clock origins from different domains are not comparable. Component spans may
nest; interval unions avoid double counting. The root stopwatch is the source
for wall time. Unobserved gaps remain unattributed. User-visible here means the
chosen host boundary; browser rendering or delivery after that boundary is not
invented. The process seam declares dispatch-to-completion. A native adapter must
declare any additional lifecycle boundary and queue visibility.

## 5. Minimal repair implemented

Added the benchmark controller, graph/Jev qualification bridges, a caller-owned
answer/grader process boundary, completed-trial receipts, a runnable synthetic
four-arm timing demonstration, retained-receipt diagnostics, focused tests, and
the successor protocol/operator documentation. The npm test suite includes the
benchmark tests. CI validates pull requests and pushes to `main`. It runs the
requested commands plus a second projector pass. Existing product source, runtime
projection and sealed results are unchanged. No new dependency, daemon, SDK or
model client is introduced.

Each attempt inherits immutable run/task/arm/repository/model/prompt/rubric
identities from its trial receipt and has its own attempt ID, candidate/request/
context bindings, source operations, model-call receipts, stage states, grade
and terminal reason. Missing data stays null. Context and source contents are
not serialized into the trace. The clock is owned by the controller, not the LLM.

The controller's own deadline is cooperative at callback boundaries. The process
seam applies a timeout to each direct child process. Arbitrary callbacks and native
Codex sessions still require owner cancellation support. Callback timeout and wall
deadline are separate terminal reasons. Each completed trial can be saved as one
atomic canonical receipt and loaded after restart. In-flight SIGKILL recovery is
not implemented. Missing preregistered trials remain in the denominator rather
than becoming imaginary successes. Native Codex lifecycle integration remains a
follow-up, not a mock completion.

## 6. Deferred architecture changes and gates

- Real graph topology adoption: prove source-bound edges reach the active caller,
  then compare identical retrieval with edges enabled/removed. Do not merely count
  graph objects or call file indexing a traversal result.
- Warm index reuse: define snapshot invalidation and distinguish cold index,
  process-warm and OS-cache conditions before implementing persistence.
- Budgeted context / progressive reads: separate product experiment with required
  evidence preservation and fallback. Ordering can be evaluated first on repairs.
- Required-position policy: retain current semantics. If later top-k context makes
  positions consequential, test required inclusion independently from fixed slots;
  do not weaken current protection to improve a score.
- Jev no-op routing: consider avoiding calls when policy leaves fewer than two
  movable candidates. Prove behavior equivalence and all-in benefit before change.
- Native Codex lifecycle integration: requires real dispatch/completion and usage
  receipts, isolation, cancellation and an explicit aggregate live-call budget.

## 7. Repeated-trial proposal

Run A Direct/off, B Direct/on, C Graph/off, D Graph/on using the same frozen task,
source scope, answer model/reasoning, context policy and grader. Start with ten
paired repetitions of the six old tasks (240 trials) as diagnostics, counterbalanced
within task/repetition and initially serial. These are not fresh held-out tasks.
Use at most two repairs and a proposed 300-second confirmation budget, with a
fixed generic repair notice rather than leaking hidden gold facts. Freeze and
approve model/API budgets separately before any live execution.

Keep the old rubric/result intact. A revised atomic L-01 rubric is a new version,
with an explicit alignment rationale and a separately preregistered question.
Report item recall and pass/fail under each declared rubric, not a retroactive win.

Primary endpoints: first-pass correctness, first-answer time, success within fixed
budgets, and grade-confirmed time-to-correct. Include cancelled, late, failed,
ungraded and missing trials. Report all-in costs only with complete per-call
usage; include failed-task spend in cost per success. Never average TTC only over
successes. Report paired task-level differences and uncertainty, accounting for
repeated measurements of the same task. Reserve new untouched tasks for confirmation.

## 8. Component-removal tests

| Component | Implemented offline qualification | Real effectiveness gate still needed |
| --- | --- | --- |
| Graph navigation | Real graph-find output equality plus graph-disabled fixture; actual build/read counts observed | Same-source direct baseline and nonempty-edge topology ablation |
| Jev | Real evaluator off, shadow, replay and injected fixture response; source validation observed | Approved repeated live trials with complete host receipts |
| Fallback | Synthetic discovery failure retained when fallback is removed; timed fallback when enabled | Safe defer-only removal against frozen failure cases |
| Required-position locking | Counterfactual fixture toggles caller flags, preserves all IDs and demonstrates positional effect | Predeclared diagnostic only; no production flag/semantics change |

These are accounting/control tests, not four new quality benchmarks. There is no
attempt to get a favorable product result by changing selection or removing a gate.

## 9. Component recommendations and local review order

| Component | Recommendation |
| --- | --- |
| Source-bound navigation and verification | Retain; conditionally route by task complexity and measured cost. |
| File-tag ranking called by graph-find | Retain as a candidate; describe its actual mechanism. |
| Graph topology / warm reuse integration | Redesign only behind the stated evidence gates. |
| Jev | Conditionally route; keep opt-in until end-to-end evidence earns promotion. |
| Direct-source fallback | Retain. |
| Required-position locking | Retain for this repair; evaluate a later inclusion/position distinction separately. |
| Old phase-field summation as total runtime | Remove as a measurement method; preserve historical artifacts. |
| Benchmark controller and process seam | Adopt after CI/local review; supply authorized live processes and complete receipts before performance claims. |

Review this report first, then the successor README/protocol, controller,
graph/Jev bridges, tests, and exact CI/PR validation receipt. Re-run locally on
the reviewed checkout before creating new provider work. No release or merge is
authorized by this report.

## Validation receipt

Validation runs in an isolated worktree of the named branch. Focused benchmark
tests include the real local answer/grader subprocess boundary, actual graph/Jev
bridges, deadline classification, phase completeness, receipt recovery, and
unknown-usage handling. The PR body records exact head/base SHAs, commands,
results, and the Actions run. Do not use an earlier candidate's successful test
count as proof for a later change. Any CI failure must be classified and repaired
from evidence, not rerun unchanged until green.

Local repair candidate results:

- `python3 -m unittest discover -s tests/benchmarks -v`: 61 passed.
- `python3 -m unittest discover -s tests/core -p 'test_jev.py' -v`: 57 passed.
- `npm test`: 358 passed across scaffold, core, adapters, skills, benchmarks,
  and parity.
- `python3 -m json.tool` for the protocol, `py_compile` for the two changed
  controller modules, and `git diff --check`: passed.
- The package projector was not rerun locally because no canonical or
  package-consumed input changed. Pull-request CI retains the two-pass projector
  and parity check.
- No live provider call, package installation, production source change, package
  projection, release, or merge was performed.
