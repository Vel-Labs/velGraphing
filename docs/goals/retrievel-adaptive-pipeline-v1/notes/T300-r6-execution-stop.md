# T300 R6 execution stop receipt

## Outcome

R6 stopped at the first lane failure. It produced no benchmark result and made
no Jev or grader call.

## Accepted transport repair

Benchmark commit `b7ca78774cbb49216b662a89d5de078444fb6059`
adds a Parent-owned `capture` command. It accepts a completed host response on
standard input, rejects empty or wrong-identity data, writes exact canonical
bytes atomically, and leaves the existing attestation and response path intact.

A fresh Luna-medium canary returned 233 canonical JSON bytes with zero tool
calls. Exact persistence, identity binding, empty-response rejection, and
immutable attestation passed. The R6 freeze then passed 10 focused transport
tests, 24 controller tests, projector idempotence, historical validation, and
one independent Luna review. Thirty-two fresh lane setup tasks returned exact
`READY` with zero tool calls.

## Live failure

- R6 run root: `successor-live-r6-6b9d120`
- Lane-manifest SHA-256:
  `3e5716dc13ae0881bd36fcdfafed7cbbc34fe474bb6048a731edd7ef188c9f5b`
- Request-byte-set SHA-256:
  `80b3411f0d30600bc302a59debe36fe66734e4aceca0da6afdae303dc096af94`
- A-S-01 request bytes: `14473`
- A-S-01 request SHA-256:
  `b6cf1fc1fd7fc0eeb5efd8751aa68be8f52de75ed3a9193b42498fa72d31a1b0`
- Frozen Luna answer task: `01a0c3ac-04cd-7cc2-9679-c0149d0836e8`

The task accepted the follow-up and completed in 14.174 seconds with no error,
assistant response, or tool marker. The coordinator therefore had no bytes to
capture. It did not attest, respond, dispatch the grader, retry, repair, or
replace the task. The controller was stopped and exited `2` with
`single_answer_grade_required`.

## Counts

- Terminal trials: 0 of 16
- Answer requests: 1
- Accepted answer responses: 0
- Grader requests: 0
- Jev calls: 0
- Retries or replacements: 0
- Provider usage or cost: none

## Classification and redesign

R5 and R6 have the same failure signature. Both real lanes asked the task to
read a request file and both ended silently before a tool call. The successful
R6 canary supplied its small input directly in the host message. This isolates
model-input delivery as the next architecture boundary.

T310 sends the exact frozen request bytes inline through the host message and
keeps the accepted Parent-owned output capture. If one exact A-S-01 inline
canary fails, this host-task benchmark architecture is terminally rejected.
