"""Tests for GeocodeAgent router audit extraction and substrate merge."""

from __future__ import annotations

from backfield_entities.entities.location.geometry_apply import (
    GEOMETRY_EDITORIAL_OVERRIDE_KEY,
    mark_geometry_editorial_override,
)
from worker.substrate.entities.location.upsert import (
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
        "h3_cell": None,
        "h3_resolution": None,
    }
    _apply_substrate_location_merge(loc, **common, geocode_router_audit_json=None)
    assert loc.geocode_router_audit_json == {"keep": True}

    _apply_substrate_location_merge(loc, **common, geocode_router_audit_json={"latest": True})
    assert loc.geocode_router_audit_json == {"latest": True}


def _merge_kwargs(**overrides: object) -> dict:
    values: dict = {
        "display_name": "Northalsted",
        "normalized": "northalsted",
        "location_type_str": "neighborhood",
        "status": "resolved",
        "external_source": "pelias",
        "external_id": "gid-1",
        "fingerprint": "fp-northalsted-stale",
        "geocode_type": "pelias",
        "formatted_address": None,
        "details": {"run_id": "run-2"},
        "geometry_value": "POINT (-87.6 41.8)",
        "geometry_type_str": "Point",
        "geometry_json": {"type": "Point", "coordinates": [-87.6, 41.8]},
        "h3_cell": "newcell",
        "h3_resolution": 11,
        "geocode_router_audit_json": None,
    }
    values.update(overrides)
    return values


def test_merge_keeps_editorially_overridden_geometry() -> None:
    from backfield_db import SubstrateLocation

    catalog = {
        "type": "Polygon",
        "coordinates": [
            [[-87.7, 41.9], [-87.6, 41.9], [-87.6, 42.0], [-87.7, 42.0], [-87.7, 41.9]]
        ],
    }
    loc = SubstrateLocation(
        project_id=1,
        name="Northalsted",
        normalized_name="northalsted",
        identity_fingerprint="fp-northalsted-stale",
        geometry_json=catalog,
        geometry_type="Polygon",
        geometry="POLYGON ((-87.7 41.9, -87.6 41.9, -87.6 42.0, -87.7 42.0, -87.7 41.9))",
        h3_cell="oldcell",
        h3_resolution=7,
        source_details_json={"run_id": "run-1"},
    )
    mark_geometry_editorial_override(loc)
    _apply_substrate_location_merge(loc, **_merge_kwargs())
    assert loc.geometry_json == catalog
    assert loc.geometry_type == "Polygon"
    assert loc.h3_cell == "oldcell"
    assert loc.identity_fingerprint == "fp-northalsted-stale"
    details = loc.source_details_json if isinstance(loc.source_details_json, dict) else {}
    assert details.get(GEOMETRY_EDITORIAL_OVERRIDE_KEY) is True
    assert details.get("run_id") == "run-2"


def test_merge_clears_editorial_override_on_authoritative_rejection() -> None:
    from backfield_db import SubstrateLocation

    loc = SubstrateLocation(
        project_id=1,
        name="Northalsted",
        normalized_name="northalsted",
        identity_fingerprint="fp-northalsted-stale",
        geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
        geometry_type="Point",
        source_details_json={GEOMETRY_EDITORIAL_OVERRIDE_KEY: True},
    )
    _apply_substrate_location_merge(loc, **_merge_kwargs(), clear_geocode_identity=True)
    assert loc.geometry_json is None
    assert loc.geometry is None
    details = loc.source_details_json if isinstance(loc.source_details_json, dict) else {}
    assert GEOMETRY_EDITORIAL_OVERRIDE_KEY not in details

