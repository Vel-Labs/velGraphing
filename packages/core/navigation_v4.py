"""Small, deterministic source-coordinate navigation primitives for V4.

The navigation surface does not infer relationships.  It only returns spans
that the supplied coordinate provider and source snapshot can verify.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .source_coordinates import (
    CoordinateProvider,
    IndexResult,
    SourceCoordinate,
    SourceSnapshot,
)


@dataclass(frozen=True)
class NavigationItem:
    """One verified coordinate and, for read operations, its exact bytes."""

    coordinate: SourceCoordinate
    content: bytes | None = None
    relation: str | None = None

    @property
    def source_sha256(self) -> str:
        return self.coordinate.source_sha256

    @property
    def snapshot_sha256(self) -> str:
        return self.coordinate.snapshot_sha256

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"coordinate": self.coordinate.to_dict()}
        if self.content is not None:
            result["content"] = self.content.decode("utf-8", errors="strict")
        if self.relation is not None:
            result["relation"] = self.relation
        return result


@dataclass(frozen=True)
class NavigationResult:
    """A bounded result, or a fail-closed deferral when evidence is absent."""

    operation: str
    supported: bool
    items: tuple[NavigationItem, ...] = ()
    reason: str | None = None

    @property
    def deferred(self) -> bool:
        return not self.supported

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "navigation-v4",
            "operation": self.operation,
            "supported": self.supported,
            "items": [item.to_dict() for item in self.items],
            "reason": self.reason,
        }


def _limit(value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("limit must be a positive integer")
    return value


class NavigationV4:
    """Exact symbol navigation over one immutable source snapshot."""

    def __init__(self, snapshot: SourceSnapshot, provider: CoordinateProvider, *, max_results: int = 64) -> None:
        self.snapshot = snapshot
        self.max_results = _limit(max_results)
        self.index: IndexResult = provider.index(snapshot)

    def _defer(self, operation: str, reason: str) -> NavigationResult:
        return NavigationResult(operation, False, reason=reason)

    def _verified(self, coordinate: SourceCoordinate) -> bool:
        if coordinate.snapshot_sha256 != self.snapshot.snapshot_sha256:
            return False
        try:
            source = self.snapshot.source(coordinate.source_path)
        except KeyError:
            return False
        return (
            coordinate.source_sha256 == source.source_sha256
            and 0 <= coordinate.byte_start < coordinate.byte_end <= len(source.content)
        )

    def _items(self, coordinates: Iterable[SourceCoordinate], *, content: bool = False, relation: str | None = None) -> tuple[NavigationItem, ...]:
        result: list[NavigationItem] = []
        for coordinate in coordinates:
            if not self._verified(coordinate):
                continue
            payload = None
            if content:
                payload = self.snapshot.source(coordinate.source_path).content[coordinate.byte_start : coordinate.byte_end]
            result.append(NavigationItem(coordinate, payload, relation))
        return tuple(result)

    def _require_supported(self, operation: str) -> NavigationResult | None:
        if not self.index.supported:
            return self._defer(operation, self.index.reason or "parser_unsupported")
        return None

    def _resolve(self, value: str | SourceCoordinate, operation: str) -> tuple[SourceCoordinate, ...] | NavigationResult:
        if isinstance(value, SourceCoordinate):
            if not self._verified(value):
                return self._defer(operation, "source_custody_mismatch")
            return (value,)
        if type(value) is not str or not value:
            return self._defer(operation, "symbol_required")
        matches = tuple(item for item in self.index.coordinates if item.symbol == value)
        if not matches:
            return self._defer(operation, "symbol_not_found")
        # A symbol inspection starts at its declaration when one is present.
        # This avoids treating a call-site as the enclosing-unit anchor.
        preferred = tuple(item for item in matches if item.occurrence_role in {"definition", "declaration"})
        return preferred or matches

    def find_symbols(self, symbol: str, *, role: str | None = None, limit: int | None = None) -> NavigationResult:
        operation = "find_symbols"
        unsupported = self._require_supported(operation)
        if unsupported is not None:
            return unsupported
        bound = _limit(limit if limit is not None else self.max_results)
        matches = (item for item in self.index.coordinates if item.symbol == symbol and (role is None or item.occurrence_role == role))
        items = self._items(tuple(matches)[:bound])
        return NavigationResult(operation, True, items) if items else self._defer(operation, "symbol_not_found")

    def inspect_symbol(self, symbol: str | SourceCoordinate, *, role: str | None = None, limit: int | None = None) -> NavigationResult:
        operation = "inspect_symbol"
        unsupported = self._require_supported(operation)
        if unsupported is not None:
            return unsupported
        resolved = self._resolve(symbol, operation)
        if isinstance(resolved, NavigationResult):
            return resolved
        bound = _limit(limit if limit is not None else self.max_results)
        matches = tuple(item for item in self.index.coordinates if item.symbol == resolved[0].symbol and (role is None or item.occurrence_role == role))
        items = self._items(matches[:bound])
        return NavigationResult(operation, True, items) if items else self._defer(operation, "symbol_not_found")

    def find_references(self, symbol: str | SourceCoordinate, *, role: str | None = None, limit: int | None = None) -> NavigationResult:
        operation = "find_references"
        unsupported = self._require_supported(operation)
        if unsupported is not None:
            return unsupported
        resolved = self._resolve(symbol, operation)
        if isinstance(resolved, NavigationResult):
            return resolved
        target = resolved[0].symbol
        roles = (role,) if role is not None else ("reference", "call")
        bound = _limit(limit if limit is not None else self.max_results)
        matches = tuple(item for item in self.index.coordinates if item.symbol == target and item.occurrence_role in roles)
        items = self._items(matches[:bound], relation="reference")
        return NavigationResult(operation, True, items) if items else self._defer(operation, "references_not_found")

    def related_symbols(self, symbol: str | SourceCoordinate, *, max_depth: int = 1, limit: int | None = None) -> NavigationResult:
        operation = "related_symbols"
        unsupported = self._require_supported(operation)
        if unsupported is not None:
            return unsupported
        if type(max_depth) is not int or not 0 <= max_depth <= 1:
            raise ValueError("max_depth must be 0 or 1")
        resolved = self._resolve(symbol, operation)
        if isinstance(resolved, NavigationResult):
            return resolved
        anchor = resolved[0]
        if not anchor.enclosing_entity:
            return self._defer(operation, "enclosing_unit_evidence_missing")
        if max_depth == 0:
            return self._defer(operation, "neighbor_depth_exhausted")
        bound = _limit(limit if limit is not None else self.max_results)
        matches = tuple(item for item in self.index.coordinates if item.enclosing_entity == anchor.enclosing_entity and item != anchor)
        items = self._items(matches[:bound], relation="enclosing_unit_neighbor")
        return NavigationResult(operation, True, items, None if items else "related_symbols_not_found")

    def read_span(self, coordinate: SourceCoordinate) -> NavigationResult:
        operation = "read_span"
        unsupported = self._require_supported(operation)
        if unsupported is not None:
            return unsupported
        if not self._verified(coordinate):
            return self._defer(operation, "source_custody_mismatch")
        return NavigationResult(operation, True, self._items((coordinate,), content=True))

    def read_symbol(self, symbol: str | SourceCoordinate, *, limit: int | None = None) -> NavigationResult:
        operation = "read_symbol"
        inspected = self.inspect_symbol(symbol, limit=limit)
        if not inspected.supported:
            return NavigationResult(operation, False, reason=inspected.reason)
        bound = _limit(limit if limit is not None else self.max_results)
        return NavigationResult(operation, True, self._items((item.coordinate for item in inspected.items[:bound]), content=True))

    def read_enclosing_unit(self, symbol: str | SourceCoordinate, *, limit: int | None = None) -> NavigationResult:
        operation = "read_enclosing_unit"
        unsupported = self._require_supported(operation)
        if unsupported is not None:
            return unsupported
        resolved = self._resolve(symbol, operation)
        if isinstance(resolved, NavigationResult):
            return resolved
        anchor = resolved[0]
        entity = anchor.enclosing_entity or (anchor.symbol if anchor.occurrence_role in {"definition", "declaration"} else None)
        if not entity:
            return self._defer(operation, "enclosing_unit_evidence_missing")
        members = tuple(item for item in self.index.coordinates if item.source_path == anchor.source_path and (item.enclosing_entity == entity or item == anchor))
        members = tuple(item for item in members if self._verified(item))
        if not members:
            return self._defer(operation, "enclosing_unit_evidence_missing")
        start, end = min(item.byte_start for item in members), max(item.byte_end for item in members)
        source = self.snapshot.source(anchor.source_path)
        line_start = 1 + source.content[:start].count(b"\n")
        line_end = 1 + source.content[: end - 1].count(b"\n")
        unit = SourceCoordinate(self.snapshot.snapshot_sha256, anchor.source_path, source.source_sha256, start, end, line_start, line_end, "enclosing_unit", "unknown", entity, entity)
        return NavigationResult(operation, True, self._items((unit,), content=True))


def navigate_v4(snapshot: SourceSnapshot, provider: CoordinateProvider, **kwargs: object) -> NavigationV4:
    """Construct a V4 navigator without any parser or model inference."""
    return NavigationV4(snapshot, provider, **kwargs)  # type: ignore[arg-type]


__all__ = ["NavigationItem", "NavigationResult", "NavigationV4", "navigate_v4"]
