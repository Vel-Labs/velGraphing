"""Experimental v4 adapter over the existing source reader, index and selector.

No oracle, filesystem discovery, provider transport, persistence or authorization
lives here. V1-v3 remain untouched. This is an explicit research route, not a
replacement for the portable graph-find command.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, replace
import hashlib
import posixpath
import re
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlsplit

VERSION = "velgraphing-frontier-v4-dev1"
POOL_LIMIT = 24
POOL_BYTES = 32768
SPAN_BYTES = 4096
ANSWER_BYTES = 16384
SEED_FILES = 6
NEIGHBOR_FILES = 4
# Explicit adapter configuration, not an inference of Python import authority.
MODULE_ROOTS = ("", "src", "Lib")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,63}")
_LINK = re.compile(r"\[[^\]\n]*\]\(([^\s()]+)\)")
_ROLE = re.compile(r":(?:func|meth|class):`([^`]+)`|\.\.\s+(?:function|class|method)::\s*([^\s(]+)")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_word(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


@dataclass(frozen=True)
class EdgeBasis:
    edge_id: str
    relation: str
    source_path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    excerpt_sha256: str
    target_path: str
    target_sha256: str

    def verify(self, sources: Mapping[str, bytes]) -> bool:
        raw = sources.get(self.source_path)
        target = sources.get(self.target_path)
        return (raw is not None and target is not None
                and digest(raw) == self.source_sha256
                and digest(target) == self.target_sha256
                and 0 <= self.byte_start < self.byte_end <= len(raw)
                and digest(raw[self.byte_start:self.byte_end]) == self.excerpt_sha256)


@dataclass(frozen=True)
class Unit:
    path: str
    source_sha256: str
    start: int
    end: int
    facets: tuple[str, ...] = ()
    origin: str = "seed"
    required: bool = False

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def key(self) -> tuple[str, int, int]:
        return self.path, self.start, self.end

    def verify(self, sources: Mapping[str, bytes]) -> None:
        if (type(self.path) is not str or not self.path
                or self.path.startswith("/") or "\\" in self.path or "\x00" in self.path
                or any(part in {"", ".", ".."} for part in self.path.split("/"))
                or type(self.required) is not bool
                or type(self.facets) is not tuple
                or any(type(f) is not str or not f for f in self.facets)):
            raise ValueError("unit_shape_invalid")
        raw = sources.get(self.path)
        if (raw is None or digest(raw) != self.source_sha256
                or type(self.start) is not int or type(self.end) is not int
                or not 0 <= self.start < self.end <= len(raw)
                or self.size > SPAN_BYTES):
            raise ValueError("unit_source_invalid")
        raw[self.start:self.end].decode("utf-8", "strict")


def _module_paths(path: str) -> tuple[str, ...]:
    if not path.endswith(".py"):
        return ()
    names = set()
    for root in MODULE_ROOTS:
        prefix = root + "/" if root else ""
        if not path.startswith(prefix):
            continue
        name = path[len(prefix):-3].replace("/", ".")
        if name.endswith(".__init__"):
            name = name[:-9]
        if name and all(part.isidentifier() for part in name.split(".")):
            names.add(name)
    return tuple(sorted(names))


def add_literal_relationships(graph: Any, sources: Mapping[str, bytes]) -> tuple[Any, tuple[EdgeBasis, ...]]:
    """Attach witnessed imports, relative document links and unambiguous RST references.

    Edges are navigation hints. A module-name match is not Python runtime name
    resolution. Dynamic imports, re-exports and ambiguous symbols are unsupported.
    No edges are inferred from topic or filename similarity.
    """
    from packages.core.models import Graph, GraphEdge, Provenance

    records = {record.provenance.path: record for record in graph.records}
    if len(records) != len(graph.records) or set(records) != set(sources):
        raise ValueError("relationship_scope_mismatch")
    for path, record in records.items():
        if (digest(sources[path]) != record.provenance.sha256
                or record.content.encode("utf-8") != sources[path]):
            raise ValueError("relationship_source_changed")
    modules: dict[str, set[str]] = defaultdict(set)
    symbols: dict[str, set[str]] = defaultdict(set)
    trees: dict[str, ast.AST] = {}
    for path in sorted(records):
        for module in _module_paths(path):
            modules[module].add(path)
        if path.endswith(".py"):
            try:
                tree = ast.parse(sources[path].decode("utf-8"))
            except (SyntaxError, ValueError, RecursionError):
                continue
            trees[path] = tree
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols[node.name].add(path)
    edges = list(graph.edges)
    bases: list[EdgeBasis] = []
    seen = set()

    def add(path: str, target: str, relation: str, start: int, end: int) -> None:
        if target == path or target not in records or not 0 <= start < end <= len(sources[path]):
            return
        key = (path, target, relation, start, end)
        if key in seen:
            return
        seen.add(key)
        source, destination = records[path], records[target]
        identity = digest(repr(key).encode("utf-8"))
        basis = EdgeBasis(identity, relation, path, digest(sources[path]), start, end,
                          digest(sources[path][start:end]), target, digest(sources[target]))
        if not basis.verify(sources):
            raise ValueError("relationship_basis_invalid")
        edges.append(GraphEdge(
            edge_id=identity, source_id=source.record_id, target_id=destination.record_id,
            relation=relation, relevance=1.0,
            provenance=Provenance(path, basis.source_sha256, f"bytes:{start}:{end}", True),
            trust=source.trust, sensitivity=source.sensitivity, freshness=source.freshness,
            admission=source.admission, eligible=source.eligible,
            agent_generated=source.agent_generated, export_allowed=source.export_allowed,
        ))
        bases.append(basis)

    for path in sorted(records):
        raw = sources[path]
        text = raw.decode("utf-8")
        offsets = [0]
        for line in raw.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))
        if path in trees:
            for node in ast.walk(trees[path]):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                names: set[str] = set()
                if isinstance(node, ast.Import):
                    names.update(alias.name for alias in node.names)
                elif node.level:
                    for module in _module_paths(path):
                        package = module.split(".") if path.endswith("/__init__.py") else module.split(".")[:-1]
                        if node.level > len(package):
                            continue
                        base = package[:len(package) - node.level + 1]
                        if node.module:
                            base.extend(node.module.split("."))
                            names.add(".".join(base))
                        else:
                            names.update(".".join((*base, alias.name)) for alias in node.names)
                else:
                    names.add(node.module or "")
                targets = {target for name in names for target in modules.get(name, ())}
                # Each import alias is independent, but ambiguous roots fail closed.
                for name in sorted(names):
                    resolved = modules.get(name, set())
                    if len(resolved) != 1:
                        continue
                    target = next(iter(resolved))
                    if isinstance(node, ast.ImportFrom) and len(targets) != 1:
                        continue
                    start = offsets[node.lineno - 1] + node.col_offset
                    end = offsets[node.end_lineno - 1] + node.end_col_offset
                    add(path, target, "imports", start, end)
        if path.lower().endswith((".md", ".markdown", ".rst", ".txt")):
            for match in _LINK.finditer(text):
                parsed = urlsplit(match.group(1))
                if parsed.scheme or parsed.netloc or parsed.query or not parsed.path:
                    continue
                relative = unquote(parsed.path)
                if "\\" in relative or "\x00" in relative or relative.startswith("/"):
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), relative))
                start = len(text[:match.start()].encode("utf-8"))
                end = len(text[:match.end()].encode("utf-8"))
                add(path, target, "documents", start, end)
        if path.lower().endswith(".rst"):
            for match in _ROLE.finditer(text):
                name = (match.group(1) or match.group(2)).strip().lstrip("~").split(".")[-1]
                targets = symbols.get(name, set())
                if len(targets) == 1:
                    add(path, next(iter(targets)), "documents",
                        len(text[:match.start()].encode("utf-8")),
                        len(text[:match.end()].encode("utf-8")))
    return Graph(graph.records, tuple(edges)), tuple(bases)


def expand_with_core_select(graph: Any, seed_ids: Sequence[str], limit: int = NEIGHBOR_FILES) -> tuple[str, ...]:
    """One canonical select() hop from exact roots; never a second traversal engine."""
    from packages.core.models import Graph, TaskSpec
    from packages.core.selection import select

    if type(limit) is not int or not 0 <= limit <= NEIGHBOR_FILES:
        raise ValueError("neighbor_budget_invalid")
    record_map = graph.record_map()
    if len(seed_ids) != len(set(seed_ids)) or any(seed not in record_map for seed in seed_ids):
        raise ValueError("seed_scope_invalid")
    # A pointer-only projection gives select exact roots without duplicating source
    # bodies or allowing an incidental mention of a filename to become a root.
    projected = Graph(tuple(replace(record, title=digest(record.record_id.encode()),
                                     content="", tags=()) for record in graph.records), graph.edges)
    selected: list[str] = []
    for seed in seed_ids:
        if len(selected) == limit:
            break
        record = record_map[seed]
        result = select(projected, TaskSpec(
            task_id="frontier-neighborhood", query_terms=(digest(seed.encode()),),
            max_depth=1, node_budget=1 + limit, minimum_relevance=1.0,
            allowed_sensitivities=(record.sensitivity,),
        ))
        if result.fail_closed:
            raise ValueError("neighborhood_authentication_divergence")
        for candidate in result.record_ids:
            if candidate not in seed_ids and candidate not in selected:
                selected.append(candidate)
                if len(selected) == limit:
                    break
    return tuple(selected)


def _paragraph(raw: bytes, start: int, end: int) -> tuple[int, int]:
    """An exact paragraph/window adapter; never fabricate section summaries."""
    left = raw.rfind(b"\n\n", 0, start)
    left = left + 2 if left >= 0 else 0
    right = raw.find(b"\n\n", end)
    right = len(raw) if right < 0 else right + 1
    if right - left > SPAN_BYTES:
        from packages.core.retrieval import _line_window
        left, right = _line_window(raw, start, end, SPAN_BYTES)
    if right - left > SPAN_BYTES or not left <= start < end <= right:
        return start, end
    return left, right


def units_for_record(record: Any, raw: bytes, values: set[str], *, origin: str) -> tuple[Unit, ...]:
    """Re-anchor every matched facet occurrence, not the first tag per file.

    The existing tag index chooses facets and files. This adapter only resolves
    their occurrences into exact source units, with a 256-anchor per-file cap.
    """
    from packages.core.retrieval import _complete_unit_bounds

    path = record.provenance.path
    if digest(raw) != record.provenance.sha256:
        raise ValueError("unit_source_changed")
    text = raw.decode("utf-8")
    found: dict[tuple[int, int], set[str]] = defaultdict(set)
    occurrences = 0
    for match in _TOKEN.finditer(text):
        value = canonical_word(match.group())
        if value not in values:
            continue
        start = len(text[:match.start()].encode("utf-8"))
        end = len(text[:match.end()].encode("utf-8"))
        left, right = _complete_unit_bounds(raw, path, start, end)
        if path.endswith(".rst") or right - left > SPAN_BYTES:
            left, right = _paragraph(raw, start, end)
        if 0 <= left < right <= len(raw) and right - left <= SPAN_BYTES:
            try:
                raw[left:right].decode("utf-8")
            except UnicodeError:
                continue
            found[left, right].add(value)
        occurrences += 1
        if occurrences == 256:
            break
    # A literal neighbor is inspectable even without a lexical match. Its first
    # nonempty source unit is only supporting context, not certified evidence.
    if not found and origin == "neighbor" and raw:
        left, right = _paragraph(raw, 0, min(1, len(raw)))
        if right > left:
            found[left, right] = set()
    return tuple(Unit(path, digest(raw), left, right, tuple(sorted(facets)), origin)
                 for (left, right), facets in sorted(found.items()))


def pack_units(units: Sequence[Unit], sources: Mapping[str, bytes], *, byte_budget: int,
               count_budget: int, order: Sequence[int] | None = None,
               diversity: bool = True) -> tuple[Unit, ...]:
    """Required units first; optional marginal facets, file diversity, then order.

    A complete provider permutation can change tie priority, not hard budgets or
    required membership. Safety dimensions are not averaged into these scores.
    """
    if (type(byte_budget) is not int or not 0 < byte_budget <= POOL_BYTES
            or type(count_budget) is not int or not 0 < count_budget <= 64):
        raise ValueError("packing_budget_invalid")
    for unit in units:
        unit.verify(sources)
    if len({unit.key for unit in units}) != len(units):
        raise ValueError("duplicate_unit")
    priority = tuple(range(len(units))) if order is None else tuple(order)
    if (any(type(i) is not int for i in priority)
            or len(priority) != len(units) or set(priority) != set(range(len(units)))):
        raise ValueError("packing_order_not_permutation")
    ranks = {index: rank for rank, index in enumerate(priority)}
    required = [index for index, unit in enumerate(units) if unit.required]
    if any(priority[i] != i for i in required):
        raise ValueError("required_pool_position_changed")
    if sum(units[i].size for i in required) > byte_budget or len(required) > count_budget:
        raise ValueError("required_evidence_does_not_fit")
    chosen = list(required)
    used = sum(units[i].size for i in chosen)
    covered = {facet for i in chosen for facet in units[i].facets}
    paths = {units[i].path for i in chosen}
    remaining = {i for i in range(len(units)) if i not in chosen}
    while remaining and len(chosen) < count_budget:
        fits = [i for i in remaining if used + units[i].size <= byte_budget
                and not any(units[i].path == units[j].path
                            and units[j].start <= units[i].start and units[i].end <= units[j].end
                            for j in chosen)]
        if not fits:
            break
        def key(i: int) -> tuple:
            unit = units[i]
            if not diversity:
                return (-ranks[i],)
            return (len(set(unit.facets) - covered), unit.path not in paths,
                    -ranks[i], -unit.size)
        pick = max(fits, key=key)
        chosen.append(pick)
        remaining.remove(pick)
        used += units[pick].size
        covered.update(units[pick].facets)
        paths.add(units[pick].path)
    # Preserve the externally supplied relative order in the delivered subset.
    return tuple(units[i] for i in sorted(chosen, key=lambda i: ranks[i]))


def candidate_packet(question: str, units: Sequence[Unit]) -> dict[str, Any]:
    return {"schema_version": "velgraphing-jev-candidates-v1", "query": question,
            "candidates": [{"id": f"c{i}", "path": u.path,
                            "source_sha256": u.source_sha256,
                            "byte_start": u.start, "byte_end": u.end,
                            "required": u.required} for i, u in enumerate(units)]}


def select_frontier(graph: Any, snapshot: Any, reader: Any, question: str, *,
                    route: str = "typed", edges: bool = True, expansion: bool = True,
                    diversity: bool = True, byte_budget: int = ANSWER_BYTES,
                    count_budget: int = POOL_LIMIT) -> dict[str, Any]:
    """Oracle-blind, transport-free development route using canonical core seams."""
    from packages.core.models import Graph, TaskSpec
    from packages.core.retrieval import build_repository_tag_index, compile_prompt, retrieve
    from packages.core.routing_v4 import _read_verified_source_bytes

    if route not in {"direct", "typed"} or not isinstance(question, str) or not question.strip():
        raise ValueError("frontier_input_invalid")
    from time_to_correct_packet import _direct_span, _STOPWORDS, _supported_path

    sources = _read_verified_source_bytes(snapshot, reader)
    trace = ["seed"]
    terms = tuple(sorted({w.casefold().encode("ascii") for w in _TOKEN.findall(question)
                          if w.casefold() not in _STOPWORDS}))
    values = {canonical_word(t.decode("ascii")) for t in terms}
    seeds = ()
    if route == "typed":
        index = build_repository_tag_index(graph, snapshot, reader)
        facets = compile_prompt(question, index)
        task = TaskSpec(task_id="frontier-dev", query_terms=(), node_budget=SEED_FILES,
                        byte_budget=POOL_BYTES,
                        allowed_sensitivities=tuple(sorted({r.sensitivity for r in graph.records}, key=str)))
        baseline = retrieve(Graph(graph.records), task, index, facets, snapshot, reader,
                            expand_one_hop=False, maximum_results=SEED_FILES, parallel=False,
                            channels=("exact", "sparse", "wiki"))
        if baseline.fail_closed:
            return {"version": VERSION, "state": "defer", "reason": baseline.reason,
                    "pool": (), "selected": (), "trace": trace + ["defer"], "edges": (), "sufficient": False}
        seeds = tuple(hit.record_id for hit in baseline.hits)
        values &= {tag.value for tag in index.tags}
        if baseline.route != "graph":
            trace.append("insufficient")
    if not seeds:
        # Direct does not build or consume the tag index or any graph edges.
        # The same existing scorer supplies one bounded typed-route fallback.
        ranked = []
        for record in graph.records:
            path = record.provenance.path
            raw = sources[path]
            if not raw or not _supported_path(path):
                continue
            _, _, score = _direct_span(raw, terms)
            score += sum(path.casefold().count(t.decode()) for t in terms)
            if score:
                ranked.append((-score, record.record_id))
        seeds = tuple(record_id for _, record_id in sorted(ranked)[:SEED_FILES])
        if route == "typed":
            trace.append("fallback")
    record_map = graph.record_map()
    typed, bases = add_literal_relationships(graph, sources) if route == "typed" else (graph, ())
    if not edges:
        typed = Graph(typed.records)
    neighbors = ()
    if route == "typed" and expansion and edges and typed.edges:
        trace.append("expand")
        neighbors = expand_with_core_select(typed, seeds)
    all_units: dict[tuple[str, int, int], Unit] = {}
    # Round-robin source units keeps one long source from consuming the shortlist.
    buckets = [list(units_for_record(record_map[r], sources[record_map[r].provenance.path],
                                     values, origin="seed" if r in seeds else "neighbor"))
               for r in (*seeds, *neighbors) if _supported_path(record_map[r].provenance.path)]
    for bucket in buckets:
        bucket.sort(key=lambda u: (-len(u.facets), u.size, u.start))
    while any(buckets):
        for bucket in buckets:
            if bucket:
                unit = bucket.pop(0)
                all_units.setdefault(unit.key, unit)
    pool = pack_units(tuple(all_units.values()), sources, byte_budget=POOL_BYTES,
                      count_budget=POOL_LIMIT, diversity=diversity)
    selected = pack_units(pool, sources, byte_budget=byte_budget,
                          count_budget=count_budget, diversity=diversity)
    missing = tuple(sorted(values - {facet for unit in selected for facet in unit.facets}))
    state = "insufficient" if selected and missing else "candidate" if selected else "defer"
    trace += ["select", state]
    return {"version": VERSION, "state": state,
            "reason": "source_verified_candidate_not_completeness_proof" if selected else "no_usable_source_units",
            "missing_query_terms": missing,
            "active_edge_count": len(typed.edges) if route == "typed" else 0,
            "pool": pool, "selected": selected, "trace": trace, "edges": bases,
            "seed_ids": seeds, "neighbor_ids": neighbors, "sufficient": False,
            "source_snapshot_sha256": snapshot.snapshot_sha256,
            "packet": candidate_packet(question, pool)}


def finalize_packet(question: str, pool: Sequence[Unit], sources: Mapping[str, bytes],
                    effective_order: Sequence[str] | None = None, *,
                    byte_budget: int = ANSWER_BYTES, count_budget: int = POOL_LIMIT) -> dict[str, Any]:
    """Apply an already validated Jev order, then revalidate before answer handoff.

    Provider failures use the baseline order. Stale source is a hard defer, never
    permission to answer from the stale baseline. The final subset keeps original
    candidate IDs and every caller-required unit; their absolute slots can close
    as optional units disappear. The Jev pool itself remains position-locked.
    """
    ids = tuple(f"c{i}" for i in range(len(pool)))
    given = ids if effective_order is None else tuple(effective_order)
    if len(given) != len(ids) or set(given) != set(ids):
        raise ValueError("final_order_not_permutation")
    order = tuple(ids.index(candidate_id) for candidate_id in given)
    chosen = pack_units(pool, sources, byte_budget=byte_budget, count_budget=count_budget,
                        order=order)
    keep = {unit.key for unit in chosen}
    packet = candidate_packet(question, pool)
    packet["candidates"] = [packet["candidates"][i] for i in order if pool[i].key in keep]
    return packet
