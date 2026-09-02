# Repository Readiness

Use `graphctl.py readiness` to build one deterministic report from an explicit
read policy. The report contains the scan policy, file index, local Markdown
path links, findings, and advisory recommendations.

The command writes JSON to standard output. It does not write a report file.
It reads only the relative `--include` paths under the exact `--root`.

## Boundary

- Declare each file or directory with `--include`.
- Use `--policy-status complete` only after a human reviews the include set.
- The default policy status is `incomplete`. This produces `unknown`.
- Hidden paths are excluded. A hidden include is rejected.
- Symlinks, hardlinks, path aliases, traversal, non-regular files, missing
  includes, and oversized files are rejected.
- The default file limit is 1 MiB. Use `--max-file-bytes` to set a smaller or
  larger explicit limit.
- `--source-revision` and `--source-observed-at` are caller declarations. The
  command does not inspect Git or infer freshness.
- A recommendation always requires human authority. It always has
  `auto_apply: false`.

The report is a derived view. It does not prove semantic quality, task
correctness, installation, adoption, publication, or repository acceptance.
It does not detect insufficiency autonomously. It reports only the declared
scan and the fixed structural checks.

## Roles

The index assigns one deterministic role to each file. Roles include root or
nested instructions, overview, manifest, workflow, plan, task truth, contract,
validation test, validation script, and source.

The command extracts inline local Markdown path links. It does not fetch URLs.
It does not validate heading anchors. A link outside the declared scan is
`unscanned` or `outside_root`. A missing target inside a declared directory is
`broken`.

## Examples

Run an incomplete scan. The status is `unknown` even when no other issue is
present.

```sh
python3 scripts/graphctl.py readiness \
  --root /path/to/project \
  --include README.md \
  --include src
```

Run a human-reviewed complete scan with caller-declared source identity.

```sh
python3 scripts/graphctl.py readiness \
  --root /path/to/project \
  --include . \
  --policy-status complete \
  --source-revision candidate-123 \
  --source-observed-at 2026-08-27T12:00:00Z
```

Capture stdout only when the current task grants authority for the target
file.

```sh
python3 scripts/graphctl.py readiness \
  --root /path/to/project \
  --include . > readiness-report.json
```

Shell redirection is outside the command. The command never creates or changes
a repository file.
