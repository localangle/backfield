"""Authorization boundary for project-owned candidate operations."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import BackfieldProject, Stylebook
from fastapi import HTTPException
from sqlmodel import Session
from stylebook_api.stylebook_permissions import require_stylebook_edit_access_by_id
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org


def require_candidate_project_in_stylebook(
    session: Session,
    *,
    auth: dict[str, Any],
    project_id: int,
    stylebook_slug: str | None,
    project_slug: str | None = None,
    require_edit: bool = False,
) -> tuple[BackfieldProject, Stylebook]:
    """Reload and authorize a candidate's project within the requested Stylebook."""

    project = session.get(BackfieldProject, project_id)
    if project is None or project.id is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project_slug is not None and project.slug != project_slug:
        raise HTTPException(status_code=404, detail="Candidate not found")
    require_project_access(session, auth, int(project.id))
    if stylebook_slug is None:
        stylebook = session.get(Stylebook, int(project.stylebook_id))
        if stylebook is None:
            raise HTTPException(status_code=404, detail="Stylebook not found")
    else:
        stylebook = require_stylebook_by_slug_in_auth_org(
            session,
            auth=auth,
            stylebook_slug=stylebook_slug,
        )
    if stylebook.id is None or int(project.stylebook_id) != int(stylebook.id):
        raise HTTPException(status_code=404, detail="Candidate not found")
    if require_edit:
        require_stylebook_edit_access_by_id(
            session,
            auth=auth,
            stylebook_id=int(stylebook.id),
        )
    return project, stylebook
