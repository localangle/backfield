"""Standalone location create must write PostGIS ``geometry`` alongside GeoJSON."""

from __future__ import annotations

from backfield_db import BackfieldOrganization, Stylebook, StylebookLocationCanonical
from backfield_entities.entities.location.persist import create_standalone_canonical
from backfield_entities.geo.geometry_bind import geojson_to_wkt
from sqlmodel import Session, SQLModel, create_engine, select


def _seed_stylebook(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-loc-geom")
    session.add(org)
    session.commit()
    session.refresh(org)
    sb = Stylebook(
        organization_id=int(org.id),  # type: ignore[arg-type]
        slug="default",
        name="Default",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    return int(sb.id)  # type: ignore[arg-type]


def test_create_standalone_canonical_binds_postgis_geometry_from_geojson() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [-92.0, 45.0],
                [-92.0, 45.1],
                [-91.9, 45.1],
                [-91.9, 45.0],
                [-92.0, 45.0],
            ]
        ],
    }
    expected_wkt = geojson_to_wkt(polygon)
    assert expected_wkt is not None

    with Session(engine) as session:
        sb_id = _seed_stylebook(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="Town Boundary",
            location_type="city",
            geometry_json=polygon,
            provenance="stylebook_ui_import_geojson",
        )
        session.commit()
        cid = str(canon.id)

    with Session(engine) as session:
        row = session.get(StylebookLocationCanonical, cid)
        assert row is not None
        assert row.geometry_json == polygon
        assert row.geometry_type == "Polygon"
        assert row.geometry is not None
        assert str(row.geometry) == expected_wkt
        assert row.h3_cell is not None


def test_create_standalone_canonical_without_geometry_leaves_postgis_null() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        sb_id = _seed_stylebook(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="No Map",
            provenance="stylebook_ui_manual",
        )
        session.commit()
        assert canon.geometry is None
        assert canon.geometry_json is None
        rows = session.exec(select(StylebookLocationCanonical)).all()
        assert len(rows) == 1
