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

`time_to_correct_host.py` is the external process boundary. The caller supplies
separate answer and grader argv arrays. The module never invokes a shell. It sends
canonical JSON on stdin and accepts canonical JSON on stdout. Each process timeout
is bounded by the remaining trial deadline. A process timeout is recorded as
`callback_timeout`; controller wall exhaustion is `deadline_exceeded`. Process
errors use closed reason codes. Stderr and arbitrary exception text are not copied
into the trial result.

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

The controller deadline is checked **between callbacks** with a private signal.
A callback-raised `TimeoutError` is not relabeled as controller wall exhaustion.
The external process boundary enforces a per-call timeout and kills its child when
that timeout expires. This does not claim native Codex lifecycle cancellation.
An in-flight trial can still be lost after SIGKILL or machine failure. A completed
trial can be atomically saved and loaded after restart. A missing preregistered
trial remains missing in the denominator. There is no daemon, database, scheduler,
or general agent runtime.

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
A phase has observed, missing, and not-applicable attempt counts. A phase observed
in only some attempts is `partial`, not `observed`. Its measured interval union is
still retained, but `complete` is false when any attempt is missing.
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

## External answer and grader process boundary

The public plugin commands are agent instructions, not a Python model dispatcher.
The supplied boundary runs caller-owned processes. It does not select a model host
or start a nested Codex CLI. The caller still owns discovery and preparation:

```python
from pathlib import Path
from scripts.benchmarks.time_to_correct import Budget, Trial
from scripts.benchmarks.time_to_correct_host import run_process_trial

trial = Trial(frozen_identity, Budget(max_repairs=2, wall_limit_ns=300_000_000_000))
result = run_process_trial(
    trial,
    prepare_attempt,
    answer_argv=["/absolute/path/to/answer-command", "--frozen-config", "answer.json"],
    grader_argv=["/absolute/path/to/grader-command", "--frozen-config", "grader.json"],
    cwd=Path("/authorized/run/root"),
    answer_timeout_s=120,
    grader_timeout_s=30,
)
```

The identity must contain the fields validated by `IDENTITY`, with opaque IDs,
full hashes, frozen model/reasoning and rubric version. `prepare_attempt` performs
actual discovery/capture/composition under `trial.phase(...)` scopes. It returns
only a JSON object for the answer process. The grader receives the completed answer
and frozen rubric identity, not the answer prompt. It returns explicit
`required_fact_score` and `required_fact_maximum`; the controller derives
`required_fact_recall`. The frozen threshold is `required_fact_recall >= 0.9`,
with exact critical facts and zero unsupported material claims.

The commands are trusted host code. Never put the `Trial`, its grades, oracle or
hidden rubric into the answer process input. Structural grader-ID separation is
not proof of independent judging. Keep grader tools/data isolated and freeze repair
feedback rules before the run. The runner supplies the attempt number, not gold
facts. A fixed generic correction prompt is the initial proposed repair policy.

Queue/approval phases require real host start/finish observations. If the host
exposes only dispatch-to-completion, keep that inclusive interval and mark queue
breakdown missing. Do not ask the answering LLM to estimate its runtime.

The process seam records only the answer input it delivered and the usage receipts
returned by each process. Completeness flags remain false unless the host can attest
that all nested calls and contexts are included. Missing values stay null. No live
provider or native Codex lifecycle integration is claimed by the offline tests.
Live execution still needs explicit approval and a host-enforced aggregate request
budget. The included Jev bridge intentionally cannot make that call.

## Completed-trial recovery

Call `save_completed_trial(receipt_directory, result)` after each terminal trial.
On restart, call `load_completed_trials(receipt_directory, registered_trial_ids)`
and pass those rows to `summarize`. Each completed receipt is canonical JSON and is
written atomically. A conflicting receipt is rejected. The loader reads only the
preregistered IDs. It does not turn an absent or interrupted trial into a result.

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
