"""Explicit helpers for test projects under strict tenancy metadata."""

from __future__ import annotations

from typing import Final

from backfield_db import BackfieldWorkspace, Stylebook
from sqlmodel import Session, col, select

_UNSET: Final = object()


def project_ownership_fields(
    session: Session,
    organization_id: int,
    *,
    workspace_id: int | None | object = _UNSET,
    stylebook_id: int | None | object = _UNSET,
) -> dict[str, int]:
    """Return only missing project ownership fields, creating valid test rows as needed."""
    organization_id = int(organization_id)
    workspace = None
    if workspace_id is not _UNSET and workspace_id is not None:
        workspace = session.get(BackfieldWorkspace, int(workspace_id))
        if workspace is None or int(workspace.organization_id) != organization_id:
            raise ValueError("test project workspace must belong to its organization")

    stylebook = None
    if stylebook_id is not _UNSET and stylebook_id is not None:
        stylebook = session.get(Stylebook, int(stylebook_id))
        if stylebook is None or int(stylebook.organization_id) != organization_id:
            raise ValueError("test project Stylebook must belong to its organization")
    elif workspace is not None:
        stylebook = session.get(Stylebook, int(workspace.stylebook_id))

    if stylebook is None:
        stylebook = session.exec(
            select(Stylebook)
            .where(Stylebook.organization_id == organization_id)
            .order_by(col(Stylebook.is_default).desc(), col(Stylebook.id).asc())
        ).first()
    if stylebook is None:
        stylebook = Stylebook(
            organization_id=organization_id,
            name=f"Test Stylebook {organization_id}",
            slug=f"test-stylebook-{organization_id}",
            is_default=True,
        )
        session.add(stylebook)
        session.flush()

    if workspace is None:
        workspace = session.exec(
            select(BackfieldWorkspace)
            .where(
                BackfieldWorkspace.organization_id == organization_id,
                BackfieldWorkspace.stylebook_id == int(stylebook.id),
            )
            .order_by(col(BackfieldWorkspace.id).asc())
        ).first()
    if workspace is None:
        workspace = BackfieldWorkspace(
            organization_id=organization_id,
            stylebook_id=int(stylebook.id),
            name=f"Test Workspace {organization_id}",
            slug=f"test-workspace-{organization_id}-{int(stylebook.id)}",
        )
        session.add(workspace)
        session.flush()

    fields: dict[str, int] = {}
    if workspace_id is _UNSET or workspace_id is None:
        fields["workspace_id"] = int(workspace.id)
    if stylebook_id is _UNSET or stylebook_id is None:
        fields["stylebook_id"] = int(stylebook.id)
    return fields
