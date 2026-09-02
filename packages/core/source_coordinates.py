"""Exact, immutable source coordinates with parser-neutral provider seams."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

_ROLES = frozenset({"definition", "declaration", "reference", "call", "import", "read", "write", "unknown"})


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_digest(value: object, label: str) -> None:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} must be a full lowercase SHA-256")


def _require_path(value: object) -> None:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        raise ValueError("source_path must be a portable relative path")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("source_path must be a portable relative path")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class SourceFile:
    """One source file and its exact bytes."""

    path: str
    content: bytes

    def __post_init__(self) -> None:
        _require_path(self.path)
        if type(self.content) is not bytes:
            raise TypeError("content must be bytes")

    @property
    def source_sha256(self) -> str:
        return _digest(self.content)

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "byte_length": len(self.content), "sha256": self.source_sha256}


@dataclass(frozen=True)
class SourceSnapshot:
    """Canonical source set. Coordinates cannot cross this snapshot."""

    sources: tuple[SourceFile, ...]

    def __post_init__(self) -> None:
        if type(self.sources) is not tuple or not self.sources:
            raise ValueError("sources must be a non-empty tuple")
        if any(type(item) is not SourceFile for item in self.sources):
            raise TypeError("sources must contain SourceFile values")
        paths = tuple(item.path for item in self.sources)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("sources must be unique and in canonical path order")

    @property
    def snapshot_sha256(self) -> str:
        return _digest(_canonical({"sources": [item.to_dict() for item in self.sources]}))

    def source(self, path: str) -> SourceFile:
        for item in self.sources:
            if item.path == path:
                return item
        raise KeyError(path)

    def to_dict(self) -> dict[str, object]:
        return {"snapshot_sha256": self.snapshot_sha256, "sources": [item.to_dict() for item in self.sources]}


@dataclass(frozen=True)
class SourceCoordinate:
    """A byte and line range bound to both source and snapshot identity."""

    snapshot_sha256: str
    source_path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int
    entity_kind: str
    occurrence_role: str
    symbol: str
    enclosing_entity: str | None = None

    def __post_init__(self) -> None:
        _require_digest(self.snapshot_sha256, "snapshot_sha256")
        _require_path(self.source_path)
        _require_digest(self.source_sha256, "source_sha256")
        if type(self.byte_start) is not int or type(self.byte_end) is not int or not 0 <= self.byte_start < self.byte_end:
            raise ValueError("byte range must be non-empty and ordered")
        if type(self.line_start) is not int or type(self.line_end) is not int or not 1 <= self.line_start <= self.line_end:
            raise ValueError("line range must be non-empty and ordered")
        if type(self.entity_kind) is not str or not self.entity_kind:
            raise ValueError("entity_kind is required")
        if self.occurrence_role not in _ROLES:
            raise ValueError("occurrence_role is unsupported")
        if type(self.symbol) is not str or not self.symbol:
            raise ValueError("symbol is required")
        if self.enclosing_entity is not None and type(self.enclosing_entity) is not str:
            raise TypeError("enclosing_entity must be a string or None")

    @property
    def path(self) -> str:
        return self.source_path

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": "source-coordinate-v1", "snapshot_sha256": self.snapshot_sha256, "source_path": self.source_path, "source_sha256": self.source_sha256, "byte_start": self.byte_start, "byte_end": self.byte_end, "line_start": self.line_start, "line_end": self.line_end, "entity_kind": self.entity_kind, "occurrence_role": self.occurrence_role, "symbol": self.symbol, "enclosing_entity": self.enclosing_entity}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SourceCoordinate":
        expected = {"schema_version", "snapshot_sha256", "source_path", "source_sha256", "byte_start", "byte_end", "line_start", "line_end", "entity_kind", "occurrence_role", "symbol", "enclosing_entity"}
        if set(payload) != expected or payload["schema_version"] != "source-coordinate-v1":
            raise ValueError("source coordinate fields must match the closed contract")
        return cls(*(payload[key] for key in ("snapshot_sha256", "source_path", "source_sha256", "byte_start", "byte_end", "line_start", "line_end", "entity_kind", "occurrence_role", "symbol", "enclosing_entity")))  # type: ignore[arg-type]


class CoordinateProvider(Protocol):
    def index(self, snapshot: SourceSnapshot) -> "IndexResult": ...


@dataclass(frozen=True)
class IndexResult:
    snapshot_sha256: str
    supported: bool
    coordinates: tuple[SourceCoordinate, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_digest(self.snapshot_sha256, "snapshot_sha256")
        if type(self.supported) is not bool:
            raise TypeError("supported must be bool")
        if not self.supported and self.coordinates:
            raise ValueError("deferred indexing cannot contain coordinates")
        if not self.supported and not self.reason:
            raise ValueError("deferred indexing requires a reason")
        if any(item.snapshot_sha256 != self.snapshot_sha256 for item in self.coordinates):
            raise ValueError("coordinate snapshot custody mismatch")
        ordered = tuple(sorted(self.coordinates, key=lambda item: (item.source_path, item.byte_start, item.byte_end, item.symbol, item.occurrence_role)))
        if ordered != self.coordinates:
            raise ValueError("coordinates must use canonical order")


class DeterministicFixtureProvider:
    """Provider for tests and fixtures; it never guesses parser truth."""

    def __init__(self, coordinates: Sequence[SourceCoordinate] | None = None, *, supported: bool = True, reason: str | None = None) -> None:
        self._coordinates = tuple(coordinates or ())
        self._supported = supported
        self._reason = reason

    def index(self, snapshot: SourceSnapshot) -> IndexResult:
        if not self._supported:
            return IndexResult(snapshot.snapshot_sha256, False, reason=self._reason or "parser_unsupported")
        bound = tuple(item for item in self._coordinates if item.snapshot_sha256 == snapshot.snapshot_sha256)
        if len(bound) != len(self._coordinates):
            raise ValueError("fixture coordinate does not match supplied snapshot")
        for item in bound:
            source = snapshot.source(item.source_path)
            if item.source_sha256 != source.source_sha256 or item.byte_end > len(source.content):
                raise ValueError("fixture coordinate does not match supplied source")
            expected_start = 1 + source.content[:item.byte_start].count(b"\n")
            expected_end = 1 + source.content[: item.byte_end - 1].count(b"\n")
            if expected_start != item.line_start or expected_end != item.line_end:
                raise ValueError("fixture coordinate line range does not match supplied source")
        return IndexResult(snapshot.snapshot_sha256, True, tuple(sorted(bound, key=lambda item: (item.source_path, item.byte_start, item.byte_end, item.symbol, item.occurrence_role))))


class ParserNeutralIndex:
    def __init__(self, result: IndexResult) -> None:
        self.result = result

    def find(self, symbol: str, *, role: str | None = None) -> tuple[SourceCoordinate, ...]:
        if not self.result.supported:
            return ()
        return tuple(item for item in self.result.coordinates if item.symbol == symbol and (role is None or item.occurrence_role == role))


def source_snapshot(sources: Mapping[str, bytes | str]) -> SourceSnapshot:
    files = tuple(SourceFile(path, value.encode("utf-8") if isinstance(value, str) else value) for path, value in sorted(sources.items()))
    return SourceSnapshot(files)


# Explicit V1 aliases keep the contract name available while the short names
# remain pleasant for callers inside the package.
SourceCoordinateV1 = SourceCoordinate
SourceFileV1 = SourceFile
SourceSnapshotV1 = SourceSnapshot
ParserNeutralIndexProvider = CoordinateProvider
FixtureSourceProvider = DeterministicFixtureProvider


__all__ = ["CoordinateProvider", "DeterministicFixtureProvider", "FixtureSourceProvider", "IndexResult", "ParserNeutralIndex", "ParserNeutralIndexProvider", "SourceCoordinate", "SourceCoordinateV1", "SourceFile", "SourceFileV1", "SourceSnapshot", "SourceSnapshotV1", "source_snapshot"]
