"""Occurrence persistence keeps evidence but only proven article offsets."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from sqlmodel import Session, SQLModel, create_engine
from stylebook_api.mention_occurrences import (
    replace_mention_occurrences_for_article,
    replace_organization_mention_occurrences_for_article,
    replace_person_mention_occurrences_for_article,
)


def _bootstrap_project(session: Session) -> int:
    organization = BackfieldOrganization(name="Org", slug="org-occurrence-spans")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    stylebook = ensure_default_stylebook_for_organization(session, int(organization.id))
    workspace = BackfieldWorkspace(
        organization_id=int(organization.id),
        stylebook_id=int(stylebook.id),
        name="Workspace",
        slug="ws-occurrence-spans",
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    project = BackfieldProject(
        organization_id=int(organization.id),
        workspace_id=int(workspace.id),
        name="Project",
        slug="proj-occurrence-spans",
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return int(project.id)


def test_review_occurrence_persistence_nulls_unproven_offsets_for_every_domain() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Council update",
            text="The council approved the budget after a long debate.",
        )
        location = SubstrateLocation(
            project_id=project_id,
            name="City Hall",
            normalized_name="city hall",
        )
        person = SubstratePerson(
            project_id=project_id,
            name="Jane Doe",
            normalized_name="jane doe",
        )
        organization = SubstrateOrganization(
            project_id=project_id,
            name="City Council",
            normalized_name="city council",
        )
        session.add_all((article, location, person, organization))
        session.commit()
        session.refresh(article)
        session.refresh(location)
        session.refresh(person)
        session.refresh(organization)

        evidence = {
            "mention_text": "Officials rejected the proposal after residents testified.",
            "quote_text": "Officials rejected the proposal after residents testified.",
            "start_char": 0,
            "end_char": 11,
            "is_quote": True,
        }
        location_rows = replace_mention_occurrences_for_article(
            session,
            article_id=int(article.id),
            location_id=int(location.id),
            occurrences_in=[evidence],
        )
        person_rows = replace_person_mention_occurrences_for_article(
            session,
            article_id=int(article.id),
            person_id=int(person.id),
            occurrences_in=[evidence],
        )
        organization_rows = replace_organization_mention_occurrences_for_article(
            session,
            article_id=int(article.id),
            organization_id=int(organization.id),
            occurrences_in=[evidence],
        )

        for row in (*location_rows, *person_rows, *organization_rows):
            assert row.start_char is None
            assert row.end_char is None
            assert row.mention_text == evidence["mention_text"]
            assert row.quote_text == evidence["quote_text"]
