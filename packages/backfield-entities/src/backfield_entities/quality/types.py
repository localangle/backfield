"""Shared row shapes for cleanup finders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CleanupLocationCanonicalRow:
    id: str
    slug: str
    label: str
    location_type: str | None
    status: str
    linked_substrate_count: int = 0
    mention_count: int = 0


LocationGeographyIssueKind = Literal["missing_geometry", "distant_linked_places"]


@dataclass(frozen=True)
class CleanupLocationGeographyIssueRow:
    id: str
    slug: str
    label: str
    location_type: str | None
    status: str
    issue: LocationGeographyIssueKind
    distant_linked_count: int = 0


@dataclass(frozen=True)
class CleanupNameMismatchIssueRow:
    id: str
    slug: str
    label: str
    entity_type: Literal["person", "organization"]
    status: str
    mismatched_linked_count: int
    mismatched_examples: list[str]
