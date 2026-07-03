"""Helpers for stylebook_connections (directed graph between canonicals)."""

from __future__ import annotations

from uuid import UUID

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.catalog.resolve import resolve_stylebook_id_for_project_id
from backfield_entities.registry.entity_types import all_entity_types
from fastapi import HTTPException
from sqlmodel import Session, select

CONNECTION_ENTITY_TYPES = all_entity_types()

ALLOWED_CONNECTION_PAIRS = (
    ("location", "person"),
    ("person", "location"),
    ("organization", "location"),
    ("location", "organization"),
    ("organization", "person"),
    ("person", "organization"),
    ("work", "person"),
    ("person", "work"),
    ("work", "organization"),
    ("organization", "work"),
    ("work", "location"),
    ("location", "work"),
    ("person", "person"),
    ("organization", "organization"),
    ("location", "location"),
    ("work", "work"),
)


def _location_display_name(
    session: Session,
    *,
    project_id: int,
    location_canonical_id: str,
    catalog_stylebook_id: int | None = None,
) -> str | None:
    try:
        stylebook_id = (
            int(catalog_stylebook_id)
            if catalog_stylebook_id is not None
            else resolve_stylebook_id_for_project_id(session, project_id)
        )
    except LookupError:
        return None
    row = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.id == location_canonical_id,
            StylebookLocationCanonical.stylebook_id == int(stylebook_id),
        )
    ).first()
    if row is None:
        return None
    return (row.label or "").strip() or None


def _person_display_name(
    session: Session,
    *,
    project_id: int,
    person_canonical_id: str,
    catalog_stylebook_id: int | None = None,
) -> str | None:
    try:
        stylebook_id = (
            int(catalog_stylebook_id)
            if catalog_stylebook_id is not None
            else resolve_stylebook_id_for_project_id(session, project_id)
        )
    except LookupError:
        return None
    row = session.exec(
        select(StylebookPersonCanonical).where(
            StylebookPersonCanonical.id == person_canonical_id,
            StylebookPersonCanonical.stylebook_id == int(stylebook_id),
        )
    ).first()
    if row is None:
        return None
    return (row.label or "").strip() or None


def _organization_display_name(
    session: Session,
    *,
    project_id: int,
    organization_canonical_id: str,
    catalog_stylebook_id: int | None = None,
) -> str | None:
    try:
        stylebook_id = (
            int(catalog_stylebook_id)
            if catalog_stylebook_id is not None
            else resolve_stylebook_id_for_project_id(session, project_id)
        )
    except LookupError:
        return None
    row = session.exec(
        select(StylebookOrganizationCanonical).where(
            StylebookOrganizationCanonical.id == organization_canonical_id,
            StylebookOrganizationCanonical.stylebook_id == int(stylebook_id),
        )
    ).first()
    if row is None:
        return None
    return (row.label or "").strip() or None


def normalize_connection_entity_id(entity_type: str, entity_id: str | int | UUID) -> str:
    """Normalize API ids to the TEXT stored on ``stylebook_connections``."""
    if entity_type in ("location", "person", "organization"):
        if isinstance(entity_id, UUID):
            return str(entity_id)
        s = str(entity_id).strip()
        try:
            UUID(s)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"{entity_type} entity_id must be a UUID",
            ) from e
        return s
    return str(int(entity_id))


def get_canonical_display_name(
    session: Session,
    project_id: int,
    entity_type: str,
    entity_id: str | int | UUID,
    catalog_stylebook_id: int | None = None,
) -> str | None:
    eid = normalize_connection_entity_id(entity_type, entity_id)
    if entity_type == "location":
        return _location_display_name(
            session,
            project_id=project_id,
            location_canonical_id=eid,
            catalog_stylebook_id=catalog_stylebook_id,
        )
    if entity_type == "person":
        return _person_display_name(
            session,
            project_id=project_id,
            person_canonical_id=eid,
            catalog_stylebook_id=catalog_stylebook_id,
        )
    if entity_type == "organization":
        return _organization_display_name(
            session,
            project_id=project_id,
            organization_canonical_id=eid,
            catalog_stylebook_id=catalog_stylebook_id,
        )
    return None


def validate_canonical_exists(
    session: Session,
    project_id: int,
    entity_type: str,
    entity_id: str | int | UUID,
    catalog_stylebook_id: int | None = None,
) -> None:
    if entity_type not in CONNECTION_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type: {entity_type}. Allowed: {list(CONNECTION_ENTITY_TYPES)}",
        )
    eid = normalize_connection_entity_id(entity_type, entity_id)
    name = get_canonical_display_name(
        session, project_id, entity_type, eid, catalog_stylebook_id
    )
    if name is None:
        raise HTTPException(
            status_code=404,
            detail=f"Canonical {entity_type} with id {eid} not found in project",
        )


def validate_connection_pair(from_entity_type: str, to_entity_type: str) -> None:
    if (from_entity_type, to_entity_type) not in ALLOWED_CONNECTION_PAIRS:
        raise HTTPException(
            status_code=400,
            detail=f"Connections from {from_entity_type} to {to_entity_type} are not allowed",
        )


def validate_not_self_connection(
    from_entity_type: str,
    from_entity_id: str,
    to_entity_type: str,
    to_entity_id: str,
) -> None:
    if from_entity_type == to_entity_type and from_entity_id == to_entity_id:
        raise HTTPException(status_code=400, detail="Cannot connect an entity to itself")


def normalize_manual_connection_nature(nature: str | None) -> str | None:
    if nature is None:
        return None
    stripped = nature.strip().lower()
    return stripped or None


def normalize_manual_connection_description(description: str | None) -> str | None:
    if description is None:
        return None
    stripped = description.strip()
    return stripped or None


def validate_manual_connection_labels(
    *,
    nature: str | None,
    description: str | None,
) -> tuple[str | None, str | None]:
    normalized_nature = normalize_manual_connection_nature(nature)
    normalized_description = normalize_manual_connection_description(description)
    if normalized_nature is None and normalized_description is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of nature or description",
        )
    return normalized_nature, normalized_description
