#!/usr/bin/env python3
"""Read-only validation and verification for a federated graph registry."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


LIFECYCLES = {
    "proposed",
    "validated",
    "admitted",
    "stale",
    "quarantined",
    "retired",
}
INGEST_MODES = {"disabled", "manual", "approved"}
SENSITIVITIES = {"public": 0, "internal": 1, "restricted": 2}
EVIDENCE_STATES = {"observed", "asserted", "inferred", "verified", "accepted"}
INACTIVE_LIFECYCLES = {"stale", "quarantined", "retired"}
VALIDATOR_ID = "graphctl-v1"
GRAPHCTL_PATH = (
    Path(__file__).resolve().parents[2]
    / "graph-engineering"
    / "scripts"
    / "graphctl.py"
)
GRAPH_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$")
NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


class RegistryInputError(Exception):
    """The registry input cannot be read as a JSON object."""


def error(code: str, message: str, path: str) -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def read_registry(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryInputError(f"cannot read registry: {exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RegistryInputError(
            f"registry is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise RegistryInputError("registry must be a JSON object")
    return value


def contained_registry_path(path: Path, workspace_root: Path) -> Path:
    lexical_root = Path(os.path.abspath(str(workspace_root)))
    lexical = Path(os.path.abspath(str(path)))
    try:
        if Path(os.path.commonpath((str(lexical_root), str(lexical)))) != lexical_root:
            raise RegistryInputError("registry path is outside --workspace-root")
        root = lexical_root.resolve(strict=False)
        resolved = lexical.resolve(strict=False)
        if Path(os.path.commonpath((str(root), str(resolved)))) != root:
            raise RegistryInputError("registry path escapes --workspace-root")
    except ValueError as exc:
        raise RegistryInputError("registry path is outside --workspace-root") from exc
    return resolved


def nonempty_string(
    value: Any, field_path: str, errors: list[dict[str, str]]
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(error("invalid_field", "must be a non-empty string", field_path))
        return None
    return value


def string_list(
    value: Any, field_path: str, errors: list[dict[str, str]]
) -> list[str] | None:
    if not isinstance(value, list):
        errors.append(error("invalid_field", "must be a list", field_path))
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(
            error("invalid_field", "must contain only non-empty strings", field_path)
        )
        return None
    if len(value) != len(set(value)):
        errors.append(error("duplicate_value", "must not contain duplicates", field_path))
        return None
    return value


def resolve_contained_path(
    raw_path: Any,
    root: Path,
    field_path: str,
    errors: list[dict[str, str]],
) -> Path | None:
    value = nonempty_string(raw_path, field_path, errors)
    if value is None:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=False)
        common = Path(os.path.commonpath((str(root), str(resolved))))
    except (OSError, ValueError) as exc:
        errors.append(error("invalid_path", f"cannot resolve path: {exc}", field_path))
        return None
    if common != root:
        errors.append(
            error("path_escape", "resolved path is outside the workspace root", field_path)
        )
        return None
    return resolved


def require_regular_file(
    path: Path | None, field_path: str, errors: list[dict[str, str]]
) -> None:
    if path is None:
        return
    try:
        mode = path.stat().st_mode
    except OSError:
        errors.append(error("file_missing", "path is not a regular file", field_path))
        return
    if not stat.S_ISREG(mode):
        errors.append(error("not_regular_file", "path is not a regular file", field_path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def stable_identifier(
    value: Any,
    pattern: re.Pattern[str],
    field_path: str,
    errors: list[dict[str, str]],
) -> str | None:
    result = nonempty_string(value, field_path, errors)
    if result is not None and pattern.fullmatch(result) is None:
        errors.append(
            error("invalid_identifier", "must be a stable lowercase identifier", field_path)
        )
        return None
    return result


def validate_registry(
    registry: dict[str, Any],
    workspace_root: Path | None = None,
    *,
    check_files: bool,
    skip_nonverifiable_files: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], Path | None]:
    errors: list[dict[str, str]] = []
    children_out: list[dict[str, Any]] = []

    if registry.get("version") != 1:
        errors.append(error("unsupported_version", "version must equal 1", "version"))
    parent_graph_id = stable_identifier(
        registry.get("graph_id"), GRAPH_ID_PATTERN, "graph_id", errors
    )
    parent_namespace = stable_identifier(
        registry.get("namespace"), NAMESPACE_PATTERN, "namespace", errors
    )
    nonempty_string(registry.get("owner"), "owner", errors)

    declared_root_raw = nonempty_string(
        registry.get("workspace_root"), "workspace_root", errors
    )
    declared_root = None
    if declared_root_raw is not None:
        declared_root = Path(
            os.path.abspath(os.path.expanduser(declared_root_raw))
        ).resolve(strict=False)

    root = workspace_root.resolve(strict=False) if workspace_root is not None else declared_root
    if workspace_root is not None and declared_root is not None and root != declared_root:
        errors.append(
            error(
                "workspace_root_mismatch",
                "registry workspace_root does not match --workspace-root",
                "workspace_root",
            )
        )

    raw_children = registry.get("children")
    if not isinstance(raw_children, list):
        errors.append(error("invalid_field", "must be a list", "children"))
        return errors, children_out, root

    seen_graph_ids = {parent_graph_id} if parent_graph_id is not None else set()
    seen_namespaces = {parent_namespace} if parent_namespace is not None else set()

    for index, child in enumerate(raw_children):
        prefix = f"children[{index}]"
        child_errors: list[dict[str, str]] = []
        if not isinstance(child, dict):
            errors.append(error("invalid_child", "must be an object", prefix))
            continue

        graph_id = stable_identifier(
            child.get("graph_id"),
            GRAPH_ID_PATTERN,
            f"{prefix}.graph_id",
            child_errors,
        )
        namespace = stable_identifier(
            child.get("namespace"),
            NAMESPACE_PATTERN,
            f"{prefix}.namespace",
            child_errors,
        )
        nonempty_string(child.get("owner"), f"{prefix}.owner", child_errors)
        if graph_id is not None:
            if graph_id in seen_graph_ids:
                child_errors.append(
                    error("duplicate_graph_id", "graph_id must be unique", f"{prefix}.graph_id")
                )
            else:
                seen_graph_ids.add(graph_id)
        if namespace is not None:
            if namespace in seen_namespaces:
                child_errors.append(
                    error(
                        "duplicate_namespace",
                        "namespace must be unique",
                        f"{prefix}.namespace",
                    )
                )
            else:
                seen_namespaces.add(namespace)

        lifecycle = child.get("lifecycle")
        if lifecycle not in LIFECYCLES:
            child_errors.append(
                error(
                    "invalid_lifecycle",
                    "must be proposed, validated, admitted, stale, quarantined, or retired",
                    f"{prefix}.lifecycle",
                )
            )
        ingest_mode = child.get("ingest_mode")
        if ingest_mode not in INGEST_MODES:
            child_errors.append(
                error(
                    "invalid_ingest_mode",
                    "must be disabled, manual, or approved",
                    f"{prefix}.ingest_mode",
                )
            )
        if lifecycle in INACTIVE_LIFECYCLES and ingest_mode == "approved":
            child_errors.append(
                error(
                    "lifecycle_ingest_conflict",
                    f"{lifecycle} children cannot use approved ingest",
                    f"{prefix}.ingest_mode",
                )
            )
        if lifecycle == "admitted" and ingest_mode != "approved":
            child_errors.append(
                error(
                    "lifecycle_ingest_conflict",
                    "admitted children must use approved ingest",
                    f"{prefix}.ingest_mode",
                )
            )
        if ingest_mode == "approved" or lifecycle == "admitted":
            nonempty_string(
                child.get("authority_ref"), f"{prefix}.authority_ref", child_errors
            )
            nonempty_string(
                child.get("validation_ref"), f"{prefix}.validation_ref", child_errors
            )
            nonempty_string(
                child.get("definition_version"),
                f"{prefix}.definition_version",
                child_errors,
            )
            if child.get("validator_id") != VALIDATOR_ID:
                child_errors.append(
                    error(
                        "invalid_validator_id",
                        f"approved or admitted children must use {VALIDATOR_ID}",
                        f"{prefix}.validator_id",
                    )
                )

        ceiling = child.get("sensitivity_ceiling")
        if ceiling not in SENSITIVITIES:
            child_errors.append(
                error(
                    "invalid_sensitivity_ceiling",
                    "must be public, internal, or restricted",
                    f"{prefix}.sensitivity_ceiling",
                )
            )
        string_list(
            child.get("allowed_node_types"),
            f"{prefix}.allowed_node_types",
            child_errors,
        )
        string_list(
            child.get("allowed_edge_types"),
            f"{prefix}.allowed_edge_types",
            child_errors,
        )

        profile_path = None
        export_path = None
        if root is None:
            nonempty_string(child.get("profile_path"), f"{prefix}.profile_path", child_errors)
            nonempty_string(child.get("export_path"), f"{prefix}.export_path", child_errors)
        else:
            profile_path = resolve_contained_path(
                child.get("profile_path"), root, f"{prefix}.profile_path", child_errors
            )
            export_path = resolve_contained_path(
                child.get("export_path"), root, f"{prefix}.export_path", child_errors
            )

        expected_digest = child.get("expected_sha256")
        if (ingest_mode == "approved" or lifecycle == "admitted") and expected_digest is None:
            child_errors.append(
                error(
                    "missing_sha256",
                    "approved or admitted children must declare expected_sha256",
                    f"{prefix}.expected_sha256",
                )
            )
        if expected_digest is not None:
            if not valid_sha256(expected_digest):
                child_errors.append(
                    error(
                        "invalid_sha256",
                        "must be a 64-character hexadecimal digest",
                        f"{prefix}.expected_sha256",
                    )
                )

        profile_digest = child.get("profile_sha256")
        if (ingest_mode == "approved" or lifecycle == "admitted") and profile_digest is None:
            child_errors.append(
                error(
                    "missing_profile_sha256",
                    "approved or admitted children must declare profile_sha256",
                    f"{prefix}.profile_sha256",
                )
            )
        if profile_digest is not None and not valid_sha256(profile_digest):
            child_errors.append(
                error(
                    "invalid_profile_sha256",
                    "must be a 64-character hexadecimal digest",
                    f"{prefix}.profile_sha256",
                )
            )

        nonverifiable = (
            ingest_mode == "disabled"
            or lifecycle == "proposed"
            or lifecycle in INACTIVE_LIFECYCLES
        )
        if check_files and not (skip_nonverifiable_files and nonverifiable):
            require_regular_file(profile_path, f"{prefix}.profile_path", child_errors)
            require_regular_file(export_path, f"{prefix}.export_path", child_errors)
            if (
                profile_path is not None
                and valid_sha256(profile_digest)
                and profile_path.is_file()
            ):
                try:
                    actual_profile_digest = sha256_file(profile_path)
                except OSError as exc:
                    child_errors.append(
                        error(
                            "profile_digest_read_failed",
                            f"cannot read profile for digest: {exc}",
                            f"{prefix}.profile_path",
                        )
                    )
                else:
                    if actual_profile_digest != profile_digest.lower():
                        child_errors.append(
                            error(
                                "profile_digest_mismatch",
                                "profile SHA-256 does not match profile_sha256",
                                f"{prefix}.profile_sha256",
                            )
                        )
            if (
                export_path is not None
                and valid_sha256(expected_digest)
                and export_path.is_file()
            ):
                try:
                    actual_digest = sha256_file(export_path)
                except OSError as exc:
                    child_errors.append(
                        error(
                            "digest_read_failed",
                            f"cannot read export for digest: {exc}",
                            f"{prefix}.export_path",
                        )
                    )
                else:
                    if actual_digest != expected_digest.lower():
                        child_errors.append(
                            error(
                                "digest_mismatch",
                                "export SHA-256 does not match expected_sha256",
                                f"{prefix}.expected_sha256",
                            )
                        )

        errors.extend(child_errors)
        children_out.append(
            {
                "index": index,
                "graph_id": graph_id,
                "namespace": namespace,
                "profile_path": profile_path,
                "export_path": export_path,
                "data": child,
                "errors": child_errors,
            }
        )

    return errors, children_out, root


def public_child_result(child: dict[str, Any]) -> dict[str, Any]:
    data = child["data"]
    return {
        "graph_id": child["graph_id"],
        "namespace": child["namespace"],
        "owner": data.get("owner"),
        "lifecycle": data.get("lifecycle"),
        "ingest_mode": data.get("ingest_mode"),
        "authority_ref": data.get("authority_ref"),
        "validation_ref": data.get("validation_ref"),
        "validator_id": data.get("validator_id"),
        "definition_version": data.get("definition_version"),
        "profile_sha256": data.get("profile_sha256"),
        "expected_sha256": data.get("expected_sha256"),
        "status": "fail" if child["errors"] else "pass",
        "errors": child["errors"],
    }


def plan_action(child: dict[str, Any]) -> dict[str, Any]:
    data = child["data"]
    lifecycle = data.get("lifecycle")
    ingest_mode = data.get("ingest_mode")
    result: dict[str, Any] = {
        "graph_id": child["graph_id"],
        "namespace": child["namespace"],
        "owner": data.get("owner"),
        "lifecycle": lifecycle,
        "ingest_mode": ingest_mode,
        "authority_ref": data.get("authority_ref"),
        "validation_ref": data.get("validation_ref"),
        "validator_id": data.get("validator_id"),
        "definition_version": data.get("definition_version"),
        "profile_sha256": data.get("profile_sha256"),
        "expected_sha256": data.get("expected_sha256"),
    }
    if child["errors"]:
        result.update({"action": "correct_registry", "status": "blocked"})
    elif ingest_mode == "disabled":
        result.update(
            {"action": "none", "status": "not_run", "reason": "ingest_disabled"}
        )
    elif lifecycle == "proposed":
        result.update(
            {"action": "validate_child", "status": "not_run", "reason": "child_proposed"}
        )
    elif lifecycle == "quarantined":
        result.update({"action": "resolve_quarantine", "status": "planned"})
    elif lifecycle == "stale":
        result.update({"action": "refresh_or_retire", "status": "planned"})
    elif lifecycle == "retired":
        result.update(
            {"action": "none", "status": "not_run", "reason": "child_retired"}
        )
    elif lifecycle == "admitted":
        result.update({"action": "verify_approved_export", "status": "planned"})
    elif ingest_mode == "approved":
        result.update({"action": "review_for_admission", "status": "planned"})
    else:
        result.update({"action": "verify_manual_export", "status": "planned"})
    return result


def load_profile(path: Path, field_path: str) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(error("profile_read_failed", f"cannot read profile: {exc}", field_path))
        return None, errors
    except json.JSONDecodeError as exc:
        errors.append(
            error(
                "invalid_profile_json",
                f"profile is not valid JSON at line {exc.lineno}, column {exc.colno}",
                field_path,
            )
        )
        return None, errors
    if not isinstance(value, dict):
        errors.append(error("invalid_profile", "profile must be a JSON object", field_path))
        return None, errors
    return value, errors


def graphctl_module() -> Any:
    spec = importlib.util.spec_from_file_location("workspace_graphctl_v1", GRAPHCTL_PATH)
    if spec is None or spec.loader is None:
        raise OSError(f"cannot load graph validator at {GRAPHCTL_PATH}")
    module = importlib.util.module_from_spec(spec)
    previous_bytecode_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting
    return module


def graphctl_issues(
    entries: list[dict[str, str]], prefix: str
) -> list[dict[str, str]]:
    return [
        error(
            f"graphctl.{entry['code']}",
            entry["message"],
            f"{prefix}:{entry['path']}",
        )
        for entry in entries
    ]


def profile_policy_errors(
    profile: dict[str, Any], child: dict[str, Any], path: str
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    policy = profile.get("export_policy")
    if not isinstance(policy, dict):
        return failures
    for field in ("allowed_node_types", "allowed_edge_types"):
        registry_values = child.get(field)
        profile_values = policy.get(field)
        if isinstance(registry_values, list) and isinstance(profile_values, list):
            expansion = sorted(set(registry_values) - set(profile_values))
            if expansion:
                failures.append(
                    error(
                        "registry_policy_expansion",
                        f"registry {field} exceeds the child export policy: {', '.join(expansion)}",
                        f"{path}.{field}",
                    )
                )
    registry_ceiling = child.get("sensitivity_ceiling")
    profile_ceiling = policy.get("sensitivity_ceiling")
    if registry_ceiling in SENSITIVITIES and profile_ceiling in SENSITIVITIES:
        if SENSITIVITIES[registry_ceiling] > SENSITIVITIES[profile_ceiling]:
            failures.append(
                error(
                    "registry_sensitivity_expansion",
                    "registry sensitivity ceiling exceeds the child export policy",
                    f"{path}.sensitivity_ceiling",
                )
            )
    return failures


def has_namespace(identifier: Any, namespace: str) -> bool:
    return isinstance(identifier, str) and identifier.startswith(f"{namespace}:")


def validate_envelope_fields(
    record: dict[str, Any], path: str, namespace: str
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if not has_namespace(record.get("id"), namespace):
        failures.append(
            error(
                "namespace_violation",
                "record id must start with the child namespace and a colon",
                f"{path}.id",
            )
        )
    for field in ("owner", "source_ref", "observed_at"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            failures.append(
                error("missing_envelope_field", "must be a non-empty string", f"{path}.{field}")
            )
    evidence_state = record.get("evidence_state")
    if evidence_state not in EVIDENCE_STATES:
        failures.append(
            error(
                "invalid_evidence_state",
                "must be observed, asserted, inferred, verified, or accepted",
                f"{path}.evidence_state",
            )
        )
    if "authority_ref" in record and (
        not isinstance(record["authority_ref"], str) or not record["authority_ref"].strip()
    ):
        failures.append(
            error(
                "invalid_authority_ref",
                "must be a non-empty string when present",
                f"{path}.authority_ref",
            )
        )
    return failures


def verify_export(child: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    data = child["data"]
    export_path: Path = child["export_path"]
    namespace = child["namespace"]
    ceiling = data["sensitivity_ceiling"]
    allowed_node_types = set(data["allowed_node_types"])
    allowed_edge_types = set(data["allowed_edge_types"])
    failures: list[dict[str, Any]] = []
    record_count = 0
    try:
        stream = export_path.open("r", encoding="utf-8")
    except OSError as exc:
        return 0, [error("export_read_failed", f"cannot read export: {exc}", "export")]
    with stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            record_count += 1
            path = f"export:{line_number}"
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                failures.append(
                    error(
                        "invalid_jsonl",
                        f"record is not valid JSON at column {exc.colno}",
                        path,
                    )
                )
                continue
            if not isinstance(record, dict):
                failures.append(error("invalid_record", "record must be an object", path))
                continue
            kind = record.get("record_type")
            item_type = record.get("node_type") if kind == "node" else record.get("edge_type")
            failures.extend(validate_envelope_fields(record, path, namespace))
            if record.get("exportable") is not True:
                failures.append(
                    error("not_exportable", "exportable must be true", f"{path}.exportable")
                )
            sensitivity = record.get("sensitivity")
            if sensitivity not in SENSITIVITIES:
                failures.append(
                    error(
                        "invalid_sensitivity",
                        "sensitivity must be public, internal, or restricted",
                        f"{path}.sensitivity",
                    )
                )
            elif SENSITIVITIES[sensitivity] > SENSITIVITIES[ceiling]:
                failures.append(
                    error(
                        "sensitivity_exceeded",
                        "record sensitivity exceeds the child ceiling",
                        f"{path}.sensitivity",
                    )
                )
            if kind == "node":
                if not isinstance(item_type, str) or item_type not in allowed_node_types:
                    failures.append(
                        error(
                            "node_type_denied",
                            "node type is not in allowed_node_types",
                            f"{path}.node_type",
                        )
                    )
            elif kind == "edge":
                if not isinstance(item_type, str) or item_type not in allowed_edge_types:
                    failures.append(
                        error(
                            "edge_type_denied",
                            "edge type is not in allowed_edge_types",
                            f"{path}.edge_type",
                        )
                    )
                for endpoint in ("from", "to"):
                    value = record.get(endpoint)
                    if not isinstance(value, str) or not value.strip() or ":" not in value:
                        failures.append(
                            error(
                                "invalid_edge_endpoint",
                                "must be a namespaced identifier",
                                f"{path}.{endpoint}",
                            )
                        )
                    elif not has_namespace(value, namespace):
                        failures.append(
                            error(
                                "edge_endpoint_namespace_violation",
                                "child export endpoints must use the child namespace",
                                f"{path}.{endpoint}",
                            )
                        )
            else:
                failures.append(
                    error(
                        "invalid_record_type",
                        "record_type must be node or edge",
                        f"{path}.record_type",
                    )
                )
    return record_count, failures


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def command_validate(registry_path: Path, workspace_root: Path) -> int:
    registry_path = contained_registry_path(registry_path, workspace_root)
    registry = read_registry(registry_path)
    errors, children, root = validate_registry(
        registry, workspace_root, check_files=True
    )
    emit(
        {
            "command": "validate-registry",
            "registry": str(registry_path.resolve(strict=False)),
            "workspace_root": str(root) if root is not None else None,
            "graph_id": registry.get("graph_id"),
            "namespace": registry.get("namespace"),
            "owner": registry.get("owner"),
            "status": "fail" if errors else "pass",
            "children": [public_child_result(child) for child in children],
            "errors": errors,
        }
    )
    return 1 if errors else 0


def command_plan(registry_path: Path, workspace_root: Path) -> int:
    registry_path = contained_registry_path(registry_path, workspace_root)
    registry = read_registry(registry_path)
    errors, children, root = validate_registry(
        registry, workspace_root, check_files=False
    )
    actions = [plan_action(child) for child in children]
    actions.sort(key=lambda item: (item.get("graph_id") or "", item.get("namespace") or ""))
    emit(
        {
            "command": "plan",
            "registry": str(registry_path.resolve(strict=False)),
            "workspace_root": str(root) if root is not None else None,
            "graph_id": registry.get("graph_id"),
            "namespace": registry.get("namespace"),
            "owner": registry.get("owner"),
            "status": "fail" if errors else "pass",
            "actions": actions,
            "errors": errors,
        }
    )
    return 1 if errors else 0


def command_verify(registry_path: Path, workspace_root: Path) -> int:
    registry_path = contained_registry_path(registry_path, workspace_root)
    registry = read_registry(registry_path)
    registry_errors, children, root = validate_registry(
        registry,
        workspace_root,
        check_files=True,
        skip_nonverifiable_files=True,
    )
    results: list[dict[str, Any]] = []
    verification_failed = bool(registry_errors)
    for child in children:
        result: dict[str, Any] = {
            "graph_id": child["graph_id"],
            "namespace": child["namespace"],
            "owner": child["data"].get("owner"),
            "lifecycle": child["data"].get("lifecycle"),
            "ingest_mode": child["data"].get("ingest_mode"),
            "authority_ref": child["data"].get("authority_ref"),
            "validation_ref": child["data"].get("validation_ref"),
            "validator_id": child["data"].get("validator_id"),
            "definition_version": child["data"].get("definition_version"),
            "profile_sha256": child["data"].get("profile_sha256"),
            "expected_sha256": child["data"].get("expected_sha256"),
        }
        data = child["data"]
        if child["errors"]:
            result.update({"status": "fail", "records_checked": 0, "errors": child["errors"]})
            verification_failed = True
        elif data.get("ingest_mode") == "disabled":
            result.update(
                {
                    "status": "not_run",
                    "reason": "ingest_disabled",
                    "records_checked": 0,
                    "errors": [],
                }
            )
        elif data.get("lifecycle") == "proposed":
            result.update(
                {
                    "status": "not_run",
                    "reason": "child_proposed",
                    "records_checked": 0,
                    "errors": [],
                }
            )
        elif data.get("lifecycle") in INACTIVE_LIFECYCLES:
            result.update(
                {
                    "status": "not_run",
                    "reason": f"child_{data['lifecycle']}",
                    "records_checked": 0,
                    "errors": [],
                }
            )
        else:
            profile, profile_errors = load_profile(
                child["profile_path"], f"children[{child['index']}].profile_path"
            )
            if profile is not None:
                try:
                    graphctl = graphctl_module()
                except (OSError, ImportError) as exc:
                    profile_errors.append(
                        error(
                            "graphctl_unavailable",
                            str(exc),
                            f"children[{child['index']}].profile_path",
                        )
                    )
                else:
                    profile_errors.extend(
                        graphctl_issues(
                            graphctl.validate_profile(profile),
                            f"children[{child['index']}].profile_path",
                        )
                    )
                    for identity_field in ("graph_id", "namespace", "definition_version"):
                        if profile.get(identity_field) != data.get(identity_field):
                            profile_errors.append(
                                error(
                                    "profile_identity_mismatch",
                                    f"profile {identity_field} does not match registry child",
                                    f"children[{child['index']}].profile_path",
                                )
                            )
                    profile_scope = profile.get("scope")
                    profile_owner = (
                        profile_scope.get("owner")
                        if isinstance(profile_scope, dict)
                        else None
                    )
                    if profile_owner != data.get("owner"):
                        profile_errors.append(
                            error(
                                "profile_owner_mismatch",
                                "profile owner does not match registry child",
                                f"children[{child['index']}].profile_path",
                            )
                        )
                    profile_errors.extend(
                        profile_policy_errors(
                            profile,
                            data,
                            f"children[{child['index']}]",
                        )
                    )
            record_count, export_errors = verify_export(child)
            if profile is not None and not profile_errors:
                try:
                    records = graphctl.read_jsonl(str(child["export_path"]))
                except graphctl.InputError as exc:
                    export_errors.append(
                        error(
                            "graphctl.export_input",
                            str(exc),
                            f"children[{child['index']}].export_path",
                        )
                    )
                else:
                    export_errors.extend(
                        graphctl_issues(
                            graphctl.validate_export(records, profile),
                            f"children[{child['index']}].export_path",
                        )
                    )
            verification_errors = profile_errors + export_errors
            result.update(
                {
                    "status": "fail" if verification_errors else "pass",
                    "records_checked": record_count,
                    "errors": verification_errors,
                }
            )
            if verification_errors:
                verification_failed = True
        results.append(result)

    results.sort(key=lambda item: (item.get("graph_id") or "", item.get("namespace") or ""))
    emit(
        {
            "command": "verify",
            "registry": str(registry_path.resolve(strict=False)),
            "workspace_root": str(root) if root is not None else None,
            "graph_id": registry.get("graph_id"),
            "namespace": registry.get("namespace"),
            "owner": registry.get("owner"),
            "status": "fail" if verification_failed else "pass",
            "children": results,
            "errors": registry_errors,
        }
    )
    return 1 if verification_failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stewardctl",
        description="Validate and verify a workspace graph federation without mutation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("validate-registry", "plan", "verify"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("registry", type=Path)
        command_parser.add_argument("--workspace-root", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-registry":
            return command_validate(args.registry, args.workspace_root)
        if args.command == "plan":
            return command_plan(args.registry, args.workspace_root)
        return command_verify(args.registry, args.workspace_root)
    except RegistryInputError as exc:
        print(f"stewardctl: input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
