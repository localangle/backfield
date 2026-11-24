"""Add, restore and suppress aliases on a canonical, for every entity kind.

An alias is suppressed (never deleted) when it is removed, so the row, its provenance and its
history stay. Neither function commits; the caller owns the transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from backfield_entities.cleanup.before_state import RowJson, row_to_json
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.entities.location.persist import (
    seed_aliases_for_canonical_label as seed_location_aliases,
)
from backfield_entities.entities.organization.persist import (
    seed_aliases_for_canonical_label as seed_organization_aliases,
)
from backfield_entities.entities.person.persist import (
    seed_aliases_for_canonical_label as seed_person_aliases,
)
from backfield_entities.text.match_normalize import normalize_match_text

_SEED_ALIASES: dict[str, Callable[..., None]] = {
    "location": seed_location_aliases,
    "person": seed_person_aliases,
    "organization": seed_organization_aliases,
}


@dataclass
class AliasChange:
    """What an alias change did, with the rows as they were so it can be understood or undone."""

    changed: bool = False
    rows_changed: int = 0
    # Rows that existed before and were changed (restored or suppressed), as they were.
    rows_before: list[RowJson] = field(default_factory=list)
    # Rows the change created.
    created_alias_ids: list[int] = field(default_factory=list)


def alias_rows_for_canonical(
    session: Session, models: CleanupEntityModels, canonical_id: str
) -> list[Any]:
    column = models.column(models.alias, models.alias_canonical_column)
    return list(session.exec(select(models.alias).where(column == canonical_id)).all())


def touch_canonical(canonical: Any) -> None:
    """Move `updated_at` so incremental exports see an alias or field change."""
    canonical.updated_at = datetime.now(UTC)


def seed_label_aliases(
    session: Session,
    models: CleanupEntityModels,
    *,
    canonical_id: str,
    label: str,
    provenance: str,
) -> None:
    """Write the alias rows a name needs (one per matching variant) for one canonical."""
    _SEED_ALIASES[models.singular](
        session, canon_id=canonical_id, label=label, provenance=provenance
    )


def add_alias(
    session: Session,
    models: CleanupEntityModels,
    *,
    canonical_id: str,
    alias_text: str,
    provenance: str,
) -> AliasChange:
    """Add a name as an alias, or bring a suppressed one back. ``changed`` is False when every
    variant of the name was already active."""
    before_rows = alias_rows_for_canonical(session, models, canonical_id)
    known_ids = {row.id for row in before_rows}
    active_before = {row.normalized_alias for row in before_rows if not row.suppressed}
    suppressed_before = {row.id: row_to_json(row) for row in before_rows if row.suppressed}

    seed_label_aliases(
        session, models, canonical_id=canonical_id, label=alias_text, provenance=provenance
    )
    session.flush()

    after_rows = alias_rows_for_canonical(session, models, canonical_id)
    active_after = {row.normalized_alias for row in after_rows if not row.suppressed}
    if active_after == active_before:
        return AliasChange()
    return AliasChange(
        changed=True,
        rows_changed=len(active_after - active_before),
        rows_before=[
            suppressed_before[row.id]
            for row in after_rows
            if row.id in suppressed_before and not row.suppressed
        ],
        created_alias_ids=[int(row.id) for row in after_rows if row.id not in known_ids],
    )


def matching_alias_rows(
    session: Session, models: CleanupEntityModels, *, canonical_id: str, alias_text: str
) -> list[Any]:
    """The alias rows for a name: same text ignoring case and spacing, or same normalized form."""
    wanted = normalize_match_text(alias_text)
    return [
        row
        for row in alias_rows_for_canonical(session, models, canonical_id)
        if normalize_match_text(row.alias_text) == wanted
        or normalize_match_text(row.normalized_alias) == wanted
    ]


def suppress_alias_rows(rows: list[Any]) -> AliasChange:
    """Suppress the active rows among ``rows``. ``changed`` is False when none was active."""
    active = [row for row in rows if not row.suppressed]
    change = AliasChange(
        changed=bool(active), rows_changed=len(active), rows_before=[row_to_json(r) for r in active]
    )
    for row in active:
        row.suppressed = True
    return change
