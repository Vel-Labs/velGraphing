# VelGraphing time-to-correct calibration v3 result

> **Verdict:** rejected for promotion.
>
> **Claim boundary:** This run compares four fixed evidence-only routes. It
> does not establish a correctness, time-to-correct, or end-to-end token
> advantage for Jev or the current graph-assisted route.

## Executive summary

The coordinator closed all 24 registered trials. Only Graph-assisted without
Jev passed one of six tasks. The other three arms passed zero tasks. The frozen
policy requires every registered trial in an arm to pass before it reports a
mean time to correct, so all four mean TTC values are `null`.

The run did identify one useful efficiency signal. Graph-assisted packets used
31.4% fewer provider input tokens than Direct packets in the Jev arms. This did
not improve correctness or end-to-end wall time. Graph-assisted plus Jev was
22.0% slower than Direct plus Jev after operator-approval time was removed.

## Benchmark identity

| Field | Value |
| --- | --- |
| Calibration | `velgraphing-ttc-calibration-v3` |
| Date | 2026-09-18 |
| Execution commit | `689060171fa2b8d2427e11970c034704cef3d976` |
| Execution tree | `f213e9cbd58d23e9a72b441c655151b5276b38ef` |
| Base commit | `031a8390ae3accce7fe4b3756f01f98f2c606ee6` |
| Task set | Six frozen tasks across four public corpora; 24 trials |
| Arms | A Direct; B Direct plus Jev; C Graph-assisted; D Graph-assisted plus Jev |
| Model | `gpt-5.6-sol`, medium reasoning, fresh answer and grader lanes |
| Jev | `jev-1.13.0`, 12 calls, no provider retries |
| Oracle SHA-256 | `b63093c73fea135584de61f2b934215f844ca14ccec41f2cfc93af0d58a7d640` |
| Result SHA-256 | `916c5e766b9152df5dac21b3cf3fec0116002dfee8d4f6c68eec9885bf94fd96` |

## Arm result

Wall values include answer and grader lane execution. The approval-excluded
column removes only observed operator-approval time. It keeps host queue time.

| Arm | Passed | Mean wall | Mean wall excluding approval | Mean TTC |
| --- | ---: | ---: | ---: | ---: |
| A Direct | 0/6 | 138.46 s | 138.46 s | `null` |
| B Direct plus Jev | 0/6 | 133.05 s | 107.16 s | `null` |
| C Graph-assisted | 1/6 | 97.40 s | 97.40 s | `null` |
| D Graph-assisted plus Jev | 0/6 | 160.19 s | 130.72 s | `null` |

The A mean contains one 294.26-second transport measurement error. This makes
B-minus-A and C-minus-A wall comparisons unsuitable for a product claim.

## Jev provider result

All 12 approved calls returned `reranked`. No call was retried.

| Metric | B Direct plus Jev | D Graph-assisted plus Jev | D minus B |
| --- | ---: | ---: | ---: |
| Provider input tokens | 50,361 total; 8,393.5 mean | 34,538 total; 5,756.3 mean | -31.4% |
| Provider output tokens | 399 total; 66.5 mean | 384 total; 64.0 mean | -3.8% |
| Provider interval | 0.489 s mean | 0.431 s mean | -0.059 s |
| Wall excluding approval | 107.16 s mean | 130.72 s mean | +22.0% |

Mean provider interval was under half a second in both Jev arms. Answer
generation and independent grading dominated the observed wall time. Native
answer and grader token counts were unavailable and remain `null`; provider
tokens are not an all-in token total.

## Retrieval diagnosis

The post-run, read-only span diagnostic found that Direct evidence overlapped
2 of 19 frozen acceptable oracle spans. Graph-assisted evidence overlapped 3 of
19. The diagnostic converted each oracle line span against the frozen lane
bytes. An overlap required the same repository-relative path and intersecting
byte ranges. This is not a semantic or fact-coverage score. Jev received the
same fixed candidate membership as its paired non-Jev arm and could only
reorder it. It could not recover missing evidence.

The shipped graph-find path created a tag index with a mean of 78.3 records and
zero edges. Cold build plus retrieval cost about 2.12 seconds in C and 1.91
seconds in D. This run therefore measures tag-index retrieval, not relationship
or neighborhood traversal.

## Failures and limitations

- Only `C-C-02` passed the independent rubric.
- `A-C-02` ended as `measurement_error` after a grader response timeout.
- Candidate confidence is descriptive. All Jev trials failed even when a
  candidate distribution confidence reached 0.99. The study has no
  candidate-level oracle and does not calibrate Jev confidence.
- Answer and grader token counts are unavailable from the native host.
- The graph route has no relationship edges and no warm-load path.
- Exact oracle-span overlap is a post-run retrieval diagnostic. It is not a
  substitute for the independent answer rubric.

## Product interpretation

The fixed evidence packets are not yet sufficient for these tasks. Jev
reranking cannot solve that recall problem. The next candidate should improve
source-span recall and add a real source-bound relationship or neighborhood
route before another full four-arm run. It should keep the current fixed packet
caps and the same independent grading boundary so the new result is comparable.

Do not optimize Jev provider latency first. Its mean interval is already under
0.5 seconds. The larger wall-time costs are answer and grader execution, plus
about two seconds for cold graph construction and retrieval.

## Validation

- 140 focused benchmark and core Jev tests passed.
- 35 final host, packet, and calibration tests passed after the route guard.
- Full repository suites passed: scaffold 11, core 229, adapters 18, skills 29,
  benchmarks 92, and package parity 10.
- Standalone source-package parity passed for 87 files with candidate SHA-256
  `644d997f372e488c8e599babfbfeac61cbab7ed559c7188996d956d29793a939`.
- The coordinator closed 24 of 24 trials. All 12 Jev receipts were consumed,
  returned `reranked`, and matched their approved request hashes.

The first package-parity run found two local Python bytecode files created by a
manual diagnostic. Their removal restored parity. This was an environment
artifact, not a product defect.
