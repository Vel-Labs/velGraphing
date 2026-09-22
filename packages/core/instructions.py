"""Provider-neutral planning for caller-resolved instruction sections."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Sequence


SCHEMA_VERSION = "instruction-plan-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANDATORY_REASON = "mandatory_inherited"
_SELECTED_REASON = "caller_selected"
_OMITTED_REASON = "caller_not_selected"


class InstructionPlanError(ValueError):
    """Raised when caller-supplied instruction data is unsafe or inconsistent."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"


def _portable_path(value: object, label: str) -> str:
    if type(value) is not str or not value or "\x00" in value or "\\" in value:
        raise InstructionPlanError(f"{label} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise InstructionPlanError(f"{label} must be a normalized relative POSIX path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise InstructionPlanError(f"{label} must not contain path aliases")
    return value


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value):
        raise InstructionPlanError(f"{label} must be a non-empty string")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        raise InstructionPlanError(f"{label} contains a control character")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise InstructionPlanError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sequence(value: object, label: str) -> tuple[Any, ...]:
    if type(value) not in {list, tuple}:
        raise TypeError(f"{label} must be a list or tuple")
    return tuple(value)


@dataclass(frozen=True)
class InstructionSection:
    """One caller-resolved instruction section with source-bound content."""

    section_id: str
    source_path: str
    content_sha256: str
    content: str
    mandatory: bool

    def __post_init__(self) -> None:
        _text(self.section_id, "section_id")
        _portable_path(self.source_path, "source_path")
        _digest(self.content_sha256, "content_sha256")
        _text(self.content, "content", allow_empty=True)
        if type(self.mandatory) is not bool:
            raise TypeError("mandatory must be an exact boolean")
        if self.content_sha256 != _content_digest(self.content):
            raise InstructionPlanError("content_sha256 does not match content")

    @classmethod
    def from_dict(
        cls, value: object, *, mandatory: bool, reason: str
    ) -> "InstructionSection":
        if type(value) is not dict or set(value) != {
            "section_id", "source_path", "content_sha256", "content", "reason"
        }:
            raise InstructionPlanError("instruction section has an invalid shape")
        expected_reason = _MANDATORY_REASON if mandatory else _SELECTED_REASON
        if reason != expected_reason or value["reason"] != expected_reason:
            raise InstructionPlanError("instruction section has an invalid reason")
        return cls(
            value["section_id"],
            value["source_path"],
            value["content_sha256"],
            value["content"],
            mandatory,
        )

    def to_dict(self, *, reason: str | None = None) -> dict[str, str]:
        value = {
            "section_id": self.section_id,
            "source_path": self.source_path,
            "content_sha256": self.content_sha256,
            "content": self.content,
        }
        if reason is not None:
            expected_reason = _MANDATORY_REASON if self.mandatory else _SELECTED_REASON
            if reason != expected_reason:
                raise InstructionPlanError("instruction section has an invalid reason")
            value["reason"] = reason
        return value


@dataclass(frozen=True)
class OmittedSupplementalSection:
    """A supplemental section that the caller did not select."""

    section_id: str
    source_path: str
    content_sha256: str
    reason: str = _OMITTED_REASON

    def __post_init__(self) -> None:
        _text(self.section_id, "section_id")
        _portable_path(self.source_path, "source_path")
        _digest(self.content_sha256, "content_sha256")
        if self.reason != _OMITTED_REASON:
            raise InstructionPlanError("unsupported omission reason")

    @classmethod
    def from_dict(cls, value: object) -> "OmittedSupplementalSection":
        if type(value) is not dict or set(value) != {
            "section_id", "source_path", "content_sha256", "reason"
        }:
            raise InstructionPlanError("omitted supplemental section has an invalid shape")
        return cls(
            value["section_id"],
            value["source_path"],
            value["content_sha256"],
            value["reason"],
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "section_id": self.section_id,
            "source_path": self.source_path,
            "content_sha256": self.content_sha256,
            "reason": self.reason,
        }


def _validate_sections(
    sections: Sequence[InstructionSection],
    *,
    mandatory: bool,
    label: str,
) -> tuple[InstructionSection, ...]:
    values = _sequence(sections, label)
    result: list[InstructionSection] = []
    for item in values:
        if type(item) is not InstructionSection:
            raise TypeError(f"{label} must contain only InstructionSection values")
        if item.mandatory is not mandatory:
            raise InstructionPlanError(f"{label} contains a section with the wrong mandatory flag")
        result.append(item)
    return tuple(result)


def _unique_ids(sections: Sequence[InstructionSection]) -> None:
    ids = [section.section_id for section in sections]
    if len(ids) != len(set(ids)):
        raise InstructionPlanError("instruction section IDs must be unique")


@dataclass(frozen=True)
class InstructionPlan:
    """A deterministic plan that never lets optional selection omit rules."""

    mandatory_sections: tuple[InstructionSection, ...]
    selected_supplemental_sections: tuple[InstructionSection, ...]
    omitted_supplemental_sections: tuple[OmittedSupplementalSection, ...]

    def __post_init__(self) -> None:
        mandatory = _validate_sections(
            self.mandatory_sections, mandatory=True, label="mandatory_sections"
        )
        selected = _validate_sections(
            self.selected_supplemental_sections,
            mandatory=False,
            label="selected_supplemental_sections",
        )
        omitted = _sequence(
            self.omitted_supplemental_sections, "omitted_supplemental_sections"
        )
        if not all(type(item) is OmittedSupplementalSection for item in omitted):
            raise TypeError(
                "omitted_supplemental_sections must contain only "
                "OmittedSupplementalSection values"
            )
        _unique_ids((*mandatory, *selected))
        omitted_ids = [item.section_id for item in omitted]
        if len(omitted_ids) != len(set(omitted_ids)):
            raise InstructionPlanError("omitted supplemental IDs must be unique")
        all_ids = [section.section_id for section in (*mandatory, *selected)]
        if set(all_ids) & set(omitted_ids):
            raise InstructionPlanError("selected and omitted supplemental IDs must be disjoint")
        if not mandatory:
            raise InstructionPlanError("at least one mandatory instruction section is required")
        object.__setattr__(self, "mandatory_sections", mandatory)
        object.__setattr__(self, "selected_supplemental_sections", selected)
        object.__setattr__(self, "omitted_supplemental_sections", omitted)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mandatory_sections": [
                section.to_dict(reason=_MANDATORY_REASON)
                for section in self.mandatory_sections
            ],
            "selected_supplemental_sections": [
                section.to_dict(reason=_SELECTED_REASON)
                for section in self.selected_supplemental_sections
            ],
            "omitted_supplemental_sections": [
                section.to_dict() for section in self.omitted_supplemental_sections
            ],
            "policy": {
                "mandatory_rules_preserved": True,
                "classifier_may_omit_mandatory": False,
                "tools_activated": False,
                "host_interception_claimed": False,
            },
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> "InstructionPlan":
        if type(value) is not dict or set(value) != {
            "schema_version",
            "mandatory_sections",
            "selected_supplemental_sections",
            "omitted_supplemental_sections",
            "policy",
        }:
            raise InstructionPlanError("instruction plan has an invalid shape")
        if value["schema_version"] != SCHEMA_VERSION:
            raise InstructionPlanError("unsupported instruction plan schema")
        policy = value["policy"]
        if type(policy) is not dict or policy != {
            "mandatory_rules_preserved": True,
            "classifier_may_omit_mandatory": False,
            "tools_activated": False,
            "host_interception_claimed": False,
        }:
            raise InstructionPlanError("instruction plan policy is not fail-closed")
        mandatory_values = _sequence(value["mandatory_sections"], "mandatory_sections")
        selected_values = _sequence(
            value["selected_supplemental_sections"],
            "selected_supplemental_sections",
        )
        omitted_values = _sequence(
            value["omitted_supplemental_sections"],
            "omitted_supplemental_sections",
        )
        return cls(
            tuple(
                InstructionSection.from_dict(
                    item, mandatory=True, reason=_MANDATORY_REASON
                )
                for item in mandatory_values
            ),
            tuple(
                InstructionSection.from_dict(
                    item, mandatory=False, reason=_SELECTED_REASON
                )
                for item in selected_values
            ),
            tuple(OmittedSupplementalSection.from_dict(item) for item in omitted_values),
        )


def plan_instructions(
    mandatory_sections: Sequence[InstructionSection],
    supplemental_sections: Sequence[InstructionSection],
    selected_supplemental_ids: Sequence[str] = (),
) -> InstructionPlan:
    """Build a plan from caller-resolved sections without discovery or activation."""

    mandatory = _validate_sections(
        mandatory_sections, mandatory=True, label="mandatory_sections"
    )
    supplemental = _validate_sections(
        supplemental_sections, mandatory=False, label="supplemental_sections"
    )
    _unique_ids((*mandatory, *supplemental))
    selected_ids = _sequence(selected_supplemental_ids, "selected_supplemental_ids")
    if not all(type(item) is str and item for item in selected_ids):
        raise InstructionPlanError("selected supplemental IDs must be non-empty strings")
    if len(selected_ids) != len(set(selected_ids)):
        raise InstructionPlanError("selected supplemental IDs must be unique")
    supplemental_by_id = {section.section_id: section for section in supplemental}
    unknown = [item for item in selected_ids if item not in supplemental_by_id]
    if unknown:
        raise InstructionPlanError("selected supplemental ID is unknown")
    selected_set = set(selected_ids)
    selected = tuple(section for section in supplemental if section.section_id in selected_set)
    omitted = tuple(
        OmittedSupplementalSection(
            section.section_id,
            section.source_path,
            section.content_sha256,
        )
        for section in supplemental
        if section.section_id not in selected_set
    )
    return InstructionPlan(mandatory, selected, omitted)
