"""Stylebook editor permissions (per-stylebook ACL)."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_org_admin
from backfield_db import Stylebook, StylebookMembership
from fastapi import HTTPException
from sqlmodel import Session, select

from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org


def can_edit_stylebook(
    session: Session,
    *,
    auth: dict[str, Any],
    stylebook_slug: str,
) -> bool:
    """Return True when caller may mutate items inside this Stylebook."""

    if auth.get("type") == "service":
        return True
    if auth.get("type") == "api_key":
        return False

    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        return False

    # Org admins can always edit.
    try:
        require_org_admin(session, auth, int(sb.organization_id))
        return True
    except HTTPException:
        pass

    uid = int(auth["user"].id)  # type: ignore[union-attr]
    row = session.exec(
        select(StylebookMembership).where(
            StylebookMembership.stylebook_id == int(sb.id),
            StylebookMembership.user_id == uid,
            StylebookMembership.role == "editor",
        )
    ).first()
    return row is not None


def require_stylebook_edit_access(
    session: Session,
    *,
    auth: dict[str, Any],
    stylebook_slug: str,
) -> None:
    if can_edit_stylebook(session, auth=auth, stylebook_slug=stylebook_slug):
        return
    raise HTTPException(status_code=403, detail="No permission to edit this stylebook")


def require_stylebook_edit_access_by_id(
    session: Session,
    *,
    auth: dict[str, Any],
    stylebook_id: int,
) -> None:
    """Require edit access for a project-derived Stylebook id."""
    if auth.get("type") == "service":
        return
    if auth.get("type") == "api_key":
        raise HTTPException(status_code=403, detail="No permission to edit this stylebook")
    stylebook = session.get(Stylebook, stylebook_id)
    if stylebook is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        require_org_admin(session, auth, int(stylebook.organization_id))
        return
    except HTTPException:
        pass
    user = auth.get("user")
    if user is not None and user.id is not None:
        membership = session.exec(
            select(StylebookMembership).where(
                StylebookMembership.stylebook_id == stylebook_id,
                StylebookMembership.user_id == int(user.id),
                StylebookMembership.role == "editor",
            )
        ).first()
        if membership is not None:
            return
    raise HTTPException(status_code=403, detail="No permission to edit this stylebook")

