# RetrieVEL benchmark readout v1

Use one readout for one run and one candidate. Keep the first screen useful to a reader who has not seen the benchmark. Keep the trial packets as the data feed behind it. A canary, calibration, and frozen comparison use the same headings. State the run type so a canary is not mistaken for a benchmark result.

Also state the comparison stage: `core single-turn`, `cold/warm opportunity`, or `iterative multi-turn`. Reuse the six headings below in each stage. Do not merge stages into one arm score. Start with one or two cases that expose the actual failure, then expand only after the measurement and product gate passes. Do not create one benchmark cell per intent variant by default.

Test three claims separately before claiming a combined gain. Direct must provide a usable baseline. Graph must actually select verified relationship evidence and show its effect on context and answer quality against Direct. Jev must apply valid judgments to the same frozen candidate pool and improve selected evidence or downstream answers against Jev off. A safe Direct fallback or a valid Jev response proves mechanism, not quality gain. Then compare A/B/C/D on matched questions. If the reasoning model may request more context, give every arm the same bounded follow-up access and record each selection-answer loop. Report cold and warm Graph work separately. The best route may differ by question; do not require Graph or Jev on every query.

## 1. Decision at a glance

State the run ID, date, candidate commit and package digest, protocol, question set, planned/completed trials, repeats, source snapshots, and result path. Mark the run `complete`, `partial`, or `invalid`. Name any oracle source append, retry, or changed answer instruction. Use `unknown (reason)` for a missing identity.

If source retrieval uses a query that differs from the full answer question, state the query rule and owner, both exact text hashes, and whether every arm used the same query. Include any runtime query-planning call, wall time, and tokens in the trial totals. A frozen, operator-supplied query is a controlled input, not proof of automatic steering.

Give one sentence for each decision:

- **Execution:** Did the planned run complete with valid evidence?
- **Answer quality:** Did the accepted-correctness gate pass? What was the main miss?
- **Mechanism:** Did Graph actually select a relationship route? What did Jev change?
- **Adoption:** Is the product gate met? What is the smallest next proof?

State `mechanism verified`, `quality gain observed`, `regression`, or `not tested` separately for Direct, Graph, Jev, and the combined or iterative path. Name the question and actual route behind each claim.

Do not merge candidates, task sets, rubrics, caps, or source snapshots into one table. Put predictions and historical results in separately labeled sections with their own identities.

## 2. Question and arm outcomes

Use the fixed A/B/C/D order below. Each cell is `passed/completed`, with planned trials stated separately. A pass requires every required fact in the frozen rubric and a valid independent grade. Keep failed and measurement-failed trials in the denominator. Mark a disputed grade `provisional` and retain its original receipt.

| Question and capability tested | A Direct, Jev off | B Direct, Jev on | C Graph enabled, Jev off | D Graph enabled, Jev on | Main observation |
| --- | ---: | ---: | ---: | ---: | --- |
| Question ID and plain-language task | passed/completed | passed/completed | passed/completed | passed/completed | One concrete success, loss, or tie and why |

Do not use a percentage, fact score, or half credit as the headline. Required-fact coverage belongs in the trial trace. Do not sum unlike question types into one quality score. Explain what each question tests, so the reader can judge whether the task set represents the intended product use.

Before a frozen run, calibrate any disputed required fact on retained, source-supported positive and negative examples. State which semantic equivalents count. Apply the same rule to every arm. Keep earlier sealed grades and mark their comparison provisional when the old rule was applied inconsistently.

Grade the supported meaning, not a required adjective in the rubric. A correct cited source path and complete statement can establish a file's role even when the answer does not repeat the role label. A generated copy, incomplete statement, or unsupported behavior claim does not establish the canonical source or the required behavior. Fix these positive and negative examples before dispatch, then apply the same rule to every arm without replacing older grades.

## 3. What happened in the pipeline

Give a compact route and evidence summary before the trial details. Report configured arm and **realized** route separately. Count Direct and Graph selections, selector Direct fallbacks and reasons, verified relationship candidates admitted and selected, source verification failures, Jev attempts, accepted reranks, Jev fallbacks, and final-context cap violations. A Graph-enabled trial that selected Direct is a Direct-route observation. A Graph preview or candidate is not a Graph-selected result.

If Direct and Graph arms use different callers, verify the Direct caller against the installed path's no-edge Direct behavior on the same frozen source and query. Compare candidate IDs, selected source ranges, and serialized final-context bytes; a common cap alone does not establish equivalent packing.

For each material quality difference, write a short failure trace in this order:

`question -> candidate evidence -> selected evidence -> Jev effect -> answer -> grade -> failure class`

Name the exact source span or evidence ID that was added, displaced, or absent. Say whether the answer had enough evidence but omitted a fact, or lacked the needed evidence. Link the retained request, answer, grade, and selector/provider receipts. Separate observed facts from an inferred cause. Classify the failure as `source/retrieval`, `relationship/route`, `selection/rerank`, `answer`, `grade/oracle`, `execution`, `measurement`, or `provider/environment`. A case may have more than one class. Keep disagreements and recoveries visible; do not silently rescore.

## 4. Trial data feed

Retain one row per dispatched trial, even when it fails. Use the same field names in every run. The row is an index into the raw packets, not a replacement for them.

| Field | Meaning |
| --- | --- |
| Trial ID, question, capability, repeat | Stable join key and the task tested. |
| Retrieval query and its chooser | Exact query sent to Direct/Graph, whether copied from the question, extracted by a deterministic rule, chosen by a model, or supplied by an operator. Count a model query-selection call and its time and tokens. |
| Configured arm, realized route, fallback reason | What was requested and what executed. |
| Graph state and turn | Cold build, verified warm reuse, or no graph; source snapshot, turn index, and any source-change invalidation. A conversation continuation is not a warm graph state. |
| Candidate and selected evidence | Candidate count, final evidence IDs/source paths, selected excerpt bytes, context cap, source revalidation, and relationship contribution. |
| Jev | `off`, `reranked`, `fallback`, or `failed`; attempt count, request hash, and whether final evidence changed. |
| Answer and grade | Pass/fail/provisional, required facts met/total, missing fact IDs, citation/support errors, and one plain-language finding. |
| Time and resources | End-to-end wall, time to accepted correctness (TTC), stage intervals, answer/grader/Jev tokens, calls, and measured cost. |
| Evidence | Paths or stable IDs for request, selected context, answer, independent grade, route, and provider receipt. |
| Failure class | First observable break in the pipeline and any downstream effect. |

For iterative trials, add one child row per model turn. Record the prior answer or uncertainty, the follow-up context request, actual Direct/Graph route, selected evidence, Jev or other classifier decision, hook event and host application when enabled, revised answer, and incremental wall time and tokens. The parent trial row carries cumulative totals. Record `not triggered` separately from `triggered but no action` for a hook. Do not credit the hook or MCP for a change made by the CLI or host outside that path.

Keep the original user question distinct from the retrieval query. An operator-supplied identifier query that selects Graph is a route smoke test; it does not prove that the installed path will choose that query from the full question. Give every arm the same query-choice policy in a matched comparison. When the retrieval query is narrower than the question, bind ordered relationship instructions, classifier relevance judgments, and the final answer to the full question; record both strings and their hashes.

Report a field only when the retained packet supports it. Use `0` for observed zero, `n/a` when a treatment does not apply, and `unknown (reason)` for missing telemetry. Request bytes and context bytes are bytes, not model tokens. Do not estimate tokens or money from bytes. A diagnostic field can be reported as a separate table when a wide trial table would be hard to read.

## 5. Time and resource ledger

Show A/B/C/D separately. Report mean end-to-end wall time over every completed trial, including failures and retries. State whether operator approval time is included; an approval-excluded time is a second labeled measure. Report stage intervals when captured: discovery, cold graph build, warm load, source capture, provider, selection/context, fallback, answer, grade, and approval. Identify the timer boundary and whether stages overlap. Do not substitute a provider interval or a sum of recorded stages for user-visible wall time.

Report confirmed TTC for passing trials. Report an arm mean TTC only when every scheduled trial has confirmed TTC; otherwise write `null` with the failed or missing trial IDs. Keep first-pass correctness and fallback-assisted correctness distinct.

Show Jev, answer, and grader calls and input/output/cache tokens separately. Count every reasoning-model turn and follow-up retrieval, including failed or unnecessary loops. Show measured provider cost, repository operations, final evidence bytes, duplicate bytes, proof errors, and prohibited writes where captured.

Separate **graph state** from **conversation state**. Cold means a graph is built from the frozen source snapshot during the measured run. Warm means the same source-bound graph is actually reused or loaded without rebuilding it; name the retained object or artifact and validate its snapshot identity. A later turn is not warm merely because the conversation continued. Measure a prewarmed single question in a fresh answer lane to isolate graph reuse, then a cold-start sequence of related turns to measure amortized work and follow-up behavior. Give Direct the same question order and conversation policy. Report first-turn, later-turn, and cumulative totals; include rebuild or invalidation after source changes when tested. An observed break-even turn requires equal or better accepted quality and cumulative end-to-end measurements, not just graph lookup time. If the shipped caller rebuilds on every invocation, mark warm product behavior `not implemented` and label any in-process reuse as a separate core experiment.

Mark unavailable metrics with a reason and identify which missing metric blocks a cost or speed claim.

For a local MCP or lifecycle hook comparison, name the host, entry point, source snapshot, and matching CLI baseline. Report whether the host actually invoked the MCP or hook, whether it applied the returned plan, and any difference in final context, answer, wall time, and tokens. A declared capability or a passing unit test is not an end-to-end invocation.

## 6. Interpretation and next proof

State the strongest supported result, the main regression or unresolved case, and the product decision. Separate execution validity, Graph-route evidence, answer quality, speed, cost, and adoption. Give the smallest next test that could change the decision. Keep the original score and raw packets intact when a later audit disputes an interpretation. Publish no provider-specific performance detail without the relevant provider permission.
