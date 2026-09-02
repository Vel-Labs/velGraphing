"""Typed retention, exact pinning, and foldable source detail."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib


class RetentionClass(str, Enum):
    PINNED_RULE = "pinned_rule"
    EVIDENCE = "evidence"
    DETAIL = "detail"
    EPHEMERAL = "ephemeral"
    SUMMARY = "summary"


@dataclass(frozen=True)
class RetainedItem:
    item_id: str
    retention: RetentionClass
    content: str
    source_item_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "retention": self.retention.value,
            "content": self.content,
            "source_item_ids": list(self.source_item_ids),
        }


@dataclass(frozen=True)
class RetentionState:
    active: tuple[RetainedItem, ...]
    archive: tuple[RetainedItem, ...] = ()
    cycles: int = 0

    def retrieve(self, item_id: str) -> RetainedItem | None:
        return next(
            (item for item in (*self.active, *self.archive) if item.item_id == item_id),
            None,
        )


def compact(state: RetentionState, *, max_active: int) -> RetentionState:
    """Compact one cycle while preserving every pinned rule byte-for-byte."""

    pinned = [item for item in state.active if item.retention is RetentionClass.PINNED_RULE]
    if len(pinned) > max_active:
        raise ValueError("max_active cannot hold all pinned rules")
    others = [item for item in state.active if item.retention is not RetentionClass.PINNED_RULE]
    priority = {
        RetentionClass.EVIDENCE: 0,
        RetentionClass.SUMMARY: 1,
        RetentionClass.DETAIL: 2,
        RetentionClass.EPHEMERAL: 3,
        RetentionClass.PINNED_RULE: -1,
    }
    others.sort(key=lambda item: (priority[item.retention], item.item_id))
    keep_count = max_active - len(pinned)
    kept = others[:keep_count]
    folded = others[keep_count:]
    archive_by_id = {item.item_id: item for item in state.archive}
    for item in folded:
        archive_by_id[item.item_id] = item
    if folded and keep_count > 0:
        summary = _fold_summary(folded, state.cycles + 1)
        if kept:
            displaced = kept.pop()
            archive_by_id[displaced.item_id] = displaced
        kept.append(summary)
    active = tuple(sorted((*pinned, *kept), key=lambda item: item.item_id))
    return RetentionState(
        active=active,
        archive=tuple(archive_by_id[key] for key in sorted(archive_by_id)),
        cycles=state.cycles + 1,
    )


def _fold_summary(items: list[RetainedItem], cycle: int) -> RetainedItem:
    source_ids = tuple(sorted(item.item_id for item in items))
    digest = hashlib.sha256("\n".join(source_ids).encode("utf-8")).hexdigest()[:16]
    previews = [" ".join(item.content.split())[:80] for item in sorted(items, key=lambda x: x.item_id)]
    return RetainedItem(
        item_id=f"fold-{cycle}-{digest}",
        retention=RetentionClass.SUMMARY,
        content=" | ".join(previews),
        source_item_ids=source_ids,
    )
