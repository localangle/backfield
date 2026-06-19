"""Tests for public canonical organization queries."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookConnection,
    StylebookOrganizationCanonical,
    SubstrateArticle,
    SubstrateOrganization,
    SubstrateOrganizationMention,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.public.connections import list_public_entity_connections
from backfield_entities.public.organizations import (
    PublicOrganizationSearchParams,
    get_public_organization,
    list_public_organization_articles,
    list_public_organization_mentions,
    search_public_organizations,
)
from backfield_entities.public.stylebook_scope import list_public_organization_type_values
from sqlmodel import Session, SQLModel, create_engine


def _seed_organizations(session: Session) -> tuple[int, int, str]:
    org = BackfieldOrganization(name="Org", slug="org-public-orgs")
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

    council = StylebookOrganizationCanonical(
        stylebook_id=stylebook_id,
        label="City Council",
        slug="city-council",
        organization_type="government",
    )
    other = StylebookOrganizationCanonical(
        stylebook_id=stylebook_id,
        label="Acme Corp",
        slug="acme-corp",
        organization_type="company",
    )
    session.add(council)
    session.add(other)
    session.commit()
    session.refresh(council)
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

    organization = SubstrateOrganization(
        project_id=project_id,
        name="City Council",
        normalized_name="city council",
        stylebook_organization_canonical_id=str(council.id),
        organization_type="government",
    )
    session.add(organization)
    session.commit()
    session.refresh(organization)
    session.add(
        SubstrateOrganizationMention(
            article_id=int(article.id),  # type: ignore[arg-type]
            organization_id=int(organization.id),  # type: ignore[arg-type]
            nature="actor",
        )
    )
    session.commit()
    return stylebook_id, project_id, str(council.id)


def test_search_public_organizations_filters_by_name_and_type() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, council_id = _seed_organizations(session)

        items, total = search_public_organizations(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicOrganizationSearchParams(q="Council"),
        )
        assert total == 1
        assert items[0].id == council_id
        assert items[0].mention_count == 1

        items, total = search_public_organizations(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicOrganizationSearchParams(organization_type="government"),
        )
        assert total == 1
        assert items[0].label == "City Council"

        items, total = search_public_organizations(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            params=PublicOrganizationSearchParams(min_mentions=1),
        )
        assert total == 1


def test_get_public_organization_and_mentions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, council_id = _seed_organizations(session)

        organization = get_public_organization(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            organization_id=council_id,
        )
        assert organization is not None
        assert organization.organization_type == "government"

        result = list_public_organization_mentions(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            organization_id=council_id,
        )
        assert result is not None
        items, total = result
        assert total == 1
        assert items[0].article.headline == "Budget vote"
        assert items[0].nature == "actor"


def test_list_public_organization_articles() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, council_id = _seed_organizations(session)

        result = list_public_organization_articles(
            session,
            stylebook_id=stylebook_id,
            project_id=project_id,
            organization_id=council_id,
        )
        assert result is not None
        items, total = result
        assert total == 1
        assert items[0].headline == "Budget vote"


def test_list_public_entity_connections_for_organization() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, council_id = _seed_organizations(session)
        person_id = str(uuid4())
        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="organization",
                from_entity_id=council_id,
                to_entity_type="person",
                to_entity_id=person_id,
                nature="employs",
            )
        )
        session.commit()

        connections = list_public_entity_connections(
            session,
            project_id=project_id,
            stylebook_id=stylebook_id,
            entity_type="organization",
            entity_id=council_id,
        )
        assert len(connections) == 1
        assert connections[0].nature == "employs"
        assert connections[0].to_entity_id == person_id


def test_list_public_organization_type_values() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _, _ = _seed_organizations(session)
        types = list_public_organization_type_values(session, stylebook_id=stylebook_id)
        assert "government" in types
        assert "company" in types
