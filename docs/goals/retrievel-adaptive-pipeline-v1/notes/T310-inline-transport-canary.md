# T310 inline transport canary receipt

## Outcome

Exact inline model input worked. The canary returned one valid answer object
with the exact execution identity and no tool call. The benchmark did not
proceed because the output used a valid but noncanonical JSON key order.

## Evidence

- Luna-medium task: `01a0c3b9-3309-7500-a3ad-6cc713dcf659`
- Setup response: exact `READY`
- Setup tool calls: `0`
- Inline request bytes: `14473`
- Inline request SHA-256:
  `b6cf1fc1fd7fc0eeb5efd8751aa68be8f52de75ed3a9193b42498fa72d31a1b0`
- Follow-up duration: `8519 ms`
- Follow-up status: `completed`
- Follow-up error: `null`
- Assistant items: `1`
- Tool calls: `0`
- Output bytes: `786`
- Output SHA-256:
  `591f2d3ee65167f5f260b26084014b5374a5b52259ef6c3733449d808057ffc6`
- Valid JSON: `true`
- Exact execution identity: `true`
- `model_calls_complete`: `true`
- `context_deliveries_complete`: `true`
- Usage: unavailable

The ignored canary receipt SHA-256 is
`f49c1a19ace2421abb38beca09c109b6ff345ffe7912dd54f6e1b367065f8e0f`.
No R7 task, controller, or provider call ran.

## Classification

This proves that the silent R5 and R6 completions came from the file-input
boundary, not the question, source context, Luna model, or output capture
concept. The remaining rejection is a benchmark serialization defect. JSON
object key order is not semantic model output.

T320 retains the exact raw assistant bytes as evidence, validates one JSON
object and its frozen schema and identity, then lets Parent serialize the
validated object canonically for the existing attestation path.
