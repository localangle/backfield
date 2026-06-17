"""Shared row shapes for cleanup finders."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CleanupLocationCanonicalRow:
    id: str
    slug: str
    label: str
    location_type: str | None
    status: str
    linked_substrate_count: int = 0
    mention_count: int = 0
