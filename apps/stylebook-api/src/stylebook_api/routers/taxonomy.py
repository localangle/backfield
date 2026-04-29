"""Reference taxonomy endpoints (PlaceExtract location types, etc.)."""

from __future__ import annotations

from typing import Any

from backfield_stylebook.place_extract_location_types import PLACE_EXTRACT_LOCATION_TYPES
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from stylebook_api.deps import get_auth

router = APIRouter(prefix="/v1", tags=["taxonomy"])


class PlaceExtractLocationTypesResponse(BaseModel):
    types: list[str]


@router.get("/place-extract-location-types")
def place_extract_location_types(
    _auth: dict[str, Any] = Depends(get_auth),
) -> PlaceExtractLocationTypesResponse:
    """Ordered PlaceExtract ``location.type`` values (same source as canonical filters)."""
    return PlaceExtractLocationTypesResponse(types=list(PLACE_EXTRACT_LOCATION_TYPES))
