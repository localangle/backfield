"""Routes that require session cookie or service Bearer token."""

from __future__ import annotations

from typing import Any

from backfield_auth import require_auth_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["secure"])


@router.get("/secure/whoami")
def whoami(auth: dict[str, Any] = Depends(require_auth_or_service)) -> dict[str, Any]:
    """Return auth mode; same contract for browser sessions and service calls."""
    out: dict[str, Any] = {
        "authenticated": True,
        "auth_type": auth["type"],
        "is_admin": auth.get("is_admin", False),
    }
    if auth["type"] == "session" and auth.get("token_data"):
        td = auth["token_data"]
        out["username"] = td.get("username")
        out["user_id"] = td.get("user_id")
        out["projects"] = td.get("projects") or []
    else:
        out["principal"] = "service"
    return out
