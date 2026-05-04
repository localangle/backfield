"""Resolve effective Stylebook from Agate project context.

Catalog resolution (**Issue 7** bridge):

1. **Explicit catalog id** — ``catalog_stylebook_id`` from caller; row must exist in project's org.
2. **Slug** — non-empty ``stylebook_slug`` in that org (rename redirects apply).
3. **Workspace** — ``workspace.stylebook_id`` (see ``resolve_stylebook_id_for_project_id``).

**Surfaces**

* Stylebook HTTP: slug query → workspace (**2 → 3**). No integer override on routes yet.

* Worker **DBOutput**: ``resolve_effective_stylebook_id`` delegates here; node ``stylebook_id``
  maps to ``catalog_stylebook_id`` (**1 → 3**).

* Worker **GeocodeAgent** DB cache: catalog id **only** from node params when cache is on —
  **no** workspace fallback there.

If step **3** fails, ``LookupError`` is raised; DBOutput persistence may catch it and skip
catalog-backed canonicalization.
"""

from __future__ import annotations

from backfield_db import BackfieldProject, BackfieldWorkspace, Stylebook
from sqlmodel import Session

STYLEBOOK_SLUG_NOT_IN_ORG = "STYLEBOOK_SLUG_NOT_IN_ORG"


def resolve_stylebook_id_for_project_id(session: Session, project_id: int) -> int:
    """Return ``workspace.stylebook_id`` for the project's workspace.

    Raises ``LookupError`` when the project has no workspace or workspace has no Stylebook.
    """
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise LookupError(f"project {project_id} not found")
    if proj.workspace_id is None:
        raise LookupError(f"project {project_id} has no workspace_id")
    ws = session.get(BackfieldWorkspace, int(proj.workspace_id))
    if ws is None:
        raise LookupError(f"workspace {proj.workspace_id} not found")
    return int(ws.stylebook_id)


def resolve_effective_stylebook_id_for_project(
    session: Session,
    project: BackfieldProject,
    *,
    stylebook_slug: str | None = None,
    catalog_stylebook_id: int | None = None,
) -> int:
    """Effective catalog row id for the project.

    Precedence: ``catalog_stylebook_id`` → ``stylebook_slug`` → workspace catalog.

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
    from backfield_stylebook.stylebook_library import resolve_stylebook_by_slug

    row = resolve_stylebook_by_slug(session, organization_id=oid, slug=raw)
    if row is None:
        raise LookupError(STYLEBOOK_SLUG_NOT_IN_ORG)
    return int(row.id)
