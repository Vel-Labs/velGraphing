# RetrieVel 0.2 Release

## Objective

Prepare a compatibility-preserving RetrieVel 0.2 release candidate from the
current VelGraphing main line, prove the installed product path, complete the
bounded cross-corpus evaluation, resolve independent audit findings, and leave
a merge-ready or released candidate without unsupported performance claims.

## Original Request

Begin the release work, use parallel workflows where they help, use the
supplied Luna implementation task, reduce legacy VelGraphing task clutter, and
move the evolved product toward packaging, refreshed documentation, expanded
benchmarking, independent audit, and release under the proposed RetrieVel name.

## Intake Summary

- Input shape: `existing_plan`
- Audience: RetrieVel users, contributors, and release operators
- Authority: `approved`
- Proof type: `test`
- Completion proof: A clean, reviewable candidate passes package parity,
  clean-install and installed-command checks, the bounded evaluation contract,
  independent audit, and the final release checklist.
- Goal oracle: The release candidate installs from its packaged bytes in a
  fresh environment, exposes the documented commands, preserves offline and
  fallback behavior, records complete evaluation telemetry, and contains only
  supportable public claims.
- Likely misfire: Rename documentation and pass unit tests while leaving the
  installed package, measurement transport, benchmark, or public claims stale.
- Blind spots considered: Name clearance, compatibility IDs, historical
  benchmark preservation, provider-performance publication limits, complete
  wall time, all-model usage, worktree drift, and sidebar task lifecycle.
- Existing plan facts: Keep `graph-engineering`, `/graph-*`, Python imports,
  schemas, and the `velGraphing` repository name stable for 0.2.x. Use
  RetrieVel as the working display name. Separate documentation, package,
  installed-path, measurement, benchmark, audit, and release gates.

## Goal Oracle

The oracle for this goal is:

`A clean RetrieVel 0.2 candidate is installed and exercised from packaged bytes, passes source/package parity and release validation, completes the frozen cross-corpus four-arm study with required telemetry and bounded live calls, survives independent audit, and publishes no claim beyond retained evidence.`

## Goal Kind

`existing_plan`

## Current Tranche

Complete the identity and documentation foundation on the isolated release
branch. Then continue through package, installed-path, measurement, benchmark,
audit, and release slices without rewriting frozen historical evidence.

## Non-Negotiable Constraints

- Keep repository source authoritative and direct fallback available.
- Keep package/plugin ID `graph-engineering`, `/graph-*` commands, imports,
  schemas, and the repository name stable for 0.2.x.
- Do not alter frozen benchmark evidence in place.
- Do not publish provider-specific performance without separate permission.
- Use one canonical writer at a time. Parent owns integration and acceptance.
- Use exact live-call budgets, no silent retry, and no credential disclosure.
- Do not claim generalized correctness, speed, token, or cost improvement from
  a small diagnostic result.

## Stop Rule

Stop only when a final audit proves the full original outcome is complete, or
when the only remaining action requires an exact human approval or external
state change and no safe local work remains.

## Canonical Board

Machine truth lives at:

`docs/goals/retrievel-release-v1/state.yaml`

## Run Command

```text
Codex: /goal Follow docs/goals/retrievel-release-v1/goal.md.
Claude Code: /goalbuddy Follow docs/goals/retrievel-release-v1/goal.md.
```

