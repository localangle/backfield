"""Shared fixtures for semantic mention search tests."""

from __future__ import annotations

import json

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
    SubstratePersonSemanticDocument,
)
from backfield_db.semantic_indexing import (
    SEMANTIC_EMBEDDING_STATUS_PENDING,
    SEMANTIC_EMBEDDING_STATUS_READY,
)
from sqlalchemy import text
from sqlmodel import Session, select


def set_person_semantic_doc_embedding(
    session: Session,
    *,
    document_id: int,
    vector: list[float],
    embedding_status: str = SEMANTIC_EMBEDDING_STATUS_READY,
) -> None:
    """SQLite cannot persist list embeddings via ORM; write JSON via raw SQL."""
    session.connection().execute(
        text(
            "UPDATE substrate_person_semantic_document "
            "SET embedding = :emb, embedding_status = :status "
            "WHERE id = :id"
        ),
        {
            "emb": json.dumps(vector),
            "status": embedding_status,
            "id": document_id,
        },
    )


def seed_person_semantic_search_rows(
    session: Session,
    *,
    project_id: int | None = None,
) -> dict[str, int]:
    if project_id is None:
        session.add(BackfieldOrganization(name="Org", slug="org-sem-search"))
        session.commit()
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "org-sem-search")
        ).one()
        session.add(
            BackfieldProject(organization_id=int(org.id), name="Proj", slug="proj-sem-search")
        )
        session.commit()
        proj = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "proj-sem-search")
        ).one()
        project_id = int(proj.id)

    article = SubstrateArticle(
        project_id=project_id,
        headline="Crime downtown",
        text="Mayor spoke.",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    article_id = int(article.id)

    person = SubstratePerson(
        project_id=project_id,
        name="Jane Smith",
        normalized_name="jane smith",
        person_type="official",
        public_figure=True,
        status="active",
    )
    session.add(person)
    session.commit()
    session.refresh(person)
    person_id = int(person.id)

    mention = SubstratePersonMention(
        article_id=article_id,
        person_id=person_id,
        nature="official",
        role_in_story="Mayor",
    )
    session.add(mention)
    session.commit()
    session.refresh(mention)
    mention_id = int(mention.id)

    quote_occ = SubstratePersonMentionOccurrence(
        person_mention_id=mention_id,
        mention_text="Mayor Jane Smith",
        quote_text="We must address downtown crime.",
        labels_json=["quote"],
    )
    mention_occ = SubstratePersonMentionOccurrence(
        person_mention_id=mention_id,
        mention_text="Mayor Jane Smith",
        quote_text=None,
        labels_json=[],
    )
    pending_occ = SubstratePersonMentionOccurrence(
        person_mention_id=mention_id,
        mention_text="Mayor Jane Smith",
        quote_text=None,
        labels_json=[],
    )
    inactive_occ = SubstratePersonMentionOccurrence(
        person_mention_id=mention_id,
        mention_text="Mayor Jane Smith",
        quote_text=None,
        labels_json=[],
    )
    session.add(quote_occ)
    session.add(mention_occ)
    session.add(pending_occ)
    session.add(inactive_occ)
    session.commit()
    session.refresh(quote_occ)
    session.refresh(mention_occ)
    session.refresh(pending_occ)
    session.refresh(inactive_occ)

    ready_doc = SubstratePersonSemanticDocument(
        project_id=project_id,
        article_id=article_id,
        person_id=person_id,
        person_mention_id=mention_id,
        person_mention_occurrence_id=int(quote_occ.id),
        search_text="Mayor quote about crime",
        source_hash="hash-ready",
        embedding_status=SEMANTIC_EMBEDDING_STATUS_READY,
        active=True,
    )
    other_ready_doc = SubstratePersonSemanticDocument(
        project_id=project_id,
        article_id=article_id,
        person_id=person_id,
        person_mention_id=mention_id,
        person_mention_occurrence_id=int(mention_occ.id),
        search_text="Mayor mention",
        source_hash="hash-other-ready",
        embedding_status=SEMANTIC_EMBEDDING_STATUS_READY,
        active=True,
    )
    pending_doc = SubstratePersonSemanticDocument(
        project_id=project_id,
        article_id=article_id,
        person_id=person_id,
        person_mention_id=mention_id,
        person_mention_occurrence_id=int(pending_occ.id),
        search_text="Pending doc",
        source_hash="hash-pending",
        embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
        active=True,
    )
    inactive_doc = SubstratePersonSemanticDocument(
        project_id=project_id,
        article_id=article_id,
        person_id=person_id,
        person_mention_id=mention_id,
        person_mention_occurrence_id=int(inactive_occ.id),
        search_text="Inactive doc",
        source_hash="hash-inactive",
        embedding_status=SEMANTIC_EMBEDDING_STATUS_READY,
        active=False,
    )
    session.add(ready_doc)
    session.add(other_ready_doc)
    session.add(pending_doc)
    session.add(inactive_doc)
    session.commit()
    session.refresh(ready_doc)
    session.refresh(other_ready_doc)
    session.refresh(pending_doc)
    session.refresh(inactive_doc)

    return {
        "project_id": project_id,
        "article_id": article_id,
        "ready_doc_id": int(ready_doc.id),
        "other_ready_doc_id": int(other_ready_doc.id),
        "pending_doc_id": int(pending_doc.id),
        "inactive_doc_id": int(inactive_doc.id),
    }
