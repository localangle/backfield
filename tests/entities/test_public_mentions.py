"""Tests for public project-wide mention queries."""

from __future__ import annotations

from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateArticleMeta,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.public.mentions import (
    PublicMentionSearchParams,
    get_public_mention,
    get_public_mention_facets,
    search_public_mentions,
)
from sqlmodel import Session, SQLModel, create_engine


def _seed_mentions(session: Session) -> tuple[int, int, int, int, int]:
    org = BackfieldOrganization(name="Org", slug="org-public-mentions")
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

    article = SubstrateArticle(
        project_id=project_id,
        headline="Budget vote",
        author="Jane Doe",
        pub_date=date(2024, 3, 1),
        text="City Hall debate",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    article_id = int(article.id)  # type: ignore[arg-type]
    session.add(
        SubstrateArticleMeta(
            article_id=article_id,
            meta_type="subject",
            category="local_government_politics",
            rationale="test",
            confidence=0.9,
        )
    )

    location_canon = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        label="City Hall",
        slug="city-hall",
        location_type="place",
    )
    person_canon = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        label="Jane Doe",
        slug="jane-doe",
        person_type="elected_official",
        public_figure=True,
    )
    org_canon = StylebookOrganizationCanonical(
        stylebook_id=stylebook_id,
        label="City Council",
        slug="city-council",
        organization_type="government",
    )
    session.add(location_canon)
    session.add(person_canon)
    session.add(org_canon)
    session.commit()
    session.refresh(location_canon)
    session.refresh(person_canon)
    session.refresh(org_canon)

    location = SubstrateLocation(
        project_id=project_id,
        name="City Hall",
        normalized_name="city hall",
        location_type="place",
        stylebook_location_canonical_id=str(location_canon.id),
    )
    person = SubstratePerson(
        project_id=project_id,
        name="Jane Doe",
        normalized_name="jane doe",
        person_type="elected_official",
        public_figure=True,
        stylebook_person_canonical_id=str(person_canon.id),
    )
    organization = SubstrateOrganization(
        project_id=project_id,
        name="City Council",
        normalized_name="city council",
        organization_type="government",
        stylebook_organization_canonical_id=str(org_canon.id),
    )
    session.add(location)
    session.add(person)
    session.add(organization)
    session.commit()
    session.refresh(location)
    session.refresh(person)
    session.refresh(organization)

    location_mention = SubstrateLocationMention(
        article_id=article_id,
        location_id=int(location.id),  # type: ignore[arg-type]
        nature="primary",
    )
    person_mention = SubstratePersonMention(
        article_id=article_id,
        person_id=int(person.id),  # type: ignore[arg-type]
        nature="subject",
    )
    organization_mention = SubstrateOrganizationMention(
        article_id=article_id,
        organization_id=int(organization.id),  # type: ignore[arg-type]
        nature="actor",
    )
    session.add(location_mention)
    session.add(person_mention)
    session.add(organization_mention)
    session.commit()
    session.refresh(location_mention)
    session.refresh(person_mention)
    session.refresh(organization_mention)

    session.add(
        SubstrateLocationMentionOccurrence(
            location_mention_id=int(location_mention.id),  # type: ignore[arg-type]
            mention_text="City Hall",
            quote_text="debate",
            occurrence_order=0,
        )
    )
    session.add(
        SubstrateLocationMentionOccurrence(
            location_mention_id=int(location_mention.id),  # type: ignore[arg-type]
            mention_text="City Hall",
            quote_text="second span",
            occurrence_order=1,
        )
    )
    session.add(
        SubstratePersonMentionOccurrence(
            person_mention_id=int(person_mention.id),  # type: ignore[arg-type]
            mention_text="Jane Doe",
        )
    )
    session.commit()

    return (
        project_id,
        int(location_mention.id),  # type: ignore[arg-type]
        int(person_mention.id),  # type: ignore[arg-type]
        int(organization_mention.id),  # type: ignore[arg-type]
        article_id,
    )


def test_search_public_mentions_returns_all_types() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, location_mid, person_mid, org_mid, _ = _seed_mentions(session)

        items, total = search_public_mentions(
            session,
            project_id=project_id,
            params=PublicMentionSearchParams(),
        )
        assert total == 3
        assert {item.mention_id for item in items} == {location_mid, person_mid, org_mid}
        assert all(item.article.headline == "Budget vote" for item in items)


def test_search_public_mentions_filters_by_entity_type_and_nature() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, location_mid, _, _, _ = _seed_mentions(session)

        items, total = search_public_mentions(
            session,
            project_id=project_id,
            params=PublicMentionSearchParams(entity_type="location", nature="primary"),
        )
        assert total == 1
        assert items[0].mention_id == location_mid
        assert items[0].location_type == "place"


def test_search_public_mentions_filters_by_author_and_section() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _, _, _, _ = _seed_mentions(session)

        _, total = search_public_mentions(
            session,
            project_id=project_id,
            params=PublicMentionSearchParams(author="Jane Doe"),
        )
        assert total == 3

        items, total = search_public_mentions(
            session,
            project_id=project_id,
            params=PublicMentionSearchParams(section="local_government_politics"),
        )
        assert total == 3
        assert len(items) == 3


def test_search_public_mentions_filters_by_has_canonical_and_q() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _, person_mid, _, _ = _seed_mentions(session)

        _, total = search_public_mentions(
            session,
            project_id=project_id,
            params=PublicMentionSearchParams(has_canonical=True),
        )
        assert total == 3

        items, total = search_public_mentions(
            session,
            project_id=project_id,
            params=PublicMentionSearchParams(q="Jane", entity_type="person"),
        )
        assert total == 1
        assert items[0].mention_id == person_mid


def test_get_public_mention_detail_returns_all_occurrences() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, location_mid, _, _, _ = _seed_mentions(session)

        detail = get_public_mention(
            session,
            project_id=project_id,
            entity_type="location",
            mention_id=location_mid,
        )
        assert detail is not None
        assert detail.label == "City Hall"
        assert len(detail.occurrences) == 2
        assert detail.canonical is not None
        assert detail.canonical.label == "City Hall"


def test_get_public_mention_returns_none_for_wrong_project() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, location_mid, _, _, _ = _seed_mentions(session)

        detail = get_public_mention(
            session,
            project_id=project_id + 999,
            entity_type="location",
            mention_id=location_mid,
        )
        assert detail is None


def test_get_public_mention_facets() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _, _, _, _ = _seed_mentions(session)

        facets = get_public_mention_facets(session, project_id=project_id)
        assert facets.entity_types == ["location", "person", "organization"]
        assert "primary" in facets.natures
        assert "subject" in facets.natures
        assert "place" in facets.location_types
        assert "elected_official" in facets.person_types
        assert "government" in facets.organization_types
