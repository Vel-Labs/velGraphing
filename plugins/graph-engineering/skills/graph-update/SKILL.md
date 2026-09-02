---
name: graph-update
description: Refresh an existing project-owned Graph Engineering view after declared source changes. Use only with explicit current task authority and a source-bound update path.
---

# Graph Update

Read the nearest instruction files, [the Graph Engineering skill](../graph-engineering/SKILL.md), the current project graph profile or export, and the declared source changes.

## Workflow

1. Confirm the graph owner, namespace, source snapshot, update authority, and changed paths.
2. Refuse an update when the existing graph is unbound, stale, above its sensitivity ceiling, or owned by another project.
3. Run `scripts/graphctl.py readiness` with explicit include paths. Do not crawl an unspecified repository.
4. If the project defines an update procedure, refresh only the changed derived records and declared dependents. Otherwise return a preview for a full rebuild; do not invent incremental persistence.
5. Compare old and new exports with `scripts/graphctl.py diff` when both exports exist.
6. Validate the updated profile or export before reporting it.

Keep source files authoritative. Preserve source paths, hashes, ranges, owner,
evidence state, and sensitivity on derived records. Do not silently merge stale
and current evidence. Do not add hooks, watchers, daemons, databases,
schedulers, cloud dependencies, or cross-project relations.

Report the source snapshot, changed paths, records refreshed, validation result,
unknowns, and remaining direct-read fallback. An update result is not proof of
task correctness, installation, federation, execution, or acceptance.
