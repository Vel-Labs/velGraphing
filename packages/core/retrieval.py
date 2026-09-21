"""Source-grounded typed tagging and deterministic hybrid retrieval.

This module is additive. It does not change legacy graph selection. Retrieval
scores rank evidence candidates. They are not probabilities, authority, or
proof that an answer is complete.
"""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
from pathlib import PurePosixPath
import posixpath
import re
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence
from urllib.parse import unquote

from .javascript_coordinates import JavaScriptCoordinateProvider
from .jev import (
    MAX_CANDIDATES,
    MAX_EXCERPT_BYTES,
    MAX_EXCERPTS_BYTES,
    JevError,
    canonical as jev_canonical,
)
from .models import (
    Admission,
    Freshness,
    Graph,
    GraphEdge,
    GraphRecord,
    Provenance,
    Sensitivity,
    TaskSpec,
    TrustClass,
    is_authenticated_eligible,
)
from .routing_v4 import SourceReaderV4, SourceSnapshotV4, _read_verified_source_bytes
from .selection import _REVERSE_RELATIONS, AssistResult, ContextSpan, assist
from .source_coordinates import SourceCoordinate, source_snapshot

if TYPE_CHECKING:
    from .selection import RankedContextCandidate


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,63}")
_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$")
_CONFIG_KEY = re.compile(r"(?m)[\"']([A-Za-z][A-Za-z0-9_.-]{1,63})[\"']\s*[:=]")
_TEST_NAME = re.compile(
    r"(?m)(?:\bdef\s+(test_[A-Za-z0-9_]+)|\b(?:it|test|describe)\s*\(\s*[\"']([^\"']{2,100})[\"'])"
)
_IMPORT = re.compile(
    r"(?m)(?:\bfrom\s+[\"']([^\"']+)[\"']|\brequire\s*\(\s*[\"']([^\"']+)[\"']|\bimport\s+(?:[^\n;]*?\s+from\s+)?[\"']([^\"']+)[\"'])"
)
_MARKDOWN_LINK = re.compile(rb"\[([^\]\r\n]+)\]\(([^)\r\n]+)\)")
_RELATION_MARKDOWN_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_RELATION_MARKDOWN_LINK = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")

_STOPWORDS = frozenset(
    {
        "about", "after", "also", "and", "are", "as", "before", "can", "could",
        "describe", "does", "each", "explain", "for", "from", "have", "how",
        "identify", "in", "into", "it", "its", "may", "must", "of", "on", "or", "our",
        "should", "that", "the", "their", "then", "these", "this", "through",
        "to", "using", "what", "when", "where", "which", "with", "would", "you",
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
        "links_to_heading", "loads_stylesheet", "notifies_panel", "owns", "packages", "packages_documentation",
        "packages_manifest", "packages_source_tree", "persists_audit_for_panel", "produces",
        "publishes_section_selection", "reads", "requires_authority", "routes", "specifies_scoring_reference",
        "supports", "tested_by", "tests", "uses", "writes",
    }
)
_CHANNEL_ORDER = ("exact", "sparse", "wiki", "graph")
_CHANNEL_WEIGHT = {"exact": 5, "sparse": 3, "wiki": 2, "graph": 2}
_RRF_K = 60
_MAX_FACETS = 20
_MIN_FACETS = 8
_MAX_TAGS_PER_RECORD = 4096
_MAX_EVIDENCE_COMPLETIONS = 6
_EVIDENCE_COMPLETION_COMMON = frozenset({
    *_PROOF_COMMON_TAGS,
    "both", "chapter", "chapters", "cite", "connect", "design", "explain",
    "frozen", "general", "guidance", "material", "reference", "separate",
    "stated", "why",
})
_ANCILLARY_DOCUMENT_HEADINGS = (
    "exercise", "flashcards", "follow-up-questions", "further-reading",
    "key-takeaways", "learning-objectives", "references",
)
_DOCUMENT_VARIANTS = frozenset({"small", "medium", "large"})


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
class RelationshipSupport:
    """One verified edge pointer associated with a selected seed."""

    edge_id: str
    relation: str
    seed_record_id: str
    target_record_id: str
    source_coordinate: SourceCoordinate
    target_coordinate: SourceCoordinate
    direction: str = "outgoing"
    sensitivity: Sensitivity = Sensitivity.PUBLIC

    def __post_init__(self) -> None:
        if self.direction not in {"incoming", "outgoing"}:
            raise ValueError("relationship support direction is unsupported")
        if not isinstance(self.sensitivity, Sensitivity):
            raise TypeError("relationship support sensitivity is unsupported")

    @property
    def seed_coordinate(self) -> SourceCoordinate:
        return self.source_coordinate if self.direction == "outgoing" else self.target_coordinate

    @property
    def related_coordinate(self) -> SourceCoordinate:
        return self.target_coordinate if self.direction == "outgoing" else self.source_coordinate

    def to_dict(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "relation": self.relation,
            "direction": self.direction,
            "seed_record_id": self.seed_record_id,
            "target_record_id": self.target_record_id,
            "related_record_id": self.target_record_id,
            "sensitivity": self.sensitivity.value,
            "source_coordinate": self.source_coordinate.to_dict(),
            "target_coordinate": self.target_coordinate.to_dict(),
            "seed_coordinate": self.seed_coordinate.to_dict(),
            "related_coordinate": self.related_coordinate.to_dict(),
        }


@dataclass(frozen=True)
class SourceRelationCoverage:
    """Deterministic outcome counts for one explicitly supported relation form."""

    relation: str
    supported: str
    resolved: int
    unresolved: int
    unsupported: int

    def __post_init__(self) -> None:
        if not self.relation or not self.supported:
            raise ValueError("relation coverage identity must be non-empty")
        if any(type(value) is not int or value < 0 for value in (
            self.resolved, self.unresolved, self.unsupported,
        )):
            raise ValueError("relation coverage counts must be non-negative integers")

    def to_dict(self) -> dict[str, object]:
        return {
            "relation": self.relation,
            "supported": self.supported,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "unsupported": self.unsupported,
        }


@dataclass(frozen=True)
class SourceRelationResult:
    """Source-bound edges and explicit coverage from the canonical relation seam."""

    edges: tuple[GraphEdge, ...]
    coverage: tuple[SourceRelationCoverage, ...]

    def __post_init__(self) -> None:
        if any(type(edge) is not GraphEdge for edge in self.edges):
            raise TypeError("source relation edges must contain GraphEdge values")
        if any(type(item) is not SourceRelationCoverage for item in self.coverage):
            raise TypeError("source relation coverage must contain SourceRelationCoverage values")
        if tuple(sorted(self.edges, key=lambda edge: edge.edge_id)) != self.edges:
            raise ValueError("source relation edges must be deterministically ordered")
        if tuple(sorted(self.coverage, key=lambda item: (item.relation, item.supported))) != self.coverage:
            raise ValueError("source relation coverage must be deterministically ordered")

    def to_dict(self) -> dict[str, object]:
        return {
            "edges": [edge.to_dict() for edge in self.edges],
            "coverage": [item.to_dict() for item in self.coverage],
        }


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
    relationship_supports: tuple[RelationshipSupport, ...] = ()


def ranked_candidates_from_retrieval(
    graph: Graph,
    task: TaskSpec,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    retrieval: RetrievalResult,
    *,
    maximum_candidates: int,
    maximum_candidate_bytes: int,
    maximum_unit_bytes: int,
) -> tuple[RankedContextCandidate, ...]:
    """Build one explicitly capped, Jev-compatible candidate shortlist.

    Candidate ranges are source-bound units. A bounded fallback range is not a
    completeness claim. Required status comes only from caller-declared proof
    obligation evidence.
    """

    from .selection import RankedContextCandidate

    if type(graph) is not Graph or type(task) is not TaskSpec:
        raise TypeError("graph and task must use exact core types")
    if type(snapshot) is not SourceSnapshotV4 or type(retrieval) is not RetrievalResult:
        raise TypeError("snapshot and retrieval must use exact core types")
    for value, limit, label in (
        (maximum_candidates, MAX_CANDIDATES, "maximum_candidates"),
        (maximum_candidate_bytes, MAX_EXCERPTS_BYTES, "maximum_candidate_bytes"),
        (maximum_unit_bytes, MAX_EXCERPT_BYTES, "maximum_unit_bytes"),
    ):
        if type(value) is not int or not 1 <= value <= limit:
            raise ValueError(f"{label}_invalid")
    if retrieval.fail_closed:
        raise ValueError("retrieval_failed_closed")
    source_bytes = _read_verified_source_bytes(snapshot, reader)
    sources = {source.path: source for source in snapshot.sources}
    records = graph.record_map()

    def make_candidate(
        record_id: str,
        path: str,
        digest: str,
        start: int,
        end: int,
        *,
        required: bool,
        parent_id: str | None = None,
        relationship_edge_id: str | None = None,
        relationship_direction: str | None = None,
        relationship_relation: str | None = None,
        relationship_sensitivity: Sensitivity | None = None,
    ) -> RankedContextCandidate:
        record = records.get(record_id)
        source = sources.get(path)
        raw = source_bytes.get(path)
        if (
            record is None or source is None or raw is None
            or record.provenance.path != path
            or record.provenance.sha256 != digest
            or source.sha256 != digest
            or hashlib.sha256(raw).hexdigest() != digest
            or record.content.encode("utf-8") != raw
            or not is_authenticated_eligible(record, task.allowed_sensitivities)
            or not 0 <= start < end <= len(raw)
        ):
            raise ValueError("candidate_custody_mismatch")
        excerpt = raw[start:end]
        try:
            if excerpt.decode("utf-8").encode("utf-8") != excerpt:
                raise ValueError("candidate_not_utf8")
        except UnicodeDecodeError as error:
            raise ValueError("candidate_not_utf8") from error
        if len(excerpt) > maximum_unit_bytes:
            raise ValueError("required_candidate_budget_exceeded" if required else "candidate_unit_budget_exceeded")
        identity = {
            "path": path,
            "source_sha256": digest,
            "byte_start": start,
            "byte_end": end,
        }
        return RankedContextCandidate(
            hashlib.sha256(jev_canonical(identity)).hexdigest(),
            path, digest, start, end, required, record_id, parent_id,
            relationship_edge_id, relationship_direction, relationship_relation,
            relationship_sensitivity,
        )

    required: list[RankedContextCandidate] = []
    required_ids: set[str] = set()
    for evidence in retrieval.evidence:
        if not evidence.obligation_ids:
            continue
        try:
            candidate = make_candidate(
                evidence.record_id, evidence.source_path, evidence.source_sha256,
                evidence.byte_start, evidence.byte_end, required=True,
            )
        except JevError as error:
            raise ValueError("required_candidate_jev_incompatible") from error
        except ValueError as error:
            if str(error) == "required_candidate_budget_exceeded":
                raise
            raise ValueError("required_candidate_custody_mismatch") from error
        raw = source_bytes[evidence.source_path]
        if evidence.excerpt_sha256 != hashlib.sha256(
            raw[evidence.byte_start:evidence.byte_end]
        ).hexdigest():
            raise ValueError("required_candidate_custody_mismatch")
        if candidate.candidate_id in required_ids:
            raise ValueError("duplicate_required_evidence")
        required_ids.add(candidate.candidate_id)
        required.append(candidate)

    required_bytes = sum(item.byte_end - item.byte_start for item in required)
    if len(required) > maximum_candidates or required_bytes > maximum_candidate_bytes:
        raise ValueError("required_candidate_budget_exceeded")

    optional_by_record: dict[str, list[RankedContextCandidate]] = defaultdict(list)
    seen_primary: set[str] = set(required_ids)
    hit_records: set[str] = set()
    hit_order: list[str] = []
    for hit in retrieval.hits:
        if hit.record_id in hit_records:
            raise ValueError("duplicate_retrieval_hit")
        hit_records.add(hit.record_id)
        hit_order.append(hit.record_id)
        record = records.get(hit.record_id)
        source = sources.get(hit.source_path)
        raw = source_bytes.get(hit.source_path)
        if (
            record is None
            or source is None
            or raw is None
            or record.provenance.path != hit.source_path
            or record.provenance.sha256 != source.sha256
            or hashlib.sha256(raw).hexdigest() != source.sha256
            or not is_authenticated_eligible(record, task.allowed_sensitivities)
        ):
            raise ValueError("retrieval_candidate_custody_mismatch")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("retrieval_candidate_not_utf8") from error
        if content.encode("utf-8") != raw or record.content.encode("utf-8") != raw:
            raise ValueError("retrieval_candidate_custody_mismatch")

        units: dict[tuple[int, int], tuple[set[str], bool]] = {}
        for tag in _extract_tags(record, content):
            if (
                tag.byte_start is None
                or tag.byte_end is None
                or tag.value not in hit.matched_facets
            ):
                continue
            start, end, complete = _bounded_source_unit_bounds(
                raw, hit.source_path, tag.byte_start, tag.byte_end, maximum_unit_bytes
            )
            if end > start:
                facets, prior_complete = units.setdefault((start, end), (set(), False))
                facets.add(tag.value)
                units[(start, end)] = facets, prior_complete or complete

        ordered_units = sorted(
            units,
            key=lambda bounds: (
                -len(units[bounds][0]),
                not units[bounds][1],
                bounds[0],
                bounds[1],
            ),
        )
        for start, end in ordered_units:
            try:
                candidate = make_candidate(
                    hit.record_id, hit.source_path, source.sha256, start, end,
                    required=False,
                )
            except JevError as error:
                if str(error) == "unsupported_source_type":
                    continue
                raise ValueError("retrieval_candidate_jev_incompatible") from error
            except ValueError as error:
                raise ValueError("retrieval_candidate_custody_mismatch") from error
            if candidate.candidate_id in seen_primary:
                continue
            seen_primary.add(candidate.candidate_id)
            optional_by_record[hit.record_id].append(candidate)

    optional = [
        candidates[offset]
        for offset in range(max(map(len, optional_by_record.values()), default=0))
        for record_id in hit_order
        if offset < len(candidates := optional_by_record[record_id])
    ]
    primary = [*required, *optional]

    # Complete named documentation evidence before final retention. Follow only
    # links present in already admitted spans, and re-enter through make_candidate
    # so every added unit receives the same custody and budget checks.
    query_path_words = {
        word
        for term in task.query_terms
        for word in _identifier_parts(term)
        if len(word) > 2 and word not in _STOPWORDS and word not in _GENERIC
    }
    query_weights: dict[str, int] = {}
    for term in task.query_terms:
        weight = 3 if "-" in term else 1
        for word in _identifier_parts(term):
            if len(word) > 2 and word not in _EVIDENCE_COMPLETION_COMMON:
                query_weights[word] = max(weight, query_weights.get(word, 0))
    query_words = set(query_weights)
    admitted_markdown = [
        candidate for candidate in primary
        if candidate.source_path.lower().endswith((".md", ".markdown"))
    ]
    target_paths: list[str] = []
    target_seen: set[str] = set()

    def path_words(path: str) -> set[str]:
        return {
            word
            for word in _identifier_parts(posixpath.basename(path).rsplit(".", 1)[0])
            if (
                len(word) > 2
                and word[0].isalpha()
                and word not in _STOPWORDS
                and word not in _GENERIC
            )
        }

    def add_target(path: str, terms: set[str], *, partial: bool = False) -> None:
        matched = terms & query_path_words
        requested_variant = query_path_words & _DOCUMENT_VARIANTS
        if (
            matched
            and (terms <= query_path_words or (partial and len(matched) >= 2))
            and (not requested_variant or not terms & _DOCUMENT_VARIANTS
                 or bool(terms & requested_variant))
            and path not in target_seen
        ):
            target_seen.add(path)
            target_paths.append(path)

    for candidate in admitted_markdown:
        add_target(candidate.source_path, path_words(candidate.source_path), partial=True)
        raw = source_bytes[candidate.source_path]
        for match in _MARKDOWN_LINK.finditer(raw, candidate.byte_start, candidate.byte_end):
            try:
                destination = match.group(2).decode("utf-8").strip()
            except UnicodeDecodeError:
                continue
            if destination.startswith("<") and ">" in destination:
                destination = destination[1:destination.index(">")]
            else:
                destination = destination.split(maxsplit=1)[0]
            destination = destination.split("#", 1)[0]
            if not destination or "://" in destination or destination.startswith("/"):
                continue
            target = posixpath.normpath(posixpath.join(
                posixpath.dirname(candidate.source_path), destination,
            ))
            if not _valid_source_path(target) or target not in sources:
                continue
            add_target(target, path_words(target))

    target_paths = target_paths[:2]
    records_by_path = {record.provenance.path: record for record in records.values()}
    completion_by_path: dict[str, list[RankedContextCandidate]] = defaultdict(list)
    completion_ids = set(required_ids)
    for path in target_paths:
        record = records_by_path.get(path)
        source = sources.get(path)
        raw = source_bytes.get(path)
        if record is None or source is None or raw is None:
            continue
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        units: dict[tuple[int, int], tuple[set[str], bool]] = {}
        for word in sorted(query_words):
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", re.IGNORECASE)
            for match in pattern.finditer(content):
                anchor_start, anchor_end = _byte_bounds(content, match.start(), match.end())
                start, end, complete = _bounded_source_unit_bounds(
                    raw, path, anchor_start, anchor_end, maximum_unit_bytes,
                )
                if end <= start:
                    continue
                first_line = raw[start:end].split(b"\n", 1)[0].decode(
                    "utf-8", errors="ignore"
                )
                heading = _canonical(first_line.lstrip("# "))
                if (
                    not raw[start:end].partition(b"\n")[2].strip()
                    or first_line.strip() == "---"
                    or heading.startswith(_ANCILLARY_DOCUMENT_HEADINGS)
                ):
                    continue
                matched, prior_complete = units.setdefault((start, end), (set(), False))
                matched.add(word)
                units[(start, end)] = matched, prior_complete or complete

        def unit_priority(bounds: tuple[int, int]) -> tuple[int, bool, int, int, bool, int]:
            start, end = bounds
            first_line = raw[start:end].split(b"\n", 1)[0].decode("utf-8", errors="ignore")
            is_heading = bool(_HEADING.match(first_line))
            heading_words = set(_words(first_line)) if is_heading else set()
            heading_weight = sum(
                query_weights.get(word, query_weights.get(word.rstrip("s"), 0))
                for word in heading_words
            )
            content_weight = sum(query_weights[word] for word in units[bounds][0])
            return (
                -heading_weight,
                not is_heading,
                start if heading_weight == 0 else -content_weight,
                -len(units[bounds][0]),
                not units[bounds][1],
                end,
            )

        for start, end in sorted(units, key=unit_priority):
            candidate = make_candidate(
                record.record_id, path, source.sha256, start, end, required=False,
            )
            if candidate.candidate_id in completion_ids:
                continue
            completion_ids.add(candidate.candidate_id)
            completion_by_path[path].append(candidate)

    completion = [
        candidates[offset]
        for offset in range(max(map(len, completion_by_path.values()), default=0))
        for path in target_paths
        if offset < len(candidates := completion_by_path[path])
    ][:_MAX_EVIDENCE_COMPLETIONS]
    primary = [*required, *completion, *optional]

    primary_ids = {candidate.candidate_id for candidate in primary}
    supports_by_parent: dict[str, list[RankedContextCandidate]] = defaultdict(list)
    seen_supports: set[RelationshipSupport] = set()
    edges = graph.edge_map()
    for support in retrieval.relationship_supports:
        if support in seen_supports:
            raise ValueError("duplicate_relationship_support")
        seen_supports.add(support)
        edge = edges.get(support.edge_id)
        seed = records.get(support.seed_record_id)
        target = records.get(support.target_record_id)
        coordinate = support.related_coordinate
        seed_coordinate = support.seed_coordinate
        seed_source = sources.get(seed_coordinate.source_path)
        seed_raw = source_bytes.get(seed_coordinate.source_path)
        source = sources.get(coordinate.source_path)
        raw = source_bytes.get(coordinate.source_path)
        expected_source_id = support.seed_record_id if support.direction == "outgoing" else support.target_record_id
        expected_target_id = support.target_record_id if support.direction == "outgoing" else support.seed_record_id
        sensitivity_rank = {
            Sensitivity.PUBLIC: 0,
            Sensitivity.INTERNAL: 1,
            Sensitivity.RESTRICTED: 2,
        }
        if (
            edge is None
            or edge.source_id != expected_source_id
            or edge.target_id != expected_target_id
            or edge.relation != support.relation
            or edge.source_coordinate != support.source_coordinate
            or edge.target_coordinate != support.target_coordinate
            or edge.sensitivity is not support.sensitivity
            or seed is None
            or target is None
            or edge.sensitivity is not max(
                (seed.sensitivity, target.sensitivity), key=sensitivity_rank.__getitem__
            )
            or edge.relation not in _ALLOWED_RELATIONS
            or not is_authenticated_eligible(edge, task.allowed_sensitivities)
            or seed_coordinate.snapshot_sha256 != snapshot.snapshot_sha256
            or coordinate.snapshot_sha256 != snapshot.snapshot_sha256
            or seed_source is None
            or seed_raw is None
            or seed.provenance.path != seed_coordinate.source_path
            or seed.provenance.sha256 != seed_coordinate.source_sha256
            or seed_source.sha256 != seed_coordinate.source_sha256
            or seed.content.encode("utf-8") != seed_raw
            or not 0 <= seed_coordinate.byte_start < seed_coordinate.byte_end <= len(seed_raw)
            or source is None
            or raw is None
            or target.provenance.path != coordinate.source_path
            or target.provenance.sha256 != coordinate.source_sha256
            or target.content.encode("utf-8") != raw
            or source.sha256 != coordinate.source_sha256
            or not is_authenticated_eligible(target, task.allowed_sensitivities)
            or not 0 <= coordinate.byte_start < coordinate.byte_end <= len(raw)
        ):
            raise ValueError("relationship_support_custody_mismatch")
        parent = next(
            (
                item for item in primary
                if item.record_id == support.seed_record_id
                and item.source_path == seed_coordinate.source_path
                and item.source_sha256 == seed_coordinate.source_sha256
                and item.byte_start <= seed_coordinate.byte_start
                and seed_coordinate.byte_end <= item.byte_end
            ),
            None,
        )
        if parent is None:
            continue
        start, end, _ = _bounded_source_unit_bounds(
            raw, coordinate.source_path, coordinate.byte_start,
            coordinate.byte_end, maximum_unit_bytes,
        )
        if end <= start:
            continue
        try:
            candidate = make_candidate(
                support.target_record_id, coordinate.source_path,
                coordinate.source_sha256, start, end, required=False,
                parent_id=parent.candidate_id,
                relationship_edge_id=support.edge_id,
                relationship_direction=support.direction,
                relationship_relation=support.relation,
                relationship_sensitivity=support.sensitivity,
            )
        except JevError as error:
            if str(error) == "unsupported_source_type":
                continue
            raise ValueError("relationship_candidate_jev_incompatible") from error
        except ValueError as error:
            raise ValueError("relationship_support_custody_mismatch") from error
        if candidate.candidate_id not in primary_ids:
            supports_by_parent[parent.candidate_id].append(candidate)

    ordered: list[RankedContextCandidate] = list(required)
    for candidate in required:
        ordered.extend(supports_by_parent.get(candidate.candidate_id, ()))
    nonrequired = [*completion, *optional]
    relationship_parents = [
        candidate for candidate in nonrequired
        if supports_by_parent.get(candidate.candidate_id)
    ]
    other_optional = [
        candidate for candidate in nonrequired
        if not supports_by_parent.get(candidate.candidate_id)
    ]
    for candidate in [*relationship_parents, *other_optional]:
        ordered.append(candidate)
        ordered.extend(supports_by_parent.get(candidate.candidate_id, ()))

    required_candidates = [candidate for candidate in ordered if candidate.required]
    required_bytes = sum(
        candidate.byte_end - candidate.byte_start for candidate in required_candidates
    )
    if (
        len(required_candidates) > maximum_candidates
        or required_bytes > maximum_candidate_bytes
    ):
        raise ValueError("required_candidate_budget_exceeded")
    retained: list[RankedContextCandidate] = []
    retained_ids: set[str] = set()
    used = 0
    remaining_required_count = len(required_candidates)
    remaining_required_bytes = required_bytes
    for candidate in ordered:
        if candidate.candidate_id in retained_ids:
            continue
        size = candidate.byte_end - candidate.byte_start
        if candidate.required:
            remaining_required_count -= 1
            remaining_required_bytes -= size
        elif (
            len(retained) + 1 + remaining_required_count > maximum_candidates
            or used + size + remaining_required_bytes > maximum_candidate_bytes
            or (
                candidate.relationship_parent_candidate_id is not None
                and candidate.relationship_parent_candidate_id not in retained_ids
            )
        ):
            continue
        retained.append(candidate)
        retained_ids.add(candidate.candidate_id)
        used += size
    return tuple(retained)


@dataclass(frozen=True)
class GraphFindResult:
    """Body-free, source-pointer result for the ``/graph-find`` seam."""

    route: str
    reason: str
    hits: tuple[RetrievalHit, ...]
    evidence: tuple[EvidenceItem, ...]
    source_snapshot_sha256: str
    context_bytes: int
    facet_coverage_percent: float
    recommended_fallback_paths: tuple[str, ...]
    fail_closed: bool
    covered_obligation_ids: tuple[str, ...] = ()
    unresolved_obligation_ids: tuple[str, ...] = ()
    unresolved_critical_obligation_ids: tuple[str, ...] = ()
    remaining_byte_budget: int = 0
    relationship_supports: tuple[RelationshipSupport, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize only ranked hits, exact pointers, and routing metadata."""

        return {
            "route": self.route,
            "reason": self.reason,
            "hits": [item.__dict__.copy() for item in self.hits],
            "evidence": [item.to_dict() for item in self.evidence],
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "context_bytes": self.context_bytes,
            "facet_coverage_percent": self.facet_coverage_percent,
            "recommended_fallback_paths": list(self.recommended_fallback_paths),
            "fail_closed": self.fail_closed,
            "covered_obligation_ids": list(self.covered_obligation_ids),
            "unresolved_obligation_ids": list(self.unresolved_obligation_ids),
            "unresolved_critical_obligation_ids": list(self.unresolved_critical_obligation_ids),
            "remaining_byte_budget": self.remaining_byte_budget,
            "relationship_supports": [item.to_dict() for item in self.relationship_supports],
            "score_meaning": (
                "deterministic_ranking_diagnostic_not_probability_authority_or_answer_confidence"
            ),
        }


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


def _relation_coordinate(
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


def _relation_ast_range(data: bytes, node: ast.AST) -> tuple[int, int] | None:
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


def _relation_module_name(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or None


def _relation_resolved_module(source_path: str, node: ast.ImportFrom) -> str | None:
    if not node.module:
        return None
    if not node.level:
        return node.module
    package = source_path[:-3].split("/")[:-1]
    if source_path.endswith("/__init__.py"):
        package = source_path[:-12].split("/")
    keep = len(package) - node.level + 1
    if not package or keep <= 0:
        return None
    return ".".join([*package[:keep], *node.module.split(".")])


def _relation_heading_slug(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value.casefold())
    value = re.sub(r"[^\w\s-]", "", value)
    return re.sub(r"[-\s]+", "-", value).strip("-")


def _relation_markdown_headings(text: str) -> list[tuple[str, int, int]]:
    headings: list[tuple[str, int, int]] = []
    fence: tuple[str, int] | None = None
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        if fence is not None:
            character, minimum = fence
            if re.fullmatch(rf" {{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*", line):
                fence = None
        else:
            opener = re.match(r" {0,3}(`{3,}|~{3,})", line)
            if opener is not None:
                run = opener.group(1)
                fence = (run[0], len(run))
            else:
                heading = _RELATION_MARKDOWN_HEADING.fullmatch(line)
                if heading is not None:
                    headings.append(
                        (heading.group(1), offset + heading.start(1), offset + heading.end(1))
                    )
        offset += len(raw_line)
    return headings


def derive_source_relations(
    graph: Graph,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
) -> SourceRelationResult:
    """Derive the supported source-witnessed relation forms.

    The seam supports named Python ``from`` imports to one top-level declaration
    static relative JavaScript named imports to one direct named export, and
    relative Markdown ``path#fragment`` links to one ATX heading. Other relation
    forms remain unsupported and are counted rather than inferred.
    """

    if type(graph) is not Graph:
        raise TypeError("graph must be an exact Graph")
    source_bytes = _read_verified_source_bytes(snapshot, reader)
    records_by_path: dict[str, GraphRecord] = {}
    for path, data in sorted(source_bytes.items()):
        candidates = [record for record in graph.records if record.provenance.path == path]
        if len(candidates) != 1:
            raise ValueError("relation source custody mismatch")
        record = candidates[0]
        try:
            record_bytes = record.content.encode("utf-8")
        except UnicodeError as error:
            raise ValueError("relation source custody mismatch") from error
        if (
            record.kind != "source"
            or record.provenance.sha256 != hashlib.sha256(data).hexdigest()
            or record_bytes != data
            or record.trust is not TrustClass.VERIFIED_SOURCE
            or record.admission is not Admission.VERIFIER
            or not is_authenticated_eligible(record, (record.sensitivity,))
        ):
            raise ValueError("relation source custody mismatch")
        records_by_path[path] = record

    modules: dict[str, list[str]] = {}
    declarations: dict[str, dict[str, list[SourceCoordinate]]] = {}
    trees: dict[str, ast.Module] = {}
    headings: dict[str, dict[str, list[SourceCoordinate]]] = {}
    counts = {
        "javascript_imports": {"resolved": 0, "unresolved": 0, "unsupported": 0},
        "python_imports": {"resolved": 0, "unresolved": 0, "unsupported": 0},
        "links_to_heading": {"resolved": 0, "unresolved": 0, "unsupported": 0},
    }
    for path, data in sorted(source_bytes.items()):
        module = _relation_module_name(path)
        if module is not None:
            modules.setdefault(module, []).append(path)
            try:
                tree = ast.parse(data.decode("utf-8"), filename=path)
            except (SyntaxError, UnicodeError):
                counts["python_imports"]["unsupported"] += 1
                continue
            trees[path] = tree
            by_name: dict[str, list[SourceCoordinate]] = {}
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                bounds = _relation_ast_range(data, node)
                if bounds is None or bounds[0] >= bounds[1]:
                    continue
                by_name.setdefault(node.name, []).append(
                    _relation_coordinate(
                        snapshot.snapshot_sha256,
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
            for heading, character_start, character_end in _relation_markdown_headings(text):
                slug = _relation_heading_slug(heading)
                if not slug:
                    continue
                start = len(text[:character_start].encode("utf-8"))
                end = len(text[:character_end].encode("utf-8"))
                by_slug.setdefault(slug, []).append(
                    _relation_coordinate(
                        snapshot.snapshot_sha256,
                        path,
                        data,
                        start,
                        end,
                        "markdown_heading",
                        "declaration",
                        slug,
                    )
                )
            headings[path] = by_slug

    edges: list[GraphEdge] = []

    def add(
        relation: str,
        source: SourceCoordinate,
        target: SourceCoordinate,
    ) -> None:
        sensitivity_rank = {
            Sensitivity.PUBLIC: 0,
            Sensitivity.INTERNAL: 1,
            Sensitivity.RESTRICTED: 2,
        }
        edge_sensitivity = max(
            (
                records_by_path[source.source_path].sensitivity,
                records_by_path[target.source_path].sensitivity,
            ),
            key=sensitivity_rank.__getitem__,
        )
        identity = json.dumps(
            [relation, source.to_dict(), target.to_dict()],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        edges.append(
            GraphEdge(
                f"edge:{hashlib.sha256(identity).hexdigest()}",
                records_by_path[source.source_path].record_id,
                records_by_path[target.source_path].record_id,
                relation,
                1.0,
                Provenance(
                    source.source_path,
                    source.source_sha256,
                    f"bytes:{source.byte_start}-{source.byte_end}",
                    True,
                ),
                TrustClass.VERIFIED_SOURCE,
                edge_sensitivity,
                Freshness.CURRENT,
                Admission.VERIFIER,
                True,
                source_coordinate=source,
                target_coordinate=target,
            )
        )

    for path, tree in sorted(trees.items()):
        data = source_bytes[path]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                counts["python_imports"]["unsupported"] += len(node.names)
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            module = _relation_resolved_module(path, node)
            targets = modules.get(module or "", ())
            for alias in node.names:
                if alias.name == "*" or module is None:
                    counts["python_imports"]["unsupported"] += 1
                    continue
                bounds = _relation_ast_range(data, alias)
                declarations_for_name = (
                    declarations.get(targets[0], {}).get(alias.name, ())
                    if len(targets) == 1
                    else ()
                )
                if len(targets) != 1 or len(declarations_for_name) != 1 or bounds is None:
                    counts["python_imports"]["unresolved"] += 1
                    continue
                add(
                    "imports",
                    _relation_coordinate(
                        snapshot.snapshot_sha256,
                        path,
                        data,
                        *bounds,
                        "python_import",
                        "import",
                        alias.name,
                    ),
                    declarations_for_name[0],
                )
                counts["python_imports"]["resolved"] += 1

    javascript = JavaScriptCoordinateProvider().relations(source_snapshot(source_bytes))
    if not javascript.supported:
        raise ValueError(javascript.reason or "javascript_relation_index_unavailable")
    counts["javascript_imports"]["unsupported"] = javascript.unsupported
    javascript_paths = frozenset(
        path for path in source_bytes
        if path.casefold().endswith((".js", ".jsx", ".mjs", ".cjs"))
    )
    javascript_exports: dict[str, dict[str, list[SourceCoordinate]]] = {}
    for item in javascript.exports:
        data = source_bytes[item.source_path]
        javascript_exports.setdefault(item.source_path, {}).setdefault(item.symbol, []).append(
            _relation_coordinate(
                snapshot.snapshot_sha256,
                item.source_path,
                data,
                item.byte_start,
                item.byte_end,
                "javascript_export_declaration",
                "definition",
                item.symbol,
            )
        )
    for item in javascript.imports:
        base = posixpath.normpath(posixpath.join(posixpath.dirname(item.source_path), item.module))
        if base == ".." or base.startswith("../"):
            counts["javascript_imports"]["unresolved"] += 1
            continue
        suffix = PurePosixPath(base).suffix.casefold()
        candidates = (
            (base,)
            if suffix
            else tuple(
                candidate
                for extension in (".cjs", ".js", ".jsx", ".mjs")
                for candidate in (f"{base}{extension}", f"{base}/index{extension}")
            )
        )
        target_paths = tuple(path for path in candidates if path in javascript_paths)
        declarations_for_name = (
            javascript_exports.get(target_paths[0], {}).get(item.symbol, ())
            if len(target_paths) == 1
            else ()
        )
        if len(target_paths) != 1 or len(declarations_for_name) != 1:
            counts["javascript_imports"]["unresolved"] += 1
            continue
        data = source_bytes[item.source_path]
        add(
            "imports",
            _relation_coordinate(
                snapshot.snapshot_sha256,
                item.source_path,
                data,
                item.byte_start,
                item.byte_end,
                "javascript_import",
                "import",
                item.symbol,
            ),
            declarations_for_name[0],
        )
        counts["javascript_imports"]["resolved"] += 1

    for path, data in sorted(source_bytes.items()):
        if path not in headings:
            continue
        text = data.decode("utf-8")
        for match in _RELATION_MARKDOWN_LINK.finditer(text):
            destination = match.group(1)
            if (
                destination != destination.strip()
                or any(character.isspace() for character in destination)
                or "#" not in destination
            ):
                counts["links_to_heading"]["unsupported"] += 1
                continue
            link_path, fragment = destination.rsplit("#", 1)
            if (
                not link_path
                or not fragment
                or "%" in link_path
                or link_path.startswith(("/", "//"))
                or ":" in link_path
                or ".." in PurePosixPath(link_path).parts
            ):
                counts["links_to_heading"]["unsupported"] += 1
                continue
            target_path = posixpath.normpath(posixpath.join(posixpath.dirname(path), link_path))
            targets = (
                headings[target_path].get(_relation_heading_slug(unquote(fragment)), ())
                if not target_path.startswith("../") and target_path in headings
                else ()
            )
            if len(targets) != 1:
                counts["links_to_heading"]["unresolved"] += 1
                continue
            start = len(text[: match.start(1)].encode("utf-8"))
            end = len(text[: match.end(1)].encode("utf-8"))
            add(
                "links_to_heading",
                _relation_coordinate(
                    snapshot.snapshot_sha256,
                    path,
                    data,
                    start,
                    end,
                    "markdown_link",
                    "reference",
                    destination,
                ),
                targets[0],
            )
            counts["links_to_heading"]["resolved"] += 1

    ordered_edges = tuple(sorted(edges, key=lambda edge: edge.edge_id))
    Graph(graph.records, ordered_edges)
    coverage = (
        SourceRelationCoverage(
            "imports",
            "javascript_tree_sitter_static_relative_named_direct_export",
            **counts["javascript_imports"],
        ),
        SourceRelationCoverage(
            "imports",
            "python_ast_from_import_named_top_level_declaration",
            **counts["python_imports"],
        ),
        SourceRelationCoverage(
            "links_to_heading",
            "markdown_relative_path_fragment_unique_atx_heading",
            **counts["links_to_heading"],
        ),
    )
    return SourceRelationResult(ordered_edges, coverage)


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
        )
        # Bound distinct retained identities, not repeated lexical occurrences.
        # Keep the first deterministic representative for each identity.
        retained = 0
        for tag in record_tags:
            identity = (tag.record_id, tag.kind.value, tag.value)
            if identity not in seen:
                seen.add(identity)
                tags.append(tag)
                retained += 1
                if retained == _MAX_TAGS_PER_RECORD:
                    break
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
        if canonical and canonical not in _STOPWORDS and (_looks_identifier(raw) or "-" in raw):
            lexical_candidates.extend(
                PromptFacet(FacetKind.IDENTIFIER, part, 9)
                for part in sorted(_identifier_parts(raw))
                if part != canonical and part not in _STOPWORDS
            )
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

    balanced_lexical: list[PromptFacet] = []
    clause_candidates: list[list[PromptFacet]] = []
    for clause in _prompt_clauses(prompt, vocabulary):
        clause_values = set(_words(clause))
        for raw in _TOKEN.findall(clause):
            clause_values.update(_identifier_parts(raw))
        clause_candidates.append([
            facet for facet in lexical_candidates
            if facet.value in vocabulary and facet.value in clause_values
        ])
    for offset in range(max(map(len, clause_candidates), default=0)):
        balanced_lexical.extend(
            candidates[offset]
            for candidates in clause_candidates
            if offset < len(candidates)
        )

    facets: list[PromptFacet] = []
    seen: set[tuple[FacetKind, str]] = set()
    required = [facet for facet in lexical_candidates if facet.required]
    lexical = [
        facet for facet in [*balanced_lexical, *lexical_candidates]
        if not facet.required
    ]
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


def graph_find(
    graph: Graph,
    task: TaskSpec,
    prompt: str,
    snapshot: SourceSnapshotV4,
    reader: SourceReaderV4,
    *,
    semantic_candidates: Sequence[str] = (),
    proof_obligations: Sequence[ProofObligation] | None = None,
    channels: Sequence[str] = _CHANNEL_ORDER,
    expand_one_hop: bool = True,
    source_bound_expansion: bool = False,
    maximum_results: int = 6,
    minimum_coverage_percent: float = 60.0,
    parallel: bool = True,
) -> GraphFindResult:
    """Run the body-free ``/graph-find`` core seam."""

    index = build_repository_tag_index(graph, snapshot, reader)
    facets = compile_prompt(
        prompt,
        index,
        semantic_candidates=semantic_candidates,
        proof_obligations=()
        if proof_obligations is None
        else tuple(proof_obligations),
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
        source_bound_expansion=source_bound_expansion,
        maximum_results=maximum_results,
        minimum_coverage_percent=minimum_coverage_percent,
        parallel=parallel,
    )
    short_prompt = len([word for word in _words(prompt) if word not in _STOPWORDS]) < 3
    if proof_obligations is None and (
        result.reason == "prompt_facets_insufficient" or short_prompt
    ):
        obligations = compile_proof_obligations(prompt, graph, index, snapshot, reader)
        facets = compile_prompt(
            prompt,
            index,
            semantic_candidates=semantic_candidates,
            proof_obligations=obligations,
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
            source_bound_expansion=source_bound_expansion,
            maximum_results=maximum_results,
            minimum_coverage_percent=minimum_coverage_percent,
            parallel=parallel,
        )
    return GraphFindResult(
        route=result.route,
        reason=result.reason,
        hits=result.hits,
        evidence=result.evidence,
        source_snapshot_sha256=snapshot.snapshot_sha256,
        context_bytes=result.context_bytes,
        facet_coverage_percent=result.facet_coverage_percent,
        recommended_fallback_paths=result.recommended_fallback_paths,
        fail_closed=result.fail_closed,
        covered_obligation_ids=result.covered_obligation_ids,
        unresolved_obligation_ids=result.unresolved_obligation_ids,
        unresolved_critical_obligation_ids=result.unresolved_critical_obligation_ids,
        remaining_byte_budget=result.remaining_byte_budget,
        relationship_supports=result.relationship_supports,
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
    source_bound_expansion: bool = False,
    maximum_results: int = 6,
    minimum_coverage_percent: float = 60.0,
    parallel: bool = True,
) -> RetrievalResult:
    """Retrieve a deterministic, bounded, source-verified evidence packet."""

    requested_channels = tuple(dict.fromkeys(channels))
    if type(source_bound_expansion) is not bool:
        raise TypeError("source_bound_expansion must be bool")
    if not requested_channels or any(channel not in _CHANNEL_ORDER for channel in requested_channels):
        raise ValueError("retrieval channels must use the closed channel vocabulary")
    if source_bound_expansion:
        requested_channels = tuple(channel for channel in requested_channels if channel != "graph")
        if not requested_channels:
            raise ValueError("source-bound expansion requires a source ranking channel")
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
    legacy_expand = expand_one_hop and not source_bound_expansion
    seed_limit = max(1, maximum_results - 2) if legacy_expand else maximum_results
    base = base_order[:seed_limit]
    expanded_from: dict[str, str] = {}
    if legacy_expand:
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
    relationship_supports: tuple[RelationshipSupport, ...] = ()
    if source_bound_expansion and expand_one_hop:
        support_by_seed = {}
        selected_seeds = {hit.record_id for hit in hits if hit.hop == 0}
        change_impact = any(
            facet.kind is FacetKind.INTENT and facet.value == "change-impact"
            for facet in facets.facets
        )
        eligible_edges = []
        for edge in sorted(graph.edges, key=lambda item: (item.source_id, item.relation, item.edge_id)):
            if edge.relation not in _ALLOWED_RELATIONS or not is_authenticated_eligible(
                edge, task.allowed_sensitivities
            ):
                continue
            if edge.source_coordinate is None or edge.target_coordinate is None:
                continue
            if (
                edge.source_coordinate.snapshot_sha256 != snapshot.snapshot_sha256
                or edge.target_coordinate.snapshot_sha256 != snapshot.snapshot_sha256
            ):
                continue
            source_record = record_map[edge.source_id]
            target_record = record_map[edge.target_id]
            if not (
                is_authenticated_eligible(source_record, task.allowed_sensitivities)
                and is_authenticated_eligible(target_record, task.allowed_sensitivities)
            ):
                continue
            sensitivity_rank = {
                Sensitivity.PUBLIC: 0,
                Sensitivity.INTERNAL: 1,
                Sensitivity.RESTRICTED: 2,
            }
            if edge.sensitivity is not max(
                (source_record.sensitivity, target_record.sensitivity),
                key=sensitivity_rank.__getitem__,
            ):
                continue
            eligible_edges.append(edge)
        direction_order = ("incoming", "outgoing") if change_impact else ("outgoing",)
        prompt_values = {facet.value for facet in facets.facets}
        for direction in direction_order:
            for symbol_matched in (True, False):
                for edge in eligible_edges:
                    if direction == "incoming":
                        if edge.relation not in _REVERSE_RELATIONS:
                            continue
                        seed_id, related_id = edge.target_id, edge.source_id
                        seed_coordinate = edge.target_coordinate
                    else:
                        seed_id, related_id = edge.source_id, edge.target_id
                        seed_coordinate = edge.source_coordinate
                    assert seed_coordinate is not None
                    if (
                        _canonical(seed_coordinate.symbol) in prompt_values
                    ) is not symbol_matched:
                        continue
                    if seed_id not in selected_seeds or seed_id in support_by_seed:
                        continue
                    support_by_seed[seed_id] = RelationshipSupport(
                        edge.edge_id,
                        edge.relation,
                        seed_id,
                        related_id,
                        edge.source_coordinate,
                        edge.target_coordinate,
                        direction,
                        edge.sensitivity,
                    )
        relationship_supports = tuple(support_by_seed[key] for key in sorted(support_by_seed))
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
        relationship_supports=relationship_supports,
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
    facet_map: dict[str, PromptFacet] = {}
    for facet in facets.facets:
        current = facet_map.get(facet.value)
        if current is None or facet.weight > current.weight:
            facet_map[facet.value] = facet

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
        ("change-impact", {"affect", "break", "change", "changes", "impact", "migration"}),
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


def _complete_unit_bounds_with_status(
    raw: bytes, path: str, start: int, end: int
) -> tuple[int, int, bool]:
    """Find a bounded complete source unit around a verified anchor."""

    if not raw:
        return 0, 0, False
    line_start = raw.rfind(b"\n", 0, start) + 1
    line_end = raw.find(b"\n", end)
    line_end = len(raw) if line_end < 0 else line_end + 1
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return (*_line_window(raw, start, end, 1200), False)
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
            return offsets[heading_line], offsets[finish] if finish < len(offsets) else len(raw), True
        return (*_paragraph_bounds(raw, lines, offsets, anchor_line), True)

    if path.lower().endswith((".rst", ".txt")):
        return (*_paragraph_bounds(raw, lines, offsets, anchor_line), True)

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
                            return opening, index + 1, True
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
                        return line_start, index + 1, True
        indentation = len(lines[anchor_line]) - len(stripped)
        finish = anchor_line + 1
        while finish < len(lines):
            candidate = lines[finish]
            if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= indentation:
                break
            finish += 1
        return offsets[anchor_line], offsets[finish] if finish < len(offsets) else len(raw), True

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
        return offsets[begin], offsets[finish] if finish < len(offsets) else len(raw), True

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
                        return offsets[brace_declaration], len(raw) if close_end < 0 else close_end + 1, True

    return (*_line_window(raw, start, end, 1200), False)


def _complete_unit_bounds(
    raw: bytes, path: str, start: int, end: int
) -> tuple[int, int]:
    """Return the existing two-value complete-unit interface."""

    return _complete_unit_bounds_with_status(raw, path, start, end)[:2]


def _paragraph_bounds(
    raw: bytes,
    lines: Sequence[str],
    offsets: Sequence[int],
    anchor_line: int,
) -> tuple[int, int]:
    """Return the complete blank-line-delimited paragraph around an anchor."""

    begin = anchor_line
    while begin > 0 and lines[begin - 1].strip():
        begin -= 1
    finish = anchor_line + 1
    while finish < len(lines) and lines[finish].strip():
        finish += 1
    return offsets[begin], offsets[finish] if finish < len(offsets) else len(raw)


def _bounded_source_unit_bounds(
    raw: bytes,
    path: str,
    start: int,
    end: int,
    maximum: int,
) -> tuple[int, int, bool]:
    """Return a bounded source unit and whether the returned unit is complete."""

    unit_start, unit_end, complete = _complete_unit_bounds_with_status(
        raw, path, start, end
    )
    if unit_end > unit_start and unit_end - unit_start <= maximum:
        return unit_start, unit_end, complete
    if path.lower().endswith((".md", ".rst", ".txt")):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        if text:
            lines = text.splitlines(keepends=True)
            offsets: list[int] = []
            position = 0
            anchor_line = 0
            for index, line in enumerate(lines):
                offsets.append(position)
                line_end = position + len(line.encode("utf-8"))
                if position <= start < line_end:
                    anchor_line = index
                position = line_end
            paragraph_start, paragraph_end = _paragraph_bounds(
                raw, lines, offsets, anchor_line
            )
            if paragraph_end - paragraph_start <= maximum:
                return paragraph_start, paragraph_end, True
    window_start, window_end = _line_window(raw, start, end, maximum)
    return window_start, window_end, False


def _line_window(raw: bytes, start: int, end: int, maximum: int) -> tuple[int, int]:
    """Return a UTF-8-aligned window containing the entire verified anchor.

    An anchor larger than the byte budget has no admissible window. Return an
    empty range so callers cannot mistake an unrelated prefix for evidence.
    Source validity and authority remain the caller's responsibility.
    """
    if (type(start) is not int or type(end) is not int or type(maximum) is not int
            or not 0 <= start < end <= len(raw) or maximum < 1):
        raise ValueError("invalid source window bounds")
    if end - start > maximum:
        return start, start
    # Verified anchors use character boundaries. Reject invalid anchors instead
    # of moving the anchor, truncating it, or inventing a replacement range.
    if (raw[start] & 0b11000000 == 0b10000000
            or (end < len(raw) and raw[end] & 0b11000000 == 0b10000000)):
        return start, start
    available = maximum - (end - start)
    lower = max(0, start - available // 2)
    left = raw.rfind(b"\n", lower, start)
    left = lower if left < 0 else left + 1
    while left < start and raw[left] & 0b11000000 == 0b10000000:
        left += 1
    limit = min(len(raw), left + maximum)
    right = raw.find(b"\n", end, limit)
    right = limit if right < 0 else right
    while right > end and right < len(raw) and raw[right] & 0b11000000 == 0b10000000:
        right -= 1
    return left, right


__all__ = [
    "AuthorityClass", "EvidenceItem", "FacetKind", "GraphFindResult", "HybridRetrievalResult",
    "NavigationContext", "NavigationResult", "SourcePreview",
    "PromptFacet", "PromptFacetSet", "ProofObligation", "RepositoryFileCard",
    "RepositoryTag", "RepositoryTagIndex", "RetrievalHit", "RetrievalResult",
    "SourceRelationCoverage", "SourceRelationResult",
    "TagKind", "build_repository_file_cards", "build_repository_tag_index",
    "compile_prompt", "compile_proof_obligations", "match_proof_obligation", "match_proof_obligations",
    "derive_source_relations", "graph_find", "retrieve", "retrieve_hybrid", "ranked_candidates_from_retrieval",
    "navigate", "compose_navigation_context",
]
