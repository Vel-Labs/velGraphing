# VelGraphing time-to-correct v1

Status: executable measurement tooling and offline qualification, **not a new
performance result**. The six-task pilot remains unchanged. No provider is
called by the included demo or qualification bridges.

## Run locally

From a clean checkout with the existing project dependencies installed:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/benchmarks -v
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/time_to_correct_fixture.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/audit_pilot_receipts.py
```

The first demo intentionally gives every arm the same answer and repair pattern.
Its timings are synthetic clock advances; they are not Jev latency or graph
performance. It demonstrates the accounting, including operator waits.

## What is implemented

`time_to_correct.py` owns a monotonic event trace, fixed repair budget, grading
boundaries, complete trial denominator, source/context receipts and per-model-call
usage. `time_to_correct_graph.py` instruments the **actual graph-find path** using
isolated module copies. `time_to_correct_jev.py` instruments the **actual Jev
evaluator** with a replay or local fixture response. No production function is
patched, no ranking semantics change, and the package projection is unchanged.

Graph instrumentation times the real scan/record creation plus tag-index creation
as cold build, prompt/facet preparation as candidate discovery, and the real
retrieval invocation including custody verification as retrieval. Those definitions
are specific to this CLI. Custody verification remains inside retrieval;
any nested index-builder call also has an inclusive build interval. Do not add
those overlapping values. Neither is a fictitious warm cache load. Warm load is explicitly not applicable. File reads
and in-memory reader accesses are recorded separately; neither is automatically
counted as model-visible content. Skipped/failed reads can leave byte counts
unknown. Instrumentation overhead is part of these observed intervals.

The graph wrapper requires the declared snapshot to equal the current accepted
source set, using SHA-256 of canonical JSON:
`{"sources":[{"path":...,"byte_length":...,"sha256":...},...]}` with rows sorted
by path, keys sorted, UTF-8 without ASCII escaping, compact separators, and no
trailing newline. This is the existing SourceSnapshotV4 identity, not a new digest
scheme. A corpus manifest file's own hash is a different binding and should also
be retained in the frozen plan. Never substitute one digest scheme for another.

## Three different clocks, three different questions

1. `first_answer_ns`: task accepted to first completed answer, regardless of grade.
2. `first_correct_answer_ns`: task accepted to the answer later graded passing.
3. `confirmed_time_to_correct_ns`: task accepted to independent confirmation that
   an answer passes. This includes earlier failures, intervening grading, repairs,
   orchestration, observable queue time and operator approval delays.

The last field is null for unresolved/failed/cancelled/late trials. Their actual
terminal wall time is retained, not dropped or substituted for time-to-correct.
A late passing grade is recorded but does not count as success within the budget.

The current deadline is checked **between callbacks**. It is not a forced kill
of a blocked model or native-agent session. Record actual overrun. A real host
adapter must implement supported cancellation/timeouts; this controller does not
pretend that a socket timeout is an end-to-end execution deadline. SIGKILL or a
machine crash can lose an in-memory trace: preregistration keeps the missing trial
visible, but cannot reconstruct its duration. There is no daemon or crash-recovery
service in this repair.

All durations use `time.monotonic_ns()` from one benchmark-controller process and
thread. Only differences in that domain are meaningful. The trace rejects worker
supplied timestamps and cross-process/thread use. Separate machines or fresh
controllers must return their own duration receipts; do not subtract their clock
origins. UTC timestamps may be added externally for correlation, not durations.
Nanosecond units do not imply nanosecond accuracy. Python documents the clock:
https://docs.python.org/3/library/time.html#time.monotonic_ns

## No double counting

Per-phase numbers are explicitly **inclusive interval unions**. A repair contains
retrieval/answer/grading work; do not add repair duration again. A model call can
contain observable host queue time; do not add that queue twice either.

`observed_wait_union_ns` is the union of measured queue/approval waits.
`observed_active_execution_ns` is the union of measured work, minus overlapping
waits. It is wall execution, not CPU time. `unattributed_ns` preserves gaps rather
than assigning them to the model. Missing phase coverage is not zero.
The root elapsed time is measured directly, never obtained by adding components.
A parallel experiment's makespan is a separate parent interval, not the sum of
its task wall times. Begin with serial, counterbalanced trials to avoid shared
hardware/provider contention confounding the four arms.

## Context and usage accounting

The host records **actual delivered UTF-8 bytes**, including separators, wrappers
and serialization, with `trial.context(raw_bytes, kind=...)`. Tool-message bytes
and complete model-request bytes are different, potentially overlapping views.
Do not sum them. Record every relevant delivery, not only the final evidence pack.
The trace stores hashes/lengths, not the contents. A hash proves identity, not that
unobservable hidden host messages have been counted.

Source operations carry source-content hashes, half-open byte ranges, logical
operation IDs, and file/memory/tool access type. Count repeated reads as work;
use range unions per source hash for content coverage. Identical source contents
share a hash, so that union is content coverage, not a count of physical files.
File-read bytes are not physical disk I/O or a token estimate.

Call `trial.usage(...)` for **every actual model call**, including discovery,
answers, retries, repairs and any model grader. Use provider/host-reported values
or mark them unavailable. Cached input and reasoning output are subsets of their
respective totals, not extra tokens to add. Do not compare Jev's token count with
another model's count as a monetary conversion. Record supplied normalized cost
only when its pricing basis is known. No price table or tokenizer is invented.

Coverage flags default to incomplete. A host may attest complete capture only
when it really controls every relevant call/delivery/read. One missing usage
receipt makes all-in token/cost totals unknown. Summaries include failed-task
spend when calculating cost per successful task. Unknown spend is not zero.
Fixture receipts stay labeled fixture; they are not actual provider spend.

## Wiring a real host, without pretending it is already wired

The public plugin commands are agent instructions, not a Python model dispatcher.
The supplied runner is callable infrastructure. An authorized native-host adapter
must provide `prepare`, `answer`, and independent `grade` callbacks:

```python
from scripts.benchmarks.time_to_correct import Trial, Budget

trial = Trial(frozen_identity, Budget(max_repairs=2, wall_limit_ns=300_000_000_000))
result = trial.run(prepare_attempt, answer_attempt, independent_grade)
```

The identity must contain the fields validated by `IDENTITY`, with opaque IDs,
full hashes, frozen model/reasoning and rubric version. `prepare_attempt` performs
actual discovery/capture/composition under `trial.phase(...)` scopes; it returns
only the selected answer input. `answer_attempt` must return only after the full
answer is available at the declared host boundary. `independent_grade` returns a
`Grade` bound to the same frozen rubric. The default pass recall is 0.9 with exact
critical facts and no unsupported material claims; changing it is an explicit,
preregistered protocol change.

The callbacks are trusted host code. Never put the `Trial`, its grades, oracle or
hidden rubric into the answering model's context. Structural grader-ID separation
is not proof of independent judging. Keep grader tools/data isolated and freeze
repair feedback rules before the run. The runner supplies attempt number, not gold
facts; a fixed generic correction prompt is the initial proposed repair policy.

Queue/approval phases require real host start/finish observations. If the host
exposes only dispatch-to-completion, keep that inclusive interval and mark queue
breakdown missing. Do not ask the answering LLM to estimate its runtime.

No live/native-host adapter is claimed by the offline tests. No nested Codex CLI,
new API SDK, background process or external service is introduced. Live execution
still needs explicit approval and a host-enforced aggregate request budget. The
included Jev bridge intentionally cannot make that call.

## Repeated trials and component removal

See `protocol.json` for the proposed, not-executed protocol. Cross Direct/Graph
with Jev off/on. First use the six old tasks for repeated **diagnostic** runs, not
fresh held-out claims. Counterbalance arm order within task/repetition and retain
all failures. Keep identical source scope, answering model/reasoning, questions,
repair budget, context policy, grader and feedback rules.

Report per-task outcomes and first-pass recall alongside pass/fail, successful
completion within fixed budgets, and uncertainty across paired repetitions.
Do not treat repetitions of six tasks as 60 independent task types. A success-
only mean runtime is not the primary statistic. Report an empirical success-by-
deadline table with the complete registered denominator; unexplained early
censoring/missing trials require bounds or an explicit survival-analysis policy.
The supplied summary deliberately returns no TTC mean when any task is unresolved.

Unit qualification removes graph work, Jev, fallback and required-position locking
in controlled fixtures. The locking counterfactual changes only fixture policy;
production semantics remain unchanged. These tests establish control/accounting
behavior, **not** a real-world component benefit. Real component-removal studies
must preserve safety controls and report failures, not tune until a preferred arm
wins. A fallback-disabled diagnostic must fail/defer safely, never force an answer.

A context-budget/pruning or incremental-read policy is a **separate product
experiment**, not a prerequisite for testing ordering's effect on repairs. Do not
bundle it into this repair or retroactively credit the pilot with that mechanism.
