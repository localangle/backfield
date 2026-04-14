"""FastAPI dependencies: session cookie, Bearer service token, optional project scope."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Cookie, Header, HTTPException, status

from backfield_auth.service_tokens import SERVICE_TOKENS, verify_service_token
from backfield_auth.session_tokens import verify_session_token

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")


def require_auth(session: str | None = Cookie(None, alias="session")) -> str:
    """Require a valid session cookie; return username."""
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token_data = verify_session_token(session)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return str(token_data.get("username", ""))


def require_service_auth(authorization: str | None = Header(None, alias="Authorization")) -> str:
    """Require `Authorization: Bearer <service token>`."""
    if not SERVICE_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service authentication not configured",
        )
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        ) from None
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
        )
    token = token.strip()
    if not verify_service_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unauthorized token",
        )
    return token


def require_auth_or_service(
    session: str | None = Cookie(None, alias="session"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """
    Accept either session cookie or service Bearer token.

    Returns:
        {"type": "session"|"service", "token_data": dict|None, "is_admin": bool}
    """
    if authorization:
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() == "bearer" and verify_service_token(token.strip()):
                return {
                    "type": "service",
                    "token_data": None,
                    "is_admin": True,
                }
        except (ValueError, AttributeError):
            pass

    if session:
        token_data = verify_session_token(session)
        if token_data:
            is_admin = bool(token_data.get("is_admin", False)) or (
                token_data.get("username", "") == ADMIN_USERNAME
            )
            return {
                "type": "session",
                "token_data": token_data,
                "is_admin": is_admin,
                "organization_id": token_data.get("organization_id"),
                "org_role": token_data.get("org_role"),
            }

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def require_project_access(project_id: int):
    """
    Factory: dependency that requires auth and session project membership.

    Service tokens may access any project. Sessions must list `project_id` in token
    `projects` or be admin. When user/project tables land in backfield-db, this can
    query membership instead of trusting the cookie list.
    """

    def _dep(
        session: str | None = Cookie(None, alias="session"),
        authorization: str | None = Header(None, alias="Authorization"),
    ) -> dict[str, Any]:
        auth = require_auth_or_service(session, authorization)
        if auth["type"] == "service":
            return auth
        token_data = auth.get("token_data") or {}
        if auth.get("is_admin"):
            return auth
        allowed: list[int] = list(token_data.get("projects") or [])
        if project_id in allowed:
            return auth
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project",
        )

    return _dep


__all__ = [
    "ADMIN_USERNAME",
    "require_auth",
    "require_auth_or_service",
    "require_project_access",
    "require_service_auth",
]
