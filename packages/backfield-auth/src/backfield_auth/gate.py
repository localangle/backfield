"""DB-backed internal and public authentication boundaries."""

from __future__ import annotations

import hashlib
import hmac
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
    """Validate a public project key and its owner's current access."""
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
    if not hmac.compare_digest(str(row.key_hash), digest):
        return None
    proj = session.get(BackfieldProject, row.project_id)
    if proj is None:
        return None
    credential_type = str(row.credential_type)
    if credential_type == "user":
        if row.user_id is None:
            # Legacy ownerless personal keys cannot prove an accountable principal.
            return None
        user = session.get(BackfieldUser, int(row.user_id))
        if user is None or user.disabled_at is not None:
            return None
        membership = session.exec(
            select(BackfieldOrganizationMembership).where(
                BackfieldOrganizationMembership.user_id == int(row.user_id),
                BackfieldOrganizationMembership.organization_id == int(proj.organization_id),
            )
        ).first()
        if membership is None:
            return None
        accessible_project_ids = session_project_ids_for_user(
            session,
            user_id=int(row.user_id),
            organization_id=int(proj.organization_id),
            org_role=str(membership.role),
        )
        if int(proj.id) not in accessible_project_ids:
            return None
    elif credential_type == "service":
        # Ownerless service keys are the explicit trusted legacy/operator path.
        if row.user_id is not None:
            return None
    else:
        return None
    return {
        "type": "api_key",
        "credential": row,
        "project_id": int(row.project_id),
        "organization_id": int(proj.organization_id),
        "credential_type": credential_type,
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


def _service_auth(
    token: str,
    *,
    service_organization_id: int | None,
) -> dict[str, Any] | None:
    if not verify_service_token(token):
        return None
    return {
        "type": "service",
        "is_admin": True,
        "organization_id": service_organization_id,
    }


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        return None
    if scheme.lower() != "bearer":
        return None
    return token.strip()


def resolve_internal_auth(
    session: Session,
    *,
    cookie: str | None,
    authorization: str | None,
    service_organization_id: int | None = None,
    allow_password_change_required: bool = False,
) -> dict[str, Any]:
    """Resolve only trusted service tokens or browser sessions."""
    token = _bearer_token(authorization)
    if token:
        service_auth = _service_auth(
            token,
            service_organization_id=service_organization_id,
        )
        if service_auth is not None:
            return service_auth
        if token.startswith("bfk_"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Project API keys are only accepted by /public/v1 endpoints",
            )

    if cookie:
        data = verify_session_token(cookie)
        if data:
            return _resolve_session_auth(
                session,
                data,
                allow_password_change_required=allow_password_change_required,
            )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def resolve_public_auth(
    session: Session,
    *,
    authorization: str | None,
    service_organization_id: int | None = None,
) -> dict[str, Any]:
    """Resolve a public project key or an explicitly scoped trusted service token."""
    token = _bearer_token(authorization)
    if token:
        service_auth = _service_auth(
            token,
            service_organization_id=service_organization_id,
        )
        if service_auth is not None:
            return service_auth
        api_auth = try_resolve_bearer_api_key(session, token)
        if api_auth is not None:
            return api_auth
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


# Compatibility for downstream callers; internal authentication is the safe default.
resolve_auth = resolve_internal_auth


def resolve_project_by_slug(
    session: Session,
    auth: dict[str, Any],
    slug: str,
) -> BackfieldProject:
    """Resolve a slug inside the caller's organization or bound API-key project."""
    normalized_slug = slug.strip()
    if not normalized_slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if auth["type"] == "api_key":
        project = session.get(BackfieldProject, int(auth["project_id"]))
        if project is None or str(project.slug) != normalized_slug:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key project mismatch",
            )
        return project
    organization_id = auth.get("organization_id")
    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit organization context is required",
        )
    project = session.exec(
        select(BackfieldProject).where(
            BackfieldProject.organization_id == int(organization_id),
            BackfieldProject.slug == normalized_slug,
        )
    ).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _resolve_session_auth(
    session: Session,
    data: dict[str, Any],
    *,
    allow_password_change_required: bool = False,
) -> dict[str, Any]:
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
    if claimed_org_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "organization_selection_required"},
        )
    membership = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.user_id == int(uid),
            BackfieldOrganizationMembership.organization_id == int(claimed_org_id),
        )
    ).first()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "organization_selection_required"},
        )

    if bool(user.must_change_password) and not allow_password_change_required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required"},
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


def require_org_member(
    session: Session,
    auth: dict[str, Any],
    organization_id: int,
) -> None:
    """Allow session members (any role) or service tokens for the organization."""
    if auth["type"] == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization settings require a session or service token",
        )
    if auth["type"] == "service":
        return
    if int(auth["organization_id"]) != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong organization")


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
    return resolve_internal_auth(session, cookie=session_cookie, authorization=authorization)
