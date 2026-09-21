# T220 installed-package canary preflight

## Decision

Reject the live call before transport. The fresh installed package found
verified graph relationships, but the ranked shortlist retained no relationship
candidate and selected the Direct route. A Jev call would therefore test Direct
plus Jev, not the required Graph plus Jev installed path.

## Installed identity

- Source checkout: `ba4c66e326c779392a8632a932e0016bb122878b`.
- Package version: `0.1.6`.
- Release manifest SHA-256:
  `9a652380694c360c1efcff3eb4ffaf1cb632e01971a2386b82b201cb4897af39`.
- Candidate SHA-256:
  `ad2d9b4002df3164035e85335e6d483977fc7675719b7fb353be2cbe881e08b2`.
- Projection map SHA-256:
  `7241eb474220c4773bfdb30242b2a972eb8f07ec3a9224e047d2ba31e0e6b044`.
- Fresh installation: isolated workspace-local Codex home outside every
  repository ancestor.
- Runtime proof: the installed launcher imported `core.retrieval` and the
  installed `runtime/core/__init__.py`. It did not import `packages.core` from
  the checkout.

The machine's global cached `0.1.6` plugin is an older candidate. It was not
modified or used. A first disposable install nested under the checkout also
resolved canonical source modules through ancestor detection. That invalid
harness result was discarded.

## Public source boundary

The canary analyzed a detached worktree at public `origin/main` commit
`3bad9cbfa618e4a39789298a52a8d03d2afdb8f2`, which includes merged PR #15.
This excludes the GoalBuddy branch's self-referential T100 note and state file.
The public source snapshot SHA-256 is
`dbd9ff89fbb78774322abfd035e17597ba378b925c88670f8a7dd57e399e492a`.

## Preflight result

- Installed graph-find route: `graph`.
- Installed graph-find reason: `verified_tag_context_selected`.
- Hits: `6`.
- Verified relationship supports: `4`.
- Direct candidates: `46`.
- Graph candidates: `46`.
- Retained relationship children: `0`.
- Ranked planner route: `direct`.
- Ranked planner reason: `direct_baseline_no_graph_relationship_gain`.

The relationship source coordinate is admitted late in the optional candidate
order. The byte cap fills before its bounded relationship target can be
retained. Later small direct units still fit. The graph relationship therefore
exists but does not reach the shortlist.

## Unused preview

The fail-closed preview was generated only to bind the rejected state:

- Candidate packet SHA-256:
  `45c5c732daa25d8446b2f8b5efed99f6953940e0d93f6b7743696fcbeedcfc5a`.
- Plan SHA-256:
  `488998dd109c440f0ed5dd48d0d3867cea2b1433253ba890ff152ce429c6bf45`.
- Candidate-set SHA-256:
  `b9ffe95cba25c5d7087630027be3373c7d9fcaad26f163fc42e15bf3135818d4`.
- Query SHA-256:
  `b67053997ffb5df0622bbbad2040e1c39dfca9acd5caf1b73765b00494cbbf49`.
- Source-set SHA-256:
  `5a4aa8fc30764621750795283ce3e342e53e49c49f9879ee540927b017bc5473`.
- Request SHA-256:
  `c007857a7a4412eeb10b3904525b3be463012bea77640fc3f79eebbf3a534cdc`.
- Request bytes: `91,978`.
- Source bytes verified: `408,190`.

No credential was accessed. No provider or model call occurred. No request was
authorized. The provider budget did not change.

## Next task

Prioritize source units that bind verified relationship supports before the
optional shortlist exhausts its byte cap. Preserve custody, required evidence,
candidate caps, and Direct default behavior. Then rerun this exact installed
preflight. Make a live call only if the installed planner selects Graph with a
verified relationship child.

## Files changed

- `docs/goals/retrievel-adaptive-pipeline-v1/notes/T220-installed-canary.md`
- `docs/goals/retrievel-adaptive-pipeline-v1/state.yaml`
