"""Tree-sitter JavaScript source coordinates.

The provider emits coordinates only for syntax represented by the maintained
JavaScript grammar.  It does not use regular expressions to assign semantic
roles.  Files with parse errors are deferred so callers cannot mistake an
incomplete tree for a complete index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .source_coordinates import IndexResult, SourceCoordinate, SourceSnapshot

try:  # Keep import failure explicit and fail closed at index time.
    from tree_sitter import Language, Parser
    import tree_sitter_javascript
except ImportError:  # pragma: no cover - exercised in dependency-free installs.
    Language = Parser = None  # type: ignore[assignment]
    tree_sitter_javascript = None  # type: ignore[assignment]


_JS_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs"})
_UNIT_TYPES = frozenset({
    "function_declaration", "function_expression", "arrow_function",
    "class_declaration", "class", "method_definition",
})
_STRUCTURAL_TYPES = _UNIT_TYPES | frozenset({
    "import_statement", "export_statement", "lexical_declaration",
    "variable_declaration",
})
_DECLARATION_PARENTS = frozenset({"formal_parameters", "required_parameter", "optional_parameter"})


def _is_javascript_path(path: str) -> bool:
    return path.casefold().endswith(tuple(_JS_SUFFIXES))


@dataclass(frozen=True)
class JavaScriptNamedImport:
    source_path: str
    module: str
    symbol: str
    byte_start: int
    byte_end: int


@dataclass(frozen=True)
class JavaScriptNamedExport:
    source_path: str
    symbol: str
    byte_start: int
    byte_end: int


@dataclass(frozen=True)
class JavaScriptRelationIndex:
    supported: bool
    imports: tuple[JavaScriptNamedImport, ...] = ()
    exports: tuple[JavaScriptNamedExport, ...] = ()
    unsupported: int = 0
    reason: str | None = None


def _name(node: object) -> str | None:
    field = getattr(node, "child_by_field_name")("name")
    if field is not None and getattr(field, "type", None) == "identifier":
        return field.text.decode("utf-8", errors="strict")
    return None


def _ancestors(node: object) -> Iterable[object]:
    parent = getattr(node, "parent", None)
    while parent is not None:
        yield parent
        parent = getattr(parent, "parent", None)


def _unit(node: object) -> tuple[str, str, object] | None:
    for parent in _ancestors(node):
        if getattr(parent, "type", None) not in _UNIT_TYPES:
            continue
        label = _name(parent)
        if label is None:
            label = f"<anonymous>@{parent.start_byte}"
        return label, getattr(parent, "type"), parent
    return None


def _is_property_identifier(node: object) -> bool:
    parent = getattr(node, "parent", None)
    if parent is None:
        return False
    if getattr(parent, "type", None) == "member_expression" and parent.child_by_field_name("property") == node:
        return True
    if getattr(parent, "type", None) in {"pair", "pair_pattern"} and parent.child_by_field_name("key") == node:
        return True
    return False


def _declaration_role(node: object) -> str | None:
    parent = getattr(node, "parent", None)
    if parent is None:
        return None
    parent_type = getattr(parent, "type", None)
    if parent_type in {"function_declaration", "class_declaration"} and parent.child_by_field_name("name") == node:
        return "definition"
    if parent_type == "variable_declarator" and parent.child_by_field_name("name") == node:
        return "definition"
    if parent_type in _DECLARATION_PARENTS:
        return "declaration"
    if parent_type in {"import_specifier", "namespace_import", "named_imports", "import_clause"}:
        return "import"
    return None


def _role(node: object) -> str | None:
    declared = _declaration_role(node)
    if declared:
        return declared
    parent = getattr(node, "parent", None)
    if parent is None:
        return None
    parent_type = getattr(parent, "type", None)
    if parent_type == "import_statement" or any(getattr(a, "type", None) == "import_statement" for a in _ancestors(node)):
        return "import"
    if parent_type == "call_expression" and parent.child_by_field_name("function") == node:
        return "call"
    if parent_type == "new_expression" and parent.child_by_field_name("constructor") == node:
        return "call"
    if parent_type in {"update_expression"} or (parent_type == "assignment_expression" and parent.child_by_field_name("left") == node):
        return "write"
    if _is_property_identifier(node):
        return None
    if parent_type in {"arguments", "return_statement", "binary_expression", "unary_expression", "ternary_expression", "template_substitution", "member_expression"}:
        return "read"
    if parent_type in {"variable_declarator", "assignment_expression"}:
        if parent.child_by_field_name("value") == node or parent.child_by_field_name("right") == node:
            return "read"
    return "reference"


def _identifiers(node: object) -> Iterable[object]:
    if getattr(node, "type", None) == "identifier":
        yield node
    for child in getattr(node, "children", ()):
        yield from _identifiers(child)


@dataclass(frozen=True)
class JavaScriptCoordinateProvider:
    """Coordinate provider backed by tree-sitter-javascript 0.25.0."""

    parser_version: str = "0.26.0"
    grammar_name: str = "tree-sitter-javascript"
    grammar_version: str = "0.25.0"

    @property
    def identity(self) -> dict[str, str]:
        return {"parser": "tree-sitter", "parser_version": self.parser_version,
                "grammar": self.grammar_name, "grammar_version": self.grammar_version}

    def index(self, snapshot: SourceSnapshot) -> IndexResult:
        if Parser is None or tree_sitter_javascript is None:
            return IndexResult(snapshot.snapshot_sha256, False, reason="javascript_parser_unavailable")
        paths = tuple(source.path for source in snapshot.sources if _is_javascript_path(source.path))
        if not paths:
            return IndexResult(snapshot.snapshot_sha256, False, reason="no_supported_javascript_sources")
        parser = Parser(Language(tree_sitter_javascript.language()))
        coordinates: list[SourceCoordinate] = []
        for path in paths:
            source = snapshot.source(path)
            tree = parser.parse(source.content)
            if tree.root_node.has_error:
                return IndexResult(snapshot.snapshot_sha256, False, reason=f"javascript_parse_error:{path}")
            units: dict[tuple[int, int], tuple[str, str, object]] = {}
            for node in self._walk(tree.root_node):
                if node.type in _STRUCTURAL_TYPES:
                    label = _name(node) or f"<anonymous>@{node.start_byte}"
                    units[(node.start_byte, node.end_byte)] = (label, node.type, node)
            for label, kind, unit in units.values():
                coordinates.append(self._coordinate(snapshot, source, unit.start_byte, unit.end_byte, kind, "unknown", label, label))
            for node in _identifiers(tree.root_node):
                role = _role(node)
                if role is None:
                    continue
                enclosing = _unit(node)
                enclosing_entity = enclosing[0] if enclosing else None
                kind = enclosing[1] if enclosing else (node.parent.type if node.parent else "identifier")
                symbol = node.text.decode("utf-8", errors="strict")
                coordinates.append(self._coordinate(snapshot, source, node.start_byte, node.end_byte, kind, role, symbol, enclosing_entity))
        ordered = tuple(sorted(coordinates, key=lambda item: (item.source_path, item.byte_start, item.byte_end, item.symbol, item.occurrence_role)))
        return IndexResult(snapshot.snapshot_sha256, True, ordered)

    def relations(self, snapshot: SourceSnapshot) -> JavaScriptRelationIndex:
        """Index the narrow static named-import and direct-export relation form."""

        paths = tuple(source.path for source in snapshot.sources if _is_javascript_path(source.path))
        if not paths:
            return JavaScriptRelationIndex(True)
        if Parser is None or tree_sitter_javascript is None:
            return JavaScriptRelationIndex(False, reason="javascript_parser_unavailable")
        parser = Parser(Language(tree_sitter_javascript.language()))
        imports: list[JavaScriptNamedImport] = []
        exports: list[JavaScriptNamedExport] = []
        unsupported = 0
        for path in paths:
            tree = parser.parse(snapshot.source(path).content)
            if tree.root_node.has_error:
                return JavaScriptRelationIndex(False, reason=f"javascript_parse_error:{path}")
            for node in self._walk(tree.root_node):
                if node.type == "call_expression" and any(child.type == "import" for child in node.children):
                    unsupported += 1
            for node in tree.root_node.children:
                if node.type == "import_statement":
                    source = node.child_by_field_name("source")
                    specifiers = tuple(child for child in self._walk(node) if child.type == "import_specifier")
                    clause = next((child for child in node.children if child.type == "import_clause"), None)
                    binding_count = sum(
                        child.type in {"identifier", "namespace_import"}
                        for child in clause.children
                    ) if clause is not None else 0
                    if source is None or source.type != "string" or not specifiers:
                        unsupported += max(1, binding_count)
                        continue
                    fragments = tuple(child for child in source.children if child.type == "string_fragment")
                    if len(fragments) != 1:
                        unsupported += len(specifiers) + binding_count
                        continue
                    module = fragments[0].text.decode("utf-8", errors="strict")
                    suffix = module.rsplit("/", 1)[-1].rsplit(".", 1)
                    if (
                        not module.startswith(("./", "../"))
                        or "\\" in module
                        or any(character in module for character in ("?", "#"))
                        or (len(suffix) == 2 and f".{suffix[1].casefold()}" not in _JS_SUFFIXES)
                    ):
                        unsupported += len(specifiers) + binding_count
                        continue
                    unsupported += binding_count
                    for specifier in specifiers:
                        name = specifier.child_by_field_name("name")
                        if name is None or name.type != "identifier":
                            unsupported += 1
                            continue
                        imports.append(JavaScriptNamedImport(
                            path, module, name.text.decode("utf-8", errors="strict"),
                            name.start_byte, name.end_byte,
                        ))
                elif node.type == "export_statement":
                    declaration = node.child_by_field_name("declaration")
                    if declaration is None or any(child.type == "default" for child in node.children):
                        if node.child_by_field_name("source") is not None:
                            unsupported += 1
                        continue
                    if declaration.type in {"function_declaration", "class_declaration"}:
                        name = declaration.child_by_field_name("name")
                        if name is not None and name.type == "identifier":
                            exports.append(JavaScriptNamedExport(
                                path, name.text.decode("utf-8", errors="strict"),
                                declaration.start_byte, declaration.end_byte,
                            ))
                    elif declaration.type in {"lexical_declaration", "variable_declaration"}:
                        for declarator in declaration.children:
                            if declarator.type != "variable_declarator":
                                continue
                            name = declarator.child_by_field_name("name")
                            if name is not None and name.type == "identifier":
                                exports.append(JavaScriptNamedExport(
                                    path, name.text.decode("utf-8", errors="strict"),
                                    declarator.start_byte, declarator.end_byte,
                                ))
        return JavaScriptRelationIndex(
            True,
            tuple(sorted(imports, key=lambda item: (item.source_path, item.byte_start, item.symbol))),
            tuple(sorted(exports, key=lambda item: (item.source_path, item.byte_start, item.symbol))),
            unsupported,
        )

    @staticmethod
    def _walk(node: object) -> Iterable[object]:
        yield node
        for child in getattr(node, "children", ()):
            yield from JavaScriptCoordinateProvider._walk(child)

    @staticmethod
    def _coordinate(snapshot: SourceSnapshot, source: object, start: int, end: int, kind: str, role: str, symbol: str, enclosing: str | None) -> SourceCoordinate:
        content = source.content  # type: ignore[attr-defined]
        return SourceCoordinate(snapshot.snapshot_sha256, source.path, source.source_sha256, start, end,  # type: ignore[attr-defined]
                                1 + content[:start].count(b"\n"), 1 + content[: end - 1].count(b"\n"), kind, role, symbol, enclosing)


__all__ = [
    "JavaScriptCoordinateProvider", "JavaScriptNamedExport", "JavaScriptNamedImport",
    "JavaScriptRelationIndex",
]
