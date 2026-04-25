"""Resolve effective Stylebook from Agate project context."""

from __future__ import annotations

from backfield_db import BackfieldProject, BackfieldWorkspace
from sqlmodel import Session


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
