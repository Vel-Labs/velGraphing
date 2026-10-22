# Frozen four-arm package binding

`release-manifest.json` is the unchanged Git blob from
`4a4c7bf4f8f000db507117909610fb25bf929949` at
`plugins/graph-engineering/.codex-plugin/release-manifest.json`.
It binds the historical study to package `graph-engineering` 0.1.6, candidate
`f47d377d6a51d66cd6b790f5d4a900f41719877b84def61e08bc548a5673e4c1`.

The `inputs/` files are the exact public source/corpus closure required by the
study validator, retained from `417523f9cfa9b39033f2ecaab58346ff5577ce8d`.
The public boundary tests stage these frozen files with this manifest and run
the real validation and Git ancestry checks. The inputs are hash-validation
fixtures; they are not imported or executed. This is not an executable
historical runtime or a new benchmark result. A new package must not inherit this study identity.
