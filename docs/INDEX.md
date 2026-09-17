# VelGraphing Repository Index

Use this page to locate current product source. Retained goal and benchmark
evidence is historical evidence, not current product truth or performance proof.
Raw local provider reports under `/reports/` remain excluded from the public
repository.

## Product Map

| Concern | Canonical source |
| --- | --- |
| Core graph and retrieval APIs | `../packages/core/` |
| Portable contracts | `../contracts/core/` |
| Knowledge Compiler adapter | `../adapters/knowledge-compiler/` |
| Orcastrata umbrella catalog intake | `integrations/ORCASTRATA_UMBRELLA_CATALOG.md` |
| Public commands | `../plugins/graph-engineering/commands/` |
| User-facing skills | `../plugins/graph-engineering/skills/` |
| Generated plugin runtime | `../plugins/graph-engineering/runtime/` |
| Projection ownership | `architecture/SOURCE_OWNERSHIP_AND_PORTABILITY.md` |
| Package identity | `architecture/PACKAGING_AND_PARITY.md` |
| Compact benchmark evidence | `../benchmarks/README.md` |
| Pre-publication red-team | `reviews/velgraphing-prepublication-red-team-2026-09-02/report-source.md` |

## Validation

```sh
PYTHONDONTWRITEBYTECODE=1 npm test
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/project_portable_plugin.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package/verify_source_package_parity.py
```

The graph is a derived navigation view. Repository source remains canonical.
