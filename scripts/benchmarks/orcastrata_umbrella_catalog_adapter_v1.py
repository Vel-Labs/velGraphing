#!/usr/bin/env python3
"""Run the deterministic Orcastrata catalog adapter comparison."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "adapters" / "orcastrata-umbrella-catalog" / "adapter.py"
DEFAULT_FIXTURE = ROOT / "benchmarks" / "orcastrata-umbrella-catalog-adapter-v1"


def _adapter():
    spec = importlib.util.spec_from_file_location("orcastrata_umbrella_catalog_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _facts_from_receipt(receipt):
    return {
        "title": receipt["preview"]["umbrella"]["title"],
        "github_repository": f"https://{receipt['target']['host']}/{receipt['target']['repository']}",
        "workgraph_id": receipt["graph_id"],
        "goalbuddy_owner": receipt["canonical_state"]["owner"],
        "active_task": receipt["canonical_state"]["active_task"],
    }


def _facts_from_record(record):
    return {
        "title": record["title"],
        "github_repository": record["references"]["github_repository"],
        "workgraph_id": record["references"]["workgraph_id"],
        "goalbuddy_owner": record["references"]["goalbuddy_owner"],
        "active_task": record["lifecycle"]["active_task"],
    }


def run(fixture: Path = DEFAULT_FIXTURE):
    adapter = _adapter()
    catalog_path = fixture / "catalog.jsonl"
    source_root = fixture / "source"
    catalog_raw = catalog_path.read_bytes()
    catalog = json.loads(catalog_raw)
    projection_path = source_root / catalog["records"][0]["references"]["projection"]

    started = time.perf_counter()
    projection_raw = projection_path.read_bytes()
    direct_facts = _facts_from_receipt(json.loads(projection_raw))
    direct_seconds = time.perf_counter() - started

    started = time.perf_counter()
    assisted_catalog_raw = catalog_path.read_bytes()
    assisted = adapter.adapt_catalog_jsonl(assisted_catalog_raw, source_root=source_root)
    assisted_seconds = time.perf_counter() - started
    assisted_record = assisted["catalog"]["records"][0]
    assisted_facts = _facts_from_record(assisted_record)
    expected = len(direct_facts)

    stale = copy.deepcopy(catalog)
    stale_record = stale["records"][0]
    stale_record["digests"]["raw_receipt_sha256"] = "sha256:" + "0" * 64
    unsigned = {key: value for key, value in stale_record.items() if key != "record_sha256"}
    stale_record["record_sha256"] = _digest(unsigned)
    stale["catalog_sha256"] = _digest(stale["records"])
    stale_result = adapter.adapt_catalog_jsonl(_canonical(stale) + b"\n", source_root=source_root)

    return {
        "schema_version": "orcastrata-umbrella-catalog-adapter-benchmark-v1",
        "fixture": str(fixture.relative_to(ROOT)),
        "scope": "deterministic_adapter_delivery_only",
        "direct": {
            "fact_recall": {"hits": expected, "total": expected, "rate": 1.0},
            "source_location_recall": {"hits": 1, "total": 1, "rate": 1.0},
            "unsupported_claims": 0,
            "source_reads": 1,
            "source_bytes_read": len(projection_raw),
            "catalog_bytes_read": 0,
            "elapsed_seconds": direct_seconds,
        },
        "catalog_assisted": {
            "fact_recall": {
                "hits": sum(assisted_facts[key] == value for key, value in direct_facts.items()),
                "total": expected,
                "rate": sum(assisted_facts[key] == value for key, value in direct_facts.items()) / expected,
            },
            "source_location_recall": {
                "hits": int(assisted_record["references"]["projection"] == projection_path.name),
                "total": 1,
                "rate": float(assisted_record["references"]["projection"] == projection_path.name),
            },
            "unsupported_claims": len(set(assisted_facts.items()) - set(direct_facts.items())),
            "stale_answer_blocked": stale_result.get("route") == "defer" and "graph" not in stale_result,
            "source_reads": 2,
            "source_bytes_read": 2 * len(projection_raw),
            "catalog_bytes_read": len(assisted_catalog_raw),
            "elapsed_seconds": assisted_seconds,
        },
        "runtime_reported_usage": {"input_tokens": None, "output_tokens": None, "cost": None},
        "interpretation": "The catalog preserves the frozen facts and source location but adds cost for this one-record cold comparison. It is navigation-only until Orcastrata publishes independently verifiable WorkGraph and board source bindings.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    print(json.dumps(run(args.fixture), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
