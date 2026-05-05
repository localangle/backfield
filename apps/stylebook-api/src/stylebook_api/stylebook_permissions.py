"""Stylebook editor permissions (per-stylebook ACL)."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_org_admin
from backfield_db import StylebookMembership
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

