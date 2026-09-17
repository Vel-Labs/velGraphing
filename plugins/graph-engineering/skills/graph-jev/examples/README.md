# Synthetic offline replay

These three source files and their candidate packet are authored test data.
`replay.json` is a handcrafted TypeSafe-shaped response, NOT a live Jev response.
Its zero usage values mean no provider was used, not that real inference is free.
Expected rerank: `c1, c0, c2`. Candidate `c2` is required and stays in position 2.
A changed query, model, source or rubric invalidates the request hash.
The parent operator guide contains runnable portable commands.
