#!/usr/bin/env python3
"""Build or verify the Graph Engineering source package release identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Any


SCHEMA_VERSION = "graph-engineering-release-manifest-v1"
PROJECTION_SCHEMA_VERSION = "graph-engineering-projection-map-v1"
PROJECTION_STATE_SCHEMA_VERSION = "graph-engineering-projection-state-v1"
PACKAGE_NAME = "graph-engineering"
PACKAGE_VERSION = "0.1.0"
PLUGIN_RELATIVE = PurePosixPath("plugins/graph-engineering")
MANIFEST_RELATIVE = PurePosixPath(".codex-plugin/release-manifest.json")
PLUGIN_JSON_RELATIVE = PurePosixPath(".codex-plugin/plugin.json")
PROJECTION_MAP_RELATIVE = PurePosixPath("contracts/package/projection-map.json")
MAX_FILE_BYTES = 8 * 1024 * 1024
SHA256_HEX = set("0123456789abcdef")
FORBIDDEN_NAMES = {
    ".ds_store",
    ".env",
    ".git",
    ".idea",
    ".ssh",
    ".vscode",
    "__pycache__",
    "credentials",
    "private",
    "secrets",
}
FORBIDDEN_SUFFIXES = (".key", ".pem", ".pyc", ".pyo")
REQUIRED_PROJECTION_EXCLUSIONS = {
    PurePosixPath("contracts/core/routing-authority-v3.schema.json"),
    PurePosixPath("contracts/core/routing-context-v3.schema.json"),
    PurePosixPath("contracts/core/routing-decision-v3.schema.json"),
    PurePosixPath("contracts/core/routing-evidence-v3.schema.json"),
}


class ParityError(ValueError):
    """A stable fail-closed parity error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ParityError("json_duplicate_key")
        value[key] = item
    return value


def _non_finite(_: str) -> object:
    raise ParityError("json_non_finite")


def _json(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_non_finite,
        )
    except ParityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ParityError(code) from error
    if not isinstance(value, dict):
        raise ParityError(code)
    return value


def _safe_relative(value: object, *, code: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ParityError(code)
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ParityError(code)
    return path


def _is_within(path: PurePosixPath, parent: PurePosixPath) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _portable_path(path: PurePosixPath) -> None:
    for part in path.parts:
        lowered = part.casefold()
        if lowered in FORBIDDEN_NAMES or lowered.endswith(FORBIDDEN_SUFFIXES):
            raise ParityError("private_or_machine_path")
        if ":" in part or part.startswith("~"):
            raise ParityError("private_or_machine_path")


def _root(value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ParityError("root_invalid")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or "\x00" in str(path):
        raise ParityError("root_invalid")
    lexical = Path(os.path.abspath(path))
    try:
        named = lexical.lstat()
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise ParityError("root_unavailable") from error
    mac_alias = str(lexical).startswith("/var/") and str(resolved) == "/private" + str(lexical)
    if (
        (resolved != lexical and not mac_alias)
        or stat.S_ISLNK(named.st_mode)
        or not stat.S_ISDIR(named.st_mode)
    ):
        raise ParityError("root_alias_forbidden")
    return lexical


def _check_components(path: Path, root: Path, *, alias_code: str, missing_code: str) -> None:
    """Reject aliases and escapes in every named component below a trusted root."""
    lexical_root = Path(os.path.abspath(root))
    lexical_path = Path(os.path.abspath(path))
    try:
        relative = lexical_path.relative_to(lexical_root)
        root_stat = lexical_root.lstat()
        resolved_root = lexical_root.resolve(strict=True)
    except ValueError as error:
        raise ParityError("path_outside_root") from error
    except FileNotFoundError as error:
        raise ParityError(missing_code) from error
    except OSError as error:
        raise ParityError("path_unavailable") from error
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ParityError(alias_code)
    current = lexical_root
    for part in relative.parts:
        current = current / part
        try:
            named = current.lstat()
            resolved = current.resolve(strict=True)
        except FileNotFoundError as error:
            raise ParityError(missing_code) from error
        except OSError as error:
            raise ParityError("path_unavailable") from error
        if stat.S_ISLNK(named.st_mode):
            raise ParityError(alias_code)
        try:
            resolved.relative_to(resolved_root)
        except ValueError as error:
            raise ParityError("path_outside_root") from error


def _read_regular(path: Path, root: Path) -> bytes:
    _check_components(
        path,
        root,
        alias_code="file_nonregular_or_alias",
        missing_code="file_missing",
    )
    try:
        path.relative_to(root)
        named = path.lstat()
    except ValueError as error:
        raise ParityError("path_outside_root") from error
    except FileNotFoundError as error:
        raise ParityError("file_missing") from error
    except OSError as error:
        raise ParityError("file_unavailable") from error
    if stat.S_ISLNK(named.st_mode) or not stat.S_ISREG(named.st_mode):
        raise ParityError("file_nonregular_or_alias")
    if named.st_nlink != 1:
        raise ParityError("file_hardlink_forbidden")
    if named.st_size > MAX_FILE_BYTES:
        raise ParityError("file_oversize")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ParityError("file_identity_changed") from error
    try:
        before = os.fstat(descriptor)
        raw = bytearray()
        while len(raw) <= MAX_FILE_BYTES:
            chunk = os.read(descriptor, min(65536, MAX_FILE_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        current = path.lstat()
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or current.st_nlink != 1
        or (before.st_dev, before.st_ino, before.st_size)
        != (after.st_dev, after.st_ino, after.st_size)
        or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise ParityError("file_identity_changed")
    if len(raw) > MAX_FILE_BYTES:
        raise ParityError("file_oversize")
    return bytes(raw)


def _inventory(
    root: Path,
    *,
    exclude: PurePosixPath | None = None,
    anchor: Path | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    read_root = anchor or root
    _check_components(
        root,
        read_root,
        alias_code="tree_alias_forbidden",
        missing_code="tree_unavailable",
    )
    try:
        root_stat = root.lstat()
    except OSError as error:
        raise ParityError("tree_unavailable") from error
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ParityError("tree_alias_forbidden")

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise ParityError("tree_unavailable") from error
        for entry in entries:
            path = Path(entry.path)
            relative = PurePosixPath(path.relative_to(root).as_posix())
            _portable_path(relative)
            try:
                named = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ParityError("tree_unavailable") from error
            if stat.S_ISLNK(named.st_mode):
                raise ParityError("tree_alias_forbidden")
            if stat.S_ISDIR(named.st_mode):
                visit(path)
                continue
            if not stat.S_ISREG(named.st_mode):
                raise ParityError("tree_nonregular_forbidden")
            if relative == exclude:
                continue
            raw = _read_regular(path, read_root)
            rows.append({"path": relative.as_posix(), "sha256": digest(raw), "size": len(raw)})

    visit(root)
    rows.sort(key=lambda row: row["path"])
    if not rows:
        raise ParityError("tree_empty")
    return rows


def _projection_contract(project: Path) -> tuple[dict[str, Any], str]:
    path = project.joinpath(*PROJECTION_MAP_RELATIVE.parts)
    contract = _json(_read_regular(path, project), "projection_map_invalid")
    if set(contract) != {"schema_version", "managed_root", "state_file", "exclusions", "mappings"}:
        raise ParityError("projection_map_shape")
    if contract["schema_version"] != PROJECTION_SCHEMA_VERSION:
        raise ParityError("projection_map_schema")
    managed = _safe_relative(contract["managed_root"], code="projection_path_invalid")
    state_file = _safe_relative(contract["state_file"], code="projection_path_invalid")
    if managed != PLUGIN_RELATIVE / "runtime" or len(state_file.parts) != 1:
        raise ParityError("projection_boundary_invalid")
    mappings = contract["mappings"]
    if not isinstance(mappings, list) or not mappings:
        raise ParityError("projection_map_shape")
    seen_sources: set[PurePosixPath] = set()
    seen_targets: set[PurePosixPath] = set()
    for row in mappings:
        if not isinstance(row, dict) or set(row) != {"source", "target"}:
            raise ParityError("projection_map_shape")
        source = _safe_relative(row["source"], code="projection_path_invalid")
        target = _safe_relative(row["target"], code="projection_path_invalid")
        _portable_path(source)
        _portable_path(target)
        if source in seen_sources or target in seen_targets:
            raise ParityError("projection_duplicate")
        try:
            target.relative_to(managed)
        except ValueError as error:
            raise ParityError("projection_target_escape") from error
        seen_sources.add(source)
        seen_targets.add(target)
    exclusions = contract["exclusions"]
    if not isinstance(exclusions, list):
        raise ParityError("projection_exclusions_invalid")
    normalized = [
        _safe_relative(value, code="projection_exclusion_invalid") for value in exclusions
    ]
    if len(set(normalized)) != len(normalized):
        raise ParityError("projection_exclusion_duplicate")
    if set(normalized) != REQUIRED_PROJECTION_EXCLUSIONS:
        raise ParityError("projection_exclusions_unapproved")
    if any(
        left != right
        and (
            _is_within(left, right)
            or _is_within(right, left)
        )
        for left in normalized
        for right in normalized
    ):
        raise ParityError("projection_exclusion_overlap")
    for exclusion in normalized:
        owners = [
            source
            for source in seen_sources
            if exclusion != source and _is_within(exclusion, source)
        ]
        if len(owners) != 1:
            raise ParityError("projection_exclusion_non_source")
    return contract, digest(canonical_json(contract))


def _verify_projection(project: Path, contract: dict[str, Any], contract_digest: str) -> None:
    managed = _safe_relative(contract["managed_root"], code="projection_path_invalid")
    state_name = _safe_relative(contract["state_file"], code="projection_path_invalid")
    expected: dict[str, bytes] = {}
    exclusions = {
        _safe_relative(value, code="projection_exclusion_invalid")
        for value in contract["exclusions"]
    }
    found_exclusions: set[PurePosixPath] = set()
    for mapping in contract["mappings"]:
        source = _safe_relative(mapping["source"], code="projection_path_invalid")
        target = _safe_relative(mapping["target"], code="projection_path_invalid")
        source_root = project.joinpath(*source.parts)
        if not source_root.is_dir() or source_root.is_symlink():
            raise ParityError("projection_source_invalid")
        target_under_plugin = target.relative_to(PLUGIN_RELATIVE)
        for row in _inventory(source_root, anchor=project):
            relative = _safe_relative(row["path"], code="projection_path_invalid")
            canonical = source / relative
            if canonical in exclusions:
                found_exclusions.add(canonical)
                continue
            destination = (target_under_plugin / relative).as_posix()
            if destination in expected:
                raise ParityError("projection_duplicate")
            expected[destination] = _read_regular(source_root.joinpath(*relative.parts), project)
    if found_exclusions != exclusions:
        raise ParityError("projection_exclusion_missing_or_nonregular")

    plugin_root = project.joinpath(*PLUGIN_RELATIVE.parts)
    for destination, source_raw in expected.items():
        package_path = plugin_root.joinpath(*PurePosixPath(destination).parts)
        if _read_regular(package_path, project) != source_raw:
            raise ParityError("projection_changed")

    runtime_root = project.joinpath(*managed.parts)
    actual_runtime = {
        row["path"]
        for row in _inventory(runtime_root, anchor=project)
        if row["path"] != state_name.as_posix()
    }
    expected_runtime = {
        PurePosixPath(path).relative_to("runtime").as_posix() for path in expected
    }
    if actual_runtime != expected_runtime:
        raise ParityError("projection_missing_or_extra")

    state = _json(
        _read_regular(runtime_root.joinpath(*state_name.parts), project),
        "projection_state_invalid",
    )
    if set(state) != {"schema_version", "contract_sha256", "files"}:
        raise ParityError("projection_state_invalid")
    if (
        state["schema_version"] != PROJECTION_STATE_SCHEMA_VERSION
        or state["contract_sha256"] != contract_digest
    ):
        raise ParityError("projection_state_identity")
    expected_state = [
        {
            "path": path,
            "sha256": digest(expected["runtime/" + path]),
            "size": len(expected["runtime/" + path]),
        }
        for path in sorted(expected_runtime)
    ]
    if state["files"] != expected_state:
        raise ParityError("projection_state_drift")


def _candidate_payload(files: list[dict[str, Any]], projection_digest: str) -> dict[str, Any]:
    return {
        "files": files,
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "projection_map_sha256": projection_digest,
        "schema_version": SCHEMA_VERSION,
    }


def build_manifest(project_root: object) -> dict[str, Any]:
    project = _root(project_root)
    contract, projection_digest = _projection_contract(project)
    _verify_projection(project, contract, projection_digest)
    plugin_root = project.joinpath(*PLUGIN_RELATIVE.parts)
    files = _inventory(plugin_root, exclude=MANIFEST_RELATIVE, anchor=project)
    plugin = _json(
        _read_regular(plugin_root.joinpath(*PLUGIN_JSON_RELATIVE.parts), project),
        "plugin_json_invalid",
    )
    if plugin.get("name") != PACKAGE_NAME or plugin.get("version") != PACKAGE_VERSION:
        raise ParityError("plugin_identity_mismatch")
    payload = _candidate_payload(files, projection_digest)
    return {**payload, "candidate_sha256": digest(canonical_json(payload))}


def write_manifest(project_root: object) -> dict[str, Any]:
    project = _root(project_root)
    manifest = build_manifest(project)
    target = project.joinpath(*PLUGIN_RELATIVE.parts, *MANIFEST_RELATIVE.parts)
    _check_components(
        target.parent,
        project,
        alias_code="tree_alias_forbidden",
        missing_code="tree_unavailable",
    )
    if target.exists() or target.is_symlink():
        _read_regular(target, project)
    raw = canonical_json(manifest)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".release-manifest-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        remaining = memoryview(raw)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise ParityError("manifest_write_failed")
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
    return manifest


def verify(project_root: object) -> dict[str, Any]:
    project = _root(project_root)
    plugin_root = project.joinpath(*PLUGIN_RELATIVE.parts)
    manifest_path = plugin_root.joinpath(*MANIFEST_RELATIVE.parts)
    actual = _json(_read_regular(manifest_path, project), "release_manifest_invalid")
    if set(actual) != {
        "candidate_sha256",
        "files",
        "package",
        "projection_map_sha256",
        "schema_version",
    }:
        raise ParityError("release_manifest_shape")
    files = actual["files"]
    if not isinstance(files, list):
        raise ParityError("release_manifest_shape")
    paths: list[str] = []
    for row in files:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size"}:
            raise ParityError("release_entry_shape")
        path = _safe_relative(row["path"], code="release_path_invalid")
        _portable_path(path)
        if path == MANIFEST_RELATIVE:
            raise ParityError("release_manifest_self_entry")
        if path.as_posix() in paths:
            raise ParityError("release_duplicate_path")
        if not isinstance(row["size"], int) or isinstance(row["size"], bool) or row["size"] < 0:
            raise ParityError("release_size_invalid")
        if (
            not isinstance(row["sha256"], str)
            or len(row["sha256"]) != 64
            or set(row["sha256"]) - SHA256_HEX
        ):
            raise ParityError("release_digest_invalid")
        paths.append(path.as_posix())
    if paths != sorted(paths):
        raise ParityError("release_paths_unsorted")
    expected = build_manifest(project)
    if actual != expected:
        raise ParityError("source_package_drift")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).absolute().parents[2],
        help="Absolute project root. Defaults to this source project.",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Atomically replace the source release manifest from current governed bytes.",
    )
    arguments = parser.parse_args()
    try:
        manifest = write_manifest(arguments.root) if arguments.write_manifest else verify(arguments.root)
    except ParityError as error:
        parser.exit(2, f"parity refused: {error.code}\n")
    print(json.dumps({"candidate_sha256": manifest["candidate_sha256"], "files": len(manifest["files"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
