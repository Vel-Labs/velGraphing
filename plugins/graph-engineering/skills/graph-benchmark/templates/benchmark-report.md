# Graph Benchmark Report

> **Verdict:** `<accepted | rejected | unresolved>`
>
> **Claim boundary:** `<one sentence stating exactly what this run proves>`

## Executive Summary

`<State the task count, repositories, quality result, efficiency result, safety
result, and most important limitation in two or three sentences.>`

## Benchmark Identity

| Field | Value |
| --- | --- |
| Benchmark ID | `<stable-id>` |
| Date | `<YYYY-MM-DD>` |
| VelGraphing version | `<version and candidate identity>` |
| Repository snapshots | `<repository, commit/tree or complete snapshot hash>` |
| Task set | `<count, tracks, difficulty distribution>` |
| Difficulty calibration | `<how difficulty was assigned and checked>` |
| Repetitions and seeds | `<count and exact seeds, or deterministic>` |
| Routes | `Direct; Graph-assisted` |
| Model and reasoning | `<exact model and level>` |
| Freshness | `<fresh/no-history policy>` |
| Tool and time limits | `<equal route limits>` |
| External sources | `<frozen identities, URLs and retrieval dates, or none>` |
| Scoring | `<executable checks, blinded rubric, human review, or unscored>` |

## Overall Results

Use relative percentage change for counts, bytes, tokens, operations, and time.
Use percentage-point change for rates. Never replace unavailable values with
zero. Use `not applicable` or `unscored` across unlike task types. Do not
calculate a weighted cross-track quality score.

| Metric | Direct | Graph-assisted | Difference | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Comparable task gates passed | `<n/N or N/A>` | `<n/N or N/A>` | `<% or N/A>` | `<use N/A when track gates differ>` |
| Required-fact recall | `<%>` | `<%>` | `<pp>` | `<improvement, tie, or regression>` |
| Executable checks passed | `<n/N>` | `<n/N>` | `<%>` | `<build or test outcome>` |
| Repository operations | `<count>` | `<count>` | `<%>` | `<navigation effort>` |
| Model-visible source bytes | `<bytes>` | `<bytes>` | `<%>` | `<context exposure>` |
| Total input tokens | `<tokens>` | `<tokens>` | `<%>` | `<model input cost>` |
| Wall-clock time | `<duration>` | `<duration>` | `<%>` | `<end-to-end latency>` |
| Repeat variability | `<range or interval>` | `<range or interval>` | `N/A` | `<stability across runs>` |
| Source fallbacks | `N/A` | `<count or rate>` | `N/A` | `<why fallback occurred>` |
| Proof or authority errors | `<count>` | `<count>` | `<%>` | `<safety outcome>` |

## Results By Track

| Track | Tasks | Direct pass rate | Graph-assisted pass rate | Difference | Main finding |
| --- | ---: | ---: | ---: | ---: | --- |
| Repository understanding | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| Debugging and coding | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| Tool use and validation | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| Architecture and change impact | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| Product and visual design | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| Technical writing | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| Creative writing | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| External-context research | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| New-feature implementation | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |
| Multi-turn and warm-session work | `<n>` | `<%>` | `<%>` | `<pp>` | `<finding>` |

## Task Results

| Task | Track | Difficulty basis | Repeats | Direct | Graph-assisted | Variability | Fallback | Outcome |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `<task-id>` | `<track>` | `<declared capability or dependency depth>` | `<n>` | `<score>` | `<score>` | `<range or interval>` | `<count>` | `<tie, improvement, or regression and why>` |

## Quality And Safety

Report the checks that match each task. Examples include required facts,
source citations, tests, builds, patch review, visual review, accessibility,
unsupported claims, prohibited writes, and authority violations.

| Check | Direct | Graph-assisted | Gate | Result |
| --- | ---: | ---: | --- | --- |
| `<check>` | `<value>` | `<value>` | `<threshold>` | `<pass or fail>` |

## Efficiency Detail

| Cost layer | Direct | Graph-assisted | Difference | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Directory listings | `<count>` | `<count>` | `<%>` | `<meaning>` |
| Search calls | `<count>` | `<count>` | `<%>` | `<meaning>` |
| Source reads | `<count>` | `<count>` | `<%>` | `<meaning>` |
| Duplicate source bytes | `<bytes>` | `<bytes>` | `<%>` | `<meaning>` |
| Cold graph build | `N/A` | `<duration and bytes>` | `N/A` | `<first-use cost>` |
| Warm graph load | `N/A` | `<duration and bytes>` | `N/A` | `<reuse cost>` |
| Graph retrieval | `N/A` | `<duration and bytes>` | `N/A` | `<selection cost>` |
| Targeted fallback | `N/A` | `<duration and bytes>` | `N/A` | `<recovery cost>` |
| Answer generation | `<duration>` | `<duration>` | `<%>` | `<model cost>` |

## Cold And Warm Interpretation

- Cold result: `<include graph construction and first-use cost>`
- Warm result: `<include later turns in the same frozen repository snapshot>`
- Break-even: `<observed turn, not estimated, or unknown>`
- Repeated reads avoided: `<count/bytes or unknown>`

## Regressions And Recoveries

| Task | Evidence missing or wrong | Detection | Fallback | Final effect |
| --- | --- | --- | --- | --- |
| `<task-id>` | `<specific evidence>` | `<detected, missed, or N/A>` | `<successful, failed, or N/A>` | `<quality and cost effect>` |

## Product Interpretation

1. **Frozen benchmark verdict:** `<Did this candidate satisfy the declared gates?>`
2. **Practical product meaning:** `<Where did the graph help, fail, or merely add cost?>`
3. **Do not claim:** `<List conclusions this evidence does not support.>`

## Reproduction

```text
<Exact read-only preparation, lane, scoring, and validation commands or tools>
```

## Evidence Inventory

- Freeze: `<path and SHA-256>`
- Questions and rubrics: `<path and SHA-256>`
- Lane responses and traces: `<paths and identities>`
- Scores and result seal: `<paths and identities>`

## Upstream Feedback Candidates

| Finding | Class | Reproducible | Sanitized | Proposed action |
| --- | --- | --- | --- | --- |
| `<one-sentence finding>` | `<target repository | harness | documentation | measurement | VelGraphing product>` | `<yes or no>` | `<yes or no>` | `<local recommendation or upstream issue draft>` |

For each reproducible VelGraphing product finding, show this draft before
requesting publication authority:

```text
Title: <concise observed defect or improvement>

Observed behavior:
<What happened without private repository details.>

Expected behavior:
<What VelGraphing should do instead.>

Evidence:
<Sanitized route comparison and stable identities.>

Reproduction:
<Minimal public or synthetic reproduction.>

Acceptance check:
<Observable condition that closes the issue.>

Privacy review:
<Confirm excluded names, paths, source, secrets, and business data.>
```

Do not open the issue until the operator approves this exact draft.

## Limitations And Next Proof

- `<Known measurement or coverage limitation>`
- `<Unmeasured or unknown value>`
- Next proof: `<smallest test that can materially change the conclusion>`
