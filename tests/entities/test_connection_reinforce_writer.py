"""Unit tests for reinforce auto-connection writer."""

from __future__ import annotations

from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookConnection,
    StylebookConnectionEvidence,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.connections.types import AutoConnectionEdgeProposal, LinkedEntitySnapshot
from backfield_entities.connections.writer import write_auto_connections
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session) -> tuple[int, int, str, str, int]:
    org = BackfieldOrganization(name="Org", slug=f"org-{uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    stylebook = ensure_default_stylebook_for_organization(session, oid)
    stylebook_id = int(stylebook.id)  # type: ignore[arg-type]
    project = BackfieldProject(
        **project_ownership_fields(session, oid),
        name="News",
        slug=f"news-{uuid4().hex[:8]}",
        organization_id=oid,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    project_id = int(project.id)  # type: ignore[arg-type]

    person = StylebookPersonCanonical(
        id=str(uuid4()),
        stylebook_id=stylebook_id,
        label="Jane",
        slug="jane",
    )
    organization = StylebookOrganizationCanonical(
        id=str(uuid4()),
        stylebook_id=stylebook_id,
        label="City Hall",
        slug="city-hall",
    )
    session.add(person)
    session.add(organization)
    article = SubstrateArticle(
        project_id=project_id,
        headline="Policy",
        text="Jane works for City Hall.",
        url=f"https://example.com/{uuid4().hex}",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return project_id, stylebook_id, str(person.id), str(organization.id), int(article.id)  # type: ignore[arg-type]


def _snapshots(person_id: str, org_id: str) -> tuple[LinkedEntitySnapshot, LinkedEntitySnapshot]:
    return (
        LinkedEntitySnapshot(
            entity_type="person",
            substrate_id=1,
            canonical_id=person_id,
            label="Jane",
        ),
        LinkedEntitySnapshot(
            entity_type="organization",
            substrate_id=2,
            canonical_id=org_id,
            label="City Hall",
        ),
    )


def test_write_creates_edge_and_evidence_child() -> None:
    session = _session()
    project_id, _sb, person_id, org_id, article_id = _seed(session)
    person, organization = _snapshots(person_id, org_id)
    result = write_auto_connections(
        session,
        project_id=project_id,
        from_entity_type="person",
        to_entity_type="organization",
        from_entities=(person,),
        to_entities=(organization,),
        edges=[
            AutoConnectionEdgeProposal(
                from_entity_id=person_id,
                to_entity_id=org_id,
                description="Jane works for City Hall",
                nature="works_for",
                confidence=0.95,
                quote="Jane works for City Hall",
                reason="explicit employment",
            )
        ],
        article_id=article_id,
        run_id="run-1",
        processed_item_id=None,
        adjudication_model="gpt-test",
        adjudication_ai_model_config_id=None,
    )
    session.commit()

    assert len(result.created) == 1
    assert result.reinforced == []
    conn = session.exec(select(StylebookConnection)).one()
    assert conn.nature == "works_for"
    evidence = session.exec(select(StylebookConnectionEvidence)).one()
    assert evidence.article_id == article_id
    assert evidence.description == "Jane works for City Hall"


def test_write_reinforces_same_nature_different_description() -> None:
    session = _session()
    project_id, stylebook_id, person_id, org_id, article_id = _seed(session)
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=person_id,
            to_entity_type="organization",
            to_entity_id=org_id,
            nature="works_for",
        )
    )
    session.commit()
    person, organization = _snapshots(person_id, org_id)

    result = write_auto_connections(
        session,
        project_id=project_id,
        from_entity_type="person",
        to_entity_type="organization",
        from_entities=(person,),
        to_entities=(organization,),
        edges=[
            AutoConnectionEdgeProposal(
                from_entity_id=person_id,
                to_entity_id=org_id,
                description="new narrative from another article",
                nature="works_for",
                confidence=0.97,
                quote="Jane is employed by City Hall",
                reason="employment",
            )
        ],
        article_id=article_id,
        run_id="run-2",
        processed_item_id=None,
        adjudication_model=None,
        adjudication_ai_model_config_id=None,
    )
    session.commit()

    assert result.created == []
    assert len(result.reinforced) == 1
    assert len(session.exec(select(StylebookConnection)).all()) == 1
    assert len(session.exec(select(StylebookConnectionEvidence)).all()) == 1


def test_write_skips_duplicate_article_evidence() -> None:
    session = _session()
    project_id, stylebook_id, person_id, org_id, article_id = _seed(session)
    person, organization = _snapshots(person_id, org_id)
    first = write_auto_connections(
        session,
        project_id=project_id,
        from_entity_type="person",
        to_entity_type="organization",
        from_entities=(person,),
        to_entities=(organization,),
        edges=[
            AutoConnectionEdgeProposal(
                from_entity_id=person_id,
                to_entity_id=org_id,
                description="Jane works for City Hall",
                nature="works_for",
                confidence=0.95,
                quote="Jane works for City Hall",
            )
        ],
        article_id=article_id,
        run_id="run-1",
        processed_item_id=None,
        adjudication_model=None,
        adjudication_ai_model_config_id=None,
    )
    session.commit()
    assert len(first.created) == 1

    second = write_auto_connections(
        session,
        project_id=project_id,
        from_entity_type="person",
        to_entity_type="organization",
        from_entities=(person,),
        to_entities=(organization,),
        edges=[
            AutoConnectionEdgeProposal(
                from_entity_id=person_id,
                to_entity_id=org_id,
                description="Different wording same article",
                nature="works_for",
                confidence=0.99,
                quote="Different wording",
            )
        ],
        article_id=article_id,
        run_id="run-2",
        processed_item_id=None,
        adjudication_model=None,
        adjudication_ai_model_config_id=None,
    )
    session.commit()
    assert second.created == []
    assert second.reinforced == []
    assert second.skipped_existing_count == 1
    assert len(session.exec(select(StylebookConnectionEvidence)).all()) == 1
