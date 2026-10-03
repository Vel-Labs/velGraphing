#!/usr/bin/env python3
"""Request-local graph tools. JSON lines in/out; no provider or repository writes."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import PurePosixPath
import re
import sys
import time

sys.dont_write_bytecode = True
import graph_find as adapter
try:
    from packages.core import Graph, TaskSpec, Sensitivity, select
    from packages.core.retrieval import _complete_unit_bounds
    from packages.core.repository_build import python_import_relations
except ModuleNotFoundError:
    from core import Graph, TaskSpec, Sensitivity, select
    from core.retrieval import _complete_unit_bounds
    from core.repository_build import python_import_relations


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded(value, maximum=64):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"limit must be an integer in 1..{maximum}")
    return value


class UnitUnavailable(ValueError):
    def __init__(self, node):
        self.node = node
        super().__init__("complete_unit_unavailable")


class Session:
    def __init__(self, root, byte_budget=32768, exclusions=()):
        self.root = adapter._canonical_root(root)
        self.graph, self.snapshot, self.reader, self.scan = adapter._scan(
            self.root, adapter.DEFAULT_MAX_FILE_BYTES, adapter.DEFAULT_MAX_TOTAL_BYTES, tuple(exclusions))
        self.identity = self.git_identity()
        self.limit = bounded(byte_budget, adapter.HARD_MAX_TOTAL_BYTES)
        self.used = self.validation_bytes = self.metadata_bytes = self.steps = 0
        self.nodes, self.seen, self.query = {}, set(), None

    def git_identity(self):
        return {"head": adapter._git(self.root, "rev-parse", "HEAD").decode().strip(),
                "branch": adapter._git(self.root, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()}

    def fresh(self, path):
        raw, reason, _, count = adapter._read_regular(
            self.root, adapter._safe_relative(path), adapter.DEFAULT_MAX_FILE_BYTES)
        self.validation_bytes += count
        if reason or raw != self.reader.sources[path]:
            raise ValueError("stale_source: rebuild in a new session")

    def rank(self, query, scope=None):
        if type(query) is not str or not query.strip() or len(query) > 4096:
            raise ValueError("nonempty intent of at most 4096 characters required")
        if scope is not None:
            scope = adapter._safe_relative(scope).as_posix()
        graph = Graph(tuple(r for r in self.graph.records if scope is None or
                            r.provenance.path == scope or r.provenance.path.startswith(scope + "/")))
        terms = tuple(sorted({t.casefold() for t in adapter._TOKEN.findall(query)}))
        task = TaskSpec(task_id="graph-tools", query_terms=terms, node_budget=max(1, len(graph.records)),
                        byte_budget=self.limit, allowed_sensitivities=(Sensitivity.INTERNAL,))
        result = select(graph, task)
        if result.fail_closed:
            raise ValueError(result.reason)
        scores = dict(result.scores)
        return sorted(graph.records, key=lambda r: (-scores.get(r.record_id, 0), r.record_id))

    def admit(self, paths):
        added = []
        for path in paths:
            raw = self.reader.sources[path]
            self.fresh(path)
            fid = "file:" + path
            if fid in self.nodes:
                continue
            source_hash = digest(raw)
            directory = "dir:" + PurePosixPath(path).parent.as_posix()
            if len(self.nodes) + 1 + (directory not in self.nodes) > 512:
                raise ValueError("graph_node_budget_exhausted")
            if directory not in self.nodes:
                self.nodes[directory] = {"id": directory, "kind": "directory", "parent": "repo"}
                added.append(self.nodes[directory])
            self.nodes[fid] = {"id": fid, "kind": "file", "parent": directory, "path": path, "source_sha256": source_hash,
                               "byte_start": 0, "byte_end": len(raw)}
            added.append(self.nodes[fid])
            # A UTF-8 BOM is a Python byte-input prefix, not declaration text.
            # Keep every anchor and delivered bound in original-source offsets.
            prefix = 3 if raw.startswith(b"\xef\xbb\xbf") else 0
            anchors = list(re.finditer(rb"(?m)^[ \t]*(?:(?:async[ \t]+)?(?:def|class)[ \t]+\w+|#{1,6}[ \t]+[^\n]+)", raw[prefix:]))
            bounds = {}
            for anchor in anchors:
                start, end = anchor.start() + prefix, anchor.end() + prefix
                label = anchor.group().decode("utf-8").strip()
                unit = _complete_unit_bounds(raw, path, start, end)
                if unit is None:
                    if len(self.nodes) >= 512:
                        raise ValueError("graph_node_budget_exhausted")
                    uid = f"unresolved:{path}:{start}:{digest(raw[start:end])[:16]}"
                    self.nodes[uid] = {"id": uid, "kind": "unresolved_unit", "parent": fid,
                                       "path": path, "source_sha256": source_hash, "label": label[:160],
                                       "reason": "complete_unit_unavailable"}
                    added.append(self.nodes[uid])
                else:
                    bounds[unit] = label
            for (start, end), label in sorted(bounds.items()):
                if len(self.nodes) >= 512:
                    raise ValueError("graph_node_budget_exhausted")
                uid = f"unit:{path}:{start}:{end}:{digest(raw[start:end])[:16]}"
                self.nodes[uid] = {"id": uid, "kind": "unit", "parent": fid, "path": path,
                                   "source_sha256": source_hash, "byte_start": start, "byte_end": end,
                                   "excerpt_sha256": digest(raw[start:end]), "label": label[:160]}
                added.append(self.nodes[uid])
        return added

    def relations(self, path):
        self.fresh(path)
        return python_import_relations(self.reader.sources[path], path, self.reader.sources)

    def action(self, action):
        if self.steps >= 32:
            raise ValueError("step_budget_exhausted")
        if self.metadata_bytes >= 2 * 1024 * 1024:
            raise ValueError("response_envelope_budget_exhausted")
        self.steps += 1
        if type(action) is not dict or type(action.get("op")) is not str:
            raise ValueError("action must be an object with op")
        allowed = {"build": {"op", "intent", "limit", "scope"},
                   "inspect": {"op", "query", "limit", "offset", "scope"},
                   "expand": {"op", "id", "query", "limit"}, "read": {"op", "id"}}
        op = action["op"]
        if op not in allowed or set(action) - (allowed[op] | {"snapshot_sha256", "head", "branch"}):
            raise ValueError("invalid_action_fields")
        if self.git_identity() != self.identity:
            raise ValueError("wrong_branch_or_head: new session required")
        for key, expected in {**self.identity, "snapshot_sha256": self.snapshot.snapshot_sha256}.items():
            if key in action and action[key] != expected:
                raise ValueError("request_identity_mismatch:" + key)
        limit = bounded(action.get("limit", 2))
        if op == "build":
            query = action.get("intent")
            ranked = self.rank(query, action.get("scope"))
            self.query = query
            return {"nodes": self.admit([r.provenance.path for r in ranked[:limit]]),
                    "eligible_files": len(ranked), "omitted_files": max(0, len(ranked) - limit),
                    "mechanism": "intent_conditioned_lexical_construction"}
        if self.query is None:
            raise ValueError("build_required")
        if op == "inspect":
            ranked = self.rank(action.get("query", self.query), action.get("scope"))
            offset = action.get("offset", 0)
            if type(offset) is not int or offset < 0:
                raise ValueError("offset must be a nonnegative integer")
            return {"nodes": list(self.nodes.values()), "candidates": [
                {"id": "file:" + r.provenance.path, "built": "file:" + r.provenance.path in self.nodes}
                for r in ranked[offset:offset + limit]], "eligible_files": len(ranked),
                "unbuilt_files": sum("file:" + r.provenance.path not in self.nodes for r in ranked),
                "relations_supported": "source_witnessed_local_python_imports_only"}
        if op == "expand":
            if ("id" in action) == ("query" in action):
                raise ValueError("expand requires exactly one of id or query")
            if "query" in action:
                ranked = self.rank(action["query"])
                paths = [r.provenance.path for r in ranked if "file:" + r.provenance.path not in self.nodes][:limit]
                return {"nodes": self.admit(paths), "edges": [], "mechanism": "query_recovery_beyond_built_graph"}
            node = self.nodes[action["id"]]
            edges = self.relations(node["path"])
            targets = sorted({e["to"][5:] for e in edges})[:limit]
            return {"nodes": self.admit(targets), "edges": [e for e in edges if e["to"][5:] in targets],
                    "omitted_targets": len({e["to"] for e in edges}) - len(targets)}
        node = self.nodes[action["id"]]
        if node["kind"] == "unresolved_unit":
            raise UnitUnavailable(node)
        key = (node["path"], node["byte_start"], node["byte_end"])
        raw = self.reader.sources[node["path"]][node["byte_start"]:node["byte_end"]]
        if any(p == key[0] and start <= key[1] and end >= key[2] for p, start, end in self.seen):
            return {"duplicate": True, "document": None}
        if len(raw) > self.limit - self.used:
            raise ValueError("shared_content_budget_exhausted")
        if len(raw) > 131072:
            raise ValueError("single_response_content_limit")
        document = {**node, "text": raw.decode("utf-8"), "excerpt_sha256": digest(raw)}
        if len(json.dumps(document).encode("utf-8")) > 256 * 1024:
            raise ValueError("single_response_envelope_limit")
        self.fresh(node["path"])
        self.used += len(raw)
        self.seen.add(key)
        return {"document": document, "byte_count": len(raw)}

    def dispatch(self, action):
        started = time.perf_counter()
        try:
            result = self.action(action)
            status, reason = "ok", "completeness_not_assessed"
        except (KeyError, OSError, TypeError, ValueError) as error:
            result, status, reason = {}, "defer", str(error)
            if isinstance(error, UnitUnavailable):
                result = {"unresolved_units": [error.node], "fallback_obligations": [
                    {"path": error.node["path"], "file_id": error.node["parent"],
                     "required_read": "complete_file", "reason": "complete_unit_unavailable"}]}
        output = {"schema_version": "graph-tools-v1", "result": result, "status": status, "reason": reason,
                  "sufficient": False, "authority_bearing": False, "snapshot_sha256": self.snapshot.snapshot_sha256,
                  **self.identity, "budget": {"limit_bytes": self.limit, "delivered_content_bytes": self.used,
                  "remaining_bytes": self.limit - self.used, "steps": self.steps, "max_steps": 32},
                  "cost": {"elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                           "source_acquisition_bytes": self.scan["source_bytes_read"],
                           "freshness_validation_bytes": self.validation_bytes,
                           "serialized_response_bytes_before_this_response": self.metadata_bytes,
                           "receiving_model_tokens": None, "provider_calls": 0},
                  "scan": self.scan}
        if len(json.dumps(output).encode("utf-8")) > 512 * 1024:
            output.update(result={}, status="defer", reason="single_response_envelope_limit")
        self.metadata_bytes += len(json.dumps(output).encode("utf-8"))
        return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--byte-budget", type=int, default=32768)
    parser.add_argument("--exclude-path-prefix", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        started = time.perf_counter()
        session = Session(args.root, args.byte_budget, args.exclude_path_prefix)
        construction_ms = round((time.perf_counter() - started) * 1000, 3)
        for line in sys.stdin:
            if len(line.encode("utf-8")) > 16384:
                action = None
            else:
                try:
                    action = json.loads(line)
                except (ValueError, UnicodeError):
                    action = None
            output = session.dispatch(action)
            output["cost"]["acquisition_ms"] = construction_ms
            print(json.dumps(output, sort_keys=True, separators=(",", ":")), flush=True)
        return 0
    except (adapter.InputError, OSError, ValueError, UnicodeError) as error:
        print(f"graph-tools: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
