"""One-time bootstrap when no users exist."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from core_api.bootstrap_users import BootstrapOrgMissingError, ensure_first_org_admin
from core_api.deps import get_session

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


class FirstUserBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None


@router.post("/first-user")
def register_first_user(
    body: FirstUserBody, session: Session = Depends(get_session)
) -> dict[str, str | int | bool]:
    try:
        result = ensure_first_org_admin(
            session,
            body.email,
            body.password,
            body.display_name,
        )
    except BootstrapOrgMissingError:
        raise HTTPException(status_code=500, detail="Default organization missing; run migrations")
    if result is None:
        raise HTTPException(status_code=400, detail="Users already exist; bootstrap disabled")
    return result
