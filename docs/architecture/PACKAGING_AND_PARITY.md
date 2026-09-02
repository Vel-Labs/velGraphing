# Packaging And Parity

## Ownership

Canonical runtime source stays in `packages/core`, `contracts/core`, and
`adapters/knowledge-compiler`. The deterministic projector copies these files
to `plugins/graph-engineering/runtime`. Commands and skills under the plugin
are canonical package sources. The release manifest inventories every other
regular plugin file. It excludes only itself.

## Release Identity

The release manifest uses schema
`graph-engineering-release-manifest-v1`. It contains the canonical package name
and version, the canonical JSON SHA-256 of `projection-map.json`, and a sorted
inventory. Each inventory row has a normalized relative POSIX path, byte size,
and lowercase SHA-256. `candidate_sha256` is the SHA-256 of the canonical JSON
for these fields. It does not include itself.

Run this command only when the governed package bytes intentionally change:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/verify_source_package_parity.py --write-manifest
```

Run this command to verify the frozen source candidate without mutation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/verify_source_package_parity.py
```

The verifier compares each canonical projection source with its runtime copy.
It validates projection state. It also compares the release manifest with a
fresh package inventory. It rejects missing, extra, changed, duplicate,
escaping, symlink, hard-link, private-path, machine-specific, oversized, and
non-regular entries. It checks each named path component from the project root.
An intermediate directory cannot redirect a read outside the project.

## Proof Boundary

Parity proves only that the current project source and current plugin package
match the recorded candidate identity. Plugin manifest validation is a separate
source-package check. Neither result proves installation, installed bytes,
fresh-task loading, marketplace discovery, federation admission, publication,
provider execution, enterprise deployment, or AOL adoption. Installed-state
tests can use temporary fixtures only. They do not create installed proof.
