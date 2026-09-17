# Evaluation protocol: Jev x graph

Status: protocol and offline fixture tests are provided. No live accuracy,
calibration, latency, cost, or adoption result is established by this module.
The included synthetic replay is a plumbing check, not held-out evidence.

## Four separate arms

| Arm | Candidate discovery | Jev |
| --- | --- | --- |
| A | Existing direct baseline | Off |
| B | Same direct baseline | Optional reranking |
| C | Existing graph-assisted baseline | Off |
| D | Same graph-assisted baseline | Optional reranking |

Compare B-A, D-C and D-B, not only D-A. Keep the answering model, source access,
task rubric, context limits, allowed tools and required evidence policy the same.
Candidate discovery differences between direct and graph are the intended graph
treatment; don't grant one arm a better hidden source allowlist.

## Stage gates

1. Verify offline and packaged behavior. No API key in CI.
2. One operator-approved public-source shadow call to validate the real API
   contract, key, model, probability shape, usage reporting and safe fallback.
3. Replay real shortlisted candidates to investigate ranking failure types.
   Use explicit consent to retain any response or source-bearing request locally.
4. Run fresh host-native worker lanes on 30-50 screening tasks with separate
   development and held-out tasks. Balance arm order and repeat enough tasks to
   estimate variation. No inherited conversation history and no nested Codex CLI.
   If fresh lanes are unavailable, report `fresh_lane_execution_unavailable`.
5. Confirm a promising result on a larger untouched set before a default change.

Use old compact benchmarks as regressions, never as fresh held-out examples.
Include misleading names, documentation/code disagreement, absent candidates,
stale files, source instructions, multi-file evidence and service failures.
Gold labels and critical facts belong outside model input and candidate capture.

## Measure outcomes before savings

Primary: required-fact and critical-fact recall, unsupported claims, exact source
citations, incomplete-answer behavior and authority errors. Preserve existing
predeclared quality gates. Do not lower them after results arrive.

Secondary: all answering-model input/output and cached tokens where available,
Jev tokens and calls, retries, source bytes, graph build/load work, tool count,
LLM turns, end-to-end runtime including tail latency, and cost per successful
task. Separate cold index costs from warm reuse. API bytes are not tokens.
Replay latency is not live inference latency. Unknown data is unknown, not zero.

Capture repo commit plus dirty-state digest, source allowlist, model IDs, prompt
and rubric versions, candidate packets/hashes, mode, required flags, arm order,
run seed where applicable, runtime environment, output and independent grading.
Assess errors by missing candidate, wrong model judgment, source mismatch,
provider failure, host composition bug and unsupported final answer.

A suggested promotion target is a meaningful all-in gain (for example 20% cost
or time reduction) with quality non-inferiority under an explicitly declared
margin and no observed new critical/authority failures. Zero observed failures
in a small test is not a universal safety claim. Record uncertainty and failed
arms. Do not advertise a speedup from a few synthetic ranking cases.

## Graph-valuing extension, only after v1

Test task-specific marginal evidence value on the existing bounded graph:
relevance plus missing-facet coverage minus redundancy and retrieval cost.
Keep these as advisory utility signals, not truth probabilities. Preserve
candidate diversity and direct fallback. Do not expand hop limits, admit nodes,
merge entities or mutate provenance just to improve a benchmark number.
