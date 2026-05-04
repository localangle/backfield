"""Resolve effective Stylebook from Agate project context."""

from __future__ import annotations

from backfield_db import BackfieldProject, BackfieldWorkspace
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
) -> int:
    """Catalog row id for Stylebook API calls (locations, meta, candidates, …).

    When ``stylebook_slug`` is empty, use the workspace Stylebook for the project.
    Otherwise resolve that slug in the **project's organization** (including rename
    redirects). Raises ``LookupError`` with message :data:`STYLEBOOK_SLUG_NOT_IN_ORG`
    when the slug is set but not found.
    """
    raw = (stylebook_slug or "").strip()
    if not raw:
        return resolve_stylebook_id_for_project_id(session, int(project.id))
    from backfield_stylebook.stylebook_library import resolve_stylebook_by_slug

    org_id = int(project.organization_id)
    row = resolve_stylebook_by_slug(session, organization_id=org_id, slug=raw)
    if row is None:
        raise LookupError(STYLEBOOK_SLUG_NOT_IN_ORG)
    return int(row.id)
