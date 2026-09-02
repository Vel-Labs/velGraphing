"""Source-grounded typed tagging and deterministic hybrid retrieval.

This module is additive. It does not change legacy graph selection. Retrieval
scores rank evidence candidates. They are not probabilities, authority, or
proof that an answer is complete.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import math
import posixpath
import re
from typing import Iterable, Mapping, Sequence

from .models import Graph, GraphRecord, Sensitivity, TaskSpec, is_authenticated_eligible
from .routing_v4 import SourceReaderV4, SourceSnapshotV4, _read_verified_source_bytes
from .selection import AssistResult, ContextSpan, assist


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,63}")
_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$")
_CONFIG_KEY = re.compile(r"(?m)[\"']([A-Za-z][A-Za-z0-9_.-]{1,63})[\"']\s*[:=]")
_TEST_NAME = re.compile(
    r"(?m)(?:\bdef\s+(test_[A-Za-z0-9_]+)|\b(?:it|test|describe)\s*\(\s*[\"']([^\"']{2,100})[\"'])"
)
_IMPORT = re.compile(
    r"(?m)(?:\bfrom\s+[\"']([^\"']+)[\"']|\brequire\s*\(\s*[\"']([^\"']+)[\"']|\bimport\s+(?:[^\n;]*?\s+from\s+)?[\"']([^\"']+)[\"'])"
)

_STOPWORDS = frozenset(
    {
        "about", "after", "also", "and", "are", "before", "can", "could",
        "describe", "does", "each", "explain", "for", "from", "have", "how",
        "identify", "into", "its", "may", "must", "of", "on", "or", "our",
        "should", "that", "the", "their", "then", "these", "this", "through",
        "to", "what", "when", "where", "which", "with", "would", "you",
    }
)
_GENERIC = frozenset({"code", "config", "data", "file", "graph", "module", "policy", "project", "repo", "source", "system"})
_PROOF_COMMON_TAGS = frozenset({
    *_STOPWORDS,
    *_GENERIC,
    "assert", "class", "const", "def", "false", "function", "get", "new",
    "behavior", "behavioral", "evidence", "implementation", "lifecycle",
    "none", "null", "return", "set", "trace", "true", "use", "using", "uses",
})
_ALLOWED_RELATIONS = frozenset(
    {
        "applies_to", "calls", "consumes", "declares", "declares_background_worker",
        "declares_packaging_command", "declares_side_panel", "depends_on", "describes",
        "dispatches_audits", "documents", "documents_audit_role", "documents_panel_surface",
        "documents_runtime_role", "emits_overlay_classes", "implements", "implements_documented_heuristic",
        "imports", "injects_content_script", "injects_overlay_styles", "loads_controller",
        "loads_stylesheet", "notifies_panel", "owns", "packages", "packages_documentation",
        "packages_manifest", "packages_source_tree", "persists_audit_for_panel", "produces",
        "publishes_section_selection", "reads", "requires_authority", "routes", "specifies_scoring_reference",
        "supports", "tested_by", "tests", "uses", "writes",
    }
)
_REVERSE_RELATIONS = frozenset(
    {
        "calls", "consumes", "declares", "depends_on", "describes", "documents",
        "implements", "imports", "packages", "produces", "supports", "tested_by",
        "tests", "uses",
    }
)
_CHANNEL_ORDER = ("exact", "sparse", "wiki", "graph")
_CHANNEL_WEIGHT = {"exact": 5, "sparse": 3, "wiki": 2, "graph": 2}
_RRF_K = 60
_MAX_FACETS = 20
_MIN_FACETS = 8
_MAX_TAGS_PER_RECORD = 4096


class TagKind(str, Enum):
    PATH = "path"
    SYMBOL = "symbol"
    IMPORT = "import"
    CONFIG = "config"
    TEST = "test"
    HEADING = "heading"
    DOCUMENTATION = "documentation"
    KEYWORD = "keyword"


_PROOF_TAG_KIND_WEIGHT = {
    TagKind.PATH: 5,
    TagKind.SYMBOL: 5,
    TagKind.CONFIG: 4,
    TagKind.TEST: 4,
    TagKind.IMPORT: 3,
    TagKind.HEADING: 2,
    TagKind.DOCUMENTATION: 1,
    TagKind.KEYWORD: 1,
}


class FacetKind(str, Enum):
    IDENTIFIER = "identifier"
    ENTITY = "entity"
    PHRASE = "phrase"
    INTENT = "intent"
    OPERATION = "operation"
    RELATION = "relation"
    ARTIFACT = "artifact"
    CONSTRAINT = "constraint"
    RISK = "risk"
    SEMANTIC = "semantic"


class AuthorityClass(str, Enum):
    """Caller-declared evidence category; it does not grant authority."""

    RUNTIME = "runtime"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"
    CONTRACT = "contract"
    TEST = "test"
    POLICY = "policy"


_MAX_PROOF_OBLIGATIONS = 6
_MAX_DOCUMENT_PROOF_UNIT_BYTES = 8192
_AUTHORITY_PRIORITY = {
    AuthorityClass.RUNTIME: 0,
    AuthorityClass.TEST: 1,
    AuthorityClass.CONTRACT: 2,
    AuthorityClass.CONFIGURATION: 3,
    AuthorityClass.POLICY: 4,
    AuthorityClass.DOCUMENTATION: 5,
}


@dataclass(frozen=True)
class ProofObligation:
    """A caller-owned lexical coverage requirement, not a truth assertion."""

    obligation_id: str
    authority_class: AuthorityClass
    source_hints: tuple[str, ...] = ()
    anchor_hints: tuple[str, ...] = ()
    required_tag_values: tuple[str, ...] = ()
    critical: bool = False

    def __post_init__(self) -> None:
        if type(self.obligation_id) is not str or not self.obligation_id.strip():
            raise ValueError("obligation_id must be non-empty")
        authority = self.authority_class
        if not isinstance(authority, AuthorityClass):
            try:
                authority = AuthorityClass(authority)
            except (TypeError, ValueError) as error:
                raise ValueError("authority_class must use the closed vocabulary") from error
            object.__setattr__(self, "authority_class", authority)
        for label, values in (
            ("source_hints", self.source_hints),
            ("anchor_hints", self.anchor_hints),
            ("required_tag_values", self.required_tag_values),
        ):
            if type(values) is not tuple or any(type(value) is not str or not value for value in values):
                raise ValueError(f"{label} must be a tuple of non-empty strings")
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{label} must be unique and sorted")
        for path in self.source_hints:
            if not _valid_source_path(path):
                raise ValueError("source hints must be project-relative traversal-free paths")
        for value in (*self.anchor_hints, *self.required_tag_values):
            if value != _canonical(value) or not value:
                raise ValueError("obligation anchors and required tags must be canonical")
        if not (self.source_hints or self.anchor_hints or self.required_tag_values):
            raise ValueError("proof obligations require at least one hint")
        if type(self.critical) is not bool:
            raise ValueError("critical must be a boolean")


@dataclass(frozen=True)
class RepositoryFileCard:
    """Minimal deterministic source-bound index record."""

    record_id: str
    source_path: str
    source_sha256: str
    anchor_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.record_id) is not str or not self.record_id:
            raise ValueError("record_id must be non-empty")
        if not _valid_source_path(self.source_path):
            raise ValueError("source_path must be project-relative and traversal-free")
        _require_sha256(self.source_sha256, "source_sha256")
        if type(self.anchor_tags) is not tuple or any(
            type(value) is not str or not value or value != _canonical(value)
            for value in self.anchor_tags
        ):
            raise ValueError("anchor_tags must be canonical strings")
        if tuple(sorted(set(self.anchor_tags))) != self.anchor_tags:
            raise ValueError("anchor_tags must be unique and sorted")

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "anchor_tags": list(self.anchor_tags),
        }


@dataclass(frozen=True)
class EvidenceItem:
    """A source-byte range bound to one or more proof obligations."""

    record_id: str
    source_path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    excerpt_sha256: str
    authority_class: AuthorityClass
    obligation_ids: tuple[str, ...]
    hop: int = 0

    def __post_init__(self) -> None:
        if type(self.record_id) is not str or not self.record_id:
            raise ValueError("record_id must be non-empty")
        if not _valid_source_path(self.source_path):
            raise ValueError("source_path must be project-relative and traversal-free")
        _require_sha256(self.source_sha256, "source_sha256")
        if type(self.byte_start) is not int or type(self.byte_end) is not int:
            raise ValueError("evidence byte ranges must use exact integers")
        if self.byte_start < 0 or self.byte_end <= self.byte_start:
            raise ValueError("evidence byte ranges must be non-empty and ordered")
        _require_sha256(self.excerpt_sha256, "excerpt_sha256")
        if not isinstance(self.authority_class, AuthorityClass):
            try:
                object.__setattr__(self, "authority_class", AuthorityClass(self.authority_class))
            except (TypeError, ValueError) as error:
                raise ValueError("authority_class must use the closed vocabulary") from error
        if type(self.obligation_ids) is not tuple or any(
            type(value) is not str or not value for value in self.obligation_ids
        ):
            raise ValueError("obligation_ids must be a tuple of non-empty strings")
        if tuple(sorted(set(self.obligation_ids))) != self.obligation_ids:
            raise ValueError("obligation_ids must be unique and sorted")
        if self.hop not in (0, 1):
            raise ValueError("evidence hop must be zero or one")
        if self.hop == 1 and not self.obligation_ids:
            raise ValueError("hop-one evidence must cover an obligation")

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "excerpt_sha256": self.excerpt_sha256,
            "authority_class": self.authority_class.value,
            "obligation_ids": list(self.obligation_ids),
            "hop": self.hop,
        }


@dataclass(frozen=True)
class RepositoryTag:
    kind: TagKind
    value: str
    record_id: str
    source_path: str
    byte_start: int | None = None
    byte_end: int | None = None

    def __post_init__(self) -> None:
        if not self.record_id or not self.source_path or not _canonical(self.value):
            raise ValueError("repository tags require canonical value, record, and source")
        if (self.byte_start is None) != (self.byte_end is None):
            raise ValueError("tag byte bounds must both be present or absent")
        if self.byte_start is not None and (self.byte_start < 0 or self.byte_end <= self.byte_start):
            raise ValueError("tag byte bounds must be ordered and non-empty")


@dataclass(frozen=True)
class RepositoryTagIndex:
    tags: tuple[RepositoryTag, ...]
    vocabulary: tuple[str, ...]
    source_snapshot_sha256: str

    def __post_init__(self) -> None:
        if tuple(sorted(set(self.vocabulary))) != self.vocabulary:
            raise ValueError("repository vocabulary must be unique and sorted")
        if len(self.source_snapshot_sha256) != 64:
            raise ValueError("source snapshot identity must be a full SHA-256")

    def by_record(self) -> dict[str, tuple[RepositoryTag, ...]]:
        grouped: dict[str, list[RepositoryTag]] = defaultdict(list)
        for tag in self.tags:
            grouped[tag.record_id].append(tag)
        return {key: tuple(value) for key, value in grouped.items()}


@dataclass(frozen=True)
class PromptFacet:
    kind: FacetKind
    value: str
    weight: int
    required: bool = False

    def __post_init__(self) -> None:
        if self.value != _canonical(self.value) or not self.value:
            raise ValueError("prompt facet values must be canonical")
        if type(self.weight) is not int or not 1 <= self.weight <= 10:
            raise ValueError("prompt facet weights must be integers from 1 to 10")


@dataclass(frozen=True)
class PromptFacetSet:
    prompt_sha256: str
    facets: tuple[PromptFacet, ...]
    rejected_semantic_candidates: tuple[str, ...] = ()
    proof_obligations: tuple[ProofObligation, ...] = ()

    def __post_init__(self) -> None:
        identities = [(facet.kind.value, facet.value) for facet in self.facets]
        if len(identities) != len(set(identities)):
            raise ValueError("prompt facets must be unique")
        if len(self.facets) > _MAX_FACETS:
            raise ValueError("prompt facets exceed the maximum")
        if len(self.prompt_sha256) != 64:
            raise ValueError("prompt identity must be a full SHA-256")
        if type(self.proof_obligations) is not tuple:
            raise ValueError("proof_obligations must be a tuple")
        if any(type(item) is not ProofObligation for item in self.proof_obligations):
            raise TypeError("proof_obligations must contain ProofObligation values")
        obligation_ids = tuple(item.obligation_id for item in self.proof_obligations)
        if len(obligation_ids) != len(set(obligation_ids)):
            raise ValueError("proof obligation IDs must be unique")

    @property
    def sufficient(self) -> bool:
        return _MIN_FACETS <= len(self.facets) <= _MAX_FACETS


@dataclass(frozen=True)
class RetrievalHit:
    record_id: str
    source_path: str
    match_score: int
    channels: tuple[str, ...]
    matched_facets: tuple[str, ...]
    hop: int
    expanded_from: str | None = None


@dataclass(frozen=True)
class RetrievalResult:
    route: str
    reason: str
    hits: tuple[RetrievalHit, ...]
    spans: tuple[ContextSpan, ...]
    context: str
    context_bytes: int
    facet_coverage_percent: float
    channel_rankings: tuple[tuple[str, tuple[str, ...]], ...]
    recommended_fallback_paths: tuple[str, ...]
    fail_closed: bool
    evidence: tuple[EvidenceItem, ...] = ()
    covered_obligation_ids: tuple[str, ...] = ()
    unresolved_obligation_ids: tuple[str, ...] = ()
    unresolved_critical_obligation_ids: tuple[str, ...] = ()
    remaining_byte_budget: int = 0


@dataclass(frozen=True)
class HybridRetrievalResult:
    retrieval: RetrievalResult
    fallback: AssistResult | None


@dataclass(frozen=True)
class SourcePreview:
    """A bounded, exact UTF-8 source span for progressive navigation."""

    record_id: str
    source_path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    excerpt_sha256: str
    text: str
    hop: int = 0
    source_snapshot_sha256: str = ""

    def __post_init__(self) -> None:
        if type(self.record_id) is not str or not self.record_id:
            raise ValueError("preview record_id must be non-empty")
        if not _valid_source_path(self.source_path):
            raise ValueError("preview source_path must be project-relative")
        _require_sha256(self.source_sha256, "preview source_sha256")
        _require_sha256(self.excerpt_sha256, "preview excerpt_sha256")
        if type(self.byte_start) is not int or type(self.byte_end) is not int:
            raise ValueError("preview byte ranges must use exact integers")
        if self.byte_start < 0 or self.byte_end <= self.byte_start:
            raise ValueError("preview byte ranges must be non-empty and ordered")
        if type(self.text) is not str or not self.text:
            raise ValueError("preview text must be non-empty UTF-8 source")
        encoded = self.text.encode("utf-8")
        if len(encoded) != self.byte_end - self.byte_start:
            raise ValueError("preview text length must match its byte range")
        if hashlib.sha256(encoded).hexdigest() != self.excerpt_sha256:
            raise ValueError("preview text must match its excerpt digest")
        if self.hop not in (0, 1):
            raise ValueError("preview hop must be zero or one")
        if self.source_snapshot_sha256:
            _require_sha256(self.source_snapshot_sha256, "preview source_snapshot_sha256")

    @property
    def content(self) -> str:
        """Compatibility alias that makes the raw preview explicit."""

        return self.text

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "excerpt_sha256": self.excerpt_sha256,
            "text": self.text,
            "hop": self.hop,
            "source_snapshot_sha256": self.source_snapshot_sha256,
        }


@dataclass(frozen=True)
class NavigationResult:
    """Navigation candidates and exact previews, separate from answer context."""

    route: str
    reason: str
    candidates: tuple[RetrievalHit, ...]
    previews: tuple[SourcePreview, ...]
    source_snapshot_sha256: str
    fail_closed: bool = False
    navigation_metadata: tuple[tuple[str, str], ...] = ()

    @property
    def hits(self) -> tuple[RetrievalHit, ...]:
        return self.candidates

    @property
    def source_previews(self) -> tuple[SourcePreview, ...]:
        return self.previews

    @property
    def metadata(self) -> tuple[tuple[str, str], ...]:
        return self.navigation_metadata

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "reason": self.reason,
            "candidates": [item.__dict__.copy() for item in self.candidates],
            "previews": [item.to_dict() for item in self.previews],
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "fail_closed": self.fail_closed,
            "navigation_metadata": [list(item) for item in self.navigation_metadata],
        }


@dataclass(frozen=True)
class NavigationContext:
    """Explicitly selected source previews and raw answer context."""

    primary_previews: tuple[SourcePreview, ...]
    supporting_previews: tuple[SourcePreview, ...]
    answer_context: str
    context_bytes: int
    source_snapshot_sha256: str
    fail_closed: bool = False
    reason: str = "verified_navigation_context"

    @property
    def primary(self) -> tuple[SourcePreview, ...]:
        return self.primary_previews

    @property
    def supporting(self) -> tuple[SourcePreview, ...]:
        return self.supporting_previews

    @property
    def source_bytes(self) -> int:
        return self.context_bytes

    def to_dict(self) -> dict[str, object]:
        return {
            "primary": [item.to_dict() for item in self.primary_previews],
            "supporting": [item.to_dict() for item in self.supporting_previews],
            "answer_context": self.answer_context,
            "context_bytes": self.context_bytes,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "fail_closed": self.fail_closed,
            "reason": self.reason,
        }


def build_repository_tag_index(
    graph: Graph,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
) -> RepositoryTagIndex:
    """Build deterministic typed tags from exact verified repository bytes."""

    source_bytes = _read_verified_source_bytes(snapshot, reader)
    tags, vocabulary = _expected_repository_tags(graph, snapshot, source_bytes)
    return RepositoryTagIndex(tags, vocabulary, snapshot.snapshot_sha256)


def compile_proof_obligations(
    prompt: str,
    graph: Graph,
    index: RepositoryTagIndex,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
) -> tuple[ProofObligation, ...]:
    """Compile prompt anchors into deterministic, complete-unit obligations.

    The compiler is deliberately lexical. It accepts only values already
    present in the verified tag index and checks each selected tag against the
    caller's exact UTF-8 source bytes. Multiple anchors in one clause produce
    one obligation whose closure is tested later by retrieval. This function
    does not inspect source-unit boundaries or alter caller-owned obligations
    passed to :func:`compile_prompt`.
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be non-empty")
    try:
        if type(graph) is not Graph or type(index) is not RepositoryTagIndex:
            raise ValueError("proof obligation inputs do not bind to verified source snapshot")
        if type(snapshot) is not SourceSnapshotV4:
            raise ValueError("proof obligation inputs do not bind to verified source snapshot")
        source_bytes = _read_verified_source_bytes(snapshot, reader)
        if not _validate_retrieval_custody(graph, index, snapshot, source_bytes):
            raise ValueError("proof obligation inputs do not bind to verified source snapshot")
    except Exception as error:
        raise ValueError("proof obligation inputs do not bind to verified source snapshot") from error

    vocabulary = set(index.vocabulary)
    obligations: list[ProofObligation] = []
    tag_values_by_path: dict[str, set[str]] = defaultdict(set)
    for tag in index.tags:
        tag_values_by_path[tag.source_path].add(tag.value)
    value_path_count = {
        value: sum(value in values for values in tag_values_by_path.values())
        for value in vocabulary
    }
    for clause_index, clause in enumerate(_prompt_clauses(prompt, vocabulary), start=1):
        raw_candidates: list[tuple[str, int, int]] = []
        clause_words = [word for word in _words(clause) if word not in _PROOF_COMMON_TAGS]
        for position, raw_word in enumerate(_TOKEN.findall(clause)):
            value = _canonical(raw_word)
            if value in vocabulary and value not in _PROOF_COMMON_TAGS:
                raw_candidates.append((value, int(_looks_identifier(raw_word)), position))
        for size in (3, 2):
            for offset in range(0, max(0, len(clause_words) - size + 1)):
                value = "-".join(clause_words[offset : offset + size])
                if value in vocabulary and value not in _PROOF_COMMON_TAGS:
                    raw_candidates.append((value, 0, offset))
        candidates: dict[str, tuple[int, int, str]] = {}
        for value, identifier_like, position in raw_candidates:
            current = candidates.get(value)
            candidate = (identifier_like, position, value)
            if current is None or candidate < current:
                candidates[value] = candidate
        ranked_values = sorted(
            candidates,
            key=lambda value: (
                -candidates[value][0],
                value_path_count[value],
                candidates[value][1],
                value,
            ),
        )[:3]
        if not ranked_values:
            continue
        selected = set(ranked_values)
        path_coverage = sorted(
            (
                _AUTHORITY_PRIORITY[_authority_class_for_source_path(path)],
                -sum(
                    _PROOF_TAG_KIND_WEIGHT[tag.kind]
                    for tag in index.tags
                    if tag.source_path == path and tag.value in selected
                ),
                len(source_bytes[path]),
                path,
            )
            for path, values in tag_values_by_path.items()
            if selected & values
        )
        if not path_coverage:
            continue
        best_path = path_coverage[0][3]
        source_hints = (best_path,)
        authority = _authority_class_for_source_path(best_path)
        obligations.append(
            ProofObligation(
                f"behavior-clause:{clause_index:02d}",
                authority,
                source_hints=source_hints,
                anchor_hints=tuple(sorted(selected)),
                critical=authority is not AuthorityClass.DOCUMENTATION,
            )
        )
    obligations.sort(
        key=lambda obligation: (
            _AUTHORITY_PRIORITY[obligation.authority_class],
            -len(obligation.anchor_hints),
            obligation.obligation_id,
        )
    )
    return tuple(obligations[:_MAX_PROOF_OBLIGATIONS])


def _expected_repository_tags(
    graph: Graph,
    snapshot: SourceSnapshotV4,
    source_bytes: Mapping[str, bytes],
) -> tuple[tuple[RepositoryTag, ...], tuple[str, ...]]:
    """Regenerate the exact deterministic tag projection from verified bytes."""

    source_identities = {source.path: source for source in snapshot.sources}
    tags: list[RepositoryTag] = []
    seen: set[tuple[str, str, str]] = set()
    for record in sorted(graph.records, key=lambda item: item.record_id):
        source = source_identities.get(record.provenance.path)
        if source is None or source.sha256 != record.provenance.sha256:
            raise ValueError("record provenance does not match the source snapshot")
        raw = source_bytes[source.path]
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("repository tagging requires exact UTF-8 source") from error
        if content.encode("utf-8") != raw or record.content.encode("utf-8") != raw:
            raise ValueError("repository tags require source-complete record content")
        record_tags = sorted(
            _extract_tags(record, content),
            key=lambda item: (
                _tag_priority(item.kind), item.value, item.byte_start or -1,
            ),
        )[:_MAX_TAGS_PER_RECORD]
        for tag in record_tags:
            identity = (tag.record_id, tag.kind.value, tag.value)
            if identity not in seen:
                seen.add(identity)
                tags.append(tag)
    tags.sort(key=lambda item: (item.value, item.kind.value, item.record_id, item.byte_start or -1))
    vocabulary = tuple(sorted({tag.value for tag in tags}))
    return tuple(tags), vocabulary


def build_repository_file_cards(
    graph: Graph,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
) -> tuple[RepositoryFileCard, ...]:
    """Build deterministic minimal cards from the verified tag index."""

    index = build_repository_tag_index(graph, snapshot, reader)
    tags_by_record = index.by_record()
    records = graph.record_map()
    cards: list[RepositoryFileCard] = []
    for record_id in sorted(tags_by_record):
        record = records.get(record_id)
        if record is None:
            raise ValueError("repository tag index references an unknown record")
        tags = tags_by_record[record_id]
        cards.append(
            RepositoryFileCard(
                record_id,
                record.provenance.path,
                record.provenance.sha256,
                tuple(sorted({tag.value for tag in tags})),
            )
        )
    return tuple(sorted(cards, key=lambda card: (card.source_path, card.record_id)))


def match_proof_obligation(
    card: RepositoryFileCard,
    obligation: ProofObligation,
) -> bool:
    """Return whether a card is an anchored candidate for an obligation."""

    if type(card) is not RepositoryFileCard or type(obligation) is not ProofObligation:
        raise TypeError("card and obligation types are exact")
    if not (obligation.anchor_hints or obligation.required_tag_values):
        return False
    if obligation.source_hints and card.source_path not in obligation.source_hints:
        return False
    if obligation.required_tag_values and not set(obligation.required_tag_values).issubset(card.anchor_tags):
        return False
    return bool(
        set(obligation.anchor_hints) & set(card.anchor_tags)
        or set(obligation.required_tag_values) & set(card.anchor_tags)
    )


def _obligation_unit_matches(
    obligation: ProofObligation,
    source_path: str,
    unit_tags: set[str],
) -> bool:
    """Return whether one complete unit atomically proves an obligation."""

    if not (obligation.anchor_hints or obligation.required_tag_values):
        return False
    if obligation.source_hints and source_path not in obligation.source_hints:
        return False
    required_values = set(obligation.anchor_hints) | set(obligation.required_tag_values)
    return required_values.issubset(unit_tags)


def match_proof_obligations(
    cards: Sequence[RepositoryFileCard],
    obligations: Sequence[ProofObligation],
) -> dict[str, tuple[str, ...]]:
    """Return deterministic obligation-to-record matches."""

    if any(type(card) is not RepositoryFileCard for card in cards):
        raise TypeError("cards must contain RepositoryFileCard values")
    if any(type(obligation) is not ProofObligation for obligation in obligations):
        raise TypeError("obligations must contain ProofObligation values")
    return {
        obligation.obligation_id: tuple(
            card.record_id for card in sorted(cards, key=lambda item: (item.source_path, item.record_id))
            if match_proof_obligation(card, obligation)
        )
        for obligation in sorted(obligations, key=lambda item: item.obligation_id)
    }


def _validate_retrieval_custody(
    graph: Graph,
    index: RepositoryTagIndex,
    snapshot: SourceSnapshotV4,
    source_bytes: Mapping[str, bytes],
) -> bool:
    """Validate the exact indexed projection against the active source bytes."""

    if index.source_snapshot_sha256 != snapshot.snapshot_sha256:
        return False
    records = graph.record_map()
    sources = {source.path: source for source in snapshot.sources}
    for record_id, tags in index.by_record().items():
        record = records.get(record_id)
        if record is None or not _valid_source_path(record.provenance.path):
            return False
        source = sources.get(record.provenance.path)
        if source is None or record.provenance.sha256 != source.sha256:
            return False
        for tag in tags:
            if (
                tag.record_id != record_id
                or tag.source_path != record.provenance.path
                or tag.source_path != source.path
            ):
                return False
    try:
        expected_tags, expected_vocabulary = _expected_repository_tags(
            graph, snapshot, source_bytes
        )
    except (KeyError, UnicodeError, ValueError):
        return False
    return index.tags == expected_tags and index.vocabulary == expected_vocabulary


def compile_prompt(
    prompt: str,
    index: RepositoryTagIndex,
    *,
    semantic_candidates: Sequence[str] = (),
    proof_obligations: Sequence[ProofObligation] = (),
) -> PromptFacetSet:
    """Compile one prompt into at most 20 typed, auditable facets.

    Model-suggested semantic candidates are accepted only when their canonical
    value already exists in the repository vocabulary.
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be non-empty")
    words = _words(prompt)
    content_words = [word for word in words if word not in _STOPWORDS]
    lexical_candidates: list[PromptFacet] = []

    for raw in _TOKEN.findall(prompt):
        canonical = _canonical(raw)
        if canonical and canonical not in _STOPWORDS and _looks_identifier(raw):
            lexical_candidates.append(PromptFacet(FacetKind.IDENTIFIER, canonical, 10, True))
    for word in content_words:
        if word not in _GENERIC:
            lexical_candidates.append(PromptFacet(FacetKind.ENTITY, word, 6))
    for size in (3, 2):
        for offset in range(0, max(0, len(content_words) - size + 1)):
            phrase = " ".join(content_words[offset : offset + size])
            if phrase in index.vocabulary:
                lexical_candidates.append(PromptFacet(FacetKind.PHRASE, phrase, 7))

    intents = _intent_facets(content_words)
    typed_candidates = [*intents, *_derived_facets(intents, content_words)]

    vocabulary = set(index.vocabulary)
    rejected: list[str] = []
    for value in semantic_candidates:
        canonical = _canonical(value)
        if canonical and canonical in vocabulary:
            typed_candidates.append(PromptFacet(FacetKind.SEMANTIC, canonical, 5))
        elif canonical:
            rejected.append(canonical)

    facets: list[PromptFacet] = []
    seen: set[tuple[FacetKind, str]] = set()
    required = [facet for facet in lexical_candidates if facet.required]
    lexical = [facet for facet in lexical_candidates if not facet.required]
    typed = sorted(
        typed_candidates,
        key=lambda item: (-item.required, -item.weight, item.kind.value, item.value),
    )
    ordered = [*required, *lexical[:12], *typed, *lexical[12:]]
    for facet in ordered:
        identity = (facet.kind, facet.value)
        if identity in seen:
            continue
        seen.add(identity)
        facets.append(facet)
        if len(facets) == _MAX_FACETS:
            break
    return PromptFacetSet(
        hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        tuple(facets),
        tuple(sorted(set(rejected))),
        tuple(proof_obligations),
    )


def retrieve(
    graph: Graph,
    task: TaskSpec,
    index: RepositoryTagIndex,
    facets: PromptFacetSet,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    channels: Sequence[str] = _CHANNEL_ORDER,
    expand_one_hop: bool = True,
    maximum_results: int = 6,
    minimum_coverage_percent: float = 60.0,
    parallel: bool = True,
) -> RetrievalResult:
    """Retrieve a deterministic, bounded, source-verified evidence packet."""

    requested_channels = tuple(dict.fromkeys(channels))
    if not requested_channels or any(channel not in _CHANNEL_ORDER for channel in requested_channels):
        raise ValueError("retrieval channels must use the closed channel vocabulary")
    if type(maximum_results) is not int or not 1 <= maximum_results <= task.node_budget:
        raise ValueError("maximum_results must fit the task node budget")
    if not math.isfinite(minimum_coverage_percent) or not 0 <= minimum_coverage_percent <= 100:
        raise ValueError("minimum coverage must be finite and bounded")
    obligations = facets.proof_obligations
    tags_by_record = index.by_record()
    snapshot_paths = {source.path for source in snapshot.sources}
    invalid_hints = {
        path
        for obligation in obligations
        for path in obligation.source_hints
        if path not in snapshot_paths
    }
    if invalid_hints:
        raise ValueError("proof obligation source hints must remain inside the source snapshot")
    source_bytes = _read_verified_source_bytes(snapshot, reader)
    if not _validate_retrieval_custody(graph, index, snapshot, source_bytes):
        return _empty_result("repository_index_custody_mismatch", fail_closed=True, obligations=obligations, remaining_byte_budget=task.byte_budget)
    if not facets.sufficient and not obligations:
        return _empty_result("prompt_facets_insufficient", fail_closed=False, obligations=obligations, remaining_byte_budget=task.byte_budget)
    record_map = graph.record_map()
    obligation_map = {item.obligation_id: item for item in obligations}
    record_obligations: dict[str, set[str]] = defaultdict(set)
    record_obligation_units: dict[str, dict[tuple[int, int], set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    if obligations:
        for obligation in obligations:
            if not (obligation.anchor_hints or obligation.required_tag_values):
                continue
            for record_id, tags in tags_by_record.items():
                source_path = record_map[record_id].provenance.path
                if obligation.source_hints and source_path not in obligation.source_hints:
                    continue
                unit_tags: dict[tuple[int, int], set[str]] = defaultdict(set)
                relevant_values = set(obligation.anchor_hints) | set(obligation.required_tag_values)
                for tag in tags:
                    if tag.byte_start is None or tag.value not in relevant_values:
                        continue
                    unit = _complete_unit_bounds(
                        source_bytes[source_path], source_path, tag.byte_start, tag.byte_end
                    )
                    unit_tags[unit].add(tag.value)
                for unit, values in unit_tags.items():
                    if _obligation_unit_matches(obligation, source_path, values):
                        record_obligations[record_id].add(obligation.obligation_id)
                        record_obligation_units[record_id][unit].add(obligation.obligation_id)

    def run_channel(
        channel: str,
    ) -> tuple[str, list[tuple[int, str]], dict[str, set[str]], tuple[str, ...]]:
        scores, matches = _channel_scores(
            channel,
            graph,
            tags_by_record,
            facets,
            task.allowed_sensitivities,
        )
        unauthenticated = tuple(sorted(
            record_id for record_id, score in scores.items()
            if score > 0
            and not is_authenticated_eligible(record_map[record_id], task.allowed_sensitivities)
        ))
        ranked = sorted(
            ((score, record_id) for record_id, score in scores.items() if score > 0),
            key=lambda item: (-item[0], item[1]),
        )
        return channel, ranked, matches, unauthenticated

    channel_rows: list[
        tuple[str, list[tuple[int, str]], dict[str, set[str]], tuple[str, ...]]
    ] = []
    if parallel and len(requested_channels) > 1:
        with ThreadPoolExecutor(max_workers=len(requested_channels)) as executor:
            futures = [executor.submit(run_channel, channel) for channel in requested_channels]
            for future in futures:
                channel_rows.append(future.result())
    else:
        channel_rows = [run_channel(channel) for channel in requested_channels]
    channel_rows.sort(key=lambda row: _CHANNEL_ORDER.index(row[0]))

    unauthenticated_matches = {
        record_id for _, _, _, matches in channel_rows for record_id in matches
    }
    if unauthenticated_matches:
        return _empty_result("tag_match_crosses_authentication_boundary", fail_closed=True, obligations=obligations, remaining_byte_budget=task.byte_budget)

    fused: Counter[str] = Counter()
    record_channels: dict[str, set[str]] = defaultdict(set)
    record_facets: dict[str, set[str]] = defaultdict(set)
    rankings: list[tuple[str, tuple[str, ...]]] = []
    for channel, ranked, matches, _ in channel_rows:
        ranking = tuple(record_id for _, record_id in ranked)
        rankings.append((channel, ranking))
        for rank, record_id in enumerate(ranking, start=1):
            fused[record_id] += _CHANNEL_WEIGHT[channel] * 1_000_000 // (_RRF_K + rank)
            record_channels[record_id].add(channel)
            record_facets[record_id].update(matches.get(record_id, set()))
    if obligations:
        # Explicit caller hints are authoritative routing seeds. They must not
        # depend on lexical facet overlap to become inspectable candidates.
        for record_id, obligation_ids in record_obligations.items():
            if not obligation_ids:
                continue
            if not is_authenticated_eligible(record_map[record_id], task.allowed_sensitivities):
                return _empty_result("tag_match_crosses_authentication_boundary", fail_closed=True, obligations=obligations, remaining_byte_budget=task.byte_budget)
            fused[record_id] = max(fused[record_id], 1)
            record_channels[record_id].add("exact")
    if not fused:
        return _empty_result(
            "no_repository_tag_match",
            fail_closed=False,
            rankings=tuple(rankings),
            fallback_paths=_obligation_source_hints(obligations),
            obligations=obligations,
            remaining_byte_budget=task.byte_budget,
        )

    base_order = [
        record_id
        for record_id, _ in sorted(fused.items(), key=lambda item: (-item[1], item[0]))
    ]
    seed_limit = max(1, maximum_results - 2) if expand_one_hop else maximum_results
    base = base_order[:seed_limit]
    expanded_from: dict[str, str] = {}
    if expand_one_hop:
        for edge in sorted(graph.edges, key=lambda item: (item.relation, item.edge_id)):
            if edge.relation not in _ALLOWED_RELATIONS:
                continue
            if not is_authenticated_eligible(edge, task.allowed_sensitivities):
                continue
            if edge.source_id in base and edge.target_id not in fused:
                fused[edge.target_id] = max(1, fused[edge.source_id] // 4)
                record_channels[edge.target_id].add("graph")
                expanded_from[edge.target_id] = edge.source_id
            if (
                edge.relation in _REVERSE_RELATIONS
                and edge.target_id in base
                and edge.source_id not in fused
            ):
                fused[edge.source_id] = max(1, fused[edge.target_id] // 4)
                record_channels[edge.source_id].add("graph")
                expanded_from[edge.source_id] = edge.target_id

    expanded_order = [
        record_id
        for record_id in sorted(expanded_from, key=lambda item: (-fused[item], item))
        if is_authenticated_eligible(record_map[record_id], task.allowed_sensitivities)
    ]
    ordered_candidates = [*base, *expanded_order, *base_order]
    ordered_ids = []
    for record_id in ordered_candidates:
        if record_id in ordered_ids:
            continue
        if not is_authenticated_eligible(record_map[record_id], task.allowed_sensitivities):
            continue
        if obligations and not record_obligations.get(record_id):
            continue
        ordered_ids.append(record_id)
        if len(ordered_ids) == maximum_results:
            break
    hits = tuple(
        RetrievalHit(
            record_id=record_id,
            source_path=record_map[record_id].provenance.path,
            match_score=fused[record_id],
            channels=tuple(sorted(record_channels[record_id], key=_CHANNEL_ORDER.index)),
            matched_facets=tuple(sorted(record_facets[record_id])),
            hop=1 if record_id in expanded_from else 0,
            expanded_from=expanded_from.get(record_id),
        )
        for record_id in ordered_ids
    )
    spans, evidence, context = _verified_spans(
        hits,
        tags_by_record,
        record_facets,
        record_obligations,
        record_obligation_units,
        obligation_map,
        source_bytes,
        {source.path: source.sha256 for source in snapshot.sources},
        task.byte_budget,
    )
    matched = {value for record_id in ordered_ids for value in record_facets[record_id]}
    total_weight = sum(facet.weight for facet in facets.facets)
    matched_weight = sum(facet.weight for facet in facets.facets if facet.value in matched)
    coverage = round(100 * matched_weight / total_weight, 2) if total_weight else 0.0
    required = {facet.value for facet in facets.facets if facet.required}
    if obligations:
        covered_obligations = {
            obligation_id for item in evidence for obligation_id in item.obligation_ids
        }
        sufficient = bool(spans) and covered_obligations == set(obligation_map)
        uncovered = [
            obligation.source_hints
            for obligation in obligations
            if obligation.obligation_id not in covered_obligations
        ]
        fallback_paths = tuple(
            sorted({path for paths in uncovered for path in paths})
        )
    else:
        covered_obligations = set()
        sufficient = bool(spans) and required.issubset(matched) and coverage >= minimum_coverage_percent
        fallback_paths = tuple(dict.fromkeys(hit.source_path for hit in hits))
    unresolved_obligations = tuple(sorted(set(obligation_map) - covered_obligations))
    unresolved_critical = tuple(sorted(
        obligation_id
        for obligation_id in unresolved_obligations
        if obligation_map[obligation_id].critical
    ))
    return RetrievalResult(
        route="graph" if sufficient else "defer",
        reason="verified_tag_context_selected" if sufficient else "tag_context_insufficient",
        hits=hits,
        spans=spans,
        context=context,
        context_bytes=len(context.encode("utf-8")),
        facet_coverage_percent=coverage,
        channel_rankings=tuple(rankings),
        recommended_fallback_paths=fallback_paths,
        fail_closed=False,
        evidence=evidence,
        covered_obligation_ids=tuple(sorted(covered_obligations)),
        unresolved_obligation_ids=unresolved_obligations,
        unresolved_critical_obligation_ids=unresolved_critical,
        remaining_byte_budget=max(0, task.byte_budget - len(context.encode("utf-8"))),
    )


def navigate(
    graph: Graph,
    task: TaskSpec,
    index: RepositoryTagIndex,
    facets: PromptFacetSet,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    channels: Sequence[str] = _CHANNEL_ORDER,
    expand_one_hop: bool = True,
    maximum_results: int = 6,
    preview_bytes: int = 256,
    maximum_previews: int = 8,
    parallel: bool = True,
) -> NavigationResult:
    """Find bounded source previews without producing answer context.

    The existing retrieval implementation remains the ranking mechanism. This
    API deliberately projects only authenticated candidates and direct,
    source-anchored previews. A one-hop hit can guide another lookup but
    cannot become answer evidence until it has its own verified source span.
    """

    if type(snapshot) is not SourceSnapshotV4:
        raise TypeError("snapshot must be an exact SourceSnapshotV4")
    if type(preview_bytes) is not int or not 1 <= preview_bytes <= min(512, task.byte_budget):
        raise ValueError("preview_bytes must be between 1 and 512 bytes")
    if type(maximum_previews) is not int or not 1 <= maximum_previews <= task.node_budget:
        raise ValueError("maximum_previews must fit the task node budget")
    try:
        source_bytes = _read_verified_source_bytes(snapshot, reader)
    except (KeyError, OSError, ValueError):
        return NavigationResult(
            "defer", "source_snapshot_custody_mismatch", (), (),
            snapshot.snapshot_sha256, True,
        )
    if not _validate_retrieval_custody(graph, index, snapshot, source_bytes):
        return NavigationResult(
            "defer", "repository_index_custody_mismatch", (), (),
            snapshot.snapshot_sha256, True,
        )
    result = retrieve(
        graph,
        task,
        index,
        facets,
        snapshot,
        reader,
        channels=channels,
        expand_one_hop=expand_one_hop,
        maximum_results=maximum_results,
        minimum_coverage_percent=0.0,
        parallel=parallel,
    )
    if result.fail_closed:
        return NavigationResult(
            "defer", result.reason, (), (), snapshot.snapshot_sha256, True,
        )

    tags_by_record = index.by_record()
    previews: list[SourcePreview] = []
    record_map = graph.record_map()
    for hit in result.hits:
        # Graph neighbors are navigation-only until a source-bound tag anchor
        # exists on the neighbor itself. Never copy the parent anchor.
        if hit.hop != 0:
            continue
        if len(previews) >= maximum_previews:
            break
        raw = source_bytes.get(hit.source_path)
        record = record_map.get(hit.record_id)
        if raw is None or record is None or record.provenance.path != hit.source_path:
            return NavigationResult(
                "defer", "preview_source_custody_mismatch", result.hits, (),
                snapshot.snapshot_sha256, True,
            )
        matched_tags = [
            tag for tag in tags_by_record.get(hit.record_id, ())
            if tag.byte_start is not None and tag.value in hit.matched_facets
        ]
        if matched_tags:
            start, end = _line_window(
                raw, matched_tags[0].byte_start, matched_tags[0].byte_end, preview_bytes
            )
        elif raw:
            start, end = 0, min(len(raw), preview_bytes)
        else:
            continue
        excerpt = raw[start:end]
        if not excerpt:
            continue
        try:
            text = excerpt.decode("utf-8")
        except UnicodeDecodeError:
            return NavigationResult(
                "defer", "preview_not_utf8", result.hits, (),
                snapshot.snapshot_sha256, True,
            )
        previews.append(
            SourcePreview(
                hit.record_id,
                hit.source_path,
                record.provenance.sha256,
                start,
                end,
                hashlib.sha256(excerpt).hexdigest(),
                text,
                0,
                snapshot.snapshot_sha256,
            )
        )
    return NavigationResult(
        "navigate" if previews else "defer",
        "verified_source_previews_selected" if previews else "no_source_preview",
        result.hits,
        tuple(previews),
        snapshot.snapshot_sha256,
        False,
        tuple(
            (key, value)
            for key, value in (
                ("candidate_count", str(len(result.hits))),
                ("preview_count", str(len(previews))),
                ("one_hop_max", "1"),
            )
        ),
    )


def compose_navigation_context(
    navigation: NavigationResult,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    primary: Sequence[SourcePreview] = (),
    supporting: Sequence[SourcePreview] = (),
    byte_budget: int | None = None,
    maximum_primary: int = 3,
    maximum_support: int = 2,
) -> NavigationContext:
    """Compose raw source text from explicit primary and support selections."""

    def failure(reason: str) -> NavigationContext:
        return NavigationContext((), (), "", 0, snapshot.snapshot_sha256, True, reason)

    if type(navigation) is not NavigationResult or type(snapshot) is not SourceSnapshotV4:
        raise TypeError("navigation and snapshot types are exact")
    if navigation.fail_closed or navigation.source_snapshot_sha256 != snapshot.snapshot_sha256:
        return failure("navigation_snapshot_mismatch")
    if byte_budget is not None and (type(byte_budget) is not int or byte_budget < 1):
        raise ValueError("byte_budget must be a positive integer")
    if type(maximum_primary) is not int or type(maximum_support) is not int:
        raise ValueError("preview limits must be integers")
    try:
        selected_primary = tuple(primary)
        selected_supporting = tuple(supporting)
    except TypeError:
        return failure("selection_not_iterable")
    selected = (*selected_primary, *selected_supporting)
    if not selected:
        return failure("selection_required")
    if len(selected_primary) > maximum_primary:
        return failure("primary_selection_limit_exceeded")
    if len(selected_supporting) > maximum_support:
        return failure("supporting_selection_limit_exceeded")
    if any(type(item) is not SourcePreview for item in selected):
        return failure("selection_type_invalid")
    if len(set(selected)) != len(selected):
        return failure("selection_duplicate")
    available = set(navigation.previews)
    if any(item not in available for item in selected):
        return failure("selection_unknown")

    try:
        source_bytes = _read_verified_source_bytes(snapshot, reader)
    except (KeyError, OSError, ValueError):
        return failure("selection_source_unavailable")
    sources = {item.path: item for item in snapshot.sources}
    for preview in selected:
        source = sources.get(preview.source_path)
        if source is None or preview.source_snapshot_sha256 != snapshot.snapshot_sha256:
            return failure("selection_cross_snapshot")
        if preview.source_sha256 != source.sha256 or preview.byte_end > len(source_bytes[preview.source_path]):
            return failure("selection_stale")
        raw_excerpt = source_bytes[preview.source_path][preview.byte_start:preview.byte_end]
        if (
            hashlib.sha256(raw_excerpt).hexdigest() != preview.excerpt_sha256
            or raw_excerpt != preview.text.encode("utf-8")
        ):
            return failure("selection_forged")
    ordered = (*selected_primary, *selected_supporting)
    raw_parts: list[str] = []
    seen_payloads: set[tuple[str, int, int, str]] = set()
    used = 0
    for preview in ordered:
        payload_key = (
            preview.source_path, preview.byte_start, preview.byte_end,
            preview.excerpt_sha256,
        )
        if payload_key in seen_payloads:
            continue
        seen_payloads.add(payload_key)
        payload_bytes = len(preview.text.encode("utf-8"))
        if byte_budget is not None and used + payload_bytes > byte_budget:
            return failure("context_byte_budget_exceeded")
        raw_parts.append(preview.text)
        used += payload_bytes
    return NavigationContext(
        selected_primary,
        selected_supporting,
        "\n\n".join(raw_parts),
        used,
        snapshot.snapshot_sha256,
        False,
        "verified_navigation_context",
    )


def retrieve_hybrid(
    graph: Graph,
    task: TaskSpec,
    index: RepositoryTagIndex,
    facets: PromptFacetSet,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    fallback_source_paths: tuple[str, ...] = (),
    **retrieve_options: object,
) -> HybridRetrievalResult:
    """Retrieve graph evidence, then use only a caller-declared fallback list."""

    result = retrieve(graph, task, index, facets, snapshot, reader, **retrieve_options)
    if result.route == "graph":
        return HybridRetrievalResult(result, None)
    if result.fail_closed:
        return HybridRetrievalResult(result, None)
    if facets.proof_obligations:
        obligation_map = {item.obligation_id: item for item in facets.proof_obligations}
        unresolved_critical = tuple(result.unresolved_critical_obligation_ids)
        if not unresolved_critical:
            return HybridRetrievalResult(result, None)
        required_paths = set()
        for obligation_id in unresolved_critical:
            obligation = obligation_map[obligation_id]
            if not obligation.source_hints:
                return HybridRetrievalResult(
                    replace(result, reason="critical_fallback_unavailable"),
                    None,
                )
            required_paths.update(obligation.source_hints)
        supplied_paths = set(fallback_source_paths)
        if not required_paths.issubset(supplied_paths):
            return HybridRetrievalResult(
                replace(result, reason="fallback_allowlist_incomplete", fail_closed=True),
                None,
            )
    else:
        required_paths = set(fallback_source_paths)
    if not fallback_source_paths:
        return HybridRetrievalResult(result, None)
    if result.remaining_byte_budget <= 0:
        if facets.proof_obligations:
            return HybridRetrievalResult(
                replace(result, reason="critical_fallback_budget_exhausted"),
                None,
            )
        return HybridRetrievalResult(result, None)
    if facets.proof_obligations:
        fallback_source_paths = tuple(sorted(required_paths))
    fallback = assist(
        graph,
        replace(task, byte_budget=result.remaining_byte_budget),
        snapshot,
        reader,
        required_source_paths=tuple(sorted(required_paths)),
        fallback_source_paths=fallback_source_paths,
        required_escalation=True,
    )
    return HybridRetrievalResult(result, fallback)


def _extract_tags(record: GraphRecord, content: str) -> Iterable[RepositoryTag]:
    path = record.provenance.path
    for value in _path_values(path):
        yield RepositoryTag(TagKind.PATH, value, record.record_id, path)
    for match in _TOKEN.finditer(content):
        raw = match.group(0)
        value = _canonical(raw)
        if not value or value in _STOPWORDS:
            continue
        kind = TagKind.SYMBOL if _looks_identifier(raw) else TagKind.KEYWORD
        start, end = _byte_bounds(content, match.start(), match.end())
        yield RepositoryTag(kind, value, record.record_id, path, start, end)
        for part in _identifier_parts(raw):
            if part != value and part not in _STOPWORDS:
                yield RepositoryTag(TagKind.SYMBOL, part, record.record_id, path, start, end)
    for match in _HEADING.finditer(content):
        value = _canonical_phrase(match.group(1))
        if value:
            start, end = _byte_bounds(content, match.start(1), match.end(1))
            yield RepositoryTag(TagKind.HEADING, value, record.record_id, path, start, end)
            for word in value.split():
                if word not in _STOPWORDS:
                    yield RepositoryTag(TagKind.DOCUMENTATION, word, record.record_id, path, start, end)
    for match in _CONFIG_KEY.finditer(content):
        value = _canonical(match.group(1))
        start, end = _byte_bounds(content, match.start(1), match.end(1))
        yield RepositoryTag(TagKind.CONFIG, value, record.record_id, path, start, end)
    for match in _TEST_NAME.finditer(content):
        raw = next(value for value in match.groups() if value)
        value = _canonical_phrase(raw)
        if value:
            start, end = _byte_bounds(content, match.start(), match.end())
            yield RepositoryTag(TagKind.TEST, value, record.record_id, path, start, end)
    for match in _IMPORT.finditer(content):
        raw = next((value for value in match.groups() if value), "")
        value = _canonical_phrase(raw)
        if value:
            start, end = _byte_bounds(content, match.start(), match.end())
            yield RepositoryTag(TagKind.IMPORT, value, record.record_id, path, start, end)


def _channel_scores(
    channel: str,
    graph: Graph,
    tags_by_record: Mapping[str, tuple[RepositoryTag, ...]],
    facets: PromptFacetSet,
    allowed_sensitivities: tuple[Sensitivity, ...],
) -> tuple[dict[str, int], dict[str, set[str]]]:
    scores: dict[str, int] = defaultdict(int)
    matches: dict[str, set[str]] = defaultdict(set)
    document_frequency: Counter[str] = Counter()
    for tags in tags_by_record.values():
        document_frequency.update({tag.value for tag in tags})
    record_count = max(1, len(tags_by_record))
    facet_map = {facet.value: facet for facet in facets.facets}

    if channel == "graph":
        relation_facets = {facet.value for facet in facets.facets if facet.kind is FacetKind.RELATION}
        for edge in graph.edges:
            if not is_authenticated_eligible(edge, allowed_sensitivities):
                continue
            relation_tokens = set(_words(edge.relation)) | {_canonical(edge.relation)}
            overlap = relation_facets & relation_tokens
            if overlap:
                scores[edge.source_id] += 3 * len(overlap)
                scores[edge.target_id] += 3 * len(overlap)
                matches[edge.source_id].update(overlap)
                matches[edge.target_id].update(overlap)
        return scores, matches

    for record_id, tags in tags_by_record.items():
        path = tags[0].source_path if tags else ""
        is_wiki = path.endswith(".md") or posixpath.basename(path).lower() in {"agents.md", "readme.md"}
        for tag in tags:
            facet = facet_map.get(tag.value)
            if facet is None:
                continue
            if channel == "exact":
                if tag.kind not in {TagKind.PATH, TagKind.SYMBOL, TagKind.CONFIG, TagKind.TEST, TagKind.HEADING}:
                    continue
                multiplier = 5 if tag.kind in {TagKind.SYMBOL, TagKind.CONFIG, TagKind.TEST} else 3
            elif channel == "sparse":
                multiplier = max(1, round(10 * math.log1p(record_count / (1 + document_frequency[tag.value]))))
            elif channel == "wiki":
                if not is_wiki or tag.kind not in {TagKind.HEADING, TagKind.DOCUMENTATION, TagKind.KEYWORD}:
                    continue
                multiplier = 3
            else:
                raise ValueError(f"unsupported retrieval channel: {channel}")
            scores[record_id] += facet.weight * multiplier
            matches[record_id].add(facet.value)
    return scores, matches


def _verified_spans(
    hits: Sequence[RetrievalHit],
    tags_by_record: Mapping[str, tuple[RepositoryTag, ...]],
    matched: Mapping[str, set[str]],
    record_obligations: Mapping[str, set[str]],
    record_obligation_units: Mapping[str, Mapping[tuple[int, int], set[str]]],
    obligations: Mapping[str, ProofObligation],
    source_bytes: Mapping[str, bytes],
    source_hashes: Mapping[str, str],
    byte_budget: int,
) -> tuple[tuple[ContextSpan, ...], tuple[EvidenceItem, ...], str]:
    spans: list[ContextSpan] = []
    evidence: list[EvidenceItem] = []
    chunks: list[str] = []
    used = 0
    seen: set[tuple[str, int, int]] = set()
    candidate_spans: dict[tuple[str, int, int], set[str]] = {}
    for hit in hits:
        raw = source_bytes[hit.source_path]
        hit_obligations = tuple(sorted(record_obligations.get(hit.record_id, ())))
        if hit.hop == 1 and not hit_obligations:
            continue
        if hit_obligations:
            for unit, obligation_ids in record_obligation_units.get(hit.record_id, {}).items():
                start, end = unit
                if end > start:
                    candidate_spans.setdefault((hit.record_id, start, end), set()).update(obligation_ids)
            continue
        candidates = []
        for tag in tags_by_record.get(hit.record_id, ()):
            if tag.byte_start is None:
                continue
            if tag.value not in matched.get(hit.record_id, set()):
                continue
            candidates.append(tag)
        selected_candidates = candidates[:4]
        bounds = [
            (
                _line_window(raw, tag.byte_start, tag.byte_end, 800),
                set(),
            )
            for tag in selected_candidates
        ]
        if not bounds:
            bounds = [((0, min(len(raw), 800)), set())] if raw else []
        for (start, end), obligation_ids in bounds:
            assert start is not None and end is not None
            identity = (hit.record_id, start, end)
            if end <= start:
                continue
            candidate_spans.setdefault(identity, set()).update(obligation_ids)
    selected_intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)
    if obligations:
        def span_priority(item: tuple[tuple[str, int, int], set[str]]) -> tuple[object, ...]:
            (record_id, start, end), span_obligation_ids = item
            classes = tuple(
                obligations[obligation_id].authority_class
                for obligation_id in sorted(span_obligation_ids)
            )
            documentation_only = bool(classes) and all(
                authority is AuthorityClass.DOCUMENTATION for authority in classes
            )
            return (
                0 if any(obligations[obligation_id].critical for obligation_id in span_obligation_ids) else 1,
                min((_AUTHORITY_PRIORITY[authority] for authority in classes), default=5),
                1 if documentation_only and end - start > _MAX_DOCUMENT_PROOF_UNIT_BYTES else 0,
                end - start,
                record_id,
                start,
                end,
            )

        coalesced_spans: list[tuple[tuple[str, int, int], set[str]]] = []
        for (record_id, start, end), span_obligation_ids in sorted(
            candidate_spans.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])
        ):
            if coalesced_spans:
                (previous_record, previous_start, previous_end), previous_ids = coalesced_spans[-1]
                if record_id == previous_record and start < previous_end:
                    coalesced_spans[-1] = (
                        (previous_record, previous_start, max(previous_end, end)),
                        previous_ids | span_obligation_ids,
                    )
                    continue
            coalesced_spans.append(((record_id, start, end), set(span_obligation_ids)))
        ordered_span_items = sorted(coalesced_spans, key=span_priority)
    else:
        ordered_span_items = list(candidate_spans.items())
    if obligations:
        hit_by_record = {hit.record_id: hit for hit in hits}
        candidate_stream = (
            (item, hit_by_record.get(item[0][0])) for item in ordered_span_items
        )
    else:
        candidate_stream = (
            (item, hit)
            for hit in hits
            for item in ordered_span_items
            if item[0][0] == hit.record_id
        )
    for ((record_id, start, end), span_obligations), hit in candidate_stream:
        if hit is None:
            continue
        raw = source_bytes[hit.source_path]
        identity = (record_id, start, end)
        if identity in seen:
            continue
        if obligations and any(
            start < selected_end and selected_start < end
            for selected_start, selected_end in selected_intervals[record_id]
        ):
            continue
        excerpt = raw[start:end]
        header = f"[{hit.source_path}:{start}-{end}]\n".encode("utf-8")
        if used + len(header) + len(excerpt) > byte_budget:
            continue
        try:
            text = excerpt.decode("utf-8")
        except UnicodeDecodeError:
            continue
        seen.add(identity)
        spans.append(ContextSpan(hit.record_id, start, end, hashlib.sha256(excerpt).hexdigest()))
        if span_obligations:
            authority_groups: dict[AuthorityClass, list[str]] = defaultdict(list)
            for obligation_id in sorted(span_obligations):
                authority_groups[obligations[obligation_id].authority_class].append(obligation_id)
        else:
            authority_groups = {AuthorityClass.RUNTIME: []}
        for authority_class, authority_ids in sorted(
            authority_groups.items(), key=lambda item: item[0].value
        ):
            evidence.append(
                EvidenceItem(
                    hit.record_id,
                    hit.source_path,
                    source_hashes[hit.source_path],
                    start,
                    end,
                    hashlib.sha256(excerpt).hexdigest(),
                    authority_class,
                    tuple(sorted(authority_ids)),
                    hit.hop,
                )
            )
        chunks.append(header.decode("utf-8") + text)
        used += len(header) + len(excerpt)
        if obligations:
            selected_intervals[record_id].append((start, end))
    return tuple(spans), tuple(evidence), "\n\n".join(chunks)


def _intent_facets(words: Sequence[str]) -> list[PromptFacet]:
    result: list[PromptFacet] = []
    groups = (
        ("locate", {"find", "locate", "owner", "owns", "where", "which"}),
        ("trace", {"flow", "how", "path", "trace"}),
        ("change-impact", {"affect", "break", "change", "impact", "migration"}),
        ("validate", {"build", "package", "release", "test", "verify"}),
        ("authority", {"authority", "credential", "permission", "privacy", "publish", "safe", "safety"}),
    )
    present = set(words)
    for value, triggers in groups:
        if present & triggers:
            result.append(PromptFacet(FacetKind.INTENT, value, 8))
    return result or [PromptFacet(FacetKind.INTENT, "explain", 6)]


def _derived_facets(intents: Sequence[PromptFacet], words: Sequence[str]) -> list[PromptFacet]:
    values = {facet.value for facet in intents}
    result: list[PromptFacet] = []
    relations = {
        "locate": ("owns", "declares"),
        "trace": ("calls", "produces", "consumes"),
        "change-impact": ("calls", "imports", "reads", "tests"),
        "validate": ("tests", "packages", "declares"),
        "authority": ("requires-authority", "owns"),
        "explain": ("describes", "uses"),
    }
    for intent in sorted(values):
        for relation in relations.get(intent, ()):
            result.append(PromptFacet(FacetKind.RELATION, relation, 5))
    present = set(words)
    operations = {
        "change": {"change", "edit", "modify", "update"},
        "inspect": {"find", "identify", "inspect", "locate"},
        "trace": {"follow", "flow", "trace"},
        "validate": {"audit", "build", "check", "release", "test", "validate", "verify"},
    }
    for value, triggers in operations.items():
        if present & triggers:
            result.append(PromptFacet(FacetKind.OPERATION, value, 6))
    artifacts = (
        ("documentation", {"doc", "docs", "document", "documentation", "readme"}),
        ("configuration", {"config", "configuration", "manifest", "setting", "settings"}),
        ("test", {"test", "tests", "validation"}),
        ("release", {"build", "package", "release", "zip"}),
        ("interface", {"panel", "route", "ui", "view"}),
        ("source", {"code", "function", "implementation", "source"}),
    )
    for value, triggers in artifacts:
        if present & triggers:
            result.append(PromptFacet(FacetKind.ARTIFACT, value, 5))
    if present & {"not", "without", "never", "no"}:
        result.append(PromptFacet(FacetKind.CONSTRAINT, "negation", 10, True))
    if present & {"authority", "credential", "delete", "permission", "privacy", "publish", "secret", "security"}:
        result.append(PromptFacet(FacetKind.RISK, "safety-sensitive", 10, True))
    return result


def _empty_result(
    reason: str,
    *,
    fail_closed: bool,
    rankings: tuple[tuple[str, tuple[str, ...]], ...] = (),
    fallback_paths: tuple[str, ...] = (),
    obligations: Sequence[ProofObligation] = (),
    remaining_byte_budget: int = 0,
) -> RetrievalResult:
    unresolved = tuple(sorted(obligation.obligation_id for obligation in obligations))
    unresolved_critical = tuple(sorted(
        obligation.obligation_id for obligation in obligations if obligation.critical
    ))
    return RetrievalResult(
        "defer", reason, (), (), "", 0, 0.0, rankings, fallback_paths,
        fail_closed, (), (), unresolved, unresolved_critical, remaining_byte_budget,
    )


def _obligation_source_hints(obligations: Sequence[ProofObligation]) -> tuple[str, ...]:
    return tuple(sorted({path for obligation in obligations for path in obligation.source_hints}))


def _path_values(path: str) -> tuple[str, ...]:
    values: set[str] = set()
    for part in path.split("/"):
        canonical = _canonical(part)
        if canonical:
            values.add(canonical)
        stem = part.rsplit(".", 1)[0]
        values.update(_identifier_parts(stem))
    return tuple(sorted(value for value in values if value and value not in _STOPWORDS))


def _authority_class_for_source_path(path: str) -> AuthorityClass:
    """Classify a source path for evidence ordering only."""

    normalized = path.casefold()
    basename = posixpath.basename(normalized)
    path_parts = normalized.split("/")
    if "docs" in path_parts[:-1] or normalized.endswith((".md", ".markdown")) or basename in {"readme", "agents"}:
        return AuthorityClass.DOCUMENTATION
    if "/test" in f"/{normalized}" or basename.startswith(("test_", "test-")):
        return AuthorityClass.TEST
    if "contract" in normalized:
        return AuthorityClass.CONTRACT
    if "policy" in normalized:
        return AuthorityClass.POLICY
    if normalized.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf")):
        return AuthorityClass.CONFIGURATION
    if any(token in basename for token in ("config", "settings", "manifest")):
        return AuthorityClass.CONFIGURATION
    return AuthorityClass.RUNTIME


def _tag_priority(kind: TagKind) -> int:
    return {
        TagKind.PATH: 0,
        TagKind.SYMBOL: 1,
        TagKind.CONFIG: 2,
        TagKind.TEST: 3,
        TagKind.IMPORT: 4,
        TagKind.HEADING: 5,
        TagKind.DOCUMENTATION: 6,
        TagKind.KEYWORD: 7,
    }[kind]


def _identifier_parts(value: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").replace("-", " ")
    return {_canonical(part) for part in separated.split() if _canonical(part)}


def _looks_identifier(value: str) -> bool:
    return "_" in value or any(character.isupper() for character in value[1:]) or any(character.isdigit() for character in value)


def _words(value: str) -> list[str]:
    return [_canonical(item) for item in _TOKEN.findall(value) if _canonical(item)]


def _prompt_clauses(value: str, vocabulary: set[str]) -> tuple[str, ...]:
    """Split prompt text at punctuation and evidence-backed coordination."""

    def has_vocabulary_evidence(fragment: str) -> bool:
        words = [word for word in _words(fragment) if word not in _PROOF_COMMON_TAGS]
        if set(words) & vocabulary:
            return True
        return any(
            "-".join(words[offset : offset + size]) in vocabulary
            for size in (3, 2)
            for offset in range(0, max(0, len(words) - size + 1))
        )

    fragments: list[str] = []
    for fragment in re.split(r"[.!?;,\n:]+", value):
        fragment = fragment.strip()
        if not fragment:
            continue
        pending = [fragment]
        split_fragments: list[str] = []
        while pending:
            current = pending.pop(0)
            match = re.search(r"\b(?:and|then)\b", current, flags=re.IGNORECASE)
            if match is None:
                split_fragments.append(current)
                continue
            left, right = current[:match.start()], current[match.end() :]
            if has_vocabulary_evidence(left) and has_vocabulary_evidence(right):
                pending = [left.strip(), right.strip(), *pending]
            else:
                split_fragments.append(current)
        fragments.extend(item for item in split_fragments if _words(item))
    return tuple(fragments)


def _canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _canonical_phrase(value: str) -> str:
    return _canonical(value)


def _valid_source_path(value: object) -> bool:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        return False
    parts = value.split("/")
    return all(part and part not in {".", ".."} for part in parts)


def _require_sha256(value: object, label: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a full lowercase SHA-256")


def _byte_bounds(content: str, start: int, end: int) -> tuple[int, int]:
    return len(content[:start].encode("utf-8")), len(content[:end].encode("utf-8"))


def _complete_unit_bounds(raw: bytes, path: str, start: int, end: int) -> tuple[int, int]:
    """Find a bounded complete source unit around a verified anchor."""

    if not raw:
        return 0, 0
    line_start = raw.rfind(b"\n", 0, start) + 1
    line_end = raw.find(b"\n", end)
    line_end = len(raw) if line_end < 0 else line_end + 1
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _line_window(raw, start, end, 1200)
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line.encode("utf-8"))
    anchor_line = 0
    for index, offset in enumerate(offsets):
        if offset <= start < (offset + len(lines[index].encode("utf-8"))):
            anchor_line = index
            break

    basename = posixpath.basename(path).lower()
    is_markdown = path.lower().endswith(".md") or basename in {"readme.md", "agents.md"}
    if is_markdown:
        heading_line = None
        heading_level = None
        for index in range(anchor_line, -1, -1):
            match = re.match(r"^\s{0,3}(#{1,6})\s+", lines[index])
            if match:
                heading_line = index
                heading_level = len(match.group(1))
                break
        if heading_line is not None and heading_level is not None:
            finish = len(lines)
            for index in range(heading_line + 1, len(lines)):
                match = re.match(r"^\s{0,3}(#{1,6})\s+", lines[index])
                if match and len(match.group(1)) <= heading_level:
                    finish = index
                    break
            return offsets[heading_line], offsets[finish] if finish < len(offsets) else len(raw)

    config_suffixes = (".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf")
    is_config_path = path.lower().endswith(config_suffixes) or any(
        token in basename for token in ("config", "settings", "manifest")
    )
    if is_config_path:
        stripped = lines[anchor_line].lstrip()
        if path.lower().endswith(".json"):
            opening = max(raw.rfind(b"{", 0, line_start), raw.rfind(b"[", 0, line_start))
            if opening >= 0:
                close = b"}" if raw[opening:opening + 1] == b"{" else b"]"
                depth = 0
                for index in range(opening, len(raw)):
                    if raw[index:index + 1] == raw[opening:opening + 1]:
                        depth += 1
                    elif raw[index:index + 1] == close:
                        depth -= 1
                        if depth == 0:
                            return opening, index + 1
        # Python or JavaScript mapping assignments use the same bounded brace
        # rule as JSON configuration, while scalar settings remain one block.
        opening = raw.find(b"{", line_start, line_end)
        if opening >= 0:
            depth = 0
            for index in range(opening, len(raw)):
                if raw[index:index + 1] == b"{":
                    depth += 1
                elif raw[index:index + 1] == b"}":
                    depth -= 1
                    if depth == 0:
                        return line_start, index + 1
        indentation = len(lines[anchor_line]) - len(stripped)
        finish = anchor_line + 1
        while finish < len(lines):
            candidate = lines[finish]
            if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= indentation:
                break
            finish += 1
        return offsets[anchor_line], offsets[finish] if finish < len(offsets) else len(raw)

    declaration = None
    for index in range(anchor_line, -1, -1):
        if re.match(r"^\s*(?:async\s+)?(?:def|class)\s+[A-Za-z_][A-Za-z0-9_]*", lines[index]):
            declaration = index
            break
    if declaration is not None:
        declaration_text = lines[declaration]
        indentation = len(declaration_text) - len(declaration_text.lstrip())
        begin = declaration
        while begin > 0 and re.match(r"^\s*@(\w|[.])+", lines[begin - 1]):
            begin -= 1
        finish = declaration + 1
        while finish < len(lines):
            candidate = lines[finish]
            if candidate.strip():
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate_indent <= indentation:
                    break
            finish += 1
        return offsets[begin], offsets[finish] if finish < len(offsets) else len(raw)

    brace_declaration = None
    for index in range(anchor_line, -1, -1):
        if re.search(r"\b(?:function|class)\s+[A-Za-z_$][\w$]*|=>\s*\{", lines[index]):
            brace_declaration = index
            break
    if brace_declaration is not None:
        opening = raw.find(b"{", offsets[brace_declaration], line_end)
        if opening >= 0:
            depth = 0
            for index in range(opening, len(raw)):
                if raw[index:index + 1] == b"{":
                    depth += 1
                elif raw[index:index + 1] == b"}":
                    depth -= 1
                    if depth == 0:
                        close_end = raw.find(b"\n", index)
                        return offsets[brace_declaration], len(raw) if close_end < 0 else close_end + 1

    return _line_window(raw, start, end, 1200)


def _line_window(raw: bytes, start: int, end: int, maximum: int) -> tuple[int, int]:
    left = raw.rfind(b"\n", max(0, start - maximum // 2), start)
    left = 0 if left < 0 else left + 1
    right = raw.find(b"\n", end, min(len(raw), end + maximum // 2))
    right = len(raw) if right < 0 else right
    if right - left > maximum:
        right = left + maximum
        while right > end and (raw[right : right + 1] and raw[right] & 0b11000000 == 0b10000000):
            right -= 1
    return left, right


__all__ = [
    "AuthorityClass", "EvidenceItem", "FacetKind", "HybridRetrievalResult",
    "NavigationContext", "NavigationResult", "SourcePreview",
    "PromptFacet", "PromptFacetSet", "ProofObligation", "RepositoryFileCard",
    "RepositoryTag", "RepositoryTagIndex", "RetrievalHit", "RetrievalResult",
    "TagKind", "build_repository_file_cards", "build_repository_tag_index",
    "compile_prompt", "compile_proof_obligations", "match_proof_obligation", "match_proof_obligations",
    "retrieve", "retrieve_hybrid", "navigate", "compose_navigation_context",
]
