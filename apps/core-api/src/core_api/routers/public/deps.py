"""Dependencies for `/public/v1` routes."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access, resolve_auth
from backfield_db import BackfieldProject
from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from core_api.deps import get_session


def require_public_api_auth(
    session: Session = Depends(get_session),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Require Bearer project API key (or service token for automation)."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use Bearer <project_api_key>.",
        )
    auth = resolve_auth(session, cookie=None, authorization=authorization)
    if auth["type"] not in ("api_key", "service"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Project API key required.",
        )
    return auth


def get_public_project(
    project_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(require_public_api_auth),
) -> BackfieldProject:
    """Resolve project by slug and enforce caller access."""
    slug = project_slug.strip()
    if not slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    project = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if project is None or project.id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return require_project_access(session, auth, int(project.id))


def require_scope(scope: str):
    """Require a project API key scope; service tokens bypass scope checks."""

    def _dep(auth: dict[str, Any] = Depends(require_public_api_auth)) -> dict[str, Any]:
        if auth["type"] == "service":
            return auth
        if scope not in (auth.get("scopes") or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required scope: {scope}",
            )
        return auth

    return _dep
