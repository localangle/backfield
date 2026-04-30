"""Tests for AdvancedGeocodeAgent router audit extraction and substrate merge."""

from __future__ import annotations

from worker.substrate_location import (
    _apply_substrate_location_merge,
    _router_audit_from_place_entry,
)


def test_router_audit_from_place_entry_accepts_dict_only() -> None:
    assert _router_audit_from_place_entry({"agate_geocode_router_audit": {"x": 1}}) == {"x": 1}
    assert _router_audit_from_place_entry({"agate_geocode_router_audit": [1, 2]}) is None
    assert _router_audit_from_place_entry({}) is None


def test_merge_preserves_audit_when_incoming_none() -> None:
    from backfield_db import SubstrateLocation

    loc = SubstrateLocation(
        project_id=1,
        name="T",
        normalized_name="t",
        geocode_router_audit_json={"keep": True},
    )
    common = {
        "display_name": "T",
        "normalized": "t",
        "location_type_str": "city",
        "status": "resolved",
        "external_source": None,
        "external_id": None,
        "fingerprint": "fp",
        "geocode_type": None,
        "formatted_address": None,
        "details": {},
        "geometry_value": None,
        "geometry_type_str": None,
        "geometry_json": None,
    }
    _apply_substrate_location_merge(loc, **common, geocode_router_audit_json=None)
    assert loc.geocode_router_audit_json == {"keep": True}

    _apply_substrate_location_merge(loc, **common, geocode_router_audit_json={"latest": True})
    assert loc.geocode_router_audit_json == {"latest": True}
