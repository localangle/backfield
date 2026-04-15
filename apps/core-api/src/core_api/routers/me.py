"""Session-scoped routes for the signed-in user."""

from __future__ import annotations

from collections import defaultdict

from backfield_db import BackfieldProject, BackfieldWorkspace
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from core_api.authz import session_project_ids_for_user
from core_api.deps import get_auth, get_session
from core_api.routers.admin_org import ProjectSummaryOut, WorkspaceWithProjectsOut

router = APIRouter(prefix="/me", tags=["me"])

# Sentinel for projects with no workspace_id (legacy / unassigned).
_UNGROUPED_ID = -1
_UNGROUPED_SLUG = "_ungrouped"


@router.get("/workspaces", response_model=list[WorkspaceWithProjectsOut])
def list_my_workspaces(
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[WorkspaceWithProjectsOut]:
    """Workspaces and projects the current user may access (session only)."""
    if auth["type"] != "session":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session required",
        )
    org_id = int(auth["organization_id"])
    uid = int(auth["user"].id)
    role = str(auth.get("org_role") or "member")
    visible = set(
        session_project_ids_for_user(
            session,
            user_id=uid,
            organization_id=org_id,
            org_role=role,
        )
    )
    if not visible:
        return []

    rows = session.exec(
        select(BackfieldProject).where(BackfieldProject.organization_id == org_id)
    ).all()
    projects_visible = [p for p in rows if p.id is not None and int(p.id) in visible]

    by_ws: dict[int | None, list[BackfieldProject]] = defaultdict(list)
    for p in projects_visible:
        by_ws[p.workspace_id].append(p)

    out: list[WorkspaceWithProjectsOut] = []

    ws_keys = [k for k in by_ws if k is not None]
    ws_meta: list[tuple[int, str, str]] = []
    for wid in ws_keys:
        ws = session.get(BackfieldWorkspace, wid)
        if ws is None or ws.id is None:
            continue
        ws_meta.append((int(ws.id), str(ws.name), str(ws.slug)))
    ws_meta.sort(key=lambda t: t[2])

    for _wid, wname, wslug in ws_meta:
        plist = sorted(by_ws[_wid], key=lambda p: p.slug)
        out.append(
            WorkspaceWithProjectsOut(
                id=_wid,
                name=wname,
                slug=wslug,
                projects=[
                    ProjectSummaryOut(
                        id=int(p.id), name=str(p.name), slug=str(p.slug)
                    )
                    for p in plist
                    if p.id is not None
                ],
            )
        )

    if None in by_ws and by_ws[None]:
        plist = sorted(by_ws[None], key=lambda p: p.slug)
        out.append(
            WorkspaceWithProjectsOut(
                id=_UNGROUPED_ID,
                name="Other projects",
                slug=_UNGROUPED_SLUG,
                projects=[
                    ProjectSummaryOut(
                        id=int(p.id), name=str(p.name), slug=str(p.slug)
                    )
                    for p in plist
                    if p.id is not None
                ],
            )
        )

    return out
