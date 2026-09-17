"""Validate Orcastrata umbrella JSONL and map it to navigation-only records."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any


CATALOG_TYPE = "orcastrata_umbrella_catalog_v1"
RECEIPT_TYPE = "orcastrata_github_umbrella_projection_receipt_v1"
GRAPH_SCHEMA = "OrcastrataUmbrellaCatalogGraphV1"
REJECTION_SCHEMA = "OrcastrataUmbrellaCatalogRejectionV1"

_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TOP_FIELDS = {
    "schema_version", "artifact_type", "manifest_sha256", "record_count",
    "catalog_sha256", "records",
}
_RECORD_FIELDS = {
    "schema_version", "record_type", "umbrella_id", "title", "summary",
    "tags", "lifecycle", "references", "digests", "evidence_state",
    "sensitivity", "exportable", "record_sha256",
}
_RECEIPT_FIELDS = {
    "artifact_type", "canonical_state", "effect_boundary", "graph_id",
    "graph_sha256", "preview", "projection_sha256", "schema_version",
    "status", "target",
}


class CatalogError(ValueError):
    def __init__(self, code: str, field: str = "$") -> None:
        super().__init__(f"{code}: {field}")
        self.code = code
        self.field = field


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CatalogError("canonical_json_invalid") from error


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError("json_duplicate_key")
        result[key] = value
    return result


def _closed(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CatalogError("shape_invalid", path)
    return value


def _text(value: Any, path: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise CatalogError("text_invalid", path)
    return value


def _relative_path(value: Any, path: str) -> str:
    text = _text(value, path, 1024)
    candidate = PurePosixPath(text)
    if candidate.is_absolute() or candidate.as_posix() != text or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise CatalogError("source_path_uncontained", path)
    return text


def _sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise CatalogError("digest_invalid", path)
    return value


def _record(value: Any, index: int) -> dict[str, Any]:
    path = f"$.records[{index}]"
    row = _closed(value, _RECORD_FIELDS, path)
    if row["schema_version"] != 1 or row["record_type"] != "umbrella":
        raise CatalogError("record_identity_invalid", path)
    _text(row["umbrella_id"], f"{path}.umbrella_id")
    _text(row["title"], f"{path}.title", 256)
    _text(row["summary"], f"{path}.summary")
    if row["evidence_state"] != "observed":
        raise CatalogError("evidence_state_invalid", f"{path}.evidence_state")
    if row["sensitivity"] not in {"public", "internal", "restricted"}:
        raise CatalogError("sensitivity_invalid", f"{path}.sensitivity")
    if not isinstance(row["exportable"], bool):
        raise CatalogError("exportability_invalid", f"{path}.exportable")
    if row["sensitivity"] == "restricted" and row["exportable"]:
        raise CatalogError("restricted_export_invalid", f"{path}.exportable")

    tags = row["tags"]
    if not isinstance(tags, list):
        raise CatalogError("tags_invalid", f"{path}.tags")
    seen_tags: set[bytes] = set()
    for tag_index, tag_value in enumerate(tags):
        tag_path = f"{path}.tags[{tag_index}]"
        tag = _closed(tag_value, {"class", "value", "owner", "source"}, tag_path)
        if tag["class"] not in {"topic", "status", "owner", "audience", "source"}:
            raise CatalogError("tag_class_invalid", f"{tag_path}.class")
        for field in ("value", "owner", "source"):
            _text(tag[field], f"{tag_path}.{field}", 256)
        encoded = _canonical(tag)
        if encoded in seen_tags:
            raise CatalogError("tag_duplicate", f"{path}.tags")
        seen_tags.add(encoded)

    lifecycle = _closed(row["lifecycle"], {"active_task", "owner", "state"}, f"{path}.lifecycle")
    if lifecycle["owner"] != "GoalBuddy" or lifecycle["state"] != "snapshot":
        raise CatalogError("lifecycle_invalid", f"{path}.lifecycle")
    if lifecycle["active_task"] is not None:
        _text(lifecycle["active_task"], f"{path}.lifecycle.active_task", 256)

    references = _closed(
        row["references"],
        {"github_repository", "projection", "workgraph_id", "goalbuddy_owner"},
        f"{path}.references",
    )
    _text(references["github_repository"], f"{path}.references.github_repository")
    _relative_path(references["projection"], f"{path}.references.projection")
    _text(references["workgraph_id"], f"{path}.references.workgraph_id")
    if references["goalbuddy_owner"] != "GoalBuddy":
        raise CatalogError("owner_invalid", f"{path}.references.goalbuddy_owner")

    digests = _closed(
        row["digests"],
        {"raw_receipt_sha256", "projection_sha256", "graph_sha256", "board_sha256"},
        f"{path}.digests",
    )
    for field, digest_value in digests.items():
        _sha(digest_value, f"{path}.digests.{field}")
    supplied = _sha(row["record_sha256"], f"{path}.record_sha256")
    unsigned = {key: item for key, item in row.items() if key != "record_sha256"}
    if supplied != _digest(unsigned):
        raise CatalogError("record_digest_mismatch", f"{path}.record_sha256")
    return row


def _parse(serialized: str | bytes | bytearray) -> dict[str, Any]:
    if not isinstance(serialized, (str, bytes, bytearray)):
        raise CatalogError("invalid_serialization")
    raw = serialized.encode("utf-8") if isinstance(serialized, str) else bytes(serialized)
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise CatalogError("jsonl_generation_invalid")
    try:
        value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=_pairs)
    except CatalogError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogError("invalid_json") from error
    if raw != _canonical(value) + b"\n":
        raise CatalogError("noncanonical_jsonl")
    allowed = _TOP_FIELDS | ({"generated_at"} if isinstance(value, dict) and "generated_at" in value else set())
    envelope = _closed(value, allowed, "$")
    if envelope["schema_version"] != 1:
        raise CatalogError("unsupported_schema", "$.schema_version")
    if envelope["artifact_type"] != CATALOG_TYPE:
        raise CatalogError("artifact_type_invalid", "$.artifact_type")
    if "generated_at" in envelope:
        _text(envelope["generated_at"], "$.generated_at", 128)
    _sha(envelope["manifest_sha256"], "$.manifest_sha256")
    records_value = envelope["records"]
    if not isinstance(records_value, list):
        raise CatalogError("records_invalid", "$.records")
    records = [_record(item, index) for index, item in enumerate(records_value)]
    if (
        isinstance(envelope["record_count"], bool)
        or not isinstance(envelope["record_count"], int)
        or envelope["record_count"] < 0
        or envelope["record_count"] != len(records)
    ):
        raise CatalogError("record_count_mismatch", "$.record_count")
    identities = [row["umbrella_id"] for row in records]
    if len(identities) != len(set(identities)) or identities != sorted(identities):
        raise CatalogError("record_identity_invalid", "$.records")
    supplied = _sha(envelope["catalog_sha256"], "$.catalog_sha256")
    if supplied != _digest(records):
        raise CatalogError("catalog_digest_mismatch", "$.catalog_sha256")
    return envelope


def _safe_read(root: Path, relative: str) -> bytes:
    candidate = PurePosixPath(_relative_path(relative, "$.references.projection"))
    root = Path(os.path.abspath(root))
    try:
        root_stat = root.lstat()
    except OSError as error:
        raise CatalogError("source_root_unavailable") from error
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise CatalogError("source_root_invalid")
    current = root
    for part in candidate.parts:
        current = current / part
        try:
            named = current.lstat()
        except OSError as error:
            raise CatalogError("source_unavailable") from error
        if stat.S_ISLNK(named.st_mode):
            raise CatalogError("source_alias_forbidden")
    try:
        current.relative_to(root)
        before = current.stat()
        raw = current.read_bytes()
        after = current.stat()
    except OSError as error:
        raise CatalogError("source_unavailable") from error
    if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev, after.st_ino, after.st_size
    ) or current.read_bytes() != raw:
        raise CatalogError("source_changed")
    return raw


def _verify_source(record: dict[str, Any], source_root: Path) -> dict[str, str]:
    raw = _safe_read(source_root, record["references"]["projection"])
    actual_raw = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_raw != record["digests"]["raw_receipt_sha256"]:
        raise CatalogError("stale_source", record["references"]["projection"])
    try:
        receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, CatalogError) as error:
        raise CatalogError("source_receipt_invalid") from error
    receipt = _closed(receipt, _RECEIPT_FIELDS, "$.source_receipt")
    if (
        receipt["schema_version"] != 1
        or receipt["artifact_type"] != RECEIPT_TYPE
        or receipt["status"] != "ok"
    ):
        raise CatalogError("source_receipt_invalid")
    boundary = _closed(
        receipt["effect_boundary"],
        {
            "acceptance_granted", "authority_granted", "goalbuddy_mutated",
            "github_called", "github_mutated", "network_used", "provider_called",
        },
        "$.source_receipt.effect_boundary",
    )
    if any(not isinstance(value, bool) or value for value in boundary.values()):
        raise CatalogError("source_effect_boundary_invalid")
    state = _closed(
        receipt["canonical_state"], {"active_task", "board_sha256", "owner"},
        "$.source_receipt.canonical_state",
    )
    if state["owner"] != "GoalBuddy":
        raise CatalogError("source_owner_invalid")
    target = _closed(receipt["target"], {"host", "repository"}, "$.source_receipt.target")
    expected_repository = f"https://{_text(target['host'], '$.source_receipt.target.host')}/{_text(target['repository'], '$.source_receipt.target.repository')}"
    if expected_repository != record["references"]["github_repository"]:
        raise CatalogError("stale_repository_binding")
    if receipt["graph_id"] != record["references"]["workgraph_id"]:
        raise CatalogError("stale_workgraph_binding")
    if state["active_task"] != record["lifecycle"]["active_task"]:
        raise CatalogError("stale_lifecycle_binding")
    if _digest(receipt["preview"]) != record["digests"]["projection_sha256"]:
        raise CatalogError("stale_projection")
    try:
        source_title = receipt["preview"]["umbrella"]["title"]
    except (KeyError, TypeError) as error:
        raise CatalogError("source_receipt_invalid") from error
    if source_title != record["title"]:
        raise CatalogError("stale_title_binding")
    if receipt["graph_sha256"] != record["digests"]["graph_sha256"]:
        raise CatalogError("stale_graph_binding")
    if state["board_sha256"] != record["digests"]["board_sha256"]:
        raise CatalogError("stale_board_binding")
    return {
        "raw_receipt": "digest_matched",
        "projection": "digest_matched",
        "graph": "bound_not_recomputed",
        "board": "bound_not_recomputed",
    }


def _reject(error: CatalogError) -> dict[str, Any]:
    return {
        "schema_version": REJECTION_SCHEMA,
        "accepted": False,
        "route": "defer",
        "consequential_use": False,
        "direct_source_fallback_required": True,
        "rejection": {"code": error.code, "field": error.field},
    }


def adapt_catalog_jsonl(
    serialized: str | bytes | bytearray,
    *,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return navigation-only graph records or a fail-closed defer result."""

    try:
        catalog = _parse(serialized)
        verification = "not_run"
        source_checks: dict[str, dict[str, str]] = {}
        if source_root is not None:
            verification = "digest_matched_navigation_only"
            for record in catalog["records"]:
                source_checks[record["umbrella_id"]] = _verify_source(record, Path(source_root))
        graph_records = []
        for record in catalog["records"]:
            graph_records.append({
                "record_id": record["umbrella_id"],
                "kind": "umbrella",
                "title": record["title"],
                "content": _canonical(record).decode("utf-8"),
                "provenance": {
                    "path": record["references"]["projection"],
                    "sha256": record["digests"]["raw_receipt_sha256"][7:],
                    "locator": record["umbrella_id"],
                    "verified": False,
                },
                "trust": "unverifiable",
                "sensitivity": record["sensitivity"],
                "freshness": "unknown",
                "admission": "none",
                "eligible": False,
                "agent_generated": False,
                "export_allowed": False,
                "tags": [
                    f"{tag['class']}:{tag['value']}" for tag in record["tags"]
                ],
                "sequence": None,
            })
        return {
            "schema_version": GRAPH_SCHEMA,
            "accepted": True,
            "route": "catalog_navigation",
            "consequential_use": False,
            "direct_source_fallback_required": True,
            "catalog_sha256": catalog["catalog_sha256"],
            "source_verification": verification,
            "source_checks": source_checks,
            "graph": {"records": graph_records, "edges": []},
            "catalog": copy.deepcopy(catalog),
        }
    except CatalogError as error:
        return _reject(error)
