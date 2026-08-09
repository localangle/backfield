"""Parse and merge organization ``settings_json`` preferences."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class MapDefaultViewport(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    zoom: float = Field(..., ge=0, le=22)

    @field_validator("lat", "lng", "zoom", mode="before")
    @classmethod
    def _coerce_finite_float(cls, value: Any) -> float:
        if isinstance(value, bool) or value is None:
            raise ValueError("must be a number")
        try:
            out = float(value)
        except (TypeError, ValueError) as err:
            raise ValueError("must be a number") from err
        if not (out == out) or out in (float("inf"), float("-inf")):  # noqa: PLR0124
            raise ValueError("must be a finite number")
        return out


class OrganizationSettings(BaseModel):
    map_default_viewport: MapDefaultViewport | None = None


def parse_organization_settings(settings_json: str | None) -> OrganizationSettings:
    if not settings_json or not str(settings_json).strip():
        return OrganizationSettings()
    try:
        raw = json.loads(settings_json)
    except json.JSONDecodeError:
        return OrganizationSettings()
    if not isinstance(raw, dict):
        return OrganizationSettings()
    try:
        return OrganizationSettings.model_validate(raw)
    except ValidationError:
        # Keep unknown keys out; recover by reading only a valid viewport when present.
        viewport_raw = raw.get("map_default_viewport")
        if viewport_raw is None:
            return OrganizationSettings()
        try:
            return OrganizationSettings(
                map_default_viewport=MapDefaultViewport.model_validate(viewport_raw)
            )
        except ValidationError:
            return OrganizationSettings()


def organization_settings_to_json(settings: OrganizationSettings) -> str | None:
    payload = settings.model_dump(exclude_none=True)
    if not payload:
        return None
    return json.dumps(payload)


def merge_map_default_viewport(
    settings_json: str | None,
    *,
    map_default_viewport: MapDefaultViewport | None | object,
    unset: object = ...,
) -> str | None:
    """Return updated settings JSON.

    Pass ``map_default_viewport=...`` (ellipsis) to leave the key unchanged.
    Pass ``None`` to clear it. Pass a ``MapDefaultViewport`` to set it.
    """
    current = parse_organization_settings(settings_json)
    if map_default_viewport is not unset:
        if map_default_viewport is None:
            current.map_default_viewport = None
        elif isinstance(map_default_viewport, MapDefaultViewport):
            current.map_default_viewport = map_default_viewport
        else:
            current.map_default_viewport = MapDefaultViewport.model_validate(map_default_viewport)
    return organization_settings_to_json(current)
