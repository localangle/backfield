"""Article-scoped raw-entry provenance for persisted entity mentions."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstratePerson,
    SubstratePersonMention,
)
from sqlmodel import Session, SQLModel, create_engine, select
from worker.substrate.entities.location.mentions import (
    _upsert_mention_and_occurrence as upsert_location_mention,
)
from worker.substrate.entities.organization.mentions import (
    _upsert_mention_and_occurrence as upsert_organization_mention,
)
from worker.substrate.entities.person.mentions import (
    _upsert_mention_and_occurrence as upsert_person_mention,
)


def test_raw_entry_id_is_scoped_to_each_article_mention() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization = BackfieldOrganization(name="Org", slug="mention-provenance")
        session.add(organization)
        session.commit()
        session.refresh(organization)
        project = BackfieldProject(
            organization_id=int(organization.id),
            name="Project",
            slug="mention-provenance",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        articles = [
            SubstrateArticle(project_id=int(project.id), headline="One", text="Shared entities"),
            SubstrateArticle(project_id=int(project.id), headline="Two", text="Shared entities"),
        ]
        location = SubstrateLocation(
            project_id=int(project.id),
            name="Chicago",
            normalized_name="chicago",
        )
        person = SubstratePerson(
            project_id=int(project.id),
            name="Cale Makar",
            normalized_name="cale makar",
        )
        extracted_organization = SubstrateOrganization(
            project_id=int(project.id),
            name="Buffalo Sabres",
            normalized_name="buffalo sabres",
        )
        session.add_all([*articles, location, person, extracted_organization])
        session.commit()
        for row in [*articles, location, person, extracted_organization]:
            session.refresh(row)

        for index, article in enumerate(articles):
            anchor = f"stylebook_output:{index}"
            upsert_location_mention(
                session,
                article_id=int(article.id),
                location_id=int(location.id),
                article_text="Shared entities",
                entry={
                    "id": anchor,
                    "location": {"full": "Chicago"},
                    "mentions": ["Chicago"],
                },
                run_id="run-shared",
                graph_id="graph-shared",
                bucket="points",
            )
            upsert_person_mention(
                session,
                article_id=int(article.id),
                person_id=int(person.id),
                article_text="Shared entities",
                entry={
                    "id": anchor,
                    "name": "Cale Makar",
                    "mentions": [{"text": "Cale Makar", "quote": False}],
                },
                run_id="run-shared",
                graph_id="graph-shared",
                bucket="ready",
            )
            upsert_organization_mention(
                session,
                article_id=int(article.id),
                organization_id=int(extracted_organization.id),
                article_text="Shared entities",
                entry={
                    "id": anchor,
                    "name": "Buffalo Sabres",
                    "mentions": [{"text": "Buffalo Sabres", "quote": False}],
                },
                run_id="run-shared",
                graph_id="graph-shared",
                bucket="ready",
            )
        session.commit()

        for model, entity_field in (
            (SubstrateLocationMention, "location_id"),
            (SubstratePersonMention, "person_id"),
            (SubstrateOrganizationMention, "organization_id"),
        ):
            rows = list(session.exec(select(model).order_by(model.article_id)).all())
            assert len(rows) == 2
            assert getattr(rows[0], entity_field) is not None
            assert rows[0].source_details_json["raw_entry_id"] == "stylebook_output:0"
            assert rows[1].source_details_json["raw_entry_id"] == "stylebook_output:1"


def test_smart_merge_preserves_editorial_fields_but_refreshes_anchor() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization = BackfieldOrganization(name="Org", slug="mention-preserve")
        session.add(organization)
        session.commit()
        session.refresh(organization)
        project = BackfieldProject(
            organization_id=int(organization.id),
            name="Project",
            slug="mention-preserve",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        article = SubstrateArticle(project_id=int(project.id), headline="One", text="Body")
        extracted = SubstrateOrganization(
            project_id=int(project.id),
            name="Buffalo Sabres",
            normalized_name="buffalo sabres",
        )
        session.add(article)
        session.add(extracted)
        session.commit()
        session.refresh(article)
        session.refresh(extracted)
        mention = SubstrateOrganizationMention(
            article_id=int(article.id),
            organization_id=int(extracted.id),
            role_in_story="Editor role",
            edited=True,
            source_details_json={
                "run_id": "run-shared",
                "raw_entry_id": "stylebook_output:0",
            },
        )
        session.add(mention)
        session.commit()

        upsert_organization_mention(
            session,
            article_id=int(article.id),
            organization_id=int(extracted.id),
            article_text="Body",
            entry={
                "id": "stylebook_output:4",
                "name": "Buffalo Sabres",
                "role_in_story": "Model role",
                "mentions": [{"text": "Buffalo Sabres", "quote": False}],
            },
            run_id="run-shared",
            graph_id="graph-shared",
            bucket="ready",
            preserve_editor_changes=True,
        )
        session.commit()
        session.refresh(mention)

        assert mention.role_in_story == "Editor role"
        assert mention.source_details_json["raw_entry_id"] == "stylebook_output:4"
