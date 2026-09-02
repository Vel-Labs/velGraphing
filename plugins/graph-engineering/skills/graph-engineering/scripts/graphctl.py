#!/usr/bin/env python3
"""Validate and inspect graph profiles and JSONL graph exports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple
from urllib.parse import unquote


EXIT_VALIDATION = 1
EXIT_INPUT = 2
GRAPH_MODES = {"execution", "communication", "knowledge", "reasoning", "provenance"}
SCOPE_KINDS = {"project", "folder", "workspace"}
EVIDENCE_STATES = {"observed", "asserted", "inferred", "verified", "accepted"}
SENSITIVITY_LEVELS = ("public", "internal", "restricted")
SENSITIVITY_RANK = {value: index for index, value in enumerate(SENSITIVITY_LEVELS)}
GRAPH_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$")
NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
TYPE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
URI_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
DEFAULT_MAX_FILE_BYTES = 1024 * 1024
RECOMMENDATION_TEXT = {
    "missing_root_instructions": (
        "Add or declare a root instruction entrypoint.",
        "A human-reviewed root AGENTS.md is present in a complete scan.",
    ),
    "missing_root_overview": (
        "Add or declare a root overview entrypoint.",
        "A human-reviewed root README.md is present in a complete scan.",
    ),
    "missing_validation_entrypoint": (
        "Add or declare a validation entrypoint.",
        "A human-approved validation test or script is present in a complete scan.",
    ),
    "broken_local_reference": (
        "Repair or remove each broken local reference.",
        "Each target resolves in a repeated complete scan.",
    ),
    "incomplete_scan_policy": (
        "Review the include set and explicitly declare a complete scan policy.",
        "A human-approved policy is rerun with --policy-status complete.",
    ),
    "source_identity_unavailable": (
        "Declare the source revision and observation time for this scan.",
        "The repeated report binds the index to both caller-declared source fields.",
    ),
}


class InputError(Exception):
    """An unreadable or malformed input."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def issue(code: str, path: str, message: str) -> Dict[str, str]:
    return {"code": code, "path": path, "message": message}


def emit(payload: Mapping[str, Any], stream: Any = sys.stdout) -> None:
    json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
    stream.write("\n")


def read_json(path: str) -> Any:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}") from exc


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise InputError(
                        f"invalid JSON in {path} at line {line_number}, column {exc.colno}"
                    ) from exc
                if not isinstance(record, dict):
                    raise InputError(f"JSONL record at {path}:{line_number} must be an object")
                record = dict(record)
                record["__graphctl_line__"] = line_number
                records.append(record)
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    return records


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(nonempty_string(item) for item in value)
    )


def unique(values: Sequence[Any]) -> bool:
    return len(values) == len(set(values))


def validate_profile(profile: Any) -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []
    if not isinstance(profile, dict):
        return [issue("profile.type", "$", "profile must be a JSON object")]

    if type(profile.get("version")) is not int or profile.get("version") != 1:
        errors.append(issue("profile.version", "version", "version must be 1"))
    if not nonempty_string(profile.get("definition_version")):
        errors.append(
            issue(
                "profile.definition_version",
                "definition_version",
                "definition_version must be a non-empty string",
            )
        )
    graph_id = profile.get("graph_id")
    if not nonempty_string(graph_id) or GRAPH_ID_PATTERN.fullmatch(graph_id) is None:
        errors.append(issue("profile.graph_id", "graph_id", "graph_id must be a stable lowercase identifier"))
    namespace = profile.get("namespace")
    if not nonempty_string(namespace) or NAMESPACE_PATTERN.fullmatch(namespace) is None:
        errors.append(issue("profile.namespace", "namespace", "namespace must be a stable lowercase identifier"))

    scope = profile.get("scope")
    if not isinstance(scope, dict):
        errors.append(issue("profile.scope", "scope", "scope must be an object"))
    else:
        if scope.get("kind") not in SCOPE_KINDS:
            errors.append(issue("profile.scope.kind", "scope.kind", "scope.kind is not supported"))
        for field in ("root", "owner"):
            if not nonempty_string(scope.get(field)):
                errors.append(
                    issue("profile.scope.required", f"scope.{field}", f"scope.{field} must be a non-empty string")
                )

    modes = profile.get("graph_modes")
    if not string_list(modes):
        errors.append(issue("profile.graph_modes", "graph_modes", "graph_modes must be a non-empty string list"))
    else:
        invalid_modes = sorted(set(modes) - GRAPH_MODES)
        if invalid_modes:
            errors.append(
                issue("profile.graph_modes.value", "graph_modes", f"unsupported graph modes: {', '.join(invalid_modes)}")
            )
        if not unique(modes):
            errors.append(issue("profile.graph_modes.duplicate", "graph_modes", "graph_modes must be unique"))

    sources = profile.get("canonical_sources")
    if not isinstance(sources, list) or not sources:
        errors.append(
            issue("profile.canonical_sources", "canonical_sources", "canonical_sources must be a non-empty list")
        )
    else:
        source_ids: List[str] = []
        for index, source in enumerate(sources):
            path = f"canonical_sources[{index}]"
            if not isinstance(source, dict):
                errors.append(issue("profile.canonical_source.type", path, "canonical source must be an object"))
                continue
            for field in ("id", "path", "role"):
                if not nonempty_string(source.get(field)):
                    errors.append(
                        issue("profile.canonical_source.required", f"{path}.{field}", f"{field} must be a non-empty string")
                    )
            if nonempty_string(source.get("id")):
                source_ids.append(source["id"])
        if not unique(source_ids):
            errors.append(issue("profile.canonical_source.duplicate", "canonical_sources", "source ids must be unique"))

    node_types = profile.get("node_types")
    node_ids: List[str] = []
    if not isinstance(node_types, list) or not node_types:
        errors.append(issue("profile.node_types", "node_types", "node_types must be a non-empty list"))
    else:
        for index, node_type in enumerate(node_types):
            path = f"node_types[{index}]"
            if (
                not isinstance(node_type, dict)
                or not nonempty_string(node_type.get("id"))
                or TYPE_ID_PATTERN.fullmatch(node_type["id"]) is None
            ):
                errors.append(issue("profile.node_type.id", f"{path}.id", "node type id must be a lowercase identifier"))
            else:
                node_ids.append(node_type["id"])
            if isinstance(node_type, dict) and not nonempty_string(node_type.get("description")):
                errors.append(
                    issue(
                        "profile.node_type.description",
                        f"{path}.description",
                        "node type description must be a non-empty string",
                    )
                )
        if not unique(node_ids):
            errors.append(issue("profile.node_type.duplicate", "node_types", "node type ids must be unique"))

    edge_types = profile.get("edge_types")
    edge_ids: List[str] = []
    if not isinstance(edge_types, list):
        errors.append(issue("profile.edge_types", "edge_types", "edge_types must be a list"))
    else:
        for index, edge_type in enumerate(edge_types):
            path = f"edge_types[{index}]"
            if not isinstance(edge_type, dict):
                errors.append(issue("profile.edge_type.type", path, "edge type must be an object"))
                continue
            if (
                not nonempty_string(edge_type.get("id"))
                or TYPE_ID_PATTERN.fullmatch(edge_type["id"]) is None
            ):
                errors.append(issue("profile.edge_type.id", f"{path}.id", "edge type id must be a lowercase identifier"))
            else:
                edge_ids.append(edge_type["id"])
            if not nonempty_string(edge_type.get("description")):
                errors.append(
                    issue(
                        "profile.edge_type.description",
                        f"{path}.description",
                        "edge type description must be a non-empty string",
                    )
                )
            for field in ("source_types", "target_types"):
                values = edge_type.get(field)
                if not string_list(values):
                    errors.append(
                        issue("profile.edge_type.types", f"{path}.{field}", f"{field} must be a non-empty string list")
                    )
                else:
                    if not unique(values):
                        errors.append(
                            issue("profile.edge_type.types.duplicate", f"{path}.{field}", f"{field} must be unique")
                        )
                    undeclared = sorted(set(values) - set(node_ids))
                    if undeclared:
                        errors.append(
                            issue(
                                "profile.edge_type.undeclared_node_type",
                                f"{path}.{field}",
                                f"undeclared node types: {', '.join(undeclared)}",
                            )
                        )
            for field in ("acyclic", "requires_authority"):
                if field in edge_type and not isinstance(edge_type[field], bool):
                    errors.append(issue("profile.edge_type.boolean", f"{path}.{field}", f"{field} must be boolean"))
        if not unique(edge_ids):
            errors.append(issue("profile.edge_type.duplicate", "edge_types", "edge type ids must be unique"))

    projection = profile.get("projection")
    if not isinstance(projection, dict) or projection.get("kind") not in {"declared", "derived", "mixed"}:
        errors.append(
            issue("profile.projection", "projection.kind", "projection.kind must be declared, derived, or mixed")
        )

    policy = profile.get("export_policy")
    if not isinstance(policy, dict):
        errors.append(issue("profile.export_policy", "export_policy", "export_policy must be an object"))
    else:
        if policy.get("default") != "deny":
            errors.append(issue("profile.export_policy.default", "export_policy.default", "default must be deny"))
        for field, declared in (("allowed_node_types", node_ids), ("allowed_edge_types", edge_ids)):
            values = policy.get(field)
            if not string_list(values, allow_empty=True):
                errors.append(
                    issue("profile.export_policy.allowlist", f"export_policy.{field}", f"{field} must be a string list")
                )
            else:
                if not unique(values):
                    errors.append(
                        issue("profile.export_policy.allowlist.duplicate", f"export_policy.{field}", f"{field} must be unique")
                    )
                undeclared = sorted(set(values) - set(declared))
                if undeclared:
                    errors.append(
                        issue(
                            "profile.export_policy.undeclared_type",
                            f"export_policy.{field}",
                            f"undeclared types: {', '.join(undeclared)}",
                        )
                    )
        if policy.get("sensitivity_ceiling") not in SENSITIVITY_RANK:
            errors.append(
                issue(
                    "profile.export_policy.sensitivity",
                    "export_policy.sensitivity_ceiling",
                    "sensitivity_ceiling must be public, internal, or restricted",
                )
            )
    return errors


def valid_timestamp(value: Any) -> bool:
    if not nonempty_string(value) or "T" not in value:
        return False
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def record_path(record: Mapping[str, Any], fallback_index: int) -> str:
    return f"line {record.get('__graphctl_line__', fallback_index + 1)}"


def validate_export(records: Sequence[Mapping[str, Any]], profile: Mapping[str, Any]) -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []
    namespace = profile["namespace"]
    prefix = f"{namespace}:"
    node_types = {item["id"] for item in profile["node_types"]}
    edge_specs = {item["id"]: item for item in profile["edge_types"]}
    policy = profile["export_policy"]
    allowed_nodes = set(policy["allowed_node_types"])
    allowed_edges = set(policy["allowed_edge_types"])
    ceiling = SENSITIVITY_RANK[policy["sensitivity_ceiling"]]
    ids: Dict[str, str] = {}
    nodes: Dict[str, Mapping[str, Any]] = {}
    edges: List[Mapping[str, Any]] = []

    for index, record in enumerate(records):
        path = record_path(record, index)
        record_type = record.get("record_type")
        if record_type not in {"node", "edge"}:
            errors.append(issue("export.record_type", path, "record_type must be node or edge"))
        record_id = record.get("id")
        if not nonempty_string(record_id):
            errors.append(issue("export.id", f"{path}.id", "id must be a non-empty string"))
        else:
            if not record_id.startswith(prefix) or len(record_id) == len(prefix):
                errors.append(issue("export.namespace", f"{path}.id", f"id must use namespace prefix {prefix}"))
            if record_id in ids:
                errors.append(issue("export.duplicate_id", f"{path}.id", f"duplicate id {record_id}"))
            else:
                ids[record_id] = path

        for field in ("owner", "source_ref"):
            if not nonempty_string(record.get(field)):
                errors.append(issue("export.required", f"{path}.{field}", f"{field} must be a non-empty string"))
        if record.get("evidence_state") not in EVIDENCE_STATES:
            errors.append(issue("export.evidence_state", f"{path}.evidence_state", "invalid evidence_state"))
        sensitivity = record.get("sensitivity")
        if sensitivity not in SENSITIVITY_RANK:
            errors.append(issue("export.sensitivity", f"{path}.sensitivity", "invalid sensitivity"))
        elif SENSITIVITY_RANK[sensitivity] > ceiling:
            errors.append(
                issue("export.sensitivity_ceiling", f"{path}.sensitivity", f"sensitivity exceeds {policy['sensitivity_ceiling']}")
            )
        if not isinstance(record.get("exportable"), bool):
            errors.append(issue("export.exportable.type", f"{path}.exportable", "exportable must be boolean"))
        elif not record["exportable"]:
            errors.append(issue("export.not_exportable", f"{path}.exportable", "non-exportable record cannot be exported"))
        if not valid_timestamp(record.get("observed_at")):
            errors.append(issue("export.observed_at", f"{path}.observed_at", "observed_at must be an ISO 8601 timestamp"))

        if record_type == "node":
            node_type = record.get("node_type")
            if node_type not in node_types:
                errors.append(issue("export.node_type", f"{path}.node_type", "node_type is not declared"))
            elif node_type not in allowed_nodes:
                errors.append(issue("export.node_type.denied", f"{path}.node_type", "node_type is not in the export allowlist"))
            if nonempty_string(record_id) and record_id not in nodes:
                nodes[record_id] = record
        elif record_type == "edge":
            edges.append(record)
            edge_type = record.get("edge_type")
            spec = edge_specs.get(edge_type)
            if spec is None:
                errors.append(issue("export.edge_type", f"{path}.edge_type", "edge_type is not declared"))
            elif edge_type not in allowed_edges:
                errors.append(issue("export.edge_type.denied", f"{path}.edge_type", "edge_type is not in the export allowlist"))
            for field in ("from", "to"):
                endpoint = record.get(field)
                if not nonempty_string(endpoint):
                    errors.append(issue("export.endpoint", f"{path}.{field}", f"{field} must be a non-empty string"))
                elif not endpoint.startswith(prefix) or len(endpoint) == len(prefix):
                    errors.append(issue("export.endpoint.namespace", f"{path}.{field}", f"{field} must use namespace prefix {prefix}"))
            if (spec and spec.get("requires_authority")) or record.get("evidence_state") == "accepted":
                if not nonempty_string(record.get("authority_ref")):
                    errors.append(
                        issue("export.authority_ref", f"{path}.authority_ref", "authority_ref is required for this edge")
                    )

    for index, edge in enumerate(edges):
        path = record_path(edge, index)
        source = nodes.get(edge.get("from"))
        target = nodes.get(edge.get("to"))
        if source is None:
            errors.append(issue("export.orphan_source", f"{path}.from", "source node is not present"))
        if target is None:
            errors.append(issue("export.orphan_target", f"{path}.to", "target node is not present"))
        spec = edge_specs.get(edge.get("edge_type"))
        if spec and source is not None and source.get("node_type") not in spec["source_types"]:
            errors.append(issue("export.source_type", f"{path}.from", "source node type is not allowed for this edge"))
        if spec and target is not None and target.get("node_type") not in spec["target_types"]:
            errors.append(issue("export.target_type", f"{path}.to", "target node type is not allowed for this edge"))

    for edge_type, spec in sorted(edge_specs.items()):
        if spec.get("acyclic") and has_cycle(edges, edge_type):
            errors.append(issue("export.cycle", f"edge_type:{edge_type}", "acyclic edge type contains a cycle"))
    return errors


def has_cycle(edges: Iterable[Mapping[str, Any]], edge_type: str) -> bool:
    adjacency: Dict[str, List[str]] = defaultdict(list)
    vertices = set()
    for edge in edges:
        if edge.get("edge_type") == edge_type and nonempty_string(edge.get("from")) and nonempty_string(edge.get("to")):
            adjacency[edge["from"]].append(edge["to"])
            vertices.add(edge["from"])
            vertices.add(edge["to"])
    state: Dict[str, int] = {}

    def visit(vertex: str) -> bool:
        current = state.get(vertex, 0)
        if current == 1:
            return True
        if current == 2:
            return False
        state[vertex] = 1
        for neighbor in adjacency.get(vertex, []):
            if visit(neighbor):
                return True
        state[vertex] = 2
        return False

    return any(visit(vertex) for vertex in sorted(vertices) if state.get(vertex, 0) == 0)


def clean_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in record.items() if key != "__graphctl_line__"}


def count_map(values: Iterable[Any]) -> Dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def stats(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    nodes = [record for record in records if record.get("record_type") == "node"]
    edges = [record for record in records if record.get("record_type") == "edge"]
    return {
        "counts": {"records": len(records), "nodes": len(nodes), "edges": len(edges)},
        "edge_types": count_map(record.get("edge_type") for record in edges),
        "evidence_states": count_map(record.get("evidence_state") for record in records),
        "node_types": count_map(record.get("node_type") for record in nodes),
        "owners": count_map(record.get("owner") for record in records),
        "sensitivities": count_map(record.get("sensitivity") for record in records),
    }


def indexed_records(records: Sequence[Mapping[str, Any]], path: str) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for index, record in enumerate(records):
        record_id = record.get("id")
        if not nonempty_string(record_id):
            raise InputError(f"record at {path}:{record.get('__graphctl_line__', index + 1)} has no valid id")
        if record_id in result:
            raise InputError(f"duplicate id {record_id} in {path}")
        result[record_id] = clean_record(record)
    return result


def load_valid_profile(path: str) -> Tuple[Mapping[str, Any], List[Dict[str, str]]]:
    profile = read_json(path)
    errors = validate_profile(profile)
    return profile if isinstance(profile, dict) else {}, errors


def command_validate_profile(args: argparse.Namespace) -> int:
    _, errors = load_valid_profile(args.profile)
    if errors:
        emit({"command": "validate-profile", "errors": errors, "valid": False}, sys.stderr)
        return EXIT_VALIDATION
    emit({"command": "validate-profile", "errors": [], "valid": True})
    return 0


def validated_export(args: argparse.Namespace) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    profile, profile_errors = load_valid_profile(args.profile)
    if profile_errors:
        return [], profile_errors
    records = read_jsonl(args.export)
    return records, validate_export(records, profile)


def command_validate_export(args: argparse.Namespace) -> int:
    records, errors = validated_export(args)
    if errors:
        emit({"command": "validate-export", "errors": errors, "records": len(records), "valid": False}, sys.stderr)
        return EXIT_VALIDATION
    emit({"command": "validate-export", "errors": [], "records": len(records), "valid": True})
    return 0


def command_stats(args: argparse.Namespace) -> int:
    records, errors = validated_export(args)
    if errors:
        emit({"command": "stats", "errors": errors, "valid": False}, sys.stderr)
        return EXIT_VALIDATION
    emit({"command": "stats", "stats": stats(records), "valid": True})
    return 0


def command_diff(args: argparse.Namespace) -> int:
    before = indexed_records(read_jsonl(args.before), args.before)
    after = indexed_records(read_jsonl(args.after), args.after)
    before_ids = set(before)
    after_ids = set(after)
    removed = sorted(before_ids - after_ids)
    added = sorted(after_ids - before_ids)
    changed = sorted(record_id for record_id in before_ids & after_ids if before[record_id] != after[record_id])
    emit({"added": added, "breaking": bool(removed), "changed": changed, "command": "diff", "removed": removed})
    return 0


def normalized_include(value: str) -> str:
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise InputError(f"include must be a relative path without traversal: {value!r}")
    normalized = candidate.as_posix().rstrip("/") or "."
    if any(part.startswith(".") and part not in {"."} for part in Path(normalized).parts):
        raise InputError(f"hidden include paths are not allowed: {value!r}")
    return normalized


def classify_role(path: str) -> str:
    relative = Path(path)
    name = relative.name
    lowered = name.lower()
    parts = {part.lower() for part in relative.parts}
    if name == "AGENTS.md":
        return "instructions"
    if lowered == "readme.md":
        return "overview"
    if lowered in {"package.json", "pyproject.toml", "plugin.json"}:
        return "manifest"
    if name == "SKILL.md":
        return "workflow"
    if lowered == "state.yaml":
        return "task_truth"
    if lowered.endswith(".schema.json") or "contracts" in parts:
        return "contract"
    if "tests" in parts or lowered.startswith("test_") or lowered.endswith("_test.py"):
        return "validation_test"
    if "scripts" in parts or lowered in {"makefile", "justfile"}:
        return "validation_script"
    if "plans" in parts or "plan" in lowered:
        return "plan"
    return "source"


def safe_root(raw_root: str) -> Path:
    root = Path(raw_root)
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise InputError(f"cannot inspect root: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode):
        raise InputError("root must not be a symlink")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise InputError("root must be a directory")
    return root.resolve()


def inspect_component(path: Path, kind: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise InputError(f"missing {kind}: {path.name}") from exc
    except OSError as exc:
        raise InputError(f"cannot inspect {kind} {path.name}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise InputError(f"symlink {kind} is not allowed: {path.name}")
    return metadata


def safe_file_bytes(path: Path, expected: os.stat_result, max_file_bytes: int) -> bytes:
    if not stat.S_ISREG(expected.st_mode):
        raise InputError(f"non-regular file is not allowed: {path.name}")
    if expected.st_size > max_file_bytes:
        raise InputError(f"file exceeds max-file-bytes: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise InputError(f"cannot open file {path.name}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise InputError(f"non-regular file is not allowed: {path.name}")
        if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
            raise InputError(f"file changed during scan: {path.name}")
        if opened.st_size > max_file_bytes:
            raise InputError(f"file exceeds max-file-bytes: {path.name}")
        chunks: List[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, max_file_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_file_bytes:
                raise InputError(f"file exceeds max-file-bytes: {path.name}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def scan_readiness_files(
    root: Path, includes: Sequence[str], max_file_bytes: int
) -> Tuple[List[Dict[str, Any]], Dict[str, bytes], Set[str], List[str]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    payloads: Dict[str, bytes] = {}
    directories: Set[str] = {"."}
    identities: Dict[Tuple[int, int], str] = {}
    directory_includes: List[str] = []

    def add_file(path: Path, metadata: os.stat_result) -> None:
        relative = path.relative_to(root).as_posix()
        identity = (metadata.st_dev, metadata.st_ino)
        prior = identities.get(identity)
        if prior is not None and prior != relative:
            raise InputError(f"file alias or hardlink is not allowed: {prior} and {relative}")
        identities[identity] = relative
        if relative in indexed:
            return
        content = safe_file_bytes(path, metadata, max_file_bytes)
        payloads[relative] = content
        indexed[relative] = {
            "bytes": len(content),
            "path": relative,
            "role": classify_role(relative),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def walk(directory: Path) -> None:
        relative_directory = directory.relative_to(root).as_posix() or "."
        directories.add(relative_directory)
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise InputError(f"cannot list directory {relative_directory}: {exc}") from exc
        for entry in entries:
            if entry.name.startswith("."):
                continue
            child = Path(entry.path)
            metadata = inspect_component(child, "scan path")
            if stat.S_ISDIR(metadata.st_mode):
                walk(child)
            elif stat.S_ISREG(metadata.st_mode):
                add_file(child, metadata)
            else:
                raise InputError(f"non-regular scan path is not allowed: {child.relative_to(root).as_posix()}")

    for include in includes:
        current = root
        if include != ".":
            for component in Path(include).parts:
                current = current / component
                metadata = inspect_component(current, "include component")
                if current != root / include and not stat.S_ISDIR(metadata.st_mode):
                    raise InputError(f"non-directory include component: {component}")
        metadata = inspect_component(current, "include") if include != "." else root.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            directory_includes.append(include)
            walk(current)
        elif stat.S_ISREG(metadata.st_mode):
            add_file(current, metadata)
        else:
            raise InputError(f"non-regular include is not allowed: {include}")
    return [indexed[path] for path in sorted(indexed)], payloads, directories, sorted(directory_includes)


def markdown_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    target = unquote(target).split("#", 1)[0].split("?", 1)[0]
    if not target or target.startswith(("#", "/", "//")) or URI_SCHEME_PATTERN.match(target):
        return None
    return target


def path_is_covered(path: str, file_paths: Set[str], directory_includes: Sequence[str]) -> bool:
    if path in file_paths:
        return True
    return any(include == "." or path == include or path.startswith(include + "/") for include in directory_includes)


def extract_local_links(
    files: Sequence[Mapping[str, Any]],
    payloads: Mapping[str, bytes],
    directories: Set[str],
    directory_includes: Sequence[str],
) -> List[Dict[str, str]]:
    file_paths = {str(item["path"]) for item in files}
    links: List[Dict[str, str]] = []
    for item in files:
        source_ref = str(item["path"])
        if Path(source_ref).suffix.lower() != ".md":
            continue
        text = payloads[source_ref].decode("utf-8", errors="replace")
        for raw in MARKDOWN_LINK_PATTERN.findall(text):
            target = markdown_target(raw)
            if target is None:
                continue
            lexical = Path(source_ref).parent / target
            parts: List[str] = []
            escaped = False
            for part in lexical.parts:
                if part in {"", "."}:
                    continue
                if part == "..":
                    if not parts:
                        escaped = True
                        break
                    parts.pop()
                else:
                    parts.append(part)
            target_ref = Path(*parts).as_posix() if parts else "."
            if escaped:
                status = "outside_root"
            elif target_ref in file_paths or target_ref in directories:
                status = "resolved"
            elif path_is_covered(target_ref, file_paths, directory_includes):
                status = "broken"
            else:
                status = "unscanned"
            links.append({"source_ref": source_ref, "status": status, "target_ref": target_ref})
    links.sort(key=lambda item: (item["source_ref"], item["target_ref"], item["status"]))
    return links


def readiness_finding(
    code: str, failure_class: str, target_refs: Sequence[str], message: str
) -> Dict[str, Any]:
    return {
        "code": code,
        "failure_class": failure_class,
        "message": message,
        "target_refs": sorted(set(target_refs)),
    }


def readiness_recommendation(finding: Mapping[str, Any]) -> Dict[str, Any]:
    code = str(finding["code"])
    action, proof = RECOMMENDATION_TEXT[code]
    targets = list(finding["target_refs"])
    return {
        "action": action,
        "auto_apply": False,
        "expected_proof": proof,
        "failure_class": finding["failure_class"],
        "finding_codes": [code],
        "id": f"recommendation-{code}",
        "requires_human_authority": True,
        "target_refs": targets,
    }


def command_readiness(args: argparse.Namespace) -> int:
    if args.max_file_bytes < 1:
        raise InputError("max-file-bytes must be a positive integer")
    root = safe_root(args.root)
    includes = sorted({normalized_include(value) for value in args.include})
    files, payloads, directories, directory_includes = scan_readiness_files(
        root, includes, args.max_file_bytes
    )
    links = extract_local_links(files, payloads, directories, directory_includes)
    findings: List[Dict[str, Any]] = []
    file_paths = {item["path"] for item in files}
    roles = {item["role"] for item in files}
    if "AGENTS.md" not in file_paths:
        findings.append(
            readiness_finding(
                "missing_root_instructions", "missing_knowledge", ["AGENTS.md"],
                "The declared scan does not contain root instructions.",
            )
        )
    if "README.md" not in file_paths:
        findings.append(
            readiness_finding(
                "missing_root_overview", "missing_knowledge", ["README.md"],
                "The declared scan does not contain a root overview.",
            )
        )
    if not ({"validation_test", "validation_script"} & roles):
        findings.append(
            readiness_finding(
                "missing_validation_entrypoint", "selection_failure", ["validation"],
                "The declared scan does not contain a validation test or script.",
            )
        )
    broken_refs = sorted(
        {value for link in links if link["status"] == "broken" for value in (link["source_ref"], link["target_ref"])}
    )
    if broken_refs:
        findings.append(
            readiness_finding(
                "broken_local_reference", "relationship_failure", broken_refs,
                "One or more local Markdown path links do not resolve in the declared scan scope.",
            )
        )
    if args.policy_status != "complete":
        findings.append(
            readiness_finding(
                "incomplete_scan_policy", "required_escalation", ["scan_policy.includes"],
                "The caller has not declared the explicit include policy complete.",
            )
        )
    missing_source_fields = [
        name
        for name, value in (
            ("scan_policy.source_revision", args.source_revision),
            ("scan_policy.source_observed_at", args.source_observed_at),
        )
        if value is None
    ]
    if missing_source_fields:
        findings.append(
            readiness_finding(
                "source_identity_unavailable", "freshness_failure", missing_source_fields,
                "The report lacks a caller-declared source revision or observation time.",
            )
        )
    ordered_findings = sorted(findings, key=lambda item: item["code"])
    recommendations = [readiness_recommendation(item) for item in ordered_findings]
    if args.policy_status != "complete":
        status_value = "unknown"
    elif ordered_findings:
        status_value = "needs_attention"
    else:
        status_value = "ready"
    emit(
        {
            "command": "readiness",
            "files": files,
            "findings": ordered_findings,
            "links": links,
            "recommendations": recommendations,
            "scan_policy": {
                "alias_policy": "reject",
                "hidden_paths": "exclude",
                "includes": includes,
                "max_file_bytes": args.max_file_bytes,
                "non_regular_policy": "reject",
                "policy_status": args.policy_status,
                "root": ".",
                "source_observed_at": args.source_observed_at,
                "source_revision": args.source_revision,
                "symlink_policy": "reject",
            },
            "schema_version": "readiness-report-v1",
            "status": status_value,
            "summary": {
                "files": len(files),
                "findings": len(ordered_findings),
                "links": len(links),
                "recommendations": len(recommendations),
            },
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="graphctl.py", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("validate-profile")
    profile_parser.add_argument("profile")
    profile_parser.set_defaults(handler=command_validate_profile)

    export_parser = subparsers.add_parser("validate-export")
    export_parser.add_argument("export")
    export_parser.add_argument("--profile", required=True)
    export_parser.set_defaults(handler=command_validate_export)

    stats_parser = subparsers.add_parser("stats")
    stats_parser.add_argument("export")
    stats_parser.add_argument("--profile", required=True)
    stats_parser.set_defaults(handler=command_stats)

    diff_parser = subparsers.add_parser("diff")
    diff_parser.add_argument("before")
    diff_parser.add_argument("after")
    diff_parser.set_defaults(handler=command_diff)

    readiness_parser = subparsers.add_parser(
        "readiness", help="build a deterministic repository-readiness report"
    )
    readiness_parser.add_argument("--root", required=True)
    readiness_parser.add_argument("--include", action="append", required=True)
    readiness_parser.add_argument(
        "--policy-status", choices=("complete", "incomplete"), default="incomplete"
    )
    readiness_parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    readiness_parser.add_argument("--source-revision")
    readiness_parser.add_argument("--source-observed-at")
    readiness_parser.set_defaults(handler=command_readiness)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.handler(args)
    except InputError as exc:
        emit({"error": str(exc), "valid": False}, sys.stderr)
        return EXIT_INPUT


if __name__ == "__main__":
    sys.exit(main())
