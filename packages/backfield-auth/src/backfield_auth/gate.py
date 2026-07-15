"""DB-backed auth: session cookie, service Bearer, project API keys (`bfk_`).

Used by core-api and agate-api with the same Postgres tables (no RPC to Core).
"""

from __future__ import annotations

import hashlib
from typing import Any

from backfield_db import (
    BackfieldApiCredential,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldUser,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
)
from fastapi import Cookie, Header, HTTPException, status
from sqlmodel import Session, col, select

from backfield_auth.service_tokens import verify_service_token
from backfield_auth.session_tokens import verify_session_token

SCOPE_READ = "read"
SCOPE_RUNS_TRIGGER = "runs:trigger"
ALL_SCOPES = (SCOPE_READ, SCOPE_RUNS_TRIGGER)


def parse_scopes(raw: str | None) -> list[str]:
    tokens = [t for t in (raw or "").split() if t]
    return [t for t in tokens if t in ALL_SCOPES] or [SCOPE_READ]


def try_resolve_bearer_api_key(session: Session, raw: str) -> dict[str, Any] | None:
    """Validate `bfk_` project API key; return auth dict or None if not a valid key."""
    raw = raw.strip()
    if not raw.startswith("bfk_") or len(raw) < 24:
        return None
    prefix = raw[:22]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    row = session.exec(
        select(BackfieldApiCredential).where(BackfieldApiCredential.key_prefix == prefix)
    ).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.key_hash != digest:
        return None
    proj = session.get(BackfieldProject, row.project_id)
    if proj is None:
        return None
    return {
        "type": "api_key",
        "credential": row,
        "project_id": int(row.project_id),
        "organization_id": int(proj.organization_id),
        "credential_type": str(row.credential_type),
        "scopes": parse_scopes(row.scopes),
    }


def session_project_ids_for_user(
    session: Session,
    *,
    user_id: int,
    organization_id: int,
    org_role: str,
) -> list[int]:
    """Project ids the user may access (org_admin = all org projects).

    Members: projects in assigned workspaces (same org) plus legacy explicit
    ``backfield_project_membership`` rows scoped to this org.
    """
    if org_role == "org_admin":
        rows = session.exec(
            select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
        ).all()
        return [int(r) for r in rows if r is not None]

    explicit: list[int] = []
    rows = session.exec(
        select(BackfieldProjectMembership.project_id).where(
            BackfieldProjectMembership.user_id == user_id
        )
    ).all()
    for pid in rows:
        if pid is None:
            continue
        proj = session.get(BackfieldProject, pid)
        if proj and proj.organization_id == organization_id:
            explicit.append(int(pid))

    ws_id_rows = session.exec(
        select(BackfieldWorkspaceMembership.workspace_id).where(
            BackfieldWorkspaceMembership.user_id == user_id
        )
    ).all()
    ws_ids = [int(w) for w in ws_id_rows if w is not None]
    from_workspaces: list[int] = []
    if ws_ids:
        ws_in_org = session.exec(
            select(BackfieldWorkspace.id).where(
                col(BackfieldWorkspace.id).in_(ws_ids),
                BackfieldWorkspace.organization_id == organization_id,
            )
        ).all()
        allowed_ws = [int(x) for x in ws_in_org if x is not None]
        if allowed_ws:
            pr = session.exec(
                select(BackfieldProject.id).where(
                    BackfieldProject.organization_id == organization_id,
                    col(BackfieldProject.workspace_id).in_(allowed_ws),
                )
            ).all()
            from_workspaces = [int(r) for r in pr if r is not None]

    return sorted(set(explicit) | set(from_workspaces))


def visible_project_ids(session: Session, auth: dict[str, Any]) -> list[int] | None:
    """
    Projects the caller may list.

    Returns None when all projects are visible (service token). Otherwise a finite list.
    """
    if auth["type"] == "service":
        return None
    if auth["type"] == "api_key":
        return [int(auth["project_id"])]
    uid = int(auth["user"].id)  # type: ignore[union-attr]
    org_id = int(auth["organization_id"])
    org_role = str(auth.get("org_role") or "member")
    return session_project_ids_for_user(
        session,
        user_id=uid,
        organization_id=org_id,
        org_role=org_role,
    )


def resolve_auth(
    session: Session,
    *,
    cookie: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    """Resolve service Bearer, project API key, session cookie, or raise 401."""
    if authorization:
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError
            token = token.strip()
            if verify_service_token(token):
                return {"type": "service", "is_admin": True}
            api_auth = try_resolve_bearer_api_key(session, token)
            if api_auth is not None:
                return api_auth
        except ValueError:
            pass

    if cookie:
        data = verify_session_token(cookie)
        if data:
            return _resolve_session_auth(session, data)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def _resolve_session_auth(session: Session, data: dict[str, Any]) -> dict[str, Any]:
    """Load the current user and DB membership; do not trust cookie authorization claims."""
    uid = data.get("user_id")
    if uid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )
    user = session.get(BackfieldUser, int(uid))
    if user is None or user.disabled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    claimed_org_id = data.get("organization_id")
    membership: BackfieldOrganizationMembership | None = None
    if claimed_org_id is not None:
        membership = session.exec(
            select(BackfieldOrganizationMembership).where(
                BackfieldOrganizationMembership.user_id == int(uid),
                BackfieldOrganizationMembership.organization_id == int(claimed_org_id),
            )
        ).first()
    if membership is None:
        membership = session.exec(
            select(BackfieldOrganizationMembership).where(
                BackfieldOrganizationMembership.user_id == int(uid)
            )
        ).first()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    org_role = str(membership.role)
    return {
        "type": "session",
        "user": user,
        "token_data": data,
        "organization_id": int(membership.organization_id),
        "org_role": org_role,
        "is_admin": org_role == "org_admin",
    }


def require_session_may_assign_project_to_workspace(
    session: Session,
    auth: dict[str, Any],
    *,
    workspace_id: int,
    organization_id: int,
) -> None:
    """Session users may only create projects in workspaces they belong to (unless org_admin).

    Service tokens and API keys are not restricted here (create uses other rules).
    """
    if auth["type"] != "session":
        return
    if int(auth["organization_id"]) != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wrong organization",
        )
    if auth.get("org_role") == "org_admin":
        return
    uid = int(auth["user"].id)  # type: ignore[union-attr]
    row = session.exec(
        select(BackfieldWorkspaceMembership).where(
            BackfieldWorkspaceMembership.user_id == uid,
            BackfieldWorkspaceMembership.workspace_id == workspace_id,
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to assign projects to this workspace",
        )


def require_org_admin(
    session: Session,
    auth: dict[str, Any],
    organization_id: int,
) -> None:
    if auth["type"] == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin actions require a session or service token",
        )
    if auth["type"] == "service":
        return
    if int(auth["organization_id"]) != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong organization")
    if auth.get("org_role") != "org_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin required",
        )


def require_project_access(
    session: Session,
    auth: dict[str, Any],
    project_id: int,
) -> BackfieldProject:
    proj = session.get(BackfieldProject, project_id)
    if proj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if auth["type"] == "service":
        return proj
    if auth["type"] == "api_key":
        if int(auth["project_id"]) != project_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key is not for this project",
            )
        return proj
    uid = int(auth["user"].id)  # type: ignore[union-attr]
    org_id = int(auth["organization_id"])
    if proj.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project not in organization",
        )
    if auth.get("org_role") == "org_admin":
        return proj
    allowed = session_project_ids_for_user(
        session,
        user_id=uid,
        organization_id=org_id,
        org_role=str(auth.get("org_role") or "member"),
    )
    if project_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to project")
    return proj


def get_auth_dependency(
    session: Session,
    session_cookie: str | None = Cookie(None, alias="session"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    return resolve_auth(session, cookie=session_cookie, authorization=authorization)
