# VelGraphing shipped-interface benchmark V1

This frozen self-conformance benchmark compares four read-only repository
navigation routes on three tasks and 19 required facts. Each answer used a
fresh `gpt-5.6-luna` High lane. A separate Luna High lane scored the answers.

## Results

| Route | Fact recall | Source-location recall | Answer pass | Source bytes | Difference from Direct | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Direct | 94.74% | 100.00% | 1/3 | At least 426,448 | Baseline | One source-byte total was known. Two were not reported. |
| Graph only | 0.00% | 5.26% | 0/3 | 0 | -100.00% recall | Body-free pointers cannot answer source-semantic questions. This is a diagnostic route. |
| Graph-assisted pointer reads | 10.53% | 10.53% | 0/3 | 5,883 | -88.89% recall | Exact graph-selected spans were very small, but they omitted most required implementation evidence. |
| Graph-assisted targeted fallback | 89.47% | 100.00% | 2/3 | 266,311 | -5.56% recall | Fallback recovered every source location and 17/19 facts. It remained one fact below Direct. |

The targeted route reached full fact recall on the architecture and failure
tasks. It missed two narrow statements on the `/graph-find` flow task. Direct
missed one of the same statements. These were answer-composition omissions,
not missing source locations: both routes had 100% source-location recall.

The benchmark does not prove context reduction. Two Direct source-byte totals
and all Direct wall-clock totals were unavailable. The graph scanned 1,176,198
source bytes per task to build its in-memory index. That processing is not the
same as model-visible context, but it must still be reported as cold-build
work.

## Verdict

The frozen acceptance gate failed:

- Targeted fallback scored 17/19 facts. Direct scored 18/19.
- A Direct lane created an unused temporary file.
- One pointer-read lane read a complete file before repeating the read with
  exact byte ranges.

Grok 4.5 and MiniMax M3 independently classified the result as `REVISE`. They
agreed that the evidence does not justify a product retrieval change. Their
recommended boundary is a new, unfrozen harness run with stricter lane
discipline and complete compound-answer requirements. DeepSeek V4 Flash ran,
but its response failed the closed JSON schema and remains advisory only.

Do not use this run for a public performance claim. It is useful evidence that
targeted fallback can recover most source semantics while graph-only and
pointer-only context remain insufficient for these tasks.

## Evidence

- `freeze.json`: unchanged benchmark, candidate, route, task, and scoring contract.
- `responses/`: the 12 exact answer-lane payloads.
- `scores.json`: independent fact matrix and aggregate scoring.
