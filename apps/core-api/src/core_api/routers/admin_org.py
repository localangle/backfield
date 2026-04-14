"""Org admin: users and project memberships in an organization."""

from __future__ import annotations

from datetime import UTC, datetime

from backfield_db import (
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldUser,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select

from core_api.authz import require_org_admin
from core_api.deps import get_auth, get_session
from core_api.security import hash_password

router = APIRouter(prefix="/organizations", tags=["admin"])


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


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str | None
    role: str
    disabled_at: datetime | None = None
    project_memberships: list[ProjectMembershipOut] | None = None


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


def _org_project_ids(session: Session, org_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == org_id)
    ).all()
    return [int(r) for r in rows if r is not None]


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


@router.get("/{org_id}/users", response_model=list[UserOut])
def list_users(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
    detail: bool = Query(False, description="Include per-project memberships for admin UI"),
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

        out.append(
            UserOut(
                id=int(u.id),
                email=str(u.email),
                display_name=u.display_name,
                role=str(m.role),
                disabled_at=u.disabled_at,
                project_memberships=pm_out,
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
