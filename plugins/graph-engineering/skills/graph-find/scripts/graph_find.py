#!/usr/bin/env python3
"""Portable, read-only Git-tracked repository adapter for ``/graph-find``."""

from __future__ import annotations

import argparse
import ast
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
import sys
from typing import Sequence
from urllib.parse import unquote

sys.dont_write_bytecode = True


_source_root = next(
    (
        _parent
        for _parent in Path(__file__).resolve().parents
        if (_parent / "packages" / "core").is_dir()
    ),
    None,
)
if _source_root is not None:
    sys.path.insert(0, str(_source_root))
else:
    _runtime_root = next(
        (
            _parent / "runtime"
            for _parent in Path(__file__).resolve().parents
            if (_parent / "runtime" / "core").is_dir()
        ),
        None,
    )
    if _runtime_root is not None:
        sys.path.insert(0, str(_runtime_root))

try:  # noqa: E402
    from packages.core import (
        Admission,
        Freshness,
        Graph,
        GraphEdge,
        GraphRecord,
        Provenance,
        Sensitivity,
        SourceCoordinate,
        SourceIdentityV4,
        SourceSnapshotV4,
        TaskSpec,
        TrustClass,
        graph_find,
    )
except ModuleNotFoundError:  # packaged plugin runtime
    from core import (  # type: ignore[no-redef]
        Admission,
        Freshness,
        Graph,
        GraphEdge,
        GraphRecord,
        Provenance,
        Sensitivity,
        SourceCoordinate,
        SourceIdentityV4,
        SourceSnapshotV4,
        TaskSpec,
        TrustClass,
        graph_find,
    )


DEFAULT_MAX_FILE_BYTES = 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 16 * 1024 * 1024
HARD_MAX_FILE_BYTES = 16 * 1024 * 1024
HARD_MAX_TOTAL_BYTES = 128 * 1024 * 1024
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,63}")
_MARKDOWN_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_MARKDOWN_LINK = re.compile(r"\[[^\]\n]+\]\(([^()\s]+#[^()\s#]+)\)")
_SENSITIVE_COMPONENTS = frozenset({"private", "secrets", "credentials"})
_SENSITIVE_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pfx"})
_PRIVATE_KEY_BASENAMES = frozenset(
    {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", "private-key", "private_key", "privatekey"}
)


class InputError(ValueError):
    """Raised for unsafe or unreadable adapter input."""


def _canonical_root(value: str) -> Path:
    if not os.path.isabs(value):
        raise InputError("--root must be an absolute path")
    if value != os.path.normpath(value):
        raise InputError("--root must not contain path aliases")
    root = Path(value)
    if not root.is_dir():
        raise InputError("--root must be a directory")
    if root.is_symlink():
        raise InputError("--root must not be a symlink alias")
    return root


def _safe_relative(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise InputError("Git path is not a normalized relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise InputError("Git path is not a normalized relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise InputError("Git path contains an alias or escape")
    return path


def _is_sensitive_path(relative: PurePosixPath) -> bool:
    parts = tuple(part.casefold() for part in relative.parts)
    basename = parts[-1]
    return (
        basename == ".env"
        or bool(set(parts) & _SENSITIVE_COMPONENTS)
        or any(basename.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)
        or basename in _PRIVATE_KEY_BASENAMES
    )


def _reject_symlink_components(root: Path, path: Path) -> None:
    relative = path.relative_to(root)
    if root.is_symlink():
        raise InputError("repository root must not be a symlink alias")
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise InputError(f"tracked path is a symlink: {relative.as_posix()}")


def _git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise InputError(f"cannot run git: {error}") from error
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise InputError(f"git {' '.join(arguments)} failed: {detail or result.returncode}")
    return result.stdout


def _repository_root(root: Path) -> None:
    reported = _git(root, "rev-parse", "--show-toplevel").decode("utf-8", "strict").strip()
    if Path(reported) != root.resolve(strict=True):
        raise InputError("--root must be the canonical Git repository root")


def _read_regular(
    root: Path, relative: PurePosixPath, maximum: int
) -> tuple[bytes | None, str | None, tuple[int, int] | None]:
    path = root.joinpath(*relative.parts)
    _reject_symlink_components(root, path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise InputError(f"cannot read tracked path {relative}: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, "non_regular", None
        inode = (metadata.st_dev, metadata.st_ino)
        if metadata.st_size > maximum:
            return None, "max_file_bytes", inode
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
    finally:
        os.close(descriptor)
    if len(data) > maximum:
        return None, "max_file_bytes", inode
    try:
        data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        return None, "invalid_utf8", inode
    return data, None, inode


class SnapshotReader:
    """Read-only reader over the exact bytes captured for one snapshot."""

    def __init__(self, root: Path, sources: dict[str, bytes]) -> None:
        self.root = root
        self.sources = sources

    def read_bytes(self, project_relative_path: str) -> bytes:
        return self.sources[project_relative_path]

    def is_symlink(self, project_relative_path: str) -> bool:
        path = self.root.joinpath(*_safe_relative(project_relative_path).parts)
        current = self.root
        for part in path.relative_to(self.root).parts:
            current /= part
            if current.is_symlink():
                return True
        return False


def _coordinate(
    snapshot_sha256: str,
    path: str,
    data: bytes,
    byte_start: int,
    byte_end: int,
    entity_kind: str,
    occurrence_role: str,
    symbol: str,
) -> SourceCoordinate:
    return SourceCoordinate(
        snapshot_sha256,
        path,
        hashlib.sha256(data).hexdigest(),
        byte_start,
        byte_end,
        1 + data[:byte_start].count(b"\n"),
        1 + data[: byte_end - 1].count(b"\n"),
        entity_kind,
        occurrence_role,
        symbol,
    )


def _ast_range(data: bytes, node: ast.AST) -> tuple[int, int] | None:
    line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    column = getattr(node, "col_offset", None)
    end_column = getattr(node, "end_col_offset", None)
    if None in (line, end_line, column, end_column):
        return None
    starts = [0]
    starts.extend(index + 1 for index, value in enumerate(data) if value == 10)
    try:
        return starts[line - 1] + column, starts[end_line - 1] + end_column
    except IndexError:
        return None


def _module_name(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or None


def _resolved_module(source_path: str, node: ast.ImportFrom) -> str | None:
    if not node.module:
        return None
    if not node.level:
        return node.module
    package = source_path[:-3].split("/")[:-1]
    if source_path.endswith("/__init__.py"):
        package = source_path[:-12].split("/")
    keep = len(package) - node.level + 1
    if keep < 0:
        return None
    return ".".join([*package[:keep], *node.module.split(".")])


def _heading_slug(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value.casefold())
    value = re.sub(r"[^\w\s-]", "", value)
    return re.sub(r"[-\s]+", "-", value).strip("-")


def _derive_edges(
    sources: dict[str, bytes], snapshot_sha256: str
) -> tuple[GraphEdge, ...]:
    modules: dict[str, list[str]] = {}
    declarations: dict[str, dict[str, list[SourceCoordinate]]] = {}
    trees: dict[str, ast.Module] = {}
    headings: dict[str, dict[str, list[SourceCoordinate]]] = {}
    for path, data in sorted(sources.items()):
        module = _module_name(path)
        if module is not None:
            modules.setdefault(module, []).append(path)
            try:
                tree = ast.parse(data.decode("utf-8"), filename=path)
            except SyntaxError:
                continue
            trees[path] = tree
            by_name: dict[str, list[SourceCoordinate]] = {}
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                bounds = _ast_range(data, node)
                if bounds is None or bounds[0] >= bounds[1]:
                    continue
                by_name.setdefault(node.name, []).append(
                    _coordinate(
                        snapshot_sha256,
                        path,
                        data,
                        *bounds,
                        "python_declaration",
                        "declaration" if isinstance(node, ast.ClassDef) else "definition",
                        node.name,
                    )
                )
            declarations[path] = by_name
        if path.casefold().endswith((".md", ".markdown")):
            text = data.decode("utf-8")
            by_slug: dict[str, list[SourceCoordinate]] = {}
            for match in _MARKDOWN_HEADING.finditer(text):
                slug = _heading_slug(match.group(1))
                if not slug:
                    continue
                start = len(text[: match.start(1)].encode("utf-8"))
                end = len(text[: match.end(1)].encode("utf-8"))
                by_slug.setdefault(slug, []).append(
                    _coordinate(snapshot_sha256, path, data, start, end, "markdown_heading", "declaration", slug)
                )
            headings[path] = by_slug

    edges: list[GraphEdge] = []

    def add(
        relation: str,
        source: SourceCoordinate,
        target: SourceCoordinate,
    ) -> None:
        identity = json.dumps(
            [relation, source.to_dict(), target.to_dict()], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        edges.append(
            GraphEdge(
                f"edge:{hashlib.sha256(identity).hexdigest()}",
                f"repo:{source.source_path}",
                f"repo:{target.source_path}",
                relation,
                1.0,
                Provenance(
                    source.source_path,
                    source.source_sha256,
                    f"bytes:{source.byte_start}-{source.byte_end}",
                    True,
                ),
                TrustClass.VERIFIED_SOURCE,
                Sensitivity.INTERNAL,
                Freshness.CURRENT,
                Admission.VERIFIER,
                True,
                source_coordinate=source,
                target_coordinate=target,
            )
        )

    for path, tree in sorted(trees.items()):
        data = sources[path]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = _resolved_module(path, node)
            targets = modules.get(module or "", ())
            if len(targets) != 1:
                continue
            target_path = targets[0]
            for alias in node.names:
                declarations_for_name = declarations.get(target_path, {}).get(alias.name, ())
                bounds = _ast_range(data, alias)
                if alias.name == "*" or len(declarations_for_name) != 1 or bounds is None:
                    continue
                add(
                    "imports",
                    _coordinate(snapshot_sha256, path, data, *bounds, "python_import", "import", alias.name),
                    declarations_for_name[0],
                )

    for path, data in sorted(sources.items()):
        if path not in headings:
            continue
        text = data.decode("utf-8")
        for match in _MARKDOWN_LINK.finditer(text):
            destination = match.group(1)
            link_path, fragment = destination.rsplit("#", 1)
            if (
                not link_path
                or "%" in link_path
                or link_path.startswith(("/", "//"))
                or ":" in link_path
                or ".." in PurePosixPath(link_path).parts
            ):
                continue
            target_path = posixpath.normpath(posixpath.join(posixpath.dirname(path), link_path))
            if target_path.startswith("../") or target_path not in headings:
                continue
            targets = headings[target_path].get(_heading_slug(unquote(fragment)), ())
            if len(targets) != 1:
                continue
            start = len(text[: match.start(1)].encode("utf-8"))
            end = len(text[: match.end(1)].encode("utf-8"))
            add(
                "links_to_heading",
                _coordinate(snapshot_sha256, path, data, start, end, "markdown_link", "reference", destination),
                targets[0],
            )
    return tuple(sorted(edges, key=lambda edge: edge.edge_id))


def _scan(
    root: Path, max_file_bytes: int, max_total_bytes: int
) -> tuple[Graph, SourceSnapshotV4, SnapshotReader, dict[str, object]]:
    _repository_root(root)
    paths = _git(root, "ls-files", "-z", "--cached").split(b"\x00")
    sources: dict[str, bytes] = {}
    inodes: set[tuple[int, int]] = set()
    total = 0
    skipped: list[dict[str, str]] = []
    sensitive_paths_excluded = 0
    for encoded in sorted(item for item in paths if item):
        try:
            relative = _safe_relative(encoded.decode("utf-8", "strict"))
        except UnicodeDecodeError as error:
            raise InputError("Git path is not UTF-8") from error
        if _is_sensitive_path(relative):
            sensitive_paths_excluded += 1
            continue
        data, skip_reason, inode = _read_regular(root, relative, max_file_bytes)
        if inode is not None and inode in inodes:
            raise InputError(f"tracked path aliases another file: {relative}")
        if inode is not None:
            inodes.add(inode)
        if skip_reason is not None:
            skipped.append({"path": relative.as_posix(), "reason": skip_reason})
            continue
        assert data is not None
        if total + len(data) > max_total_bytes:
            skipped.append({"path": relative.as_posix(), "reason": "max_total_bytes"})
            continue
        total += len(data)
        sources[relative.as_posix()] = data
    if not sources:
        raise InputError("repository has no usable Git-tracked UTF-8 files")
    reader = SnapshotReader(root, sources)
    snapshot = SourceSnapshotV4(
        tuple(
            SourceIdentityV4(path, len(data), hashlib.sha256(data).hexdigest())
            for path, data in sorted(sources.items())
        )
    )
    records = tuple(
        GraphRecord(
            record_id=f"repo:{path}",
            kind="source",
            title=path,
            content=data.decode("utf-8"),
            provenance=Provenance(path, hashlib.sha256(data).hexdigest(), "git-tracked-bytes", True),
            trust=TrustClass.VERIFIED_SOURCE,
            sensitivity=Sensitivity.INTERNAL,
            freshness=Freshness.CURRENT,
            admission=Admission.VERIFIER,
            eligible=True,
        )
        for path, data in sorted(sources.items())
    )
    edges = _derive_edges(sources, snapshot.snapshot_sha256)
    reason_counts: dict[str, int] = {}
    for item in skipped:
        reason = item["reason"]
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    if sensitive_paths_excluded:
        reason_counts["sensitive_paths_excluded"] = sensitive_paths_excluded
    scan_complete = not any(
        item["reason"] in {"max_file_bytes", "max_total_bytes"} for item in skipped
    ) and not sensitive_paths_excluded
    metadata = {
        "files_scanned": len(sources),
        "files_skipped": skipped,
        "skip_counts": dict(sorted(reason_counts.items())),
        "sensitive_paths_excluded": sensitive_paths_excluded,
        "scan_complete": scan_complete,
        "source_bytes": total,
        "max_file_bytes": max_file_bytes,
        "max_total_bytes": max_total_bytes,
        "edges_derived": len(edges),
    }
    return Graph(records, edges), snapshot, reader, metadata


def _positive_bounded(value: str, label: str, ceiling: int) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{label} must be an integer") from error
    if not 1 <= number <= ceiling:
        raise argparse.ArgumentTypeError(f"{label} must be between 1 and {ceiling}")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="absolute canonical Git repository root")
    parser.add_argument("--prompt", required=True, help="non-empty repository navigation prompt")
    parser.add_argument("--semantic-candidate", action="append", default=[], help="optional known vocabulary candidate")
    parser.add_argument("--max-file-bytes", type=lambda value: _positive_bounded(value, "--max-file-bytes", HARD_MAX_FILE_BYTES), default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-bytes", type=lambda value: _positive_bounded(value, "--max-total-bytes", HARD_MAX_TOTAL_BYTES), default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--maximum-results", type=lambda value: _positive_bounded(value, "--maximum-results", 200), default=6)
    parser.add_argument("--byte-budget", type=lambda value: _positive_bounded(value, "--byte-budget", HARD_MAX_TOTAL_BYTES), default=32768)
    arguments = parser.parse_args(argv)
    if not arguments.prompt.strip():
        parser.error("--prompt must be non-empty")
    try:
        root = _canonical_root(arguments.root)
        graph, snapshot, reader, scan_metadata = _scan(
            root, arguments.max_file_bytes, arguments.max_total_bytes
        )
        terms = tuple(sorted(set(token.casefold() for token in _TOKEN.findall(arguments.prompt))))
        task = TaskSpec(
            task_id="graph-find",
            query_terms=terms,
            node_budget=arguments.maximum_results,
            byte_budget=arguments.byte_budget,
            allowed_sensitivities=(Sensitivity.INTERNAL,),
        )
        result = graph_find(
            graph,
            task,
            arguments.prompt,
            snapshot,
            reader,
            semantic_candidates=tuple(arguments.semantic_candidate),
            expand_one_hop=False,
            source_bound_expansion=True,
            maximum_results=arguments.maximum_results,
        )
        if scan_metadata["sensitive_paths_excluded"]:
            result = replace(result, route="defer", reason="sensitive_paths_excluded")
        elif not scan_metadata["scan_complete"]:
            result = replace(result, route="defer", reason="repository_scan_incomplete")
        payload = result.to_dict()
        payload["scan"] = scan_metadata
        json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    except (InputError, OSError, TypeError, ValueError, UnicodeError) as error:
        print(f"graph-find: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
