"""Deterministic repository views over the existing admitted source snapshot.

No provider, persistence, crawler or import-time I/O. The graphctl owner handles
admission and output. Full rebuilds intentionally re-resolve all dependents.
"""
from __future__ import annotations

import ast
from collections import defaultdict
import hashlib
import json
import re
from pathlib import PurePosixPath

from .models import Admission, Freshness, GraphEdge, Provenance, Sensitivity, TrustClass
from .retrieval import build_repository_file_cards, build_repository_tag_index, _complete_unit_bounds
from .routing_v4 import SourceSnapshotV4

SCHEMA = "retrievel-repository-map-v1"
BUILDER_VERSION = "deterministic-full-rebuild-v1"


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def python_import_relations(raw, path, source_paths):
    """Source-witnessed local Python imports; shared with the existing tool loop.

    This is static syntactic resolution, not proof of Python runtime binding.
    Physical LF offsets preserve BOM/CRLF/Unicode original-source byte custody.
    """
    if not path.endswith(".py"):
        return []
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError):
        return []
    package = list(PurePosixPath(path).parent.parts)
    offsets = [0]
    for line in raw.split(b"\n"):
        offsets.append(offsets[-1] + len(line) + 1)
    edges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [a.name.split(".") for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > len(package):
                continue
            base = package[:len(package) - node.level + 1] if node.level else []
            base += node.module.split(".") if node.module else []
            modules = [base] + [base + a.name.split(".") for a in node.names]
        else:
            continue
        start, end = offsets[node.lineno - 1], min(len(raw), offsets[node.end_lineno])
        for module in modules:
            stem = "/".join(module)
            for target in (stem + ".py", stem + "/__init__.py"):
                if target in source_paths and target != path:
                    witness = dict(path=path, source_sha256=digest(raw), byte_start=start,
                                   byte_end=end, excerpt_sha256=digest(raw[start:end]))
                    edges.append(dict(kind="imports", **{"from": "file:" + path, "to": "file:" + target},
                                      witness=witness))
    return sorted({json.dumps(e, sort_keys=True): e for e in edges}.values(),
                  key=lambda e: (e["to"], e["witness"]["byte_start"]))


def python_symbols(raw, path):
    if not path.endswith(".py"):
        return [], "not_supported"
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError):
        return [], "parse_unavailable"
    offsets = [0]
    for line in raw.split(b"\n"):
        offsets.append(offsets[-1] + len(line) + 1)
    prefix = 3 if raw.startswith(b"\xef\xbb\xbf") else 0
    symbols = []

    def visit(node, parents=()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = offsets[node.lineno - 1] + node.col_offset + (prefix if node.lineno == 1 else 0)
            unit = _complete_unit_bounds(raw, path, start, min(len(raw), start + 3))
            name = ".".join((*parents, node.name))
            item = dict(name=node.name, qualified_name=name, source_path=path,
                        source_sha256=digest(raw), declaration_byte_start=start,
                        kind="class" if isinstance(node, ast.ClassDef) else "function",
                        complete_unit_available=unit is not None)
            if unit is not None:
                left, right = unit
                item.update(id=f"unit:{path}:{left}:{right}:{digest(raw[left:right])[:16]}",
                            byte_start=left, byte_end=right, excerpt_sha256=digest(raw[left:right]))
            else:
                item.update(id=f"unresolved:{path}:{start}", reason="complete_unit_unavailable")
            symbols.append(item)
            parents = (*parents, node.name)
        for child in ast.iter_child_nodes(node):
            visit(child, parents)

    visit(tree)
    return sorted(symbols, key=lambda s: (s["declaration_byte_start"], s["qualified_name"])), "parsed"


def build_manifest(graph, snapshot, reader, *, namespace, policy, scan, builder):
    index = build_repository_tag_index(graph, snapshot, reader)
    cards = {c.source_path: c.to_dict() for c in build_repository_file_cards(graph, snapshot, reader)}
    files, symbols, relationships = [], [], []
    for source in snapshot.sources:
        path = source.path
        raw = reader.read_bytes(path)
        decls, status = python_symbols(raw, path)
        card = cards[path]
        files.append(dict(**card, bytes=source.byte_length, symbol_status=status))
        symbols.extend(decls)
        for edge in python_import_relations(raw, path, {s.path for s in snapshot.sources}):
            target = edge["to"][5:]
            witness = edge["witness"]
            edge_id = "import:" + digest(canonical(edge))
            typed = GraphEdge(edge_id, "repo:" + path, "repo:" + target, "imports", 1.0,
                              Provenance(path, source.sha256,
                                         f"bytes:{witness['byte_start']}:{witness['byte_end']}", True),
                              TrustClass.VERIFIED_SOURCE, Sensitivity.INTERNAL, Freshness.CURRENT,
                              Admission.VERIFIER, eligible=True)
            relationships.append(dict(**typed.to_dict(), witness=witness))
    tags = [dict(kind=t.kind.value, value=t.value, record_id=t.record_id,
                 source_path=t.source_path, byte_start=t.byte_start, byte_end=t.byte_end)
            for t in index.tags]
    postings = defaultdict(list)
    for number, tag in enumerate(tags):
        postings[tag["value"]].append(number)
    manifest = dict(schema_version=SCHEMA, builder_version=BUILDER_VERSION, builder=builder,
                    namespace=namespace, owner="graph-engineering/graphctl",
                    snapshot=snapshot.to_dict(), policy=policy, scan=scan,
                    files=files, symbols=symbols, relationships=relationships,
                    tags=tags, keywords=dict(sorted(postings.items())),
                    sensitivity="internal", export_allowed=False,
                    authority_bearing=False, completeness_assessment="not_assessed")
    manifest["manifest_sha256"] = digest(canonical(manifest))
    return manifest


def validate_manifest(manifest):
    if type(manifest) is not dict or manifest.get("schema_version") != SCHEMA:
        raise ValueError("unsupported repository map")
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if manifest.get("manifest_sha256") != digest(canonical(body)):
        raise ValueError("repository map checksum mismatch")
    snapshot = SourceSnapshotV4.from_dict(manifest["snapshot"])
    if [(f["source_path"], f["source_sha256"], f["bytes"]) for f in manifest["files"]] != [
            (s.path, s.sha256, s.byte_length) for s in snapshot.sources]:
        raise ValueError("file view disagrees with snapshot")
    tags, keywords = manifest.get("tags"), manifest.get("keywords")
    if type(tags) is not list or type(keywords) is not dict:
        raise ValueError("repository map tags must be an array and keywords must be an object")
    for keyword, postings in keywords.items():
        if type(keyword) is not str or type(postings) is not list:
            raise ValueError("repository map keyword postings must be arrays keyed by strings")
        if any(type(posting) is not int or not 0 <= posting < len(tags) for posting in postings):
            raise ValueError("repository map keyword posting must be an integer within the tag range")
    return snapshot


def changes(previous, current):
    validate_manifest(current)
    if previous is None:
        return dict(added=[f["source_path"] for f in current["files"]], changed=[], removed=[],
                    unchanged=0, policy_changed=False, builder_changed=False,
                    method="full_rebuild; renames are removal plus addition")
    validate_manifest(previous)
    if previous["namespace"] != current["namespace"]:
        raise ValueError("previous map has a different namespace")
    before = {s["path"]: s["sha256"] for s in previous["snapshot"]["sources"]}
    after = {s["path"]: s["sha256"] for s in current["snapshot"]["sources"]}
    return dict(added=sorted(after.keys() - before.keys()), removed=sorted(before.keys() - after.keys()),
                changed=sorted(p for p in before.keys() & after.keys() if before[p] != after[p]),
                unchanged=sum(before[p] == after[p] for p in before.keys() & after.keys()),
                policy_changed=previous["policy"] != current["policy"],
                builder_changed=previous["builder"] != current["builder"],
                method="full_rebuild; renames are removal plus addition")


def search_manifest(manifest, query, limit=10):
    """Rank stored metadata pointers only; never treat a saved map as fresh source."""
    validate_manifest(manifest)
    if not query.strip() or not 1 <= limit <= 64:
        raise ValueError("nonempty query and limit 1..64 required")
    from .retrieval import _canonical, _identifier_parts
    named_terms = {_canonical(t) for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", query)}
    terms = set(named_terms)
    terms |= {part for term in tuple(terms) for part in _identifier_parts(term)}
    scores = defaultdict(int)
    for term in sorted(terms):
        for posting in manifest["keywords"].get(term, ()):
            tag = manifest["tags"][posting]
            scores[tag["source_path"]] += 2 if tag["kind"] in {"path", "symbol"} else 1
    # Common prose words can also be function names. Give exact-name priority
    # only to a standalone identifier or an explicitly written code identifier.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", query.strip()):
        explicit_names = named_terms
    else:
        explicit_names = {_canonical(t) for t in re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", query)}
        explicit_names |= {_canonical(t) for t in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(", query)}
        explicit_names |= {_canonical(t) for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
                           if "_" in t or any(c.isupper() for c in t[1:])}
    exact_declarations = {s["source_path"] for s in manifest["symbols"]
                          if _canonical(s["name"]) in explicit_names}
    for path in exact_declarations:
        scores.setdefault(path, 0)
    ranked = sorted(scores, key=lambda path: (path not in exact_declarations, -scores[path], path))[:limit]
    cards = {f["source_path"]: f for f in manifest["files"]}
    return dict(query=query, manifest_sha256=manifest["manifest_sha256"],
                source_snapshot_sha256=manifest["snapshot"]["snapshot_sha256"],
                hits=[dict(path=p, source_sha256=cards[p]["source_sha256"], score=scores[p],
                           exact_declaration_match=p in exact_declarations,
                           symbols=[s for s in manifest["symbols"] if s["source_path"] == p],
                           outgoing_relationships=[e for e in manifest["relationships"]
                                                   if e["source_id"] == "repo:" + p]) for p in ranked],
                freshness="not_checked", required_next_action="read_current_source",
                completeness_assessment="not_assessed", authority_bearing=False)
