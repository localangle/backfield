"""Legacy unauthenticated probe routes (pre-/public/v1)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["public"])


@router.get("/public/ping")
def public_ping() -> dict[str, bool | str]:
    """Unauthenticated probe for connectivity and routing."""
    return {"ok": True, "scope": "public"}
