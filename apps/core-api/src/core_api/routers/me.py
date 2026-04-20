"""Session-scoped routes for the signed-in user."""

from __future__ import annotations

from collections import defaultdict

from backfield_db import BackfieldProject, BackfieldWorkspace, BackfieldWorkspaceMembership
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, select

from core_api.authz import session_project_ids_for_user
from core_api.deps import get_auth, get_session
from core_api.routers.admin_org import (
    ProjectSummaryOut,
    WorkspaceWithProjectsOut,
    _stylebook_name_map,
)

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

    member_ws_ids: set[int] = set()
    if role != "org_admin":
        wm_rows = session.exec(
            select(BackfieldWorkspaceMembership).where(
                BackfieldWorkspaceMembership.user_id == uid,
            )
        ).all()
        for wm in wm_rows:
            if wm.workspace_id is None:
                continue
            ws = session.get(BackfieldWorkspace, int(wm.workspace_id))
            if ws is None or ws.id is None:
                continue
            if int(ws.organization_id) != org_id:
                continue
            member_ws_ids.add(int(ws.id))

    if not visible and role != "org_admin" and not member_ws_ids:
        return []

    rows = session.exec(
        select(BackfieldProject).where(BackfieldProject.organization_id == org_id)
    ).all()
    if role == "org_admin":
        projects_visible = [p for p in rows if p.id is not None]
    else:
        projects_visible = [p for p in rows if p.id is not None and int(p.id) in visible]

    by_ws: dict[int | None, list[BackfieldProject]] = defaultdict(list)
    for p in projects_visible:
        by_ws[p.workspace_id].append(p)

    entries: list[tuple[int, str, str, list[ProjectSummaryOut]]] = []
    present_ws_ids: set[int] = set()

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
        projects_out = [
            ProjectSummaryOut(id=int(p.id), name=str(p.name), slug=str(p.slug))
            for p in plist
            if p.id is not None
        ]
        entries.append((_wid, wname, wslug, projects_out))
        present_ws_ids.add(_wid)

    if role == "org_admin":
        all_ws = session.exec(
            select(BackfieldWorkspace).where(BackfieldWorkspace.organization_id == org_id)
        ).all()
        for ws in all_ws:
            if ws.id is None or int(ws.id) in present_ws_ids:
                continue
            entries.append(
                (
                    int(ws.id),
                    str(ws.name),
                    str(ws.slug),
                    [],
                )
            )
            present_ws_ids.add(int(ws.id))
    else:
        for wid in sorted(member_ws_ids):
            if wid in present_ws_ids:
                continue
            ws = session.get(BackfieldWorkspace, wid)
            if ws is None or ws.id is None:
                continue
            entries.append((int(ws.id), str(ws.name), str(ws.slug), []))
            present_ws_ids.add(int(ws.id))

    entries.sort(key=lambda t: t[2])

    wids_real = [wid for wid, _, _, _ in entries]
    ws_by_id: dict[int, BackfieldWorkspace] = {}
    if wids_real:
        wrows = session.exec(
            select(BackfieldWorkspace).where(col(BackfieldWorkspace.id).in_(wids_real))
        ).all()
        for w in wrows:
            if w.id is not None:
                ws_by_id[int(w.id)] = w
    sb_ids = {
        int(ws_by_id[wid].stylebook_id) for wid in wids_real if wid in ws_by_id
    }
    sb_labels = _stylebook_name_map(session, org_id, sb_ids)

    out: list[WorkspaceWithProjectsOut] = []
    for wid, wname, wslug, projects in entries:
        ws_row = ws_by_id.get(wid)
        if ws_row is not None:
            sid = int(ws_row.stylebook_id)
            sname = sb_labels.get(sid, "")
        else:
            sid = None
            sname = None
        out.append(
            WorkspaceWithProjectsOut(
                id=wid,
                name=wname,
                slug=wslug,
                projects=projects,
                stylebook_id=sid,
                stylebook_name=sname,
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
                    ProjectSummaryOut(id=int(p.id), name=str(p.name), slug=str(p.slug))
                    for p in plist
                    if p.id is not None
                ],
                stylebook_id=None,
                stylebook_name=None,
            )
        )

    return out
