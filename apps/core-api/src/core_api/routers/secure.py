"""Routes that require session cookie or service Bearer token."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from core_api.deps import get_auth

router = APIRouter(tags=["secure"])


@router.get("/secure/whoami")
def whoami(auth: dict[str, Any] = Depends(get_auth)) -> dict[str, Any]:
    """Return auth mode (DB-validated session or service token)."""
    out: dict[str, Any] = {
        "authenticated": True,
        "auth_type": auth["type"],
    }
    if auth["type"] == "service":
        out["principal"] = "service"
        out["is_admin"] = True
        return out
    if auth["type"] == "api_key":
        out["principal"] = "api_key"
        out["project_id"] = auth.get("project_id")
        out["credential_type"] = auth.get("credential_type")
        return out
    user = auth["user"]
    td = auth.get("token_data") or {}
    out["email"] = str(user.email)
    out["user_id"] = int(user.id)
    out["organization_id"] = auth.get("organization_id")
    out["org_role"] = auth.get("org_role")
    out["projects"] = td.get("projects") or []
    out["is_admin"] = bool(auth.get("is_admin"))
    return out
