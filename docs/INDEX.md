# VelGraphing Repository Index

Use this page to locate current product source. Historical experiment boards,
versioned harnesses, traces, and model responses are not part of the public
repository.

## Product Map

| Concern | Canonical source |
| --- | --- |
| Core graph and retrieval APIs | `../packages/core/` |
| Portable contracts | `../contracts/core/` |
| Knowledge Compiler adapter | `../adapters/knowledge-compiler/` |
| Public commands | `../plugins/graph-engineering/commands/` |
| User-facing skills | `../plugins/graph-engineering/skills/` |
| Generated plugin runtime | `../plugins/graph-engineering/runtime/` |
| Projection ownership | `architecture/SOURCE_OWNERSHIP_AND_PORTABILITY.md` |
| Package identity | `architecture/PACKAGING_AND_PARITY.md` |
| Compact benchmark evidence | `../benchmarks/README.md` |

## Validation

```sh
PYTHONDONTWRITEBYTECODE=1 npm test
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/project_portable_plugin.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/verify_source_package_parity.py
```

The graph is a derived navigation view. Repository source remains canonical.
