# T260 final-candidate freeze blocker

## Outcome

T260 stopped at its pre-answer relationship gate. No provider, answer, or
grader call ran.

The final product branch was merged normally into the benchmark branch in the
local benchmark worktree. The regenerated R5 pools passed custody and package
checks, but the D-01 Graph pool did not contain the required source-bound
relationship delta. The benchmark was not frozen or pushed.

## Branch and custody

- Local benchmark merge: `84c7674549bdbc2312e268bfb4f3ea67a86305b1`
- Merge parents:
  - benchmark head `ade03a64`
  - product head `a444792`
- Product commit `fbfa54b0d1f223a073e67753ea1b3cd958d48baa` is an ancestor.
- Package candidate remains
  `6adb2850258ed178376b6d63c2dcaae04457844cefec6a38411a5bfe2166c19e`.
- Historical R4 result before and after:
  `884dbb95387ff6b49606c2303b2788cb6d80a573eaa5fd4a63571814074f5a54`.
- The local merge is clean and unpushed.

## R5 preflight

- Candidate pools SHA-256:
  `1307fade22088ffce12b9f02d06e34cd04d8853f01d7f4328cafaba7e0a87757`
- Preflight SHA-256:
  `2585024964806b2217359bee593005856cbc3ac9102809acc759e1cccfcd166d`
- Pools: 8 paired Direct and Graph pools
- Planned Jev calls: 8
- Calls executed: 0
- Fresh answer or grader identities created: 0

The D-01 Direct and Graph requests were byte-identical at 109,650 bytes with
request SHA-256 beginning `b63f730a`. The Graph pool recorded:

- `relationship_candidate_count: 0`
- `relationship_delta_present: false`

The relation seam derived the correct source-bound edge from
`sorts/benchmark_sorts.py` to the `quick_sort` declaration in
`sorts/quick_sort.py`. Its exact target coordinate is bytes 257 through 267.
Retrieval instead used the prompt-matched `merge_sort` import as the one
relationship support for the caller seed. That target was already in the
Direct pool, so Graph added no relationship candidate.

## Independent review

Luna returned `REVISE`. It confirmed that the D-01 gate is valid. The question
asks for the imported dependency immediately after `merge_sort`; the corrected
rubric requires `quick_sort`, its ordering behavior, and duplicate handling.

The smallest generic repair is to treat the named import as an ordered source
anchor and choose the next verified same-file import edge. The repair must keep
the current one-support-per-seed policy, source coordinates, custody, and caps.
It must not add a D-01, corpus, path, or symbol exception. Missing or ambiguous
anchors must fail closed.

## Proof boundary

This is a source-bound preflight defect. It is not a provider, answer-model, or
grader result. Historical R4 is unchanged. R5 remains unexecuted and unsealed.
