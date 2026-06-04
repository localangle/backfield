"""Semantic document embedding collection and apply tests."""

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
from backfield_db.semantic_indexing import (
    SEMANTIC_EMBEDDING_STATUS_FAILED,
    SEMANTIC_EMBEDDING_STATUS_PENDING,
    SEMANTIC_EMBEDDING_STATUS_READY,
)
from backfield_stylebook.semantic_indexing.embedding import (
    _apply_person_outcome,
    apply_embedding_batch_outcomes,
    collect_pending_semantic_documents,
    plan_embedding_batches,
)
from backfield_stylebook.semantic_indexing.embedding_contract import (
    EmbeddingVectorOutcome,
    PendingSemanticDocument,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_person_semantic_doc(session: Session) -> tuple[int, int, PendingSemanticDocument]:
    org = BackfieldOrganization(name="Org", slug="org-embed")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        name="Demo",
        slug="demo-embed",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    project_id = int(proj.id)  # type: ignore[arg-type]
    article = SubstrateArticle(
        project_id=project_id,
        headline="Story",
        text="Mayor Jane Jones spoke downtown.",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    article_id = int(article.id)  # type: ignore[arg-type]
    person = SubstratePerson(
        project_id=project_id,
        name="Jane Jones",
        normalized_name="jane jones",
    )
    session.add(person)
    session.commit()
    session.refresh(person)
    mention = SubstratePersonMention(article_id=article_id, person_id=int(person.id))
    session.add(mention)
    session.commit()
    session.refresh(mention)
    occurrence = SubstratePersonMentionOccurrence(
        person_mention_id=int(mention.id),
        mention_text="Jane Jones",
    )
    session.add(occurrence)
    session.commit()
    session.refresh(occurrence)
    doc = SubstratePersonSemanticDocument(
        project_id=project_id,
        article_id=article_id,
        person_id=int(person.id),
        person_mention_id=int(mention.id),
        person_mention_occurrence_id=int(occurrence.id),
        search_text="Person: Jane Jones",
        source_hash="abc123",
        embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    pending = PendingSemanticDocument(
        entity_type="person",
        document_id=int(doc.id),  # type: ignore[arg-type]
        search_text=str(doc.search_text),
    )
    return project_id, article_id, pending


def test_plan_embedding_batches_groups_documents() -> None:
    docs = [
        PendingSemanticDocument(entity_type="person", document_id=i, search_text=f"t{i}")
        for i in range(5)
    ]
    plans = plan_embedding_batches(docs, batch_size=2)
    assert len(plans) == 3
    assert len(plans[0].documents) == 2
    assert len(plans[2].documents) == 1


def test_collect_pending_includes_failed_for_retry() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id, pending = _seed_person_semantic_doc(session)
        row = session.get(SubstratePersonSemanticDocument, pending.document_id)
        assert row is not None
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_FAILED
        row.embedding_error = "old failure"
        session.add(row)
        session.commit()

        collected = collect_pending_semantic_documents(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        assert len(collected) == 1


def test_apply_person_outcome_sets_ready_fields() -> None:
    row = SubstratePersonSemanticDocument(
        project_id=1,
        article_id=1,
        person_id=1,
        person_mention_id=1,
        person_mention_occurrence_id=1,
        search_text="Person: Jane Jones",
        source_hash="abc123",
    )
    _apply_person_outcome(
        row,
        vector=[0.1, 0.2, 0.3],
        error_message=None,
        embedding_model="openai/text-embedding-3-small",
        embedding_dimensions=3,
    )
    assert row.embedding == [0.1, 0.2, 0.3]
    assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_READY
    assert row.embedding_model == "openai/text-embedding-3-small"
    assert row.embedding_dimensions == 3
    assert row.embedding_error is None
    assert row.embedded_at is not None


def test_apply_embedding_batch_outcomes_marks_failed_and_skips_missing() -> None:
    """SQLite tests status metadata only; pgvector assignment is covered in-memory above."""
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id, pending = _seed_person_semantic_doc(session)
        missing = PendingSemanticDocument(
            entity_type="person",
            document_id=9999,
            search_text="missing",
        )
        summary = apply_embedding_batch_outcomes(
            session,
            outcomes=[
                EmbeddingVectorOutcome(document=missing, vector=None, error_message="nope"),
            ],
            embedding_model="openai/text-embedding-3-small",
            embedding_dimensions=3,
        )
        session.commit()
        assert summary.indexed == 0
        assert summary.failed == 0
        assert summary.skipped == 1

        row = session.get(SubstratePersonSemanticDocument, pending.document_id)
        assert row is not None
        assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_PENDING

        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_PENDING
        session.add(row)
        summary2 = apply_embedding_batch_outcomes(
            session,
            outcomes=[
                EmbeddingVectorOutcome(
                    document=pending,
                    vector=None,
                    error_message="provider timeout",
                ),
            ],
            embedding_model="openai/text-embedding-3-small",
            embedding_dimensions=3,
        )
        session.commit()
        assert summary2.failed == 1
        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_FAILED
        assert row.embedding_error == "provider timeout"
