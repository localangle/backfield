"""Shared canonical persist plan types (entity-neutral)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# LLM must assert definitive same-entity identity; below this we keep review / materialize.
ADJUDICATION_LINK_MIN_CONFIDENCE = 0.9
# When organization_type labels differ only within editorially compatible pairs, accept a
# slightly lower LLM confidence after alias/name match (see organization_types_are_link_compatible).
ADJUDICATION_COMPATIBLE_TYPE_LINK_MIN_CONFIDENCE = 0.75


class CanonicalPersistDecision(StrEnum):
    DEFER = "defer"
    LINK_EXISTING = "link_existing"
    MATERIALIZE_NEW = "materialize_new"


@dataclass(frozen=True)
class CanonicalPersistPlan:
    decision: CanonicalPersistDecision
    """When ``LINK_EXISTING``, the canonical row id to attach."""

    existing_canonical_id: str | None = None
    """Structured audit trail persisted on substrate ``canonical_review_reasons_json``."""

    resolution_reasons: tuple[dict[str, Any], ...] = ()
