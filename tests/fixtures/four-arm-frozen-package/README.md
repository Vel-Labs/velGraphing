# Frozen four-arm package binding

`release-manifest.json` is the unchanged Git blob from
`4a4c7bf4f8f000db507117909610fb25bf929949` at
`plugins/graph-engineering/.codex-plugin/release-manifest.json`.
It binds the historical study to package `graph-engineering` 0.1.6, candidate
`f47d377d6a51d66cd6b790f5d4a900f41719877b84def61e08bc548a5673e4c1`.

The public boundary tests stage this manifest with the unchanged source and
corpus files that the study binds. They run the real validation and Git ancestry
checks. This fixture is package metadata, not an executable historical runtime
or a new benchmark result. A new package must not inherit this study identity.
