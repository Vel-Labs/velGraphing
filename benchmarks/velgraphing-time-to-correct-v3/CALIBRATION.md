# Time-to-correct calibration v3

This freeze reuses the sealed v2 corpus, questions, oracle, and 24-trial order.
It changes the measurement boundary and replaces repository-readable answer
inputs with a frozen evidence-only payload. It does not change product graph
retrieval, Jev prompts, scoring, or pass gates.

The controller builds one deterministic source-bound candidate packet per arm.
Direct uses flat lexical selection. Graph-assisted uses the shipped graph-find
tag index and its exact source pointers. The shipped graph has no edges in this
study, so edge expansion is `not_available`. The study does not invent edges or
claim graph-edge traversal.

Each packet has at most six candidates. Each source span is at most 4,096 bytes.
The final ordered evidence prefix is at most 16,384 bytes. The run uses no
incremental candidate batches and no dynamic fallback. Required evidence that
does not fit must fail closed.

The primary run allows 12 Jev calls and no provider retries. The controller
binds the execution candidate at run time. The base commit records the `main`
state from which this measurement candidate started.

The v3 summary retains each arm and these paired contrasts:

- B minus A: Jev effect on Direct.
- D minus C: Jev effect on Graph-assisted.
- C minus A: Graph effect without Jev.
- D minus B: Graph effect with Jev.

Unknown values stay `null`. Missing trials stay visible. Warm graph load stays
`not_applicable` because the current route performs a cold in-memory graph build.
The provider does not report shared-state and question-suffix token counts, so
both values stay `null`. Candidate confidence is descriptive. Candidate
calibration is unscored because the study has no candidate-level oracle.

Order and rubric sensitivity are a future companion ablation. It requires a
separate provider-call budget and candidate-level labels. The primary run does
not authorize those calls.

The answer must cite retained candidate IDs as `[cN]`. This check proves only
that each cited ID exists in the delivered evidence packet. It does not prove
that the citation supports the claim. The independent grader remains the
correctness control.

The result keeps full wall time and confirmed time-to-correct. It also reports
both values with only observed operator-approval time removed. Host queue time
remains part of wall time. Active execution, observed waits, and unattributed
time stay separate.
