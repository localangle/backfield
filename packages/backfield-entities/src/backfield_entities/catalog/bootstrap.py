"""Per-organization default Stylebook (bootstrap)."""

from __future__ import annotations

from backfield_db import Stylebook
from sqlmodel import Session, select


def ensure_default_stylebook_for_organization(session: Session, organization_id: int) -> Stylebook:
    """Return the org default Stylebook, creating slug ``default`` if missing (idempotent)."""
    row = session.exec(
        select(Stylebook).where(
            Stylebook.organization_id == organization_id,
            Stylebook.is_default == True,  # noqa: E712
        )
    ).first()
    if row is not None:
        return row

    legacy = session.exec(
        select(Stylebook).where(
            Stylebook.organization_id == organization_id,
            Stylebook.slug == "default",
        )
    ).first()
    if legacy is not None:
        legacy.is_default = True
        session.add(legacy)
        session.flush()
        return legacy

    sb = Stylebook(
        organization_id=organization_id,
        slug="default",
        name="Default Stylebook",
        is_default=True,
    )
    session.add(sb)
    session.flush()
    session.refresh(sb)
    return sb
