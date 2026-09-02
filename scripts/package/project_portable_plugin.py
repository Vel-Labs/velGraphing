#!/usr/bin/env python3
"""Project canonical Graph Engineering sources into the portable plugin tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any


SCHEMA_VERSION = "graph-engineering-projection-map-v1"
STATE_SCHEMA_VERSION = "graph-engineering-projection-state-v1"
REQUIRED_EXCLUSIONS = {
    PurePosixPath("contracts/core/routing-authority-v3.schema.json"),
    PurePosixPath("contracts/core/routing-context-v3.schema.json"),
    PurePosixPath("contracts/core/routing-decision-v3.schema.json"),
    PurePosixPath("contracts/core/routing-evidence-v3.schema.json"),
}
IGNORED_SOURCE_PARTS = {"__pycache__"}
IGNORED_SOURCE_SUFFIXES = {".pyc", ".pyo"}


class ProjectionError(RuntimeError):
    """Raised before projection when the contract or filesystem is unsafe."""


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ProjectionError(f"{label} must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        raise ProjectionError(f"{label} must be a normalized relative POSIX path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ProjectionError(f"{label} must not contain traversal segments")
    return path


def _within(path: PurePosixPath, parent: PurePosixPath) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _load_contract(contract_path: Path) -> dict[str, Any]:
    try:
        contract = json.loads(_read_regular_file(contract_path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectionError(f"cannot read projection contract: {error}") from error
    if not isinstance(contract, dict):
        raise ProjectionError("projection contract must be an object")
    if set(contract) != {"schema_version", "managed_root", "state_file", "exclusions", "mappings"}:
        raise ProjectionError("projection contract has missing or unsupported fields")
    if contract["schema_version"] != SCHEMA_VERSION:
        raise ProjectionError("unsupported projection contract schema")
    managed_root = _safe_relative(contract["managed_root"], "managed_root")
    state_file = _safe_relative(contract["state_file"], "state_file")
    if len(state_file.parts) != 1:
        raise ProjectionError("state_file must be a direct child of managed_root")
    mappings = contract["mappings"]
    if not isinstance(mappings, list) or not mappings:
        raise ProjectionError("mappings must be a non-empty array")
    seen_sources: set[PurePosixPath] = set()
    seen_targets: set[PurePosixPath] = set()
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict) or set(mapping) != {"source", "target"}:
            raise ProjectionError(f"mappings[{index}] has an invalid shape")
        source = _safe_relative(mapping["source"], f"mappings[{index}].source")
        target = _safe_relative(mapping["target"], f"mappings[{index}].target")
        if not _within(target, managed_root) or target == managed_root:
            raise ProjectionError(f"mappings[{index}].target must be below managed_root")
        if source in seen_sources or target in seen_targets:
            raise ProjectionError("projection mappings must have unique sources and targets")
        if any(_within(source, prior) or _within(prior, source) for prior in seen_sources):
            raise ProjectionError("projection sources must not overlap")
        if any(_within(target, prior) or _within(prior, target) for prior in seen_targets):
            raise ProjectionError("projection targets must not overlap")
        if _within(source, managed_root) or _within(managed_root, source):
            raise ProjectionError("projection sources and managed_root must not overlap")
        seen_sources.add(source)
        seen_targets.add(target)
    exclusions = contract["exclusions"]
    if not isinstance(exclusions, list):
        raise ProjectionError("exclusions must be an array")
    normalized: list[PurePosixPath] = [
        _safe_relative(value, f"exclusions[{index}]")
        for index, value in enumerate(exclusions)
    ]
    if len(set(normalized)) != len(normalized):
        raise ProjectionError("projection exclusions must be unique")
    if set(normalized) != REQUIRED_EXCLUSIONS:
        raise ProjectionError("projection exclusions must be exactly the approved canonical files")
    if any(
        left != right and (_within(left, right) or _within(right, left))
        for left in normalized
        for right in normalized
    ):
        raise ProjectionError("projection exclusions must not overlap")
    for exclusion in normalized:
        owners = [source for source in seen_sources if _within(exclusion, source) and exclusion != source]
        if len(owners) != 1:
            raise ProjectionError("each projection exclusion must be below exactly one source")
    return contract


def _read_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProjectionError(f"not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def _reject_symlink_components(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ProjectionError(f"path escapes declared root: {path}") from error
    current = root
    if root.is_symlink():
        raise ProjectionError(f"declared root must not be a symlink: {root}")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ProjectionError(f"symlink traversal is not allowed: {current}")


def _scan_source(root: Path, source: PurePosixPath) -> list[tuple[PurePosixPath, bytes]]:
    source_path = root.joinpath(*source.parts)
    _reject_symlink_components(root, source_path)
    if not source_path.is_dir():
        raise ProjectionError(f"projection source is not a directory: {source}")
    files: list[tuple[PurePosixPath, bytes]] = []
    for directory, names, filenames in os.walk(source_path, followlinks=False):
        names[:] = [name for name in names if name not in IGNORED_SOURCE_PARTS]
        names.sort()
        filenames.sort()
        directory_path = Path(directory)
        for name in names:
            child = directory_path / name
            if child.is_symlink():
                raise ProjectionError(f"source symlink is not allowed: {child.relative_to(root)}")
        for name in filenames:
            if Path(name).suffix in IGNORED_SOURCE_SUFFIXES:
                continue
            child = directory_path / name
            if child.is_symlink():
                raise ProjectionError(f"source symlink is not allowed: {child.relative_to(root)}")
            relative = PurePosixPath(child.relative_to(source_path).as_posix())
            files.append((relative, _read_regular_file(child)))
    return files


def _scan_managed_tree(root: Path) -> tuple[set[PurePosixPath], set[PurePosixPath]]:
    files: set[PurePosixPath] = set()
    directories: set[PurePosixPath] = {PurePosixPath(".")}
    for directory, names, filenames in os.walk(root, followlinks=False):
        names.sort()
        filenames.sort()
        directory_path = Path(directory)
        relative_directory = PurePosixPath(directory_path.relative_to(root).as_posix())
        for name in names:
            child = directory_path / name
            if child.is_symlink():
                raise ProjectionError(f"managed target symlink is not allowed: {child}")
            directories.add(relative_directory / name)
        for name in filenames:
            child = directory_path / name
            if child.is_symlink():
                raise ProjectionError(f"managed target symlink is not allowed: {child}")
            if not child.is_file():
                raise ProjectionError(f"managed target contains a non-regular file: {child}")
            files.add(relative_directory / name)
    return files, directories


def _expected_directories(files: set[PurePosixPath]) -> set[PurePosixPath]:
    expected = {PurePosixPath(".")}
    for path in files:
        parent = path.parent
        while parent != PurePosixPath("."):
            expected.add(parent)
            parent = parent.parent
    return expected


def _preflight_existing(
    managed_path: Path,
    state_name: PurePosixPath,
    expected_files: dict[PurePosixPath, bytes],
    contract_digest: str,
) -> None:
    if not managed_path.exists():
        return
    if managed_path.is_symlink() or not managed_path.is_dir():
        raise ProjectionError("managed_root must be a real directory")
    actual_files, actual_directories = _scan_managed_tree(managed_path)
    state_relative = state_name
    state_path = managed_path.joinpath(*state_relative.parts)
    if state_relative not in actual_files:
        if actual_files or actual_directories != {PurePosixPath(".")}:
            raise ProjectionError("managed_root contains unmanaged content")
        return
    try:
        state = json.loads(_read_regular_file(state_path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectionError(f"invalid projection state: {error}") from error
    if not isinstance(state, dict) or set(state) != {"schema_version", "contract_sha256", "files"}:
        raise ProjectionError("projection state has an invalid shape")
    if state["schema_version"] != STATE_SCHEMA_VERSION or state["contract_sha256"] != contract_digest:
        raise ProjectionError("projection state does not match this contract")
    entries = state["files"]
    if not isinstance(entries, list):
        raise ProjectionError("projection state files must be an array")
    recorded: dict[PurePosixPath, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise ProjectionError("projection state contains an invalid file entry")
        path = _safe_relative(entry["path"], "projection state file path")
        if path in recorded:
            raise ProjectionError("projection state contains a duplicate file path")
        recorded[path] = entry
    ignored_recorded = {
        path
        for path in recorded
        if any(part in IGNORED_SOURCE_PARTS for part in path.parts)
        or path.suffix in IGNORED_SOURCE_SUFFIXES
    }
    recorded_files = set(recorded) - ignored_recorded
    if actual_files != recorded_files | {state_relative}:
        raise ProjectionError("managed_root contains unmanaged or missing files")
    if actual_directories != _expected_directories(actual_files):
        raise ProjectionError("managed_root contains unmanaged directories")
    for path, entry in recorded.items():
        if path in ignored_recorded:
            continue
        data = _read_regular_file(managed_path.joinpath(*path.parts))
        if entry["size"] != len(data) or entry["sha256"] != _digest(data):
            raise ProjectionError(f"managed file changed outside the projector: {path}")
    # A valid prior state authorizes replacement. All unsafe checks finish first.
    if set(recorded) == set(expected_files) and all(
        recorded[path]["sha256"] == _digest(data) for path, data in expected_files.items()
    ):
        return


def project(project_root: Path, contract_path: Path) -> dict[str, Any]:
    """Project files and return deterministic, host-neutral projection state."""
    root = project_root.absolute()
    contract_path = contract_path.absolute()
    if not root.is_dir():
        raise ProjectionError("project root must be a directory")
    _reject_symlink_components(root, contract_path)
    contract = _load_contract(contract_path)
    contract_bytes = _canonical_json(contract)
    contract_digest = _digest(contract_bytes)
    managed_root = _safe_relative(contract["managed_root"], "managed_root")
    state_name = _safe_relative(contract["state_file"], "state_file")
    managed_path = root.joinpath(*managed_root.parts)
    _reject_symlink_components(root, managed_path)

    expected_files: dict[PurePosixPath, bytes] = {}
    exclusions = {_safe_relative(value, "exclusion") for value in contract["exclusions"]}
    found_exclusions: set[PurePosixPath] = set()
    for mapping in contract["mappings"]:
        source = _safe_relative(mapping["source"], "mapping source")
        target = _safe_relative(mapping["target"], "mapping target")
        target_under_managed = target.relative_to(managed_root)
        for relative, data in _scan_source(root, source):
            canonical = source / relative
            if canonical in exclusions:
                found_exclusions.add(canonical)
                continue
            destination = target_under_managed / relative
            if destination in expected_files:
                raise ProjectionError(f"duplicate projected target: {destination}")
            expected_files[destination] = data
    if found_exclusions != exclusions:
        raise ProjectionError("every projection exclusion must name an existing regular source file")

    _preflight_existing(managed_path, state_name, expected_files, contract_digest)
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "contract_sha256": contract_digest,
        "files": [
            {"path": path.as_posix(), "sha256": _digest(expected_files[path]), "size": len(expected_files[path])}
            for path in sorted(expected_files, key=lambda item: item.as_posix())
        ],
    }

    managed_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(root, managed_path.parent)
    stage_parent = Path(tempfile.mkdtemp(prefix=".graph-engineering-stage-", dir=managed_path.parent))
    stage = stage_parent / "runtime"
    backup: Path | None = None
    try:
        stage.mkdir()
        for relative in sorted(expected_files, key=lambda item: item.as_posix()):
            destination = stage.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(expected_files[relative])
        stage.joinpath(*state_name.parts).write_bytes(_canonical_json(state))
        if managed_path.exists():
            backup = stage_parent / "previous-runtime"
            managed_path.rename(backup)
        stage.rename(managed_path)
        if backup is not None:
            shutil.rmtree(backup)
    except Exception:
        if backup is not None and backup.exists() and not managed_path.exists():
            backup.rename(managed_path)
        raise
    finally:
        if stage_parent.exists():
            shutil.rmtree(stage_parent)
    return state


def main() -> int:
    script_root = Path(__file__).absolute().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=script_root, help="Project root. Defaults to the repository root.")
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="Projection contract. Defaults to contracts/package/projection-map.json under --root.",
    )
    arguments = parser.parse_args()
    contract = arguments.contract or arguments.root / "contracts/package/projection-map.json"
    try:
        state = project(arguments.root, contract)
    except ProjectionError as error:
        parser.exit(2, f"projection refused: {error}\n")
    print(json.dumps(state, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
