"""Resolve the effective Stylebook from project context.

Catalog resolution:

1. **Explicit catalog id** — ``catalog_stylebook_id`` from caller; row must exist in project's org.
2. **Slug** — non-empty ``stylebook_slug`` in that org (rename redirects apply).
3. **Project ownership** — direct project Stylebook, then its workspace Stylebook during rollout.
4. **Organization default** — default Stylebook, then first Stylebook by id.

**Surfaces**

* Stylebook HTTP: slug query → project ownership → organization default (**2 → 3 → 4**).

* Worker **DBOutput**: ``resolve_effective_stylebook_id`` delegates here; node ``stylebook_id``
  maps to ``catalog_stylebook_id`` (**1 → 3 → 4**).

* Worker **GeocodeAgent** DB cache: project-scoped fingerprint lookup works without a catalog id;
  canonical lookup, adjudication, and materialization use only the node's catalog id, with no
  organization-default fallback.

If the fallback chain finds no Stylebook, ``LookupError`` is raised; DBOutput persistence may
catch it and skip catalog-backed canonicalization.
"""

from __future__ import annotations

from backfield_db import BackfieldProject, BackfieldWorkspace, Stylebook
from sqlmodel import Session, col, select

STYLEBOOK_SLUG_NOT_IN_ORG = "STYLEBOOK_SLUG_NOT_IN_ORG"


def resolve_stylebook_id_for_project_id(session: Session, project_id: int) -> int:
    """Return the project's owned Stylebook with rolling-upgrade fallbacks."""
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise LookupError(f"project {project_id} not found")
    oid = int(proj.organization_id)

    if proj.stylebook_id is not None:
        project_stylebook = session.get(Stylebook, int(proj.stylebook_id))
        if project_stylebook is None or int(project_stylebook.organization_id) != oid:
            raise ValueError("project Stylebook does not belong to the project's organization")
        return int(project_stylebook.id)

    if proj.workspace_id is not None:
        workspace = session.get(BackfieldWorkspace, int(proj.workspace_id))
        if workspace is None or int(workspace.organization_id) != oid:
            raise ValueError("project workspace does not belong to the project's organization")
        workspace_stylebook = session.get(Stylebook, int(workspace.stylebook_id))
        if workspace_stylebook is None or int(workspace_stylebook.organization_id) != oid:
            raise ValueError("workspace Stylebook does not belong to the project's organization")
        return int(workspace_stylebook.id)

    sb = session.exec(
        select(Stylebook)
        .where(Stylebook.organization_id == oid)
        .order_by(col(Stylebook.is_default).desc(), col(Stylebook.id).asc())
    ).first()
    if sb is None or sb.id is None:
        raise LookupError(f"organization {oid} has no stylebooks")
    return int(sb.id)


def resolve_effective_stylebook_id_for_project(
    session: Session,
    project: BackfieldProject,
    *,
    stylebook_slug: str | None = None,
    catalog_stylebook_id: int | None = None,
) -> int:
    """Effective catalog row id for the project.

    Precedence: explicit id → slug → project → workspace → organization default.

    Raises ``ValueError`` when ``catalog_stylebook_id`` is invalid or wrong organization.

    Raises ``LookupError`` with :data:`STYLEBOOK_SLUG_NOT_IN_ORG` when slug does not resolve.
    """
    oid = int(project.organization_id)
    if catalog_stylebook_id is not None:
        sb = session.get(Stylebook, int(catalog_stylebook_id))
        if sb is None or sb.id is None:
            msg = f"stylebook {catalog_stylebook_id} not found"
            raise ValueError(msg)
        if int(sb.organization_id) != oid:
            msg = "stylebook does not belong to the project's organization"
            raise ValueError(msg)
        return int(sb.id)

    raw = (stylebook_slug or "").strip()
    if not raw:
        return resolve_stylebook_id_for_project_id(session, int(project.id))
    from backfield_entities.catalog.stylebook_library import resolve_stylebook_by_slug

    row = resolve_stylebook_by_slug(session, organization_id=oid, slug=raw)
    if row is None:
        raise LookupError(STYLEBOOK_SLUG_NOT_IN_ORG)
    return int(row.id)
