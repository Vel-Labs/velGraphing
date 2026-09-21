# T210 clean R4 sealed result

## Decision

Accept the clean R4 run as one sealed, oracle-assisted fallback study. Do not
use it as a Direct, Graph, Jev, retrieval-performance, all-model token, or cost
claim.

## Candidate and seal

- Benchmark head: `ade03a64d14516a90ad0322612ec1c3b2fb60feb`.
- Manifest SHA-256:
  `4ddd687e0b1aa891db3c24067186fd8748df355bbc2af0e10aab0da09440d314`.
- Ignored run root:
  `.velgraphing-local/velgraphing-four-arm-study-v1/successor-live-r4-4f07ef8`.
- Result SHA-256:
  `884dbb95387ff6b49606c2303b2788cb6d80a573eaa5fd4a63571814074f5a54`.
- Controller result: exit `0`.
- Calls: 16 answers, 16 graders, and 8 Jev provider requests.
- Retries: `0`.
- Verified fallback appends: `4`.
- Outcome: 9 passing trials and 7 failed trials.

An independent Luna audit returned `PASS`. It confirmed the manifest, contract,
rubric, controller, host, source snapshot, candidate pool, verifier, fallback,
receipt, call-count, duration, and token-accounting bindings.

## Outcome by arm

| Arm | Pass | Fail | Verified fallbacks |
| --- | ---: | ---: | ---: |
| A Direct / Jev off | 2 | 2 | 1 |
| B Direct / Jev on | 2 | 2 | 2 |
| C Graph / Jev off | 2 | 2 | 1 |
| D Graph / Jev on | 3 | 1 | 0 |

No arm passed all four trials. The frozen mean time-to-correct value is
therefore null for every arm. Passing-trial-only means are diagnostic and are
not comparable performance claims.

## Mechanism evidence

- Every arm passed S-01 and M-02.
- Only Graph plus Jev passed D-01. Its final context was 5,042 bytes, versus
  11,856 bytes for Graph without Jev. The graph exposed the `quick_sort`
  relationship candidate and Jev retained it first.
- Every arm failed L-01 although the required evidence survived selection.
  This is an answer-use failure, not a demonstrated retrieval failure.
- Jev provider duration averaged 0.788 seconds for Direct and 0.741 seconds
  for Graph. The answer and grader calls dominated trial wall time.
- The 8 provider calls used 223,904 input tokens and 6,224 output tokens.
  Answer-model and grader-model token usage was unavailable.

Diagnostic all-trial wall-time means were 105.451 seconds for A, 92.327 for B,
97.674 for C, and 102.265 for D. These values come from one run with stochastic
answer and grader calls. They do not establish a speed ranking.

## Claim boundary

The only allowed claim is that this exact clean R4 artifact measures
oracle-assisted fallback time to correctness under its frozen contract. It
shows a useful Graph plus Jev mechanism on one relationship task. It does not
establish general correctness, speed, context, token, cost, or retrieval
superiority.

## Next task

Run one current installed-package canary on public source. Rebuild every hash
from the installed `0.1.6` package before approval. Use one Jev call, no retry,
and exact source revalidation. This closes the remaining installed-path proof
gap before any replication or final external audit.

## Files changed

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T210-r4-sealed-result.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
