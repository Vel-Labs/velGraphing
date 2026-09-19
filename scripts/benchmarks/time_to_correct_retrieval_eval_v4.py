#!/usr/bin/env python3
"""Post-hoc retrieval diagnostics. No retrieval, provider, or source-body access.

A caller must freeze candidate bytes before giving the evaluator separate labels.
The expected hash detects a changed artifact; it is NOT proof of sandboxing or
of the selector's earlier blindness. Run selection without an oracle mount.
All recall below is source-path/range coverage, not semantic fact coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, Sequence

VERSION = "velgraphing-retrieval-eval-v4"
ROUTES = {"direct", "tag_index", "typed_graph", "typed_graph_no_edges",
          "typed_graph_no_expansion"}
PRODUCTION_STUDY = "velgraphing-v4-six-task-production"
FIXTURE_STUDY = "unit-fixture"
PRODUCTION_TASKS = {"C-01", "C-02", "S-01", "L-01", "M-01", "M-02"}
CONTROL_KEYS = {"seed_record_ids", "seed_limit", "shortlist_byte_budget",
                "derived_edge_count", "source_bound_expansion", "expand_one_hop"}
FORBIDDEN_CANDIDATE_KEYS = {"oracle", "labels", "acceptable_spans", "critical_facts",
                            "graph_expected", "answer", "provider_response", "score"}
MAX_INPUT_BYTES = 16 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class EvaluationError(ValueError):
    pass


def exact_keys(row: Any, keys: set[str]) -> None:
    if type(row) is not dict or set(row) != keys:
        raise EvaluationError("invalid_schema")


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output = {}
    for key, value in pairs:
        if key in output:
            raise EvaluationError("duplicate_json_key")
        output[key] = value
    return output


def reject_constant(_: str) -> None:
    raise EvaluationError("nonfinite_json")


def decode(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                           parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise EvaluationError("invalid_json") from None
    if type(value) is not dict:
        raise EvaluationError("invalid_schema")
    return value


def read_input(path: Path) -> bytes:
    """Regular, single-link input; the explicitly chosen parent is trusted."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise EvaluationError("secure_read_unsupported")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > MAX_INPUT_BYTES):
            raise EvaluationError("invalid_input_file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) > MAX_INPUT_BYTES or identity(before) != identity(after):
            raise EvaluationError("input_changed_or_oversize")
        return raw
    finally:
        os.close(fd)


def valid_path(path: Any) -> str:
    if (type(path) is not str or not path or "\\" in path or ":" in path
            or any(ord(ch) < 32 for ch in path)):
        raise EvaluationError("invalid_source_path")
    value = PurePosixPath(path)
    if (value.is_absolute() or value.as_posix() != path
            or any(part in {".", ".."} for part in value.parts)):
        raise EvaluationError("invalid_source_path")
    return path


def valid_sha(value: Any) -> str:
    if type(value) is not str or not SHA.fullmatch(value):
        raise EvaluationError("invalid_sha256")
    return value


def positive_int(value: Any, *, zero: bool = False) -> int:
    if type(value) is not int or value < (0 if zero else 1):
        raise EvaluationError("invalid_integer")
    return value


def source_map(sources: Any) -> dict[str, tuple[str, int]]:
    if type(sources) is not list:
        raise EvaluationError("invalid_sources")
    result = {}
    for row in sources:
        exact_keys(row, {"path", "source_sha256", "byte_length"})
        path = valid_path(row["path"])
        if path in result:
            raise EvaluationError("duplicate_source")
        result[path] = (valid_sha(row["source_sha256"]), positive_int(row["byte_length"], zero=True))
    return result


def validate_span(row: Mapping[str, Any], sources: Mapping[str, tuple[str, int]]) -> None:
    path = valid_path(row.get("path"))
    sha = valid_sha(row.get("source_sha256"))
    start = positive_int(row.get("byte_start"), zero=True)
    end = positive_int(row.get("byte_end"))
    if path not in sources or sources[path][0] != sha:
        raise EvaluationError("source_outside_snapshot")
    if not start < end <= sources[path][1]:
        raise EvaluationError("invalid_span")


def reject_oracle_fields(value: Any) -> None:
    if type(value) is dict:
        if set(value) & FORBIDDEN_CANDIDATE_KEYS:
            raise EvaluationError("oracle_shaped_field")
        for item in value.values():
            reject_oracle_fields(item)
    elif type(value) is list:
        for item in value:
            reject_oracle_fields(item)


def validate_candidates(value: dict[str, Any]) -> dict[str, Any]:
    reject_oracle_fields(value)
    exact_keys(value, {"schema_version", "study_id", "selector_commit", "runs"})
    if (value["schema_version"] != "velgraphing-ranked-candidates-v4"
            or value["study_id"] not in {FIXTURE_STUDY, PRODUCTION_STUDY}
            or type(value["selector_commit"]) is not str
            or not COMMIT.fullmatch(value["selector_commit"])
            or type(value["runs"]) is not list or not value["runs"]):
        raise EvaluationError("invalid_candidate_artifact")
    keys = set()
    for run in value["runs"]:
        exact_keys(run, {"task_id", "route", "source_snapshot_sha256", "sources",
                         "candidates", "controls", "metrics"})
        if (type(run["task_id"]) is not str or not run["task_id"]
                or type(run["route"]) is not str or run["route"] not in ROUTES
                or type(run["candidates"]) is not list):
            raise EvaluationError("invalid_run")
        key = run["task_id"], run["route"]
        if key in keys:
            raise EvaluationError("duplicate_run")
        keys.add(key)
        valid_sha(run["source_snapshot_sha256"])
        sources = source_map(run["sources"])
        exact_keys(run["controls"], CONTROL_KEYS)
        controls = run["controls"]
        if (type(controls["seed_record_ids"]) is not list
                or any(type(item) is not str or not item for item in controls["seed_record_ids"])
                or len(controls["seed_record_ids"]) != len(set(controls["seed_record_ids"]))
                or type(controls["source_bound_expansion"]) is not bool
                or type(controls["expand_one_hop"]) is not bool):
            raise EvaluationError("invalid_controls")
        positive_int(controls["seed_limit"])
        positive_int(controls["shortlist_byte_budget"])
        positive_int(controls["derived_edge_count"], zero=True)
        expected_flags = {
            "direct": (False, False),
            "tag_index": (False, False),
            "typed_graph": (True, True),
            "typed_graph_no_edges": (True, True),
            "typed_graph_no_expansion": (True, False),
        }[run["route"]]
        if (controls["source_bound_expansion"], controls["expand_one_hop"]) != expected_flags:
            raise EvaluationError("route_control_mismatch")
        ids = set()
        for candidate in run["candidates"]:
            exact_keys(candidate, {"id", "path", "source_sha256", "byte_start", "byte_end", "required"})
            if (type(candidate["id"]) is not str or not candidate["id"]
                    or candidate["id"] in ids or type(candidate["required"]) is not bool):
                raise EvaluationError("invalid_candidate_identity")
            ids.add(candidate["id"])
            validate_span(candidate, sources)
        if (len(run["candidates"]) > controls["seed_limit"]
                or sum(item["byte_end"] - item["byte_start"] for item in run["candidates"])
                > controls["shortlist_byte_budget"]):
            raise EvaluationError("shortlist_control_mismatch")
        exact_keys(run["metrics"], {"source_operations", "cold_ns", "warm_ns", "retrieval_ns",
                                    "expansion_ns", "fallback_ns", "source_failures", "authority_failures"})
        for metric in run["metrics"].values():
            if metric is not None:
                positive_int(metric, zero=True)
    by_task: dict[str, list[dict[str, Any]]] = {}
    for run in value["runs"]:
        by_task.setdefault(run["task_id"], []).append(run)
    for task_runs in by_task.values():
        first = task_runs[0]
        for run in task_runs[1:]:
            if (run["source_snapshot_sha256"] != first["source_snapshot_sha256"]
                    or source_map(run["sources"]) != source_map(first["sources"])):
                raise EvaluationError("paired_snapshot_mismatch")
            if (run["controls"]["seed_limit"] != first["controls"]["seed_limit"]
                    or run["controls"]["shortlist_byte_budget"]
                    != first["controls"]["shortlist_byte_budget"]):
                raise EvaluationError("paired_control_mismatch")
        typed = [run for run in task_runs if run["route"].startswith("typed_graph")]
        if typed:
            typed_seeds = {tuple(run["controls"]["seed_record_ids"]) for run in typed}
            typed_edges = {run["controls"]["derived_edge_count"] for run in typed}
            if len(typed_seeds) != 1:
                raise EvaluationError("typed_seed_mismatch")
            if len(typed_edges) != 1:
                raise EvaluationError("typed_edge_count_mismatch")
    if value["study_id"] == PRODUCTION_STUDY:
        expected = {(task, route) for task in PRODUCTION_TASKS for route in ROUTES}
        if keys != expected or len(value["runs"]) != 30:
            raise EvaluationError("production_run_matrix_mismatch")
        for run in value["runs"]:
            if (run["controls"]["seed_limit"] != 12
                    or run["controls"]["shortlist_byte_budget"] != 24_576):
                raise EvaluationError("production_control_mismatch")
    return value


def validate_labels(value: dict[str, Any], candidates: Mapping[str, Any]) -> dict[str, Any]:
    exact_keys(value, {"schema_version", "tasks"})
    if value["schema_version"] != "velgraphing-span-labels-v4" or type(value["tasks"]) is not dict:
        raise EvaluationError("invalid_label_artifact")
    runs = {}
    for run in candidates["runs"]:
        old = runs.setdefault(run["task_id"], run)
        if (old["source_snapshot_sha256"] != run["source_snapshot_sha256"]
                or source_map(old["sources"]) != source_map(run["sources"])):
            raise EvaluationError("paired_snapshot_mismatch")
    if set(value["tasks"]) != set(runs):
        raise EvaluationError("label_task_mismatch")
    for task, row in value["tasks"].items():
        exact_keys(row, {"source_snapshot_sha256", "groups"})
        if row["source_snapshot_sha256"] != runs[task]["source_snapshot_sha256"]:
            raise EvaluationError("label_snapshot_mismatch")
        if type(row["groups"]) is not list or not row["groups"]:
            raise EvaluationError("missing_span_labels")
        ids = set()
        for group in row["groups"]:
            exact_keys(group, {"id", "critical", "acceptable_spans"})
            if (type(group["id"]) is not str or not group["id"] or group["id"] in ids
                    or (group["critical"] is not None and type(group["critical"]) is not bool)
                    or type(group["acceptable_spans"]) is not list or not group["acceptable_spans"]):
                raise EvaluationError("invalid_label_group")
            ids.add(group["id"])
            for span in group["acceptable_spans"]:
                exact_keys(span, {"path", "source_sha256", "byte_start", "byte_end"})
                validate_span(span, source_map(runs[task]["sources"]))
    return value


def frozen_prefix(rows: Sequence[Mapping[str, Any]], k: int, budget: int) -> list[Mapping[str, Any]]:
    """Diagnostic prefix, NOT a deployable selector. Never consults labels.

    Stop before an overflowing whole candidate. Do not skip ahead or cut text.
    Required IDs outside this prefix are reported; this prefix is never an answer.
    """
    retained, used = [], 0
    for row in rows[:k]:
        size = row["byte_end"] - row["byte_start"]
        if used + size > budget:
            break
        retained.append(row)
        used += size
    return retained


def overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return (a["path"] == b["path"] and a["source_sha256"] == b["source_sha256"]
            and max(a["byte_start"], b["byte_start"]) < min(a["byte_end"], b["byte_end"]))


def covers(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return (a["path"] == b["path"] and a["source_sha256"] == b["source_sha256"]
            and a["byte_start"] <= b["byte_start"] and a["byte_end"] >= b["byte_end"])


def unique_bytes(rows: Sequence[Mapping[str, Any]]) -> int:
    groups: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for row in rows:
        groups.setdefault((row["path"], row["source_sha256"]), []).append((row["byte_start"], row["byte_end"]))
    total = 0
    for spans in groups.values():
        right = -1
        for start, end in sorted(spans):
            total += max(0, end - max(start, right))
            right = max(right, end)
    return total


def score_prefix(rows: Sequence[Mapping[str, Any]], groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    hits, full, first = [], [], None
    for group in groups:
        hit = any(overlap(candidate, span) for candidate in rows for span in group["acceptable_spans"])
        # Single-span containment is deliberately stricter than a fragmented union.
        complete = any(covers(candidate, span) for candidate in rows for span in group["acceptable_spans"])
        hits.append(hit)
        full.append(complete)
    for rank, candidate in enumerate(rows, 1):
        if any(overlap(candidate, span) for group in groups for span in group["acceptable_spans"]):
            first = rank
            break
    critical_indices = [i for i, group in enumerate(groups) if group["critical"] is True]
    critical_known = all(group["critical"] is not None for group in groups) and bool(critical_indices)
    total = sum(row["byte_end"] - row["byte_start"] for row in rows)
    return {
        "candidate_count": len(rows), "excerpt_bytes": total,
        "acceptable_group_count": len(groups), "overlap_hit_groups": sum(hits),
        "acceptable_span_group_overlap_recall": sum(hits) / len(groups),
        "single_candidate_full_span_group_recall": sum(full) / len(groups),
        "critical_span_group_overlap_recall": (sum(hits[i] for i in critical_indices) / len(critical_indices)
                                                 if critical_known else None),
        "first_overlapping_rank": first, "reciprocal_first_overlap_rank": 1 / first if first else 0.0,
        "unique_paths": len({row["path"] for row in rows}),
        "repeated_range_byte_fraction": (total - unique_bytes(rows)) / total if total else 0.0,
        "semantic_fact_recall": None, "candidate_ndcg": None,
    }


def evaluate(candidate_raw: bytes, expected_sha256: str, label_raw: bytes,
             ks: Sequence[int], budgets: Sequence[int]) -> dict[str, Any]:
    if hashlib.sha256(candidate_raw).hexdigest() != valid_sha(expected_sha256):
        raise EvaluationError("candidate_artifact_changed")
    candidates = validate_candidates(decode(candidate_raw))
    labels = validate_labels(decode(label_raw), candidates)
    for value in (*ks, *budgets):
        positive_int(value)
    results = []
    for run in candidates["runs"]:
        for k in sorted(set(ks)):
            for budget in sorted(set(budgets)):
                selected = frozen_prefix(run["candidates"], k, budget)
                selected_ids = {row["id"] for row in selected}
                missing_required = [row["id"] for row in run["candidates"]
                                    if row["required"] and row["id"] not in selected_ids]
                results.append({"task_id": run["task_id"], "route": run["route"], "k": k,
                                "byte_budget": budget, "missing_required_ids_in_diagnostic_prefix": missing_required,
                                **score_prefix(selected, labels["tasks"][run["task_id"]]["groups"]),
                                "observed_route_metrics": run["metrics"]})
    return {"schema_version": VERSION, "candidate_artifact_sha256": expected_sha256,
            "labels_sha256": hashlib.sha256(label_raw).hexdigest(),
            "selector_commit": candidates["selector_commit"], "provider_calls": 0,
            "candidate_source_bytes_independently_revalidated": False,
            "oracle_isolation_proven_by_this_scorer": False,
            "interpretation": "post_hoc_path_and_range_diagnostics_not_semantic_support_or_product_acceptance",
            "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--expected-candidates-sha256", required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, nargs="+", default=[4, 6, 12])
    parser.add_argument("--byte-budgets", type=int, nargs="+", default=[8192, 16384, 24576])
    args = parser.parse_args()
    try:
        result = evaluate(read_input(args.candidates), args.expected_candidates_sha256,
                          read_input(args.labels), args.k, args.byte_budgets)
        # Exclusive creation prevents accidentally replacing a sealed result.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
    except (EvaluationError, OSError) as error:
        parser.exit(2, f"retrieval evaluation failed: {type(error).__name__}: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
