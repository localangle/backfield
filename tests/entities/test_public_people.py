"""Tests for public canonical person queries."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookConnection,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.public.connections import list_public_entity_connections
from backfield_entities.public.people import (
    PublicPersonSearchParams,
    get_public_person,
    list_public_person_articles,
    list_public_person_mentions,
    search_public_people,
)
from backfield_entities.public.stylebook_scope import list_public_person_type_values
from sqlmodel import Session, SQLModel, create_engine


def _seed_people(session: Session) -> tuple[int, int, str]:
    org = BackfieldOrganization(name="Org", slug="org-public-people")
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

    mayor = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        label="Jane Doe",
        slug="jane-doe",
        title="Mayor",
        affiliation="City Hall",
        person_type="elected_official",
        public_figure=True,
    )
    other = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        label="John Smith",
        slug="john-smith",
        affiliation="Local Shop",
    )
    session.add(mayor)
    session.add(other)
    session.commit()
    session.refresh(mayor)
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

    person = SubstratePerson(
        project_id=project_id,
        name="Jane Doe",
        normalized_name="jane doe",
        stylebook_person_canonical_id=str(mayor.id),
        title="Mayor",
        affiliation="City Hall",
    )
    session.add(person)
    session.commit()
    session.refresh(person)
    session.add(
        SubstratePersonMention(
            article_id=int(article.id),  # type: ignore[arg-type]
            person_id=int(person.id),  # type: ignore[arg-type]
            nature="subject",
        )
    )
    session.commit()
    return stylebook_id, project_id, str(mayor.id)


def test_search_public_people_filters_by_name_and_affiliation() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, mayor_id = _seed_people(session)

        items, total = search_public_people(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicPersonSearchParams(q="Jane"),
        )
        assert total == 1
        assert items[0].id == mayor_id
        assert items[0].mention_count == 1

        items, total = search_public_people(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicPersonSearchParams(affiliation="City Hall"),
        )
        assert total == 1
        assert items[0].label == "Jane Doe"

        items, total = search_public_people(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicPersonSearchParams(min_mentions=1),
        )
        assert total == 1


def test_get_public_person_and_mentions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, mayor_id = _seed_people(session)

        person = get_public_person(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            person_id=mayor_id,
        )
        assert person is not None
        assert person.title == "Mayor"
        assert person.stylebook_slug == "default"

        result = list_public_person_mentions(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            person_id=mayor_id,
        )
        assert result is not None
        items, total = result
        assert total == 1
        assert items[0].article.headline == "Budget vote"
        assert items[0].nature == "subject"


def test_list_public_person_articles() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, mayor_id = _seed_people(session)

        result = list_public_person_articles(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            person_id=mayor_id,
        )
        assert result is not None
        items, total = result
        assert total == 1
        assert items[0].headline == "Budget vote"
        assert items[0].author is None

        filtered_result = list_public_person_articles(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            person_id=mayor_id,
            nature="subject",
        )
        assert filtered_result is not None
        filtered, filtered_total = filtered_result
        assert filtered_total == 1
        assert len(filtered) == 1


def test_list_public_entity_connections_for_person() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, mayor_id = _seed_people(session)
        location_id = str(uuid4())
        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=mayor_id,
                to_entity_type="location",
                to_entity_id=location_id,
                nature="works_at",
            )
        )
        session.commit()

        connections = list_public_entity_connections(
            session,
            project_id=project_id,
            stylebook_id=stylebook_id,
            entity_type="person",
            entity_id=mayor_id,
        )
        assert len(connections) == 1
        assert connections[0].nature == "works_at"
        assert connections[0].to_entity_id == location_id


def test_list_public_person_type_values() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _, _ = _seed_people(session)
        types = list_public_person_type_values(session, stylebook_id=stylebook_id)
        assert "elected_official" in types
