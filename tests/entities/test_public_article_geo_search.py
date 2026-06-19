"""Tests for public geographic article search."""

from __future__ import annotations

from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
)
from backfield_entities.geo.h3_index import derive_h3_index
from backfield_entities.public.article_geo_search import (
    PublicArticleGeoSearchMode,
    PublicArticleGeoSearchParams,
    search_public_articles_by_geo,
)
from sqlmodel import Session, SQLModel, create_engine


def _seed_geo_articles(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-public-geo-articles")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        name="News",
        slug="news",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    project_id = int(proj.id)  # type: ignore[arg-type]

    near = SubstrateArticle(
        project_id=project_id,
        headline="Downtown bridge vote",
        text="Story near downtown.",
        pub_date=date(2024, 3, 1),
    )
    far = SubstrateArticle(
        project_id=project_id,
        headline="Remote county news",
        text="Story far away.",
        pub_date=date(2024, 2, 1),
    )
    session.add(near)
    session.add(far)
    session.commit()
    session.refresh(near)
    session.refresh(far)

    for article, lng, lat, label, nature in (
        (near, -87.6, 41.8, "City Hall", "primary"),
        (far, -122.4, 37.8, "Bay Office", "secondary"),
    ):
        location = SubstrateLocation(
            project_id=project_id,
            name=label,
            normalized_name=label.lower(),
            location_type="place",
            formatted_address=label,
            geometry_type="Point",
            geometry_json={"type": "Point", "coordinates": [lng, lat]},
        )
        h3 = derive_h3_index(location.geometry_json)
        if h3 is not None:
            location.h3_cell = h3.h3_cell
            location.h3_resolution = h3.h3_resolution
        session.add(location)
        session.commit()
        session.refresh(location)
        session.add(
            SubstrateLocationMention(
                article_id=int(article.id),  # type: ignore[arg-type]
                location_id=int(location.id),  # type: ignore[arg-type]
                nature=nature,
            )
        )
    session.commit()
    return project_id


def test_search_public_articles_by_geo_point_radius() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_geo_articles(session)
        items, total = search_public_articles_by_geo(
            session,
            project_id=project_id,
            params=PublicArticleGeoSearchParams(
                mode=PublicArticleGeoSearchMode.point,
                center_lng=-87.6,
                center_lat=41.8,
                radius_miles=5.0,
            ),
        )

    assert total == 1
    assert len(items) == 1
    assert items[0].article.headline == "Downtown bridge vote"
    assert len(items[0].matching_locations) == 1
    assert items[0].matching_locations[0].label == "City Hall"
    assert items[0].matching_locations[0].h3_cell
    assert items[0].matching_locations[0].h3_resolution == 11
    assert items[0].search_mode == "point"


def test_search_public_articles_by_geo_bbox() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_geo_articles(session)
        items, total = search_public_articles_by_geo(
            session,
            project_id=project_id,
            params=PublicArticleGeoSearchParams(
                mode=PublicArticleGeoSearchMode.bbox,
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
            ),
        )

    assert total == 1
    assert items[0].article.headline == "Downtown bridge vote"
    assert items[0].search_mode == "bbox"


def test_search_public_articles_by_geo_nature_filter() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_geo_articles(session)
        items, total = search_public_articles_by_geo(
            session,
            project_id=project_id,
            params=PublicArticleGeoSearchParams(
                mode=PublicArticleGeoSearchMode.point,
                center_lng=-87.6,
                center_lat=41.8,
                radius_miles=5.0,
                nature="primary",
            ),
        )

    assert total == 1
    assert items[0].article.headline == "Downtown bridge vote"
    assert items[0].matching_locations[0].nature == "primary"

    with Session(engine) as session:
        items, total = search_public_articles_by_geo(
            session,
            project_id=project_id,
            params=PublicArticleGeoSearchParams(
                mode=PublicArticleGeoSearchMode.point,
                center_lng=-87.6,
                center_lat=41.8,
                radius_miles=5.0,
                nature="secondary",
            ),
        )

    assert total == 0
    assert items == []
