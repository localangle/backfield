"""Tests for public canonical location queries."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookConnection,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.public.connections import list_public_entity_connections
from backfield_entities.public.location_geo_search import (
    PublicLocationGeoSearchMode,
    PublicLocationGeoSearchParams,
    search_public_locations_by_geo,
)
from backfield_entities.public.locations import (
    PublicLocationSearchParams,
    get_public_location,
    list_public_location_articles,
    list_public_location_mentions,
    search_public_locations,
)
from backfield_entities.public.stylebook_scope import list_public_location_type_values
from sqlmodel import Session, SQLModel, create_engine, select


def _seed_locations(session: Session) -> tuple[int, int, str]:
    org = BackfieldOrganization(name="Org", slug="org-public-locations")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    stylebook = ensure_default_stylebook_for_organization(session, oid)
    stylebook_id = int(stylebook.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="News", slug="news", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    project_id = int(proj.id)  # type: ignore[arg-type]

    city_hall = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        label="City Hall",
        slug="city-hall",
        location_type="place",
        formatted_address="123 Main St",
        geometry_type="Point",
        geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
    )
    other = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        label="Far Away Park",
        slug="far-away-park",
        location_type="place",
        geometry_type="Point",
        geometry_json={"type": "Point", "coordinates": [-88.0, 42.5]},
    )
    session.add(city_hall)
    session.add(other)
    session.commit()
    session.refresh(city_hall)
    session.refresh(other)

    article = SubstrateArticle(
        project_id=project_id,
        headline="Budget vote",
        text="Body",
        pub_date=date(2024, 3, 1),
    )
    session.add(article)
    session.commit()
    session.refresh(article)

    location = SubstrateLocation(
        project_id=project_id,
        name="City Hall",
        normalized_name="city hall",
        location_type="place",
        formatted_address="123 Main St",
        stylebook_location_canonical_id=str(city_hall.id),
        geometry_type="Point",
        geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
    )
    session.add(location)
    session.commit()
    session.refresh(location)
    session.add(
        SubstrateLocationMention(
            article_id=int(article.id),  # type: ignore[arg-type]
            location_id=int(location.id),  # type: ignore[arg-type]
            nature="primary",
        )
    )
    session.commit()
    session.refresh(location)
    mention = session.exec(
        select(SubstrateLocationMention).where(
            SubstrateLocationMention.location_id == int(location.id)  # type: ignore[arg-type]
        )
    ).one()
    session.add(
        SubstrateLocationMentionOccurrence(
            location_mention_id=int(mention.id),  # type: ignore[arg-type]
            mention_text="City Hall",
            quote_text="debate at City Hall",
        )
    )
    session.commit()
    return stylebook_id, project_id, str(city_hall.id)


def test_search_public_locations_filters_by_name_and_type() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, city_hall_id = _seed_locations(session)

        items, total = search_public_locations(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicLocationSearchParams(q="City Hall"),
        )
        assert total == 1
        assert items[0].id == city_hall_id
        assert items[0].mention_count == 1
        assert items[0].geometry_json is not None

        items, total = search_public_locations(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicLocationSearchParams(location_type="place"),
        )
        assert total == 2


def test_search_public_locations_by_geo_point() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, city_hall_id = _seed_locations(session)

        items, total = search_public_locations_by_geo(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicLocationGeoSearchParams(
                mode=PublicLocationGeoSearchMode.point,
                center_lng=-87.6,
                center_lat=41.8,
                radius_miles=5,
            ),
        )
        assert total == 1
        assert items[0].id == city_hall_id

        items, total = search_public_locations_by_geo(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicLocationGeoSearchParams(
                mode=PublicLocationGeoSearchMode.point,
                center_lng=-87.6,
                center_lat=41.8,
                radius_miles=0.1,
            ),
        )
        assert total == 1

        items, total = search_public_locations_by_geo(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicLocationGeoSearchParams(
                mode=PublicLocationGeoSearchMode.point,
                center_lng=-122.0,
                center_lat=37.0,
                radius_miles=1,
            ),
        )
        assert total == 0


def test_get_public_location_and_mentions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, city_hall_id = _seed_locations(session)

        location = get_public_location(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            location_id=city_hall_id,
        )
        assert location is not None
        assert location.formatted_address == "123 Main St"

        result = list_public_location_mentions(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            location_id=city_hall_id,
        )
        assert result is not None
        items, total = result
        assert total == 1
        assert items[0].article.headline == "Budget vote"
        assert items[0].nature == "primary"


def test_list_public_location_mentions_filters_by_quote() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, city_hall_id = _seed_locations(session)

        unfiltered = list_public_location_mentions(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            location_id=city_hall_id,
        )
        assert unfiltered is not None
        assert unfiltered[1] == 1

        quoted = list_public_location_mentions(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            location_id=city_hall_id,
            quotes_only=True,
        )
        assert quoted is not None
        items, total = quoted
        assert total == 1
        assert items[0].evidence is not None
        assert items[0].evidence.quote_text == "debate at City Hall"


def test_list_public_location_articles() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, city_hall_id = _seed_locations(session)

        result = list_public_location_articles(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            location_id=city_hall_id,
        )
        assert result is not None
        items, total = result
        assert total == 1
        assert items[0].headline == "Budget vote"


def test_list_public_entity_connections_for_location() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, city_hall_id = _seed_locations(session)
        person_id = str(uuid4())
        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=person_id,
                to_entity_type="location",
                to_entity_id=city_hall_id,
                nature="works_at",
            )
        )
        session.commit()

        connections = list_public_entity_connections(
            session,
            project_id=project_id,
            stylebook_id=stylebook_id,
            entity_type="location",
            entity_id=city_hall_id,
        )
        assert len(connections) == 1
        assert connections[0].nature == "works_at"


def test_list_public_location_type_values() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _, _ = _seed_locations(session)
        types = list_public_location_type_values(session, stylebook_id=stylebook_id)
        assert "place" in types
