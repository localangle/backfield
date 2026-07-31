"""Login, logout, session — DB-backed users."""

from __future__ import annotations

import os

from backfield_auth import (
    create_organization_selection_token,
    create_session_token,
    resolve_auth,
    verify_organization_selection_token,
)
from backfield_auth.deps import require_auth
from backfield_auth.identity import LoginCredentials, NewPasswordBody
from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldUser,
)
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from core_api.authz import session_project_ids_for_user
from core_api.deps import get_auth, get_session
from core_api.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class OrganizationChoice(BaseModel):
    id: int
    name: str
    slug: str


class UserResponse(BaseModel):
    email: str
    authenticated: bool
    user_id: int | None = None
    organization_id: int | None = None
    organization_name: str | None = None
    organization_slug: str | None = None
    org_role: str | None = None
    organizations: list[OrganizationChoice] = Field(default_factory=list)


class LoginResponse(BaseModel):
    success: bool
    email: str
    organization_selection_required: bool = False
    organizations: list[OrganizationChoice] = Field(default_factory=list)


class SelectOrganizationBody(BaseModel):
    organization_id: int


class SwitchOrganizationBody(BaseModel):
    organization_id: int


class ChangePasswordBody(NewPasswordBody):
    pass


def _session_cookie_settings() -> dict[str, str | int | bool | None]:
    is_production = os.getenv("ENVIRONMENT") == "production"
    domain = (os.getenv("SESSION_COOKIE_DOMAIN") or "").strip() or None
    # Deployed multi-host tenants set SESSION_COOKIE_DOMAIN so Agate/Stylebook
    # share one session. Honor Domain whenever configured (not only production).
    if is_production or domain:
        return {
            "httponly": True,
            "secure": True,
            "samesite": "none",
            "path": "/",
            "domain": domain,
            "max_age": 7 * 24 * 60 * 60,
        }
    return {
        "httponly": True,
        "secure": False,
        "samesite": "lax",
        "path": "/",
        "domain": None,
        "max_age": 7 * 24 * 60 * 60,
    }


def _set_session_cookie(response: Response, token: str) -> None:
    settings = _session_cookie_settings()
    response.set_cookie(key="session", value=token, **settings)


def _clear_session_cookie(response: Response) -> None:
    settings = _session_cookie_settings()
    response.delete_cookie(
        key="session",
        path=str(settings["path"]),
        domain=settings["domain"],  # type: ignore[arg-type]
        secure=bool(settings["secure"]),
        samesite=str(settings["samesite"]),  # type: ignore[arg-type]
    )


def _set_organization_selection_cookie(response: Response, token: str) -> None:
    settings = _session_cookie_settings()
    response.set_cookie(
        key="organization_selection",
        value=token,
        httponly=True,
        secure=bool(settings["secure"]),
        samesite=str(settings["samesite"]),  # type: ignore[arg-type]
        path="/v1/auth",
        domain=settings["domain"],  # type: ignore[arg-type]
        max_age=10 * 60,
    )


def _clear_organization_selection_cookie(response: Response) -> None:
    settings = _session_cookie_settings()
    response.delete_cookie(
        key="organization_selection",
        path="/v1/auth",
        domain=settings["domain"],  # type: ignore[arg-type]
        secure=bool(settings["secure"]),
        samesite=str(settings["samesite"]),  # type: ignore[arg-type]
    )


def _organization_selection_clear_header() -> str:
    response = Response()
    _clear_organization_selection_cookie(response)
    return response.headers["set-cookie"]


def _active_memberships(
    session: Session,
    user_id: int,
) -> list[tuple[BackfieldOrganizationMembership, BackfieldOrganization]]:
    rows = session.exec(
        select(BackfieldOrganizationMembership, BackfieldOrganization)
        .join(
            BackfieldOrganization,
            BackfieldOrganization.id == BackfieldOrganizationMembership.organization_id,
        )
        .where(BackfieldOrganizationMembership.user_id == user_id)
        .order_by(BackfieldOrganization.name, BackfieldOrganization.id)
    ).all()
    return list(rows)


def _organization_choices(
    rows: list[tuple[BackfieldOrganizationMembership, BackfieldOrganization]],
) -> list[OrganizationChoice]:
    return [
        OrganizationChoice(id=int(org.id), name=str(org.name), slug=str(org.slug))
        for _, org in rows
        if org.id is not None
    ]


def _issue_session(
    session: Session,
    response: Response,
    *,
    user: BackfieldUser,
    membership: BackfieldOrganizationMembership,
) -> None:
    org_id = int(membership.organization_id)
    org_role = str(membership.role)
    project_ids = session_project_ids_for_user(
        session,
        user_id=int(user.id),
        organization_id=org_id,
        org_role=org_role,
    )
    token = create_session_token(
        user_id=int(user.id),
        email=str(user.email),
        projects=project_ids,
        organization_id=org_id,
        org_role=org_role,
        is_admin=org_role == "org_admin",
    )
    _set_session_cookie(response, token)


@router.post("/login")
def login(
    body: LoginCredentials,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    email_norm = body.email
    user = session.exec(select(BackfieldUser).where(BackfieldUser.email == email_norm)).first()
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    memberships = _active_memberships(session, int(user.id))
    if not memberships:
        raise HTTPException(status_code=403, detail="User has no organization membership")
    if len(memberships) > 1:
        organization_ids = [int(membership.organization_id) for membership, _ in memberships]
        selection_token = create_organization_selection_token(
            user_id=int(user.id),
            organization_ids=organization_ids,
        )
        _clear_session_cookie(response)
        _set_organization_selection_cookie(response, selection_token)
        return LoginResponse(
            success=False,
            email=str(user.email),
            organization_selection_required=True,
            organizations=_organization_choices(memberships),
        )

    _clear_organization_selection_cookie(response)
    _issue_session(session, response, user=user, membership=memberships[0][0])
    return LoginResponse(success=True, email=str(user.email))


@router.post("/select-organization", response_model=LoginResponse)
def select_organization(
    body: SelectOrganizationBody,
    response: Response,
    session: Session = Depends(get_session),
    selection_cookie: str | None = Cookie(None, alias="organization_selection"),
) -> LoginResponse:
    token_data = (
        verify_organization_selection_token(selection_cookie)
        if selection_cookie is not None
        else None
    )
    if token_data is None:
        raise HTTPException(
            status_code=401,
            detail="Organization selection has expired",
            headers={"Set-Cookie": _organization_selection_clear_header()},
        )
    user_id = int(token_data["user_id"])
    allowed_ids = {int(value) for value in token_data["organization_ids"]}
    if body.organization_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="Organization is not available")
    user = session.get(BackfieldUser, user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Invalid organization selection")
    membership = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.user_id == user_id,
            BackfieldOrganizationMembership.organization_id == body.organization_id,
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="Organization is not available")
    _clear_organization_selection_cookie(response)
    _issue_session(session, response, user=user, membership=membership)
    return LoginResponse(success=True, email=str(user.email))


@router.post("/switch-organization", response_model=LoginResponse)
def switch_organization(
    body: SwitchOrganizationBody,
    response: Response,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> LoginResponse:
    if auth["type"] != "session":
        raise HTTPException(status_code=403, detail="Session required")
    user = auth["user"]
    membership = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.user_id == int(user.id),
            BackfieldOrganizationMembership.organization_id == body.organization_id,
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="Organization is not available")
    _issue_session(session, response, user=user, membership=membership)
    return LoginResponse(success=True, email=str(user.email))


@router.get("/me", response_model=UserResponse)
def me(
    session: Session = Depends(get_session),
    cookie: str | None = Cookie(None, alias="session"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> UserResponse:
    if not cookie and not authorization:
        return UserResponse(email="", authenticated=False)
    try:
        auth = resolve_auth(session, cookie=cookie, authorization=authorization)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            raise
        return UserResponse(email="", authenticated=False)
    if auth.get("type") != "session":
        return UserResponse(email="", authenticated=False)
    user = auth["user"]
    org_id = int(auth["organization_id"])
    org = session.get(BackfieldOrganization, org_id)
    return UserResponse(
        email=str(user.email),
        authenticated=True,
        user_id=int(user.id),
        organization_id=org_id,
        organization_name=str(org.name) if org is not None else None,
        organization_slug=str(org.slug) if org is not None else None,
        org_role=str(auth.get("org_role")),
        organizations=_organization_choices(_active_memberships(session, int(user.id))),
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> dict[str, bool]:
    if auth["type"] != "session":
        raise HTTPException(status_code=403, detail="Session required")
    user = auth["user"]
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    try:
        new_password = body.validated_new_password(email=str(user.email))
    except (ValidationError, ValueError) as exc:
        detail = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool | str]:
    _clear_session_cookie(response)
    return {"success": True, "message": "Logged out successfully"}


@router.get("/session-check")
def session_check(username: str = Depends(require_auth)) -> dict[str, str]:
    return {"username": username}
