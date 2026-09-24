# Product Identity And Compatibility

## Current identity

The public display name is RetrieVel. Use “RetrieVel, formerly VelGraphing”
when a transition note needs to connect the new name to earlier material.

| Surface | Stable identifier or rule |
| --- | --- |
| Public display name | RetrieVel |
| Compatibility phrase | RetrieVel, formerly VelGraphing |
| GitHub repository name | `velGraphing` through the 0.2.x line |
| Plugin and Python package ID | `graph-engineering` |
| Public commands | Existing `/graph-*` names |
| Python imports | Existing import names |
| Schemas and internal compatibility identifiers | Existing identifiers, including `graph-engineering-release-manifest-v1` |

The display name does not change repository URLs, plugin coordinates, package
metadata, imports, commands, schema names, or serialized identifiers. Historical
benchmark directories and frozen labels also keep their original names.

## Migration rules

- Use RetrieVel for current product descriptions.
- Use the compatibility phrase when the previous name matters to readers.
- Keep `velGraphing` as the repository name for 0.2.x.
- Keep `graph-engineering` as the plugin and Python package ID.
- Do not rename `/graph-*` commands, Python imports, schemas, or internal IDs
  as part of the display-name change.
- Keep existing links, package coordinates, and historical evidence paths
  intact. Update only their human-readable labels when needed.
- Treat any repository rename or package-ID migration as a separate decision.
  It requires an explicit compatibility plan and validation of installation,
  packaging, parity, release metadata, and existing consumers.

This first 0.2.0 slice changes documentation only. It does not bump the package
version or change runtime behavior. It does not claim general wall-clock,
correctness, token, cost, or provider-performance improvements. The retained
four-arm result is directional diagnostic evidence only. The corpus pilot does
not establish wall-clock savings. See the [benchmark evidence index](../../benchmarks/README.md)
for the retained result boundaries.
