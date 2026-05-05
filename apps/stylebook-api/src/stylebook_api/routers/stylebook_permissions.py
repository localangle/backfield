"""Stylebook-scoped permission introspection for UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from stylebook_api.deps import get_auth, get_session
from stylebook_api.stylebook_permissions import can_edit_stylebook

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-permissions"])


class StylebookPermissionsOut(BaseModel):
    can_edit: bool


@router.get("/{stylebook_slug}/permissions", response_model=StylebookPermissionsOut)
def get_stylebook_permissions(
    stylebook_slug: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StylebookPermissionsOut:
    return StylebookPermissionsOut(
        can_edit=can_edit_stylebook(session, auth=auth, stylebook_slug=stylebook_slug)
    )

