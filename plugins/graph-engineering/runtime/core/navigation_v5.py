"""Bounded progressive navigation over one immutable source snapshot.

The V5 surface is deliberately additive.  Graph entries are navigation hints
only.  They are validated, intersected with the supplied snapshot, and used
to narrow coordinate inspection.  Only an exact coordinate read returns
source content.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterator

from .navigation_v4 import NavigationItem, NavigationResult
from .source_coordinates import CoordinateProvider, SourceCoordinate, SourceSnapshot


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_MISSING = object()


def _canonical_bytes(value: object) -> bytes:
    """Return the deterministic UTF-8 representation used for accounting."""

    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _valid_int(value: object, label: str, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")


@dataclass(frozen=True)
class NavigationBudget:
    """Immutable limits for one V5 operation.

    ``max_steps`` and ``max_hops`` are hard protocol limits.  A caller may
    choose a smaller budget, but cannot use a larger one.
    """

    max_steps: int = 6
    max_candidates: int = 64
    max_source_bytes: int = 65_536
    max_metadata_bytes: int = 16_384
    max_hops: int = 1

    def __post_init__(self) -> None:
        _valid_int(self.max_steps, "max_steps", minimum=1)
        if self.max_steps > 6:
            raise ValueError("max_steps cannot exceed 6")
        _valid_int(self.max_candidates, "max_candidates", minimum=1)
        _valid_int(self.max_source_bytes, "max_source_bytes")
        _valid_int(self.max_metadata_bytes, "max_metadata_bytes")
        if type(self.max_hops) is not int or self.max_hops not in (0, 1):
            raise ValueError("max_hops must be 0 or 1")

    @property
    def source_bytes(self) -> int:
        """Compatibility name for the source-byte limit."""

        return self.max_source_bytes

    @property
    def metadata_bytes(self) -> int:
        """Compatibility name for the metadata-byte limit."""

        return self.max_metadata_bytes


@dataclass(frozen=True)
class NavigationStep:
    """One deterministic, non-authoritative navigation step."""

    kind: str
    source_path: str | None = None
    hop: int = 0
    candidate_count: int = 0
    regions_considered: int = 0
    coordinates_inspected: int = 0
    graph_metadata_bytes: int = 0
    source_bytes_read: int = 0
    result_metadata_bytes: int = 0
    direct_fallback_used: bool = False
    supporting_context: bool = False

    def __post_init__(self) -> None:
        if type(self.kind) is not str or not self.kind:
            raise ValueError("step kind is required")
        if self.source_path is not None and type(self.source_path) is not str:
            raise TypeError("step source_path must be a string or None")
        if type(self.hop) is not int or self.hop not in (0, 1):
            raise ValueError("step hop must be 0 or 1")
        for label in (
            "candidate_count",
            "regions_considered",
            "coordinates_inspected",
            "graph_metadata_bytes",
            "source_bytes_read",
            "result_metadata_bytes",
        ):
            _valid_int(getattr(self, label), label)
        if type(self.direct_fallback_used) is not bool or type(self.supporting_context) is not bool:
            raise TypeError("step flags must be booleans")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "source_path": self.source_path,
            "hop": self.hop,
            "candidate_count": self.candidate_count,
            "regions_considered": self.regions_considered,
            "coordinates_inspected": self.coordinates_inspected,
            "graph_metadata_bytes": self.graph_metadata_bytes,
            "source_bytes_read": self.source_bytes_read,
            "result_metadata_bytes": self.result_metadata_bytes,
            "direct_fallback_used": self.direct_fallback_used,
            "supporting_context": self.supporting_context,
        }


@dataclass(frozen=True)
class NavigationCost(Mapping[str, int | bool]):
    """Deterministic operation accounting exposed on every V5 result."""

    candidate_count: int = 0
    regions_considered: int = 0
    coordinates_inspected: int = 0
    graph_metadata_bytes: int = 0
    source_bytes_read: int = 0
    result_metadata_bytes: int = 0
    steps: int = 0
    hops: int = 0
    direct_fallback_used: bool = False
    fallback_bytes: int = 0
    total_bytes: int = 0

    _FIELDS = (
        "candidate_count",
        "regions_considered",
        "coordinates_inspected",
        "graph_metadata_bytes",
        "source_bytes_read",
        "result_metadata_bytes",
        "steps",
        "hops",
        "direct_fallback_used",
        "fallback_bytes",
        "total_bytes",
    )

    def __post_init__(self) -> None:
        for label in self._FIELDS:
            value = getattr(self, label)
            if label == "direct_fallback_used":
                if type(value) is not bool:
                    raise TypeError("direct_fallback_used must be a boolean")
            else:
                _valid_int(value, label)

    def __getitem__(self, key: str) -> int | bool:
        if key not in self._FIELDS:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._FIELDS)

    def __len__(self) -> int:
        return len(self._FIELDS)

    def to_dict(self) -> dict[str, int | bool]:
        return {key: self[key] for key in self._FIELDS}


@dataclass(frozen=True)
class NavigationV5Result(NavigationResult):
    """V4-compatible result with V5 trace and cost fields."""

    cost: NavigationCost = NavigationCost()
    steps: tuple[NavigationStep, ...] = ()
    graph_trace: tuple[Mapping[str, object], ...] = ()
    authority_bearing: bool = False
    supporting_context: tuple[SourceCoordinate, ...] = ()

    def __post_init__(self) -> None:
        if type(self.cost) is not NavigationCost:
            raise TypeError("cost must be a NavigationCost")
        if type(self.steps) is not tuple or any(type(step) is not NavigationStep for step in self.steps):
            raise TypeError("steps must contain NavigationStep values")
        if type(self.graph_trace) is not tuple:
            raise TypeError("graph_trace must be a tuple")
        if type(self.authority_bearing) is not bool:
            raise TypeError("authority_bearing must be a boolean")
        if type(self.supporting_context) is not tuple or any(type(item) is not SourceCoordinate for item in self.supporting_context):
            raise TypeError("supporting_context must contain SourceCoordinate values")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "navigation-v5",
            "operation": self.operation,
            "supported": self.supported,
            "items": [item.to_dict() for item in self.items],
            "reason": self.reason,
            "cost": self.cost.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "graph_trace": [dict(item) for item in self.graph_trace],
            "authority_bearing": self.authority_bearing,
            "supporting_context": [item.to_dict() for item in self.supporting_context],
        }

    @property
    def sufficient(self) -> bool:
        """Graph navigation never proves that the selected evidence is complete."""

        return False


class _NavigationInputError(ValueError):
    """An untrusted graph or direct-path input failed closed."""


def _normalize_path(value: object) -> str:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        raise _NavigationInputError("path_invalid")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise _NavigationInputError("path_traversal")
    return "/".join(parts)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unique_coordinate_bytes(coordinates: Sequence[SourceCoordinate]) -> int:
    grouped: dict[str, list[tuple[int, int]]] = {}
    for coordinate in coordinates:
        grouped.setdefault(coordinate.source_path, []).append((coordinate.byte_start, coordinate.byte_end))
    total = 0
    for ranges in grouped.values():
        merged: list[list[int]] = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        total += sum(end - start for start, end in merged)
    return total


def _query_terms(query: object) -> tuple[str, ...]:
    if type(query) is not str:
        raise _NavigationInputError("query_required")
    terms = tuple(dict.fromkeys(token.lower() for token in _TOKEN_RE.findall(query)))
    if not terms:
        raise _NavigationInputError("query_required")
    return terms


def _rank(entry: Mapping[str, object]) -> tuple[float, str]:
    raw = entry.get("rank", entry.get("score", entry.get("priority", 0)))
    if raw is None:
        raw = 0
    if type(raw) not in (int, float) or isinstance(raw, bool) or not math.isfinite(float(raw)):
        raise _NavigationInputError("rank_invalid")
    return (float(raw), str(entry["source_path"]))


class NavigationV5:
    """Bounded graph funnel and exact-read navigator for one snapshot."""

    def __init__(
        self,
        snapshot: SourceSnapshot,
        provider: CoordinateProvider,
        *,
        budget: NavigationBudget | None = None,
        max_results: int | None = None,
    ) -> None:
        if type(snapshot) is not SourceSnapshot:
            raise TypeError("snapshot must be a SourceSnapshot")
        self.snapshot = snapshot
        if budget is not None and type(budget) is not NavigationBudget:
            raise TypeError("budget must be a NavigationBudget")
        selected = budget or NavigationBudget()
        if max_results is not None:
            _valid_int(max_results, "max_results", minimum=1)
            selected = NavigationBudget(
                max_steps=selected.max_steps,
                max_candidates=min(selected.max_candidates, max_results),
                max_source_bytes=selected.max_source_bytes,
                max_metadata_bytes=selected.max_metadata_bytes,
                max_hops=selected.max_hops,
            )
        self.budget = selected
        self._index_error: str | None = None
        try:
            index = provider.index(snapshot)
            if index.snapshot_sha256 != snapshot.snapshot_sha256:
                self._index_error = "source_custody_mismatch"
            elif not index.supported:
                self._index_error = index.reason or "parser_unsupported"
            else:
                self._coordinates = tuple(index.coordinates)
                self._index_error = self._validate_coordinates(self._coordinates)
        except Exception as exc:  # provider/parser errors are fail-closed
            self._coordinates = ()
            self._index_error = "parser_error" if not isinstance(exc, _NavigationInputError) else str(exc)
        if not hasattr(self, "_coordinates"):
            self._coordinates = ()

    def _validate_coordinates(self, coordinates: Sequence[SourceCoordinate]) -> str | None:
        for coordinate in coordinates:
            if coordinate.snapshot_sha256 != self.snapshot.snapshot_sha256:
                return "source_custody_mismatch"
            try:
                source = self.snapshot.source(coordinate.source_path)
            except KeyError:
                return "source_custody_mismatch"
            if coordinate.source_sha256 != source.source_sha256 or coordinate.byte_end > len(source.content):
                return "source_custody_mismatch"
        return None

    def _verified(self, coordinate: SourceCoordinate) -> bool:
        if coordinate.snapshot_sha256 != self.snapshot.snapshot_sha256:
            return False
        try:
            source = self.snapshot.source(coordinate.source_path)
        except KeyError:
            return False
        if coordinate.source_sha256 != source.source_sha256 or not 0 <= coordinate.byte_start < coordinate.byte_end <= len(source.content):
            return False
        expected_start = 1 + source.content[: coordinate.byte_start].count(b"\n")
        expected_end = 1 + source.content[: coordinate.byte_end - 1].count(b"\n")
        return coordinate.line_start == expected_start and coordinate.line_end == expected_end

    def _base_cost(self, *, graph_metadata_bytes: int = 0, source_bytes_read: int = 0, fallback_bytes: int = 0) -> NavigationCost:
        return NavigationCost(
            graph_metadata_bytes=graph_metadata_bytes,
            source_bytes_read=source_bytes_read,
            fallback_bytes=fallback_bytes,
            total_bytes=graph_metadata_bytes + source_bytes_read,
        )

    def _defer(
        self,
        operation: str,
        reason: str,
        *,
        cost: NavigationCost | None = None,
        steps: tuple[NavigationStep, ...] = (),
        graph_trace: tuple[Mapping[str, object], ...] = (),
    ) -> NavigationV5Result:
        return NavigationV5Result(operation, False, reason=reason, cost=cost or NavigationCost(), steps=steps, graph_trace=graph_trace)

    def _metadata_size(self, items: Sequence[NavigationItem], steps: Sequence[NavigationStep], operation: str) -> int:
        return len(_canonical_bytes({
            "operation": operation,
            "items": [item.coordinate.to_dict() for item in items],
            "steps": [step.to_dict() for step in steps],
        }))

    def _finish(
        self,
        operation: str,
        items: Sequence[NavigationItem],
        *,
        steps: tuple[NavigationStep, ...],
        graph_trace: tuple[Mapping[str, object], ...],
        graph_metadata_bytes: int,
        source_bytes_read: int,
        fallback_bytes: int,
        regions_considered: int,
        coordinates_inspected: int,
        hops: int,
        direct_fallback_used: bool,
        supporting_context: Sequence[SourceCoordinate] = (),
        authority_bearing: bool = False,
        reason: str | None = None,
    ) -> NavigationV5Result:
        ordered_items = tuple(items)
        result_metadata_bytes = self._metadata_size(ordered_items, steps, operation)
        cost = NavigationCost(
            candidate_count=len(ordered_items),
            regions_considered=regions_considered,
            coordinates_inspected=coordinates_inspected,
            graph_metadata_bytes=graph_metadata_bytes,
            source_bytes_read=source_bytes_read,
            result_metadata_bytes=result_metadata_bytes,
            steps=len(steps),
            hops=hops,
            direct_fallback_used=direct_fallback_used,
            fallback_bytes=fallback_bytes,
            total_bytes=graph_metadata_bytes + source_bytes_read + result_metadata_bytes,
        )
        if graph_metadata_bytes + result_metadata_bytes > self.budget.max_metadata_bytes:
            return self._defer(operation, "metadata_budget_exhausted", cost=cost, steps=steps, graph_trace=graph_trace)
        return NavigationV5Result(operation, True, ordered_items, reason, cost, steps, graph_trace, authority_bearing, tuple(supporting_context))

    def _admit_graph(self, graph: Sequence[Mapping[str, object]]) -> tuple[tuple[tuple[str, float], ...], int, str | None]:
        if isinstance(graph, (str, bytes, bytearray)) or not isinstance(graph, Sequence):
            return (), 0, "graph_input_invalid"
        metadata_bytes = 0
        admitted: dict[str, tuple[float, Mapping[str, object]]] = {}
        try:
            for entry in graph:
                if not isinstance(entry, Mapping):
                    return (), metadata_bytes, "graph_entry_invalid"
                encoded = _canonical_bytes(dict(entry))
                metadata_bytes += len(encoded)
                if metadata_bytes > self.budget.max_metadata_bytes:
                    return (), metadata_bytes, "metadata_budget_exhausted"
                path = _normalize_path(entry.get("source_path", _MISSING))
                try:
                    source = self.snapshot.source(path)
                except KeyError:
                    return (), metadata_bytes, "path_unknown"
                for key in ("snapshot_sha256",):
                    if key in entry and entry[key] != self.snapshot.snapshot_sha256:
                        return (), metadata_bytes, "source_custody_mismatch"
                for key in ("source_sha256", "source_hash", "sha256", "hash"):
                    if key in entry and entry[key] != source.source_sha256:
                        return (), metadata_bytes, "source_hash_mismatch"
                rank = _rank({**entry, "source_path": path})
                existing = admitted.get(path)
                if existing is None or rank[0] < existing[0]:
                    admitted[path] = (rank[0], entry)
                if len(admitted) > self.budget.max_candidates:
                    return (), metadata_bytes, "candidate_budget_exhausted"
        except _NavigationInputError as exc:
            return (), metadata_bytes, str(exc)
        except (TypeError, ValueError, OverflowError):
            return (), metadata_bytes, "path_invalid"
        ordered = tuple((path, admitted[path][0]) for path in sorted(admitted, key=lambda item: (admitted[item][0], item)))
        return ordered, metadata_bytes, None

    def _coordinate_matches(self, coordinate: SourceCoordinate, terms: tuple[str, ...]) -> bool:
        value = coordinate.symbol.lower()
        return any(term == value or term in value for term in terms)

    def _one_hop(self, coordinates: Sequence[SourceCoordinate], terms: tuple[str, ...]) -> tuple[tuple[SourceCoordinate, ...], tuple[SourceCoordinate, ...], str | None]:
        additions: list[SourceCoordinate] = []
        supporting: list[SourceCoordinate] = []
        for coordinate in coordinates:
            candidates = [item for item in self._coordinates if item != coordinate and item.source_path != coordinate.source_path and item.symbol == coordinate.symbol and self._verified(item)]
            if not candidates:
                continue
            preferred = [item for item in candidates if item.occurrence_role in {"definition", "declaration"}]
            if len(preferred) == 1:
                additions.append(preferred[0])
                supporting.append(preferred[0])
            elif len(preferred) > 1 or len(candidates) > 1:
                return (), (), "ambiguous_hop"
            elif self._coordinate_matches(candidates[0], terms):
                additions.append(candidates[0])
                supporting.append(candidates[0])
        unique = tuple(dict.fromkeys(additions))
        return unique, tuple(dict.fromkeys(supporting)), None

    def search(
        self,
        query: str | Sequence[Mapping[str, object]],
        graph: Sequence[Mapping[str, object]] | str = (),
        *,
        direct_paths: Sequence[str] = (),
        fallback_paths: Sequence[str] | None = None,
        direct_allowlist: Sequence[str] | None = None,
        allow_direct_fallback: bool = False,
        max_hops: int | None = None,
        hop: bool = True,
        limit: int | None = None,
    ) -> NavigationV5Result:
        """Search coordinates through an untrusted graph funnel.

        For convenience, callers may pass ``search(graph, query)`` as well
        as ``search(query, graph)``.  A direct fallback is executed only when
        explicitly requested by an allowlist or ``allow_direct_fallback``.
        """

        if not isinstance(query, str) and isinstance(graph, str):
            query, graph = graph, query
        operation = "search"
        if self._index_error is not None:
            return self._defer(operation, self._index_error)
        try:
            terms = _query_terms(query)
        except _NavigationInputError as exc:
            return self._defer(operation, str(exc))
        requested_hops = self.budget.max_hops if max_hops is None and hop else 0 if not hop else self.budget.max_hops
        if max_hops is not None:
            requested_hops = max_hops
        if type(requested_hops) is not int or requested_hops not in (0, 1) or requested_hops > self.budget.max_hops:
            return self._defer(operation, "hop_budget_exhausted")
        if limit is not None:
            if type(limit) is not int or limit < 1:
                return self._defer(operation, "candidate_budget_exhausted")
            if limit > self.budget.max_candidates:
                return self._defer(operation, "candidate_budget_exhausted")
        fallback = fallback_paths if fallback_paths is not None else direct_allowlist if direct_allowlist is not None else direct_paths
        try:
            fallback_paths_tuple = tuple(_normalize_path(path) for path in fallback)
        except _NavigationInputError as exc:
            return self._defer(operation, str(exc))
        for path in fallback_paths_tuple:
            try:
                self.snapshot.source(path)
            except KeyError:
                return self._defer(operation, "path_unknown")
        if len(set(fallback_paths_tuple)) != len(fallback_paths_tuple):
            fallback_paths_tuple = tuple(dict.fromkeys(fallback_paths_tuple))
        admitted, graph_metadata_bytes, graph_error = self._admit_graph(graph if not isinstance(graph, str) else ())
        if graph_error is not None:
            return self._defer(operation, graph_error, cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes))
        paths = tuple(path for path, _ in admitted)
        trace = tuple({"source_path": path, "rank": rank} for path, rank in admitted)
        steps: list[NavigationStep] = [NavigationStep("graph_funnel", regions_considered=len(paths), graph_metadata_bytes=graph_metadata_bytes)]
        if len(steps) > self.budget.max_steps:
            return self._defer(operation, "step_budget_exhausted", cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes), steps=tuple(steps), graph_trace=trace)
        coordinates_inspected = sum(1 for item in self._coordinates if item.source_path in paths)
        graph_coordinates = tuple(item for item in self._coordinates if item.source_path in paths and self._coordinate_matches(item, terms) and self._verified(item))
        graph_items = [NavigationItem(item, None) for item in graph_coordinates]
        supporting: tuple[SourceCoordinate, ...] = ()
        hops = 0
        if requested_hops:
            if len(steps) >= self.budget.max_steps:
                return self._defer(operation, "step_budget_exhausted", cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes), steps=tuple(steps), graph_trace=trace)
            additions, supporting, hop_error = self._one_hop(graph_coordinates, terms)
            if hop_error is not None:
                return self._defer(operation, hop_error, cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes), steps=tuple(steps), graph_trace=trace)
            if additions:
                graph_items.extend(NavigationItem(item, None, "supporting_context") for item in additions if item not in graph_coordinates)
                hops = 1
                steps.append(NavigationStep("syntax_hop", hop=1, candidate_count=len(graph_items), coordinates_inspected=coordinates_inspected, supporting_context=True))
        direct_used = False
        source_bytes_read = 0
        fallback_bytes = 0
        if (allow_direct_fallback or bool(fallback_paths_tuple)):
            if not fallback_paths_tuple:
                return self._defer(operation, "fallback_allowlist_required", cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes), steps=tuple(steps), graph_trace=trace)
            if len(steps) >= self.budget.max_steps:
                return self._defer(operation, "step_budget_exhausted", cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes), steps=tuple(steps), graph_trace=trace)
            direct_used = True
            direct_coords: list[SourceCoordinate] = []
            for path in fallback_paths_tuple:
                source = self.snapshot.source(path)
                if source_bytes_read + len(source.content) > self.budget.max_source_bytes:
                    return self._defer(operation, "source_budget_exhausted", cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes, source_bytes_read=source_bytes_read, fallback_bytes=fallback_bytes), steps=tuple(steps), graph_trace=trace)
                source_bytes_read += len(source.content)
                fallback_bytes += len(source.content)
                direct_coords.extend(item for item in self._coordinates if item.source_path == path and self._coordinate_matches(item, terms) and self._verified(item))
            steps.append(NavigationStep("direct_fallback", source_bytes_read=source_bytes_read, direct_fallback_used=True))
            for coordinate in direct_coords:
                if all(item.coordinate != coordinate for item in graph_items):
                    graph_items.append(NavigationItem(coordinate, None))
        if len(graph_items) > self.budget.max_candidates or (limit is not None and len(graph_items) > limit):
            return self._defer(operation, "candidate_budget_exhausted", cost=self._base_cost(graph_metadata_bytes=graph_metadata_bytes, source_bytes_read=source_bytes_read, fallback_bytes=fallback_bytes), steps=tuple(steps), graph_trace=trace)
        result = self._finish(operation, graph_items, steps=tuple(steps), graph_trace=trace, graph_metadata_bytes=graph_metadata_bytes, source_bytes_read=source_bytes_read, fallback_bytes=fallback_bytes, regions_considered=len(paths), coordinates_inspected=coordinates_inspected, hops=hops, direct_fallback_used=direct_used, supporting_context=supporting)
        if result.supported and not result.items:
            return NavigationV5Result("search", False, reason="search_no_match", cost=result.cost, steps=result.steps, graph_trace=result.graph_trace)
        return result

    def navigate(self, *args: Any, **kwargs: Any) -> NavigationV5Result:
        """Alias for :meth:`search`."""

        return self.search(*args, **kwargs)

    def progressive_search(self, *args: Any, **kwargs: Any) -> NavigationV5Result:
        """Explicit alias for callers that name the route."""

        return self.search(*args, **kwargs)

    def read_exact(self, coordinate: SourceCoordinate) -> NavigationV5Result:
        """Read one exact, custody-verified coordinate with authority."""

        operation = "read_exact"
        if self._index_error is not None:
            return self._defer(operation, self._index_error)
        if not isinstance(coordinate, SourceCoordinate) or not self._verified(coordinate):
            return self._defer(operation, "source_custody_mismatch")
        payload = self.snapshot.source(coordinate.source_path).content[coordinate.byte_start : coordinate.byte_end]
        if len(payload) > self.budget.max_source_bytes:
            return self._defer(operation, "source_budget_exhausted")
        item = NavigationItem(coordinate, payload)
        step = NavigationStep("exact_read", source_path=coordinate.source_path, source_bytes_read=len(payload))
        return self._finish(operation, (item,), steps=(step,), graph_trace=(), graph_metadata_bytes=0, source_bytes_read=len(payload), fallback_bytes=0, regions_considered=1, coordinates_inspected=1, hops=0, direct_fallback_used=False, authority_bearing=True)

    def read_span(self, coordinate: SourceCoordinate) -> NavigationV5Result:
        """V4-compatible name for an exact read."""

        result = self.read_exact(coordinate)
        return NavigationV5Result("read_span", result.supported, result.items, result.reason, result.cost, result.steps, result.graph_trace, result.authority_bearing, result.supporting_context)

    def read(self, coordinate: SourceCoordinate) -> NavigationV5Result:
        """Alias for :meth:`read_exact`."""

        return self.read_exact(coordinate)

    def read_symbol(self, symbol: str, *, limit: int | None = None) -> NavigationV5Result:
        """Resolve a definition/declaration, then perform exact reads."""

        if self._index_error is not None:
            return self._defer("read_symbol", self._index_error)
        if type(symbol) is not str or not symbol:
            return self._defer("read_symbol", "symbol_required")
        matches = tuple(item for item in self._coordinates if item.symbol == symbol and item.occurrence_role in {"definition", "declaration"} and self._verified(item))
        if not matches:
            return self._defer("read_symbol", "symbol_not_found")
        if limit is not None and (type(limit) is not int or limit < 1 or len(matches) > limit):
            return self._defer("read_symbol", "candidate_budget_exhausted")
        items: list[NavigationItem] = []
        source_bytes = _unique_coordinate_bytes(matches)
        if source_bytes > self.budget.max_source_bytes:
            return self._defer("read_symbol", "source_budget_exhausted")
        for coordinate in matches:
            payload = self.snapshot.source(coordinate.source_path).content[coordinate.byte_start : coordinate.byte_end]
            items.append(NavigationItem(coordinate, payload))
        step = NavigationStep("exact_read", source_bytes_read=source_bytes)
        return self._finish("read_symbol", items, steps=(step,), graph_trace=(), graph_metadata_bytes=0, source_bytes_read=source_bytes, fallback_bytes=0, regions_considered=len(matches), coordinates_inspected=len(matches), hops=0, direct_fallback_used=False, authority_bearing=True)


def navigate_v5(snapshot: SourceSnapshot, provider: CoordinateProvider, **kwargs: object) -> NavigationV5:
    """Construct a V5 navigator without parser or model inference."""

    return NavigationV5(snapshot, provider, **kwargs)  # type: ignore[arg-type]


__all__ = [
    "NavigationBudget",
    "NavigationCost",
    "NavigationItem",
    "NavigationResult",
    "NavigationStep",
    "NavigationV5",
    "NavigationV5Result",
    "navigate_v5",
]
