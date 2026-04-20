"""Org admin: users and project memberships in an organization."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldUser,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
    Stylebook,
)
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select

from core_api.authz import require_org_admin
from core_api.deps import get_auth, get_session
from core_api.security import hash_password

router = APIRouter(prefix="/organizations", tags=["admin"])


def _slugify_workspace_name(name: str) -> str:
    s = name.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "workspace"


def _allocate_workspace_slug(session: Session, org_id: int, name: str) -> str:
    base = _slugify_workspace_name(name)
    slug = base
    n = 2
    while True:
        hit = session.exec(
            select(BackfieldWorkspace.id).where(
                BackfieldWorkspace.organization_id == org_id,
                BackfieldWorkspace.slug == slug,
            )
        ).first()
        if hit is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


class UserCreateBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None
    role: str = "member"


class ProjectMembershipOut(BaseModel):
    project_id: int
    slug: str
    name: str
    role: str | None = None


class WorkspaceMembershipOut(BaseModel):
    id: int
    name: str
    slug: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str | None
    role: str
    disabled_at: datetime | None = None
    project_memberships: list[ProjectMembershipOut] | None = None
    workspace_memberships: list[WorkspaceMembershipOut] | None = None


class ProjectSummaryOut(BaseModel):
    id: int
    name: str
    slug: str


class UserPatchBody(BaseModel):
    display_name: str | None = None
    role: str | None = None


class MembershipRow(BaseModel):
    project_id: int
    role: str | None = None


class ReplaceProjectMembershipsBody(BaseModel):
    memberships: list[MembershipRow]


class ReplaceWorkspaceMembershipsBody(BaseModel):
    workspace_ids: list[int]


class WorkspaceWithProjectsOut(BaseModel):
    id: int
    name: str
    slug: str
    projects: list[ProjectSummaryOut]
    stylebook_id: int | None = None
    stylebook_name: str | None = None


class StylebookListOut(BaseModel):
    id: int
    name: str
    slug: str
    is_default: bool


class OrganizationOut(BaseModel):
    id: int
    name: str
    slug: str


class OrganizationPatchBody(BaseModel):
    name: str


class WorkspaceCreateBody(BaseModel):
    name: str
    """Attach an existing org Stylebook; default is the org bootstrap Stylebook."""

    stylebook_id: int | None = None


class WorkspacePatchBody(BaseModel):
    name: str | None = None
    stylebook_id: int | None = None


def _org_project_ids(session: Session, org_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == org_id)
    ).all()
    return [int(r) for r in rows if r is not None]


def _stylebook_must_belong_to_org(session: Session, org_id: int, stylebook_id: int) -> None:
    sb = session.get(Stylebook, stylebook_id)
    if sb is None or int(sb.organization_id) != org_id:
        raise HTTPException(status_code=400, detail="Stylebook not found in this organization")


def _stylebook_name_map(session: Session, org_id: int, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = session.exec(
        select(Stylebook).where(
            Stylebook.organization_id == org_id,
            col(Stylebook.id).in_(ids),
        )
    ).all()
    return {int(r.id): str(r.name) for r in rows if r.id is not None}


def _org_workspace_ids(session: Session, org_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldWorkspace.id).where(BackfieldWorkspace.organization_id == org_id)
    ).all()
    return [int(r) for r in rows if r is not None]


def _workspace_with_projects_out(
    session: Session, org_id: int, wid: int
) -> WorkspaceWithProjectsOut | None:
    ws = session.get(BackfieldWorkspace, wid)
    if ws is None or ws.id is None or int(ws.organization_id) != org_id:
        return None
    plist_rows = session.exec(
        select(BackfieldProject).where(
            BackfieldProject.organization_id == org_id,
            BackfieldProject.workspace_id == int(ws.id),
        )
    ).all()
    projects_out = [
        ProjectSummaryOut(id=int(p.id), name=str(p.name), slug=str(p.slug))
        for p in plist_rows
        if p.id is not None
    ]
    projects_out.sort(key=lambda x: x.slug)
    sb_id = int(ws.stylebook_id)
    sb_names = _stylebook_name_map(session, org_id, {sb_id})
    return WorkspaceWithProjectsOut(
        id=int(ws.id),
        name=str(ws.name),
        slug=str(ws.slug),
        projects=projects_out,
        stylebook_id=sb_id,
        stylebook_name=sb_names.get(sb_id, ""),
    )


def _workspace_memberships_for_user_org(
    session: Session, org_id: int, user_id: int
) -> list[WorkspaceMembershipOut]:
    wm_rows = session.exec(
        select(BackfieldWorkspaceMembership).where(
            BackfieldWorkspaceMembership.user_id == user_id,
        )
    ).all()
    out: list[WorkspaceMembershipOut] = []
    for wm in wm_rows:
        if wm.workspace_id is None:
            continue
        ws = session.get(BackfieldWorkspace, wm.workspace_id)
        if ws is None or int(ws.organization_id) != org_id:
            continue
        out.append(
            WorkspaceMembershipOut(id=int(ws.id), name=str(ws.name), slug=str(ws.slug))
        )
    return sorted(out, key=lambda x: x.slug)


def _membership_for_user_org(
    session: Session, org_id: int, user_id: int
) -> BackfieldOrganizationMembership | None:
    return session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.organization_id == org_id,
            BackfieldOrganizationMembership.user_id == user_id,
        )
    ).first()


def _active_org_admin_count(session: Session, org_id: int) -> int:
    mems = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.organization_id == org_id,
            BackfieldOrganizationMembership.role == "org_admin",
        )
    ).all()
    n = 0
    for m in mems:
        u = session.get(BackfieldUser, m.user_id)
        if u is not None and u.disabled_at is None:
            n += 1
    return n


def _is_only_active_org_admin(session: Session, org_id: int, user_id: int) -> bool:
    m = _membership_for_user_org(session, org_id, user_id)
    if m is None or str(m.role) != "org_admin":
        return False
    return _active_org_admin_count(session, org_id) == 1


@router.patch("/{org_id}", response_model=OrganizationOut)
def patch_organization(
    org_id: int,
    body: OrganizationPatchBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> OrganizationOut:
    """Update organization display fields (publication name). Org admins only."""
    require_org_admin(session, auth, org_id)
    org = session.get(BackfieldOrganization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    org.name = name
    session.add(org)
    session.commit()
    session.refresh(org)
    if org.id is None:
        raise HTTPException(status_code=500, detail="Organization persist failed")
    return OrganizationOut(id=int(org.id), name=str(org.name), slug=str(org.slug))


@router.get("/{org_id}/projects", response_model=list[ProjectSummaryOut])
def list_org_projects(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_org_admin(session, auth, org_id)
    rows = session.exec(
        select(BackfieldProject).where(BackfieldProject.organization_id == org_id)
    ).all()
    out: list[ProjectSummaryOut] = []
    for p in rows:
        if p.id is None:
            continue
        out.append(ProjectSummaryOut(id=int(p.id), name=str(p.name), slug=str(p.slug)))
    return sorted(out, key=lambda x: x.slug)


@router.get("/{org_id}/stylebooks", response_model=list[StylebookListOut])
def list_org_stylebooks(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> list[StylebookListOut]:
    """List org Stylebooks for admin UI (e.g. workspace assignment). Org admins only."""
    require_org_admin(session, auth, org_id)
    rows = list(
        session.exec(select(Stylebook).where(Stylebook.organization_id == org_id)).all()
    )
    rows.sort(key=lambda s: (not bool(s.is_default), str(s.name)))
    out: list[StylebookListOut] = []
    for s in rows:
        if s.id is None:
            continue
        out.append(
            StylebookListOut(
                id=int(s.id),
                name=str(s.name),
                slug=str(s.slug),
                is_default=bool(s.is_default),
            )
        )
    return out


@router.get("/{org_id}/workspaces", response_model=list[WorkspaceWithProjectsOut])
def list_org_workspaces(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_org_admin(session, auth, org_id)
    ws_rows = session.exec(
        select(BackfieldWorkspace).where(BackfieldWorkspace.organization_id == org_id)
    ).all()
    proj_rows = session.exec(
        select(BackfieldProject).where(BackfieldProject.organization_id == org_id)
    ).all()
    projects_by_ws: dict[int, list[BackfieldProject]] = {}
    for p in proj_rows:
        if p.workspace_id is None:
            continue
        wid = int(p.workspace_id)
        projects_by_ws.setdefault(wid, []).append(p)
    sb_ids_ws = {int(w.stylebook_id) for w in ws_rows if w.id is not None}
    sb_name_map = _stylebook_name_map(session, org_id, sb_ids_ws)
    out: list[WorkspaceWithProjectsOut] = []
    for ws in ws_rows:
        if ws.id is None:
            continue
        plist = projects_by_ws.get(int(ws.id), [])
        projects_out = [
            ProjectSummaryOut(id=int(p.id), name=str(p.name), slug=str(p.slug))
            for p in plist
            if p.id is not None
        ]
        projects_out.sort(key=lambda x: x.slug)
        sb_id = int(ws.stylebook_id)
        out.append(
            WorkspaceWithProjectsOut(
                id=int(ws.id),
                name=str(ws.name),
                slug=str(ws.slug),
                projects=projects_out,
                stylebook_id=sb_id,
                stylebook_name=sb_name_map.get(sb_id, ""),
            )
        )
    return sorted(out, key=lambda x: x.slug)


@router.post("/{org_id}/workspaces", response_model=WorkspaceWithProjectsOut)
def create_workspace(
    org_id: int,
    body: WorkspaceCreateBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WorkspaceWithProjectsOut:
    """Create an empty workspace; org admins only. Session callers get workspace membership."""
    require_org_admin(session, auth, org_id)
    label = body.name.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Name is required")
    slug = _allocate_workspace_slug(session, org_id, label)
    default_sb = ensure_default_stylebook_for_organization(session, org_id)
    sb_id = int(default_sb.id)  # type: ignore[arg-type]
    if body.stylebook_id is not None:
        _stylebook_must_belong_to_org(session, org_id, body.stylebook_id)
        sb_id = body.stylebook_id
    ws = BackfieldWorkspace(organization_id=org_id, stylebook_id=sb_id, name=label, slug=slug)
    session.add(ws)
    session.flush()
    if ws.id is None:
        raise HTTPException(status_code=500, detail="Workspace persist failed")
    wid = int(ws.id)
    if auth["type"] == "session":
        uid = int(auth["user"].id)  # type: ignore[union-attr]
        exists = session.exec(
            select(BackfieldWorkspaceMembership).where(
                BackfieldWorkspaceMembership.user_id == uid,
                BackfieldWorkspaceMembership.workspace_id == wid,
            )
        ).first()
        if exists is None:
            session.add(BackfieldWorkspaceMembership(user_id=uid, workspace_id=wid))
    session.commit()
    session.refresh(ws)
    sb_id = int(ws.stylebook_id)
    sb_names = _stylebook_name_map(session, org_id, {sb_id})
    return WorkspaceWithProjectsOut(
        id=wid,
        name=str(ws.name),
        slug=str(ws.slug),
        projects=[],
        stylebook_id=sb_id,
        stylebook_name=sb_names.get(sb_id, ""),
    )


@router.patch(
    "/{org_id}/workspaces/{workspace_id}",
    response_model=WorkspaceWithProjectsOut,
)
def patch_workspace(
    org_id: int,
    workspace_id: int,
    body: WorkspacePatchBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> WorkspaceWithProjectsOut:
    """Update workspace display name and/or Stylebook (slug unchanged). Org admins only."""
    require_org_admin(session, auth, org_id)
    ws = session.get(BackfieldWorkspace, workspace_id)
    if ws is None or ws.id is None or int(ws.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="No fields to update")
    did = False
    if "name" in raw:
        if raw["name"] is None:
            raise HTTPException(status_code=400, detail="Name is required")
        name = str(raw["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        ws.name = name
        did = True
    if "stylebook_id" in raw:
        if raw["stylebook_id"] is None:
            raise HTTPException(status_code=400, detail="stylebook_id is required when provided")
        _stylebook_must_belong_to_org(session, org_id, int(raw["stylebook_id"]))
        ws.stylebook_id = int(raw["stylebook_id"])
        did = True
    if not did:
        raise HTTPException(status_code=400, detail="No fields to update")
    session.add(ws)
    session.commit()
    session.refresh(ws)
    out = _workspace_with_projects_out(session, org_id, int(ws.id))
    if out is None:
        raise HTTPException(status_code=500, detail="Workspace load failed")
    return out


@router.get("/{org_id}/users", response_model=list[UserOut])
def list_users(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
    detail: bool = Query(
        False,
        description="Include legacy project memberships and workspace memberships for admin UI",
    ),
):
    require_org_admin(session, auth, org_id)
    proj_ids = _org_project_ids(session, org_id)
    projects_by_id: dict[int, BackfieldProject] = {}
    for pid in proj_ids:
        p = session.get(BackfieldProject, pid)
        if p:
            projects_by_id[pid] = p

    memberships = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.organization_id == org_id
        )
    ).all()
    out: list[UserOut] = []
    for m in memberships:
        u = session.get(BackfieldUser, m.user_id)
        if u is None:
            continue
        pm_out: list[ProjectMembershipOut] | None = None
        ws_out: list[WorkspaceMembershipOut] | None = None
        if detail:
            pm_out = []
            if proj_ids:
                pm_rows = session.exec(
                    select(BackfieldProjectMembership).where(
                        BackfieldProjectMembership.user_id == u.id,
                        col(BackfieldProjectMembership.project_id).in_(proj_ids),
                    )
                ).all()
                for pm in pm_rows:
                    if pm.project_id is None:
                        continue
                    proj = projects_by_id.get(int(pm.project_id))
                    if proj is None:
                        continue
                    pm_out.append(
                        ProjectMembershipOut(
                            project_id=int(pm.project_id),
                            slug=str(proj.slug),
                            name=str(proj.name),
                            role=pm.role,
                        )
                    )
                pm_out.sort(key=lambda x: x.slug)
            ws_out = _workspace_memberships_for_user_org(session, org_id, int(u.id))

        out.append(
            UserOut(
                id=int(u.id),
                email=str(u.email),
                display_name=u.display_name,
                role=str(m.role),
                disabled_at=u.disabled_at,
                project_memberships=pm_out,
                workspace_memberships=ws_out,
            )
        )
    return out


@router.post("/{org_id}/users", response_model=UserOut)
def create_user(
    org_id: int,
    body: UserCreateBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_org_admin(session, auth, org_id)
    email = body.email.strip().lower()
    existing = session.exec(select(BackfieldUser).where(BackfieldUser.email == email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = BackfieldUser(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    session.add(user)
    session.flush()
    session.add(
        BackfieldOrganizationMembership(
            user_id=int(user.id),
            organization_id=org_id,
            role=body.role if body.role in ("org_admin", "member") else "member",
        )
    )
    session.commit()
    session.refresh(user)
    mem = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.user_id == user.id,
            BackfieldOrganizationMembership.organization_id == org_id,
        )
    ).first()
    role = str(mem.role) if mem else "member"
    return UserOut(
        id=int(user.id),
        email=str(user.email),
        display_name=user.display_name,
        role=role,
        disabled_at=user.disabled_at,
        project_memberships=None,
        workspace_memberships=None,
    )


@router.patch("/{org_id}/users/{user_id}", response_model=UserOut)
def patch_user(
    org_id: int,
    user_id: int,
    body: UserPatchBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_org_admin(session, auth, org_id)
    mem = _membership_for_user_org(session, org_id, user_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="User not in organization")
    user = session.get(BackfieldUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is None and body.display_name is None:
        session.refresh(user)
        session.refresh(mem)
        return UserOut(
            id=int(user.id),
            email=str(user.email),
            display_name=user.display_name,
            role=str(mem.role),
            disabled_at=user.disabled_at,
            project_memberships=None,
            workspace_memberships=None,
        )

    if body.role is not None:
        new_role = body.role if body.role in ("org_admin", "member") else mem.role
        if str(mem.role) == "org_admin" and new_role == "member":
            if _is_only_active_org_admin(session, org_id, user_id):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot demote the last organization admin",
                )
        mem.role = str(new_role)
        session.add(mem)

    if body.display_name is not None:
        user.display_name = body.display_name
        session.add(user)

    session.commit()
    session.refresh(user)
    session.refresh(mem)
    return UserOut(
        id=int(user.id),
        email=str(user.email),
        display_name=user.display_name,
        role=str(mem.role),
        disabled_at=user.disabled_at,
        project_memberships=None,
        workspace_memberships=None,
    )


@router.delete("/{org_id}/users/{user_id}")
def disable_user(
    org_id: int,
    user_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> dict[str, bool]:
    require_org_admin(session, auth, org_id)
    caller_id = int(auth["user"].id)
    if user_id == caller_id:
        raise HTTPException(status_code=400, detail="Cannot disable your own account")
    mem = _membership_for_user_org(session, org_id, user_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="User not in organization")
    if str(mem.role) == "org_admin" and _is_only_active_org_admin(session, org_id, user_id):
        raise HTTPException(status_code=400, detail="Cannot disable the last organization admin")
    user = session.get(BackfieldUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.disabled_at = datetime.now(UTC)
    session.add(user)
    session.commit()
    return {"ok": True}


@router.put(
    "/{org_id}/users/{user_id}/workspace-memberships",
    response_model=list[WorkspaceMembershipOut],
)
def replace_workspace_memberships(
    org_id: int,
    user_id: int,
    body: ReplaceWorkspaceMembershipsBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    """Assign workspaces for a user; member gets all projects in those workspaces."""
    require_org_admin(session, auth, org_id)
    mem = _membership_for_user_org(session, org_id, user_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="User not in organization")
    user = session.get(BackfieldUser, user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=400, detail="User is disabled or missing")
    if str(mem.role) == "org_admin":
        raise HTTPException(
            status_code=400,
            detail="Organization admins already have access to all projects",
        )

    org_ws = set(_org_workspace_ids(session, org_id))
    for wid in body.workspace_ids:
        if wid not in org_ws:
            raise HTTPException(
                status_code=400,
                detail=f"Workspace {wid} is not in this organization",
            )

    existing = session.exec(
        select(BackfieldWorkspaceMembership).where(
            BackfieldWorkspaceMembership.user_id == user_id,
        )
    ).all()
    for wm in existing:
        if wm.workspace_id is None:
            continue
        ws = session.get(BackfieldWorkspace, wm.workspace_id)
        if ws is not None and int(ws.organization_id) == org_id:
            session.delete(wm)

    now = datetime.now(UTC)
    for wid in body.workspace_ids:
        session.add(
            BackfieldWorkspaceMembership(
                user_id=user_id,
                workspace_id=wid,
                created_at=now,
            )
        )
    session.commit()

    return _workspace_memberships_for_user_org(session, org_id, user_id)


@router.put(
    "/{org_id}/users/{user_id}/project-memberships",
    response_model=list[ProjectMembershipOut],
)
def replace_project_memberships(
    org_id: int,
    user_id: int,
    body: ReplaceProjectMembershipsBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    """Legacy explicit per-project grants; prefer ``workspace-memberships`` for new admin flows."""
    require_org_admin(session, auth, org_id)
    mem = _membership_for_user_org(session, org_id, user_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="User not in organization")
    user = session.get(BackfieldUser, user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=400, detail="User is disabled or missing")

    org_pids = set(_org_project_ids(session, org_id))
    for row in body.memberships:
        if row.project_id not in org_pids:
            raise HTTPException(
                status_code=400,
                detail=f"Project {row.project_id} is not in this organization",
            )

    existing = session.exec(
        select(BackfieldProjectMembership).where(BackfieldProjectMembership.user_id == user_id)
    ).all()
    for pm in existing:
        if pm.project_id is not None and int(pm.project_id) in org_pids:
            session.delete(pm)

    now = datetime.now(UTC)
    for row in body.memberships:
        session.add(
            BackfieldProjectMembership(
                user_id=user_id,
                project_id=row.project_id,
                role=row.role,
                created_at=now,
            )
        )
    session.commit()

    out: list[ProjectMembershipOut] = []
    for row in body.memberships:
        proj = session.get(BackfieldProject, row.project_id)
        if proj is None:
            continue
        out.append(
            ProjectMembershipOut(
                project_id=row.project_id,
                slug=str(proj.slug),
                name=str(proj.name),
                role=row.role,
            )
        )
    return sorted(out, key=lambda x: x.slug)
