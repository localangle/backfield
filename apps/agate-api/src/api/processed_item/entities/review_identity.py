"""Deterministic identity helpers for processed-item entity enrichment."""

from __future__ import annotations

import re
from typing import Any, TypeVar

EntityT = TypeVar("EntityT")

_POSITIONAL_RAW_ENTRY_ID_RE = re.compile(r"^stylebook_output:\d+$")


def source_raw_entry_id(
    source_details: Any,
    *,
    run_id: str | None = None,
) -> str | None:
    """Return a normalized source anchor, optionally restricted to one run."""
    if not isinstance(source_details, dict):
        return None
    if run_id is not None and str(source_details.get("run_id") or "") != run_id:
        return None
    raw = source_details.get("raw_entry_id")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def is_safe_legacy_raw_entry_id(value: str) -> bool:
    """Legacy shared-entity anchors are safe only when they are not list positions."""
    return bool(value) and _POSITIONAL_RAW_ENTRY_ID_RE.fullmatch(value) is None


def add_unique_index(
    index: dict[str, EntityT | None],
    *,
    key: str | None,
    entity: EntityT,
) -> None:
    """Index a key only while it uniquely identifies one entity."""
    if not key:
        return
    if key not in index:
        index[key] = entity
        return
    if index[key] is not entity:
        index[key] = None


def ordered_row_keys(payload: Any, anchor: Any) -> list[str]:
    """Return stable lookup priority without unordered-set behavior."""
    keys: list[str] = []

    def add(raw: Any) -> None:
        if raw is None:
            return
        value = str(raw).strip()
        if value and value not in keys:
            keys.append(value)

    add(anchor)
    if isinstance(payload, dict):
        add(payload.get("id"))
        add(payload.get("mention_id"))
    return keys
