"""Unit tests for organization settings_json helpers."""

from __future__ import annotations

import json

import pytest
from backfield_db.organization_settings import (
    MapDefaultViewport,
    merge_map_default_viewport,
    parse_organization_settings,
)
from pydantic import ValidationError


def test_parse_empty_and_invalid() -> None:
    assert parse_organization_settings(None).map_default_viewport is None
    assert parse_organization_settings("").map_default_viewport is None
    assert parse_organization_settings("not-json").map_default_viewport is None
    assert parse_organization_settings("[]").map_default_viewport is None


def test_parse_and_merge_viewport() -> None:
    raw = merge_map_default_viewport(
        None,
        map_default_viewport=MapDefaultViewport(lat=41.88, lng=-87.63, zoom=11),
    )
    assert raw is not None
    parsed = parse_organization_settings(raw)
    assert parsed.map_default_viewport is not None
    assert parsed.map_default_viewport.lat == pytest.approx(41.88)
    assert parsed.map_default_viewport.zoom == pytest.approx(11)

    cleared = merge_map_default_viewport(raw, map_default_viewport=None)
    assert cleared is None

    kept = merge_map_default_viewport(raw, map_default_viewport=...)
    assert kept is not None
    assert json.loads(kept)["map_default_viewport"]["lng"] == pytest.approx(-87.63)


def test_viewport_bounds() -> None:
    with pytest.raises(ValidationError):
        MapDefaultViewport(lat=100, lng=0, zoom=3)
    with pytest.raises(ValidationError):
        MapDefaultViewport(lat=0, lng=0, zoom=50)
