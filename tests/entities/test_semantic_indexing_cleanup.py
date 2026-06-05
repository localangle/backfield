"""Semantic document cleanup before substrate deletes."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
    SubstratePersonSemanticDocument,
)
from backfield_db.semantic_indexing import SEMANTIC_EMBEDDING_STATUS_PENDING
from backfield_entities.semantic_indexing.cleanup import delete_semantic_documents_for_person
from sqlmodel import Session, SQLModel, create_engine, select


def test_delete_semantic_documents_for_person_allows_substrate_delete() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-sem-clean")
        session.add(org)
        session.commit()
        session.refresh(org)
        proj = BackfieldProject(organization_id=int(org.id), name="P", slug="p-sem-clean")
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id = int(proj.id)

        article = SubstrateArticle(project_id=project_id, headline="H", text="Jane spoke.")
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)

        person = SubstratePerson(
            project_id=project_id,
            name="Jane Smith",
            normalized_name="jane smith",
            status="active",
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        person_id = int(person.id)

        mention = SubstratePersonMention(article_id=article_id, person_id=person_id)
        session.add(mention)
        session.commit()
        session.refresh(mention)
        mention_id = int(mention.id)

        occurrence = SubstratePersonMentionOccurrence(
            person_mention_id=mention_id,
            mention_text="Jane Smith",
        )
        session.add(occurrence)
        session.commit()
        session.refresh(occurrence)

        session.add(
            SubstratePersonSemanticDocument(
                project_id=project_id,
                article_id=article_id,
                person_id=person_id,
                person_mention_id=mention_id,
                person_mention_occurrence_id=int(occurrence.id),
                search_text="Jane Smith",
                source_hash="hash-clean",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
            )
        )
        session.commit()

        removed = delete_semantic_documents_for_person(
            session,
            person_id=person_id,
            project_id=project_id,
        )
        assert removed == 1
        session.delete(person)
        session.commit()

        assert session.exec(select(SubstratePersonSemanticDocument)).all() == []
        assert session.get(SubstratePerson, person_id) is None
