# Orcastrata Umbrella Catalog Adapter

This dependency-free adapter consumes the canonical Orcastrata JSONL catalog.
It validates the closed V1 shape and all catalog and record digests. If an
admitted source root is supplied, it also matches the raw projection receipt
and projection digests plus the graph and board digest bindings.

The V1 producer does not publish the source paths or digest rules needed to
recompute the underlying WorkGraph and GoalBuddy board digests. The adapter
therefore emits navigation-only records. It sets `eligible` to `false`, uses
`freshness: unknown`, and requires direct source fallback for consequential
claims. It never writes to Orcastrata, GoalBuddy, WorkGraph, or GitHub.
