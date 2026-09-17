# Orcastrata Umbrella Catalog Adapter V1

This deterministic comparison uses one frozen synthetic producer-shaped source.
It checks five exact facts and one source location through Direct and
catalog-assisted routes. It also verifies that stale source returns `defer`
without a graph or answer.

Run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/benchmarks/orcastrata_umbrella_catalog_adapter_v1.py
```

The comparison measures adapter delivery only. It does not measure model answer
quality or prove a context, token, latency, or cost improvement. `source_reads`
counts file-content reads made by each route. Catalog input bytes are reported
separately from source bytes.
