# T120 fact-level failure attribution

## Decision

Revise the benchmark protocol before another live run. The sealed T110 result
remains valid custody evidence. It is not valid Graph or Jev efficacy evidence.

## Blocking protocol defects

1. M-02 asks for one documented process choice, but its rubric accepts only the
   automated CI/CD example. The public source supports multiple valid choices.
2. L-01 and M-02 require literal source paths. Answer lanes are told to cite
   evidence IDs. The grader input does not include the evidence-ID-to-path map.
3. Arm A is an edge-disabled frozen-shortlist baseline. It is not an ordinary
   repository-reading Direct workflow.

## Fact-level attribution

| Required fact | A | B | C | D |
| --- | --- | --- | --- | --- |
| D-01 identifies `quick_sort` | absent from pool | absent from pool | dropped by final selection | supported |
| D-01 explains ordering | absent from pool | absent from pool | dropped by final selection | supported at the public-question level |
| D-01 explains duplicates | absent from pool | absent from pool | dropped by final selection | supported at the public-question level |
| L-01 traffic and read heat | supported | supported | supported | supported |
| L-01 layered cache and immutable mapping | answer omission | supported | supported | supported |
| L-01 vertical and horizontal guidance | supported | supported | supported | supported |
| L-01 stateless replicas | supported | dropped by final selection | supported | supported |
| L-01 cites both chapters | grading contract defect | grading contract defect | grading contract defect | grading contract defect |
| L-01 attributes case facts versus general guidance | supported | supported | supported | supported |
| M-02 baseline versus implementation | supported | supported | supported | supported |
| M-02 process-documentation choice | rubric defect | rubric defect | rubric defect | rubric defect |
| M-02 training choice | supported | supported | supported | supported |
| M-02 flexible status | supported | supported | supported | supported |
| M-02 cites playbook and FAQ | grading contract defect | grading contract defect | grading contract defect | grading contract defect |

The Graph pool contains the D-01 `quick_sort` relation candidate. Graph/off
drops it at final selection. Graph/Jev keeps it. The resulting D answer covers
the public question. This is a useful mechanism trace, but the invalid grading
contract prevents an efficacy claim.

## Next package

Implement a successor-only deterministic protocol repair. Preserve all frozen
T110 files and its result seal. Add citation mapping to grader input, make M-02
accept any source-supported playbook choice, make D-01 scoring match the public
question, and name arm A accurately. Validate offline before considering repair
loops or another live run.

## Proof boundary

No provider response details, credentials, hidden labels, or new calls were
used. This attribution does not establish Graph, Jev, model, token, cost, or
time-to-correct performance.
