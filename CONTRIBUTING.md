# Contributing

Thank you for improving RetrieVel. Keep changes source-bound, small, and
readable. Repository source is authoritative; generated plugin runtime files
must be regenerated from source.

## Local setup

Use Python 3.11 or newer and a repository-local environment:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Before opening a change

Run the focused checks for the files you changed. For a normal product change,
run the full local suite and the package projection checks:

```sh
PYTHONDONTWRITEBYTECODE=1 npm test
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/package/project_portable_plugin.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/package/verify_source_package_parity.py
git diff --check
```

Do not edit `plugins/graph-engineering/runtime/` by hand. Do not add network,
provider, daemon, database, crawler, federation, or silent repository-write
behavior. Add tests for changed behavior and state any skipped validation.

## Pull requests

Describe the behavior changed, files changed, commands run, and remaining
risks. Keep benchmark claims tied to retained evidence. Do not include private
repository content, secrets, credentials, or source bodies in exported graph
artifacts or issue reports.
