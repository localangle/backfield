"""Resolve the authoritative Stylebook from project ownership."""

from __future__ import annotations

from backfield_db import BackfieldProject, Stylebook
from sqlmodel import Session

STYLEBOOK_SLUG_NOT_IN_ORG = "STYLEBOOK_SLUG_NOT_IN_ORG"
STYLEBOOK_OVERRIDE_CONFLICT = "STYLEBOOK_OVERRIDE_CONFLICT"


def resolve_stylebook_id_for_project_id(session: Session, project_id: int) -> int:
    """Return the project's directly owned Stylebook."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise LookupError(f"project {project_id} not found")
    oid = int(proj.organization_id)
    project_stylebook = session.get(Stylebook, int(proj.stylebook_id))
    if project_stylebook is None or int(project_stylebook.organization_id) != oid:
        raise ValueError("project Stylebook does not belong to the project's organization")
    return int(project_stylebook.id)


def resolve_effective_stylebook_id_for_project(
    session: Session,
    project: BackfieldProject,
    *,
    stylebook_slug: str | None = None,
    catalog_stylebook_id: int | None = None,
) -> int:
    """Return project ownership, accepting only matching compatibility overrides."""
    oid = int(project.organization_id)
    if project.id is None:
        raise ValueError("project row has no id")
    project_stylebook_id = resolve_stylebook_id_for_project_id(session, int(project.id))
    if catalog_stylebook_id is not None:
        sb = session.get(Stylebook, int(catalog_stylebook_id))
        if sb is None or sb.id is None:
            msg = f"stylebook {catalog_stylebook_id} not found"
            raise ValueError(msg)
        if int(sb.organization_id) != oid:
            msg = "stylebook does not belong to the project's organization"
            raise ValueError(msg)
        if int(sb.id) != project_stylebook_id:
            raise ValueError(
                f"{STYLEBOOK_OVERRIDE_CONFLICT}: explicit Stylebook does not match "
                "project assignment"
            )

    raw = (stylebook_slug or "").strip()
    if not raw:
        return project_stylebook_id
    from backfield_entities.catalog.stylebook_library import resolve_stylebook_by_slug

    row = resolve_stylebook_by_slug(session, organization_id=oid, slug=raw)
    if row is None:
        raise LookupError(STYLEBOOK_SLUG_NOT_IN_ORG)
    if int(row.id) != project_stylebook_id:
        raise ValueError(
            f"{STYLEBOOK_OVERRIDE_CONFLICT}: Stylebook name does not match project assignment"
        )
    return project_stylebook_id
