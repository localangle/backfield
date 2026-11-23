"""`merged_into`: where a merged-away canonical id went, so old ids keep resolving."""

from __future__ import annotations

from backfield_db import StylebookCanonicalRedirect
from pydantic import BaseModel
from sqlalchemy import update
from sqlmodel import Session, col, select

MAX_REDIRECT_HOPS = 25


class CanonicalResolution(BaseModel):
    """Where a canonical id leads: itself, or the survivor it was merged into."""

    entity_type: str
    requested_id: str
    resolved_id: str
    merged: bool


def record_redirect(
    session: Session, *, stylebook_id: int, entity_type: str, old_id: str, new_id: str
) -> StylebookCanonicalRedirect:
    """Point ``old_id`` at ``new_id`` and shorten every chain that ended at ``old_id``.

    Keeps redirects one hop deep in practice, so resolving an old id is one lookup.
    """
    session.execute(
        update(StylebookCanonicalRedirect)
        .where(
            StylebookCanonicalRedirect.stylebook_id == stylebook_id,
            StylebookCanonicalRedirect.entity_type == entity_type,
            StylebookCanonicalRedirect.new_id == old_id,
        )
        .values(new_id=new_id)
    )
    existing = session.exec(
        select(StylebookCanonicalRedirect).where(
            StylebookCanonicalRedirect.stylebook_id == stylebook_id,
            StylebookCanonicalRedirect.entity_type == entity_type,
            StylebookCanonicalRedirect.old_id == old_id,
        )
    ).first()
    if existing is not None:
        existing.new_id = new_id
        session.add(existing)
        return existing
    redirect = StylebookCanonicalRedirect(
        stylebook_id=stylebook_id, entity_type=entity_type, old_id=old_id, new_id=new_id
    )
    session.add(redirect)
    return redirect


def link_redirect_to_action(
    session: Session, *, stylebook_id: int, entity_type: str, old_id: str, action_id: str
) -> None:
    """Record which ledger row made a redirect (the action row must already be flushed)."""
    session.execute(
        update(StylebookCanonicalRedirect)
        .where(
            StylebookCanonicalRedirect.stylebook_id == stylebook_id,
            StylebookCanonicalRedirect.entity_type == entity_type,
            col(StylebookCanonicalRedirect.old_id) == old_id,
        )
        .values(action_id=action_id)
    )


def resolve_canonical(
    session: Session, *, stylebook_id: int, entity_type: str, canonical_id: str
) -> CanonicalResolution:
    """Follow ``merged_into`` to the current id (the id itself when it was never merged away)."""
    current = canonical_id
    for _ in range(MAX_REDIRECT_HOPS):
        next_id = session.exec(
            select(StylebookCanonicalRedirect.new_id).where(
                StylebookCanonicalRedirect.stylebook_id == stylebook_id,
                StylebookCanonicalRedirect.entity_type == entity_type,
                StylebookCanonicalRedirect.old_id == current,
            )
        ).first()
        if next_id is None or next_id == current:
            break
        current = str(next_id)
    return CanonicalResolution(
        entity_type=entity_type,
        requested_id=canonical_id,
        resolved_id=current,
        merged=current != canonical_id,
    )
