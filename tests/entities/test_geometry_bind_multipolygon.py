"""GeoJSON → WKT / PostGIS bind helpers."""

from __future__ import annotations

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.geo.geometry_bind import (
    GeometryBindError,
    assign_geojson_geometry,
    geojson_to_wkt,
    normalize_geojson_type,
)
from backfield_entities.geo.rebind_postgis import rebind_missing_location_postgis_geometry
from sqlmodel import Session, SQLModel, create_engine

ROUTE_W_MULTIPOLYGON: dict = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-92.1805, 38.5943],
                [-92.1708, 38.5943],
                [-92.1708, 38.5977],
                [-92.1805, 38.5977],
                [-92.1805, 38.5943],
            ]
        ]
    ],
}


def _seed_project(session: Session, *, slug_suffix: str) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug=f"org-{slug_suffix}")
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(
        organization_id=org_id,
        slug="default",
        name="Default",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    ws = BackfieldWorkspace(
        organization_id=org_id,
        stylebook_id=sb_id,
        name="WS",
        slug="ws",
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)
    proj = BackfieldProject(
        organization_id=org_id,
        workspace_id=int(ws.id),  # type: ignore[arg-type]
        stylebook_id=sb_id,
        name="P",
        slug="p",
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_normalize_geojson_type_preserves_multipolygon() -> None:
    # ``str.title()`` turns MultiPolygon into Multipolygon — that must never gate WKT.
    assert normalize_geojson_type("MultiPolygon") == "MultiPolygon"
    assert normalize_geojson_type("multipolygon") == "MultiPolygon"
    assert normalize_geojson_type("LineString") == "LineString"
    assert normalize_geojson_type("linestring") == "LineString"


def test_geojson_to_wkt_multipolygon() -> None:
    wkt = geojson_to_wkt(ROUTE_W_MULTIPOLYGON)
    assert wkt is not None
    assert wkt.startswith("MULTIPOLYGON ((")
    assert "-92.1805 38.5943" in wkt


def test_geojson_to_wkt_linestring() -> None:
    wkt = geojson_to_wkt(
        {
            "type": "LineString",
            "coordinates": [[-92.18, 38.59], [-92.17, 38.60]],
        }
    )
    assert wkt is not None
    assert wkt.startswith("LINESTRING (")
    assert "-92.18 38.59" in wkt
    assert "-92.17 38.6" in wkt


def test_assign_geojson_geometry_writes_postgis_for_multipolygon() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _sb_id, project_id = _seed_project(session, slug_suffix="mp")
        loc = SubstrateLocation(
            project_id=project_id,
            name="Route W",
            normalized_name="route w",
            location_type="street_road",
            identity_fingerprint="fp-route-w",
            geometry_json={"type": "Point", "coordinates": [-92.0, 38.0]},
            geometry="POINT (-92.0 38.0)",
            geometry_type="Point",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)

        assign_geojson_geometry(session, loc, ROUTE_W_MULTIPOLYGON)
        session.add(loc)
        session.commit()
        session.refresh(loc)

        assert loc.geometry_json == ROUTE_W_MULTIPOLYGON
        assert loc.geometry_type == "MultiPolygon"
        assert loc.geometry is not None
        assert str(loc.geometry).startswith("MULTIPOLYGON")
        assert loc.h3_cell is not None
        assert loc.h3_resolution == 8


def test_assign_geojson_geometry_rejects_unconvertible_shape() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        sb_id, _project_id = _seed_project(session, slug_suffix="bad")
        row = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Bad",
            slug="bad",
            location_type="street_road",
            primary_substrate_location_id=None,
            status="active",
            geometry="POINT (0 0)",
            geometry_json={"type": "Point", "coordinates": [0, 0]},
            geometry_type="Point",
        )
        session.add(row)
        session.commit()
        with pytest.raises(GeometryBindError):
            assign_geojson_geometry(
                session,
                row,
                {"type": "MultiPolygon", "coordinates": []},
            )
        # Prior PostGIS must remain — never half-update GeoJSON while clearing geometry.
        session.refresh(row)
        assert row.geometry is not None
        assert row.geometry_json == {"type": "Point", "coordinates": [0, 0]}


def test_rebind_missing_postgis_from_geometry_json() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        sb_id, project_id = _seed_project(session, slug_suffix="rebind")
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Route W",
            slug="route-w",
            location_type="street_road",
            primary_substrate_location_id=None,
            status="active",
            geometry_json=ROUTE_W_MULTIPOLYGON,
            geometry_type="MultiPolygon",
            geometry=None,
            h3_cell="8826550d37fffff",
            h3_resolution=8,
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)

        loc = SubstrateLocation(
            project_id=project_id,
            name="Route W",
            normalized_name="route w",
            location_type="street_road",
            identity_fingerprint="fp-route-w-rebind",
            stylebook_location_canonical_id=str(canon.id),
            geometry_json=ROUTE_W_MULTIPOLYGON,
            geometry_type="MultiPolygon",
            geometry=None,
            h3_cell="8826550d37fffff",
            h3_resolution=8,
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]
        cid = str(canon.id)

        dry = rebind_missing_location_postgis_geometry(session, dry_run=True)
        assert dry.rebound_count == 2
        assert cid in dry.canonical_ids
        assert sid in dry.substrate_ids
        session.refresh(loc)
        assert loc.geometry is None

        applied = rebind_missing_location_postgis_geometry(session, dry_run=False)
        session.commit()
        assert applied.rebound_count == 2
        session.refresh(loc)
        session.refresh(canon)
        assert loc.geometry is not None
        assert str(loc.geometry).startswith("MULTIPOLYGON")
        assert canon.geometry is not None
        assert str(canon.geometry).startswith("MULTIPOLYGON")
