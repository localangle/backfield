"""Resolve Stylebook catalog scope for public project routes."""

from __future__ import annotations

from backfield_db import BackfieldProject, StylebookPersonCanonical
from sqlmodel import Session, select

from backfield_entities.catalog.resolve import resolve_effective_stylebook_id_for_project


def resolve_public_stylebook_id(session: Session, project: BackfieldProject) -> int:
    """Effective Stylebook catalog id for a public API project."""
    return resolve_effective_stylebook_id_for_project(session, project)


def get_public_person_canonical(
    session: Session,
    *,
    stylebook_id: int,
    person_id: str,
) -> StylebookPersonCanonical | None:
    """Load an active canonical person in the project's Stylebook."""
    canon = session.get(StylebookPersonCanonical, person_id.strip())
    if canon is None or int(canon.stylebook_id) != stylebook_id:
        return None
    if str(canon.status) != "active":
        return None
    return canon


def list_public_person_type_values(session: Session, *, stylebook_id: int) -> list[str]:
    from sqlalchemy import func

    from backfield_entities.entities.person.types import PERSON_TYPE_VALUES

    rows = session.exec(
        select(StylebookPersonCanonical.person_type).where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            StylebookPersonCanonical.status == "active",
            StylebookPersonCanonical.person_type.isnot(None),
            func.length(func.trim(StylebookPersonCanonical.person_type)) > 0,
        )
    ).all()
    stored = {str(r).strip() for r in rows if r is not None and str(r).strip()}
    return sorted(set(PERSON_TYPE_VALUES) | stored)
