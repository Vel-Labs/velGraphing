# T320 R7 terminal stop receipt

## Outcome

R7 stopped at the first grader failure. It produced no terminal trial and made
no Jev call. The predeclared terminal rule rejects another transport variant.

## Accepted benchmark transport

Benchmark commit `47c793673c397a59d2095489803cc1f5db612242`
stores exact assistant bytes as `assistant-response.raw`, validates one JSON
object against the frozen response contract and execution identity, and writes
a semantically equivalent canonical `draft.json`. Parent then uses the existing
attestation and response path.

Validation passed:

- 11 focused capture and attestation tests;
- 24 four-arm controller tests;
- historical bundle and R4/R5/R6 immutability checks;
- 32 accepted fresh task identities with exact `READY` and zero setup tools;
- one independent Luna freeze audit.

R7 lane-manifest SHA-256:
`08b413e8e80ac02e8ea4265869994797772d7d731f274364dd1e46bfbb441793`.

## Live evidence

The A-S-01 answer completed end to end.

- Answer task: `01a0c3c2-f98a-7280-ad26-49cd98395f76`
- Answer request bytes: `14473`
- Answer request SHA-256:
  `5e1846384b340c2898f4ef0e8e93fd48d80b94ebfbc82e1f3f652e309059ddc8`
- Raw answer SHA-256:
  `77b123cd2e978020fb7adc1d5e0a01c2b1207058f5624ab3547b2d23ca0c26c6`
- Canonical answer SHA-256:
  `0d98f54fa801e3837f5b62e61cbfe7c24655f301af39b9721ecea0e85173a945`
- Attestation SHA-256:
  `3d569d444478a656a1be5e62f7132a991522839fb215dc23b084824f672980b8`
- Answer tool calls: `0`

The controller then emitted the A-S-01 grader request.

- Grader task: `01a0c3c1-0499-7a02-b329-63e512b7f683`
- Grader request bytes: `3528`
- Grader request SHA-256:
  `36f9a35bbe1a1ff429081fb5a95b395b5ba87b5aa40dccbeeab730151942d7f2`
- Follow-up duration: `10575 ms`
- Follow-up status: `completed`
- Follow-up error: `null`
- Assistant, tool, and reasoning items: `0`

The coordinator did not capture, attest, respond, retry, replace, repair, or
dispatch a later task. The Parent stopped the exact controller process.

## Counts and interpretation

- Terminal trials: `0 of 16`
- Accepted answer calls: `1`
- Accepted grader calls: `0`
- Jev calls: `0`
- Retries, replacements, or answer repairs: `0`
- Provider usage or cost: none

This run validates the answer transport mechanism. It does not provide Graph,
Jev, correctness, token, cost, or wall-clock comparative evidence. The final
blocker is an empty host-native grader completion. Changing the grader model,
reusing another task, grading in Parent, or retrying would change the frozen
study and violate the terminal rule.
