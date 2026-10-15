"""PostGIS coverage for radius search geometry.

The default suite runs on SQLite, where ``_sqlite_geometry_matches`` matches
points only. Coverage that depends on PostGIS geometry therefore needs
``BACKFIELD_DATABASE_URL_DIRECT``, the same way the worker's Postgres tests do.
"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
)
from backfield_entities.geo.geometry_bind import assign_geojson_geometry
from backfield_entities.public.article_geo_search import (
    PublicArticleGeoSearchMode,
    PublicArticleGeoSearchParams,
    search_public_articles_by_geo,
)
from sqlalchemy import delete, text
from sqlmodel import Session, col, create_engine, select

from tests.project_helpers import project_ownership_fields

_DATABASE_URL = os.getenv("BACKFIELD_DATABASE_URL_DIRECT", "")

requires_postgres = pytest.mark.skipif(
    not _DATABASE_URL.startswith("postgresql"),
    reason="requires BACKFIELD_DATABASE_URL_DIRECT for PostgreSQL",
)

CENTER_LNG = -77.0
CENTER_LAT = 39.0


def _cleanup(session: Session, project_id: int) -> None:
    article_ids = session.exec(  # type: ignore[call-overload]
        select(SubstrateArticle.id).where(
            SubstrateArticle.project_id == project_id  # type: ignore[arg-type]
        )
    ).all()
    if article_ids:
        session.exec(  # type: ignore[call-overload]
            delete(SubstrateLocationMention).where(
                col(SubstrateLocationMention.article_id).in_([int(a) for a in article_ids])
            )
        )
    session.exec(  # type: ignore[call-overload]
        delete(SubstrateLocation).where(
            SubstrateLocation.project_id == project_id  # type: ignore[arg-type]
        )
    )
    session.exec(  # type: ignore[call-overload]
        delete(SubstrateArticle).where(
            SubstrateArticle.project_id == project_id  # type: ignore[arg-type]
        )
    )
    project = session.get(BackfieldProject, project_id)
    if project is not None:
        organization_id = int(project.organization_id)
        session.delete(project)
        session.commit()
        organization = session.get(BackfieldOrganization, organization_id)
        if organization is not None:
            session.delete(organization)
    session.commit()


def _ids(session: Session, *, project_id: int, **overrides) -> set[int]:
    params = PublicArticleGeoSearchParams(
        mode=PublicArticleGeoSearchMode.point,
        center_lng=CENTER_LNG,
        center_lat=CENTER_LAT,
        **overrides,
    )
    items, _total = search_public_articles_by_geo(
        session,
        project_id=project_id,
        params=params,
    )
    return {int(item.id) for item in items}


def _ring_of_points(session: Session, suffix: str, *, radius_miles: float, fraction: float):
    """Seed one article per bearing, each at a fixed fraction of the radius.

    ``ST_Project`` places each point on the WGS84 spheroid, the model
    ``ST_DWithin`` measures with, so the distance is exact rather than a
    spherical estimate. The band these points sit in is about half a percent
    wide, so a spherical estimate would not be precise enough.
    """
    organization = BackfieldOrganization(name=f"Ring {suffix}", slug=f"ring-{suffix}")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    organization_id = int(organization.id)  # type: ignore[arg-type]

    project = BackfieldProject(
        **project_ownership_fields(session, organization_id),
        organization_id=organization_id,
        name=f"Ring {suffix}",
        slug=f"ring-{suffix}",
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    project_id = int(project.id)  # type: ignore[arg-type]

    meters = radius_miles * 1609.34 * fraction
    placed = session.exec(  # type: ignore[call-overload]
        text(
            """
            SELECT d AS bearing,
                   ST_X(p.geom::geometry) AS lng,
                   ST_Y(p.geom::geometry) AS lat
            FROM generate_series(0, 350, 10) AS d,
                 LATERAL (
                     SELECT ST_Project(
                         ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                         :meters,
                         radians(d)
                     ) AS geom
                 ) p
            """
        ).bindparams(lng=CENTER_LNG, lat=CENTER_LAT, meters=meters)
    ).all()
    assert len(placed) == 36

    article_ids: list[int] = []
    for row in placed:
        article = SubstrateArticle(
            project_id=project_id,
            headline=f"Bearing {int(row.bearing)}",
            text=f"Bearing {int(row.bearing)}",
            pub_date=date(2024, 6, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_ids.append(int(article.id))  # type: ignore[arg-type]

        location = SubstrateLocation(
            project_id=project_id,
            name=f"bearing-{int(row.bearing)}-{suffix}",
            normalized_name=f"bearing-{int(row.bearing)}-{suffix}",
            location_type="place",
            formatted_address=f"bearing-{int(row.bearing)}-{suffix}",
        )
        assign_geojson_geometry(
            session,
            location,
            {"type": "Point", "coordinates": [float(row.lng), float(row.lat)]},
        )
        session.add(location)
        session.commit()
        session.refresh(location)
        session.add(
            SubstrateLocationMention(
                article_id=article_ids[-1],
                location_id=int(location.id),  # type: ignore[arg-type]
                nature="primary",
            )
        )
        session.commit()

    return project_id, article_ids


@requires_postgres
def test_every_point_inside_the_radius_is_returned_whatever_its_bearing() -> None:
    """A point just inside the radius is returned from any direction.

    ST_Buffer on a geography returns a 32-sided polygon inscribed in the
    circle, and its edges sit inside the radius. Measured on PostGIS 3.6: of
    360 bearings at 3210 m from a center with a 3218.68 m radius, all 360 are
    within the radius and 136 fall inside the buffer polygon.
    """
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    with Session(engine) as session:
        project_id, article_ids = _ring_of_points(
            session,
            suffix,
            radius_miles=2.0,
            fraction=0.998,
        )
        try:
            found = _ids(session, project_id=project_id, radius_miles=2.0, limit=100)
            missing = sorted(set(article_ids) - found)
            assert not missing, (
                f"{len(missing)} of {len(article_ids)} points inside the radius were "
                "left out, so the radius is not being measured directly"
            )
        finally:
            _cleanup(session, project_id)


@requires_postgres
def test_a_point_outside_the_radius_is_still_excluded() -> None:
    """The paired control: the boundary holds, rather than simply widening."""
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    with Session(engine) as session:
        project_id, article_ids = _ring_of_points(
            session,
            suffix,
            radius_miles=2.0,
            fraction=1.002,
        )
        try:
            found = _ids(session, project_id=project_id, radius_miles=2.0, limit=100)
            assert not (set(article_ids) & found), (
                "points outside the radius were returned"
            )
        finally:
            _cleanup(session, project_id)


def _rectangle(*, half_lng: float, half_lat: float) -> dict:
    """Build the five-point box a geocoder viewport produces."""
    min_lng = CENTER_LNG - half_lng
    max_lng = CENTER_LNG + half_lng
    min_lat = CENTER_LAT - half_lat
    max_lat = CENTER_LAT + half_lat
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lng, min_lat],
                [max_lng, min_lat],
                [max_lng, max_lat],
                [min_lng, max_lat],
                [min_lng, min_lat],
            ]
        ],
    }


def _seed_two_areas(session: Session, suffix: str):
    """Seed a state-scale box and a block-scale box, both over the center.

    The query center is the centroid of the larger box on purpose. A rule that
    compared only centroids would still return the state article from a query
    placed anywhere else, and these tests would not notice.
    """
    organization = BackfieldOrganization(name=f"Areas {suffix}", slug=f"areas-{suffix}")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    organization_id = int(organization.id)  # type: ignore[arg-type]

    project = BackfieldProject(
        **project_ownership_fields(session, organization_id),
        organization_id=organization_id,
        name=f"Areas {suffix}",
        slug=f"areas-{suffix}",
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    project_id = int(project.id)  # type: ignore[arg-type]

    articles: dict[str, int] = {}
    # The first box spans about 215 by 138 miles, the scale of a state. The
    # second spans about one mile, the scale of a city block.
    for key, headline, half_lng, half_lat in (
        ("state", "Statewide budget vote", 2.0, 1.0),
        ("block", "Corner store reopens", 0.007, 0.007),
    ):
        article = SubstrateArticle(
            project_id=project_id,
            headline=headline,
            text=headline,
            pub_date=date(2024, 5, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        articles[key] = int(article.id)  # type: ignore[arg-type]

        location = SubstrateLocation(
            project_id=project_id,
            name=f"{key}-{suffix}",
            normalized_name=f"{key}-{suffix}",
            location_type="state" if key == "state" else "neighborhood",
            formatted_address=f"{key}-{suffix}",
        )
        assign_geojson_geometry(
            session,
            location,
            _rectangle(half_lng=half_lng, half_lat=half_lat),
        )
        session.add(location)
        session.commit()
        session.refresh(location)
        session.add(
            SubstrateLocationMention(
                article_id=articles[key],
                location_id=int(location.id),  # type: ignore[arg-type]
                nature="primary",
            )
        )
        session.commit()

    return project_id, articles["state"], articles["block"]


@requires_postgres
def test_a_state_scale_area_does_not_answer_a_two_mile_radius() -> None:
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    with Session(engine) as session:
        project_id, state_id, block_id = _seed_two_areas(session, suffix)
        try:
            found = _ids(session, project_id=project_id, radius_miles=2.0)
            assert block_id in found, (
                "a block-scale area should still answer a two-mile radius over it"
            )
            assert state_id not in found, (
                "a state-scale area should not answer a two-mile radius inside it"
            )
        finally:
            _cleanup(session, project_id)


@requires_postgres
def test_a_state_scale_area_still_answers_a_state_scale_radius() -> None:
    """The rule is relative to the radius asked for, not a blanket exclusion.

    Without this, a change that simply dropped every large area would pass the
    test above while leaving coarse places unreachable at any radius.
    """
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    with Session(engine) as session:
        project_id, state_id, block_id = _seed_two_areas(session, suffix)
        try:
            found = _ids(session, project_id=project_id, radius_miles=200.0)
            assert state_id in found
            assert block_id in found
        finally:
            _cleanup(session, project_id)


@requires_postgres
def test_a_caller_can_widen_the_limit() -> None:
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    with Session(engine) as session:
        project_id, state_id, block_id = _seed_two_areas(session, suffix)
        try:
            found = _ids(
                session,
                project_id=project_id,
                radius_miles=2.0,
                max_place_radius_miles=500.0,
            )
            assert state_id in found
            assert block_id in found
        finally:
            _cleanup(session, project_id)
