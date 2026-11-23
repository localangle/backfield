"""Dependencies for the preview cleanup routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backfield_auth.gate import SCOPE_CLEANUP_APPLY, SCOPE_CLEANUP_READ
from backfield_db import BackfieldProject
from backfield_entities.public.stylebook_scope import resolve_public_stylebook_id
from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project, require_public_api_auth, require_scope

require_cleanup_read = require_scope(SCOPE_CLEANUP_READ)
require_cleanup_apply = require_scope(SCOPE_CLEANUP_APPLY)


def is_service_principal(auth: dict[str, Any]) -> bool:
    """True for the shared service token and for service-type project keys."""
    return auth["type"] == "service" or auth.get("credential_type") == "service"


def require_queue_scope_allowed(auth: dict[str, Any], scope: str) -> None:
    """Stylebook-wide queues are for service principals; other keys see their own project."""
    if scope == "stylebook" and not is_service_principal(auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Stylebook-wide queues need a service key.",
        )


@dataclass(frozen=True)
class CleanupContext:
    """The authenticated caller, project, and Stylebook a cleanup route works on."""

    auth: dict[str, Any]
    project: BackfieldProject
    stylebook_id: int
    stylebook_slug: str


def get_cleanup_context(
    stylebook_slug: str,
    project: BackfieldProject = Depends(get_public_project),
    auth: dict[str, Any] = Depends(require_public_api_auth),
    session: Session = Depends(get_session),
) -> CleanupContext:
    """Resolve the path's Stylebook inside the key's organization (never an implied default)."""
    slug = stylebook_slug.strip()
    if not slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stylebook not found")
    try:
        stylebook_id = resolve_public_stylebook_id(session, project, stylebook_slug=slug)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Stylebook not found"
        ) from exc
    return CleanupContext(
        auth=auth, project=project, stylebook_id=stylebook_id, stylebook_slug=slug
    )
