---
name: graph-start
description: Prepare the smallest project-owned Graph Engineering setup from a read-only readiness report. Use for a setup preview or an explicitly approved repository-local graph; do not use for federation or silent mutation.
---

# Graph Start

Read the nearest instruction files and [the Graph Engineering skill](../graph-engineering/SKILL.md). Run its bundled `scripts/graphctl.py readiness` against explicit include paths before proposing changes.

## Workflow

1. Confirm the repository, canonical source owners, namespace, and current task authority.
2. Apply the graph-worthiness gate. Name the simpler direct baseline.
3. Run readiness for the exact include paths. Treat an incomplete scan as `unknown`.
4. Return a setup preview with the exact files, source references, validation commands, and rollback steps.
5. Require explicit approval before any repository-local write.
6. After approval, make only the previewed changes and validate the profile or export.

Do not create a second source of truth. Do not add hooks, daemons, crawlers,
databases, schedulers, cloud dependencies, or federation entries. A readiness
report and a validated graph are derived views. They do not prove task
correctness, installation, federation, execution, or acceptance.

Use `graph-steward` for workspace or cross-project federation.
