# Knowledge Compiler Adapter

This adapter accepts one serialized `CompilerCandidateRecordV1`. It returns a
`GraphCandidateV1` envelope or a typed rejection.

The accepted envelope preserves the complete compiler candidate under
`compiler_candidate`. It always sets `eligibility` to `false`. Human review is
evidence only. A separate policy or verifier must make an admission decision.

The adapter is dependency-free. It does not read or write compiler storage. It
does not call compiler ingest, render, audit, qmd, or other compiler services.
