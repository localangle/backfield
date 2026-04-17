"""Starter geocode stub (gazetteer); authenticated like Agate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from stylebook_api.deps import get_auth

router = APIRouter(prefix="/v1/geocode", tags=["geocode"])

_GAZETTEER: dict[str, dict[str, Any]] = {
    "chicago, il": {"lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL"},
    "austin, tx": {"lat": 30.2672, "lon": -97.7431, "label": "Austin, TX"},
    "minneapolis, mn": {"lat": 44.9778, "lon": -93.2650, "label": "Minneapolis, MN"},
}


class GeocodeBody(BaseModel):
    query: str


@router.post("/resolve")
def geocode_resolve(
    body: GeocodeBody,
    _auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, Any]:
    """Resolve a free-text location string to coordinates (starter stub)."""
    key = body.query.strip().lower()
    hit = _GAZETTEER.get(key)
    if hit:
        return hit
    for k, v in _GAZETTEER.items():
        if key in k or k in key:
            return v
    return {"lat": None, "lon": None, "label": body.query, "note": "unresolved_stub"}
