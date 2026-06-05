"""Semantic document synchronization tests (Issue 4)."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateLocationSemanticDocument,
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
from backfield_entities.ingest.semantic_indexing import (
    sync_semantic_documents_for_article,
    sync_semantic_documents_for_entity_type,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_project(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-semantic-sync")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-semantic", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    pid = int(proj.id)  # type: ignore[arg-type]
    article = SubstrateArticle(
        project_id=pid,
        headline="Mayor speaks on downtown crime",
        text=(
            "City leaders met downtown. "
            '"We need more officers downtown," Mayor Jane Jones said. '
            "Responders took victims to the hospital."
        ),
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return pid, int(article.id)  # type: ignore[arg-type]


def _seed_person_chain(
    session: Session, *, project_id: int, article_id: int
) -> tuple[int, int, int]:
    person = SubstratePerson(
        project_id=project_id,
        name="Jane Jones",
        normalized_name="jane jones",
        title="Mayor",
        affiliation="Springfield",
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
        mention_text="Jones",
        quote_text="We need more officers downtown.",
        start_char=44,
        end_char=82,
        occurrence_order=1,
        labels_json=["speech"],
    )
    session.add(occurrence)
    session.commit()
    session.refresh(occurrence)
    return int(person.id), int(mention.id), int(occurrence.id)


def _seed_location_chain(
    session: Session, *, project_id: int, article_id: int
) -> tuple[int, int, int]:
    location = SubstrateLocation(
        project_id=project_id,
        name="Springfield General Hospital",
        normalized_name="springfield general hospital",
        location_type="place",
        formatted_address="100 Main St",
    )
    session.add(location)
    session.commit()
    session.refresh(location)
    mention = SubstrateLocationMention(article_id=article_id, location_id=int(location.id))
    session.add(mention)
    session.commit()
    session.refresh(mention)
    occurrence = SubstrateLocationMentionOccurrence(
        location_mention_id=int(mention.id),
        mention_text="the hospital",
        start_char=90,
        end_char=102,
        occurrence_order=1,
        labels_json=["setting"],
    )
    session.add(occurrence)
    session.commit()
    session.refresh(occurrence)
    return int(location.id), int(mention.id), int(occurrence.id)


def test_first_sync_creates_pending_person_documents() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _seed_person_chain(session, project_id=project_id, article_id=article_id)

        result = sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        person_summary = result.summaries[0]
        assert person_summary.created == 1
        assert person_summary.pending == 1
        rows = session.exec(select(SubstratePersonSemanticDocument)).all()
        assert len(rows) == 1
        assert rows[0].embedding_status == SEMANTIC_EMBEDDING_STATUS_PENDING
        assert rows[0].active is True
        assert rows[0].search_text


def test_repeated_sync_is_idempotent_for_unchanged_hashes() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _seed_person_chain(session, project_id=project_id, article_id=article_id)

        sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()
        first_hash = session.exec(select(SubstratePersonSemanticDocument)).one().source_hash

        second = sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        assert second.summaries[0].unchanged == 1
        assert second.summaries[0].created == 0
        assert second.summaries[0].updated == 0
        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        assert row.source_hash == first_hash
        assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_PENDING


def test_source_edit_updates_only_affected_document() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _person_id, _mention_id, occurrence_id = _seed_person_chain(
            session, project_id=project_id, article_id=article_id
        )
        sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()
        first_hash = session.exec(select(SubstratePersonSemanticDocument)).one().source_hash

        occurrence = session.get(SubstratePersonMentionOccurrence, occurrence_id)
        assert occurrence is not None
        occurrence.quote_text = "We need more officers and community programs downtown."
        occurrence.end_char = 105
        session.add(occurrence)
        session.commit()

        updated = sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        assert updated.summaries[0].updated == 1
        assert updated.summaries[0].pending == 1
        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        assert row.source_hash != first_hash
        assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_PENDING


def test_suppressed_occurrence_deactivates_semantic_document() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _person_id, _mention_id, occurrence_id = _seed_person_chain(
            session, project_id=project_id, article_id=article_id
        )
        sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        occurrence = session.get(SubstratePersonMentionOccurrence, occurrence_id)
        assert occurrence is not None
        occurrence.suppressed = True
        session.add(occurrence)
        session.commit()

        deactivated = sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        assert deactivated.summaries[0].deactivated == 1
        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        assert row.active is False
        assert row.stale is True


def test_deleted_mention_deactivates_semantic_document() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _person_id, mention_id, _occurrence_id = _seed_person_chain(
            session, project_id=project_id, article_id=article_id
        )
        sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        mention = session.get(SubstratePersonMention, mention_id)
        assert mention is not None
        mention.deleted = True
        session.add(mention)
        session.commit()

        deactivated = sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        assert deactivated.summaries[0].deactivated == 1
        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        assert row.active is False


def test_failed_document_with_unchanged_hash_stays_retryable() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _seed_person_chain(session, project_id=project_id, article_id=article_id)
        sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_FAILED
        row.embedding_error = "provider timeout"
        session.add(row)
        session.commit()

        second = sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        assert second.summaries[0].failed_unchanged == 1
        assert second.summaries[0].updated == 0
        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_FAILED
        assert row.embedding_error == "provider timeout"


def test_ready_document_with_unchanged_hash_is_not_remarked_pending() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _seed_person_chain(session, project_id=project_id, article_id=article_id)
        sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_READY
        session.add(row)
        session.commit()

        second = sync_semantic_documents_for_article(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_types=("person",),
        )
        session.commit()

        assert second.summaries[0].unchanged == 1
        row = session.exec(select(SubstratePersonSemanticDocument)).one()
        assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_READY


def test_location_sync_creates_and_updates_documents() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        _location_id, _mention_id, occurrence_id = _seed_location_chain(
            session, project_id=project_id, article_id=article_id
        )

        first = sync_semantic_documents_for_entity_type(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_type="location",
        )
        session.commit()
        assert first.summaries[0].created == 1

        occurrence = session.get(SubstrateLocationMentionOccurrence, occurrence_id)
        assert occurrence is not None
        occurrence.mention_text = "Springfield General"
        session.add(occurrence)
        session.commit()

        second = sync_semantic_documents_for_entity_type(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_type="location",
        )
        session.commit()
        assert second.summaries[0].updated == 1
        row = session.exec(select(SubstrateLocationSemanticDocument)).one()
        assert "Springfield General" in row.search_text


def test_unsupported_entity_type_reports_structured_result() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id, article_id = _seed_project(session)
        result = sync_semantic_documents_for_entity_type(
            session,
            project_id=project_id,
            article_id=article_id,
            entity_type="organization",
        )
        assert result.summaries[0].unsupported == 1
        assert result.summaries[0].created == 0
