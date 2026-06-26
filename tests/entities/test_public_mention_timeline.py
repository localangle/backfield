"""Tests for public canonical entity mention timelines."""

from __future__ import annotations

from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.public.mention_timeline import (
    PublicEntityMentionTimelineParams,
    list_public_location_mention_timeline,
    list_public_person_mention_timeline,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _seed_person_timeline(session: Session) -> tuple[int, int, str]:
    org = BackfieldOrganization(name="Org", slug="org-public-mention-timeline")
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
    )
    session.add(mayor)
    session.commit()
    session.refresh(mayor)

    march_article = SubstrateArticle(
        project_id=project_id,
        headline="March story",
        text="Body",
        pub_date=date(2024, 3, 1),
    )
    february_article = SubstrateArticle(
        project_id=project_id,
        headline="February story",
        text="Body",
        pub_date=date(2024, 2, 1),
    )
    session.add(march_article)
    session.add(february_article)
    session.commit()
    session.refresh(march_article)
    session.refresh(february_article)

    person = SubstratePerson(
        project_id=project_id,
        name="Jane Doe",
        normalized_name="jane doe",
        stylebook_person_canonical_id=str(mayor.id),
    )
    person_two = SubstratePerson(
        project_id=project_id,
        name="Jane Doe",
        normalized_name="jane doe",
        stylebook_person_canonical_id=str(mayor.id),
    )
    session.add(person)
    session.add(person_two)
    session.commit()
    session.refresh(person)
    session.refresh(person_two)

    session.add(
        SubstratePersonMention(
            article_id=int(march_article.id),  # type: ignore[arg-type]
            person_id=int(person.id),  # type: ignore[arg-type]
            nature="subject",
        )
    )
    session.add(
        SubstratePersonMention(
            article_id=int(february_article.id),  # type: ignore[arg-type]
            person_id=int(person.id),  # type: ignore[arg-type]
            nature="subject",
        )
    )
    session.add(
        SubstratePersonMention(
            article_id=int(march_article.id),  # type: ignore[arg-type]
            person_id=int(person_two.id),  # type: ignore[arg-type]
            nature="actor",
        )
    )
    session.commit()
    return stylebook_id, project_id, str(mayor.id)


def test_list_public_person_mention_timeline_groups_by_pub_date() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, person_id = _seed_person_timeline(session)

        items = list_public_person_mention_timeline(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            person_id=person_id,
        )
        assert items is not None
        assert len(items) == 2
        assert items[0].pub_date == date(2024, 2, 1)
        assert items[0].mention_count == 1
        assert items[1].pub_date == date(2024, 3, 1)
        assert items[1].mention_count == 2


def test_list_public_person_mention_timeline_filters_by_pub_date() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, person_id = _seed_person_timeline(session)

        items = list_public_person_mention_timeline(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            person_id=person_id,
            params=PublicEntityMentionTimelineParams(pub_date_from=date(2024, 3, 1)),
        )
        assert items is not None
        assert len(items) == 1
        assert items[0].pub_date == date(2024, 3, 1)
        assert items[0].mention_count == 2


def test_list_public_location_mention_timeline_filters_by_quote() -> None:
    from backfield_db import (
        StylebookLocationCanonical,
        SubstrateLocation,
        SubstrateLocationMention,
        SubstrateLocationMentionOccurrence,
    )

    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-timeline-quote")
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
        )
        session.add(city_hall)
        session.commit()
        session.refresh(city_hall)

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
            stylebook_location_canonical_id=str(city_hall.id),
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

        unfiltered = list_public_location_mention_timeline(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            location_id=str(city_hall.id),
        )
        assert unfiltered is not None
        assert len(unfiltered) == 1
        assert unfiltered[0].mention_count == 1

        quoted = list_public_location_mention_timeline(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            location_id=str(city_hall.id),
            params=PublicEntityMentionTimelineParams(quotes_only=True),
        )
        assert quoted is not None
        assert len(quoted) == 1
        assert quoted[0].mention_count == 1
