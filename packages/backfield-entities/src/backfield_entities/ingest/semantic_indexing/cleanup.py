"""Delete semantic index rows before substrate deletes (FK safety)."""

from __future__ import annotations

from backfield_db import SubstrateLocationSemanticDocument, SubstratePersonSemanticDocument
from sqlalchemy import delete
from sqlmodel import Session


def delete_semantic_documents_for_person(
    session: Session,
    *,
    person_id: int,
    project_id: int | None = None,
) -> int:
    """Remove all semantic documents for one substrate person (before row delete)."""
    stmt = delete(SubstratePersonSemanticDocument).where(
        SubstratePersonSemanticDocument.person_id == person_id,
    )
    if project_id is not None:
        stmt = stmt.where(SubstratePersonSemanticDocument.project_id == project_id)
    result = session.exec(stmt)
    return int(result.rowcount or 0)


def delete_semantic_documents_for_location(
    session: Session,
    *,
    location_id: int,
    project_id: int | None = None,
) -> int:
    """Remove all semantic documents for one substrate location (before row delete)."""
    stmt = delete(SubstrateLocationSemanticDocument).where(
        SubstrateLocationSemanticDocument.location_id == location_id,
    )
    if project_id is not None:
        stmt = stmt.where(SubstrateLocationSemanticDocument.project_id == project_id)
    result = session.exec(stmt)
    return int(result.rowcount or 0)
