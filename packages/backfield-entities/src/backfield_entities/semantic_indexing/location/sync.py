"""Synchronize location semantic document rows with builder output."""

from __future__ import annotations

from backfield_db import SubstrateLocationSemanticDocument
from backfield_db.semantic_indexing import SEMANTIC_EMBEDDING_STATUS_PENDING
from sqlmodel import Session, select

from backfield_entities.semantic_indexing.common.article import load_article_source
from backfield_entities.semantic_indexing.contracts import (
    SemanticDocumentBuildSkip,
    SemanticDocumentDraft,
)
from backfield_entities.semantic_indexing.location.builder import build_occurrence_document
from backfield_entities.semantic_indexing.location.loader import load_sync_bundles
from backfield_entities.semantic_indexing.sync_apply import apply_semantic_document_sync
from backfield_entities.semantic_indexing.sync_contract import SemanticSyncSummary


def sync_semantic_documents(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> SemanticSyncSummary:
    article = load_article_source(session, article_id)
    if article is None:
        return SemanticSyncSummary(entity_type="location")

    bundles = load_sync_bundles(session, article_id=article_id)
    expected: dict[int, SemanticDocumentDraft] = {}
    inactive: set[int] = set()

    for location, mention, occurrence, canonical in bundles:
        result = build_occurrence_document(
            project_id=project_id,
            article=article,
            location=location,
            mention=mention,
            occurrence=occurrence,
            canonical=canonical,
        )
        if isinstance(result, SemanticDocumentBuildSkip):
            inactive.add(result.occurrence_id)
        else:
            expected[result.occurrence_id] = result

    existing_rows = session.exec(
        select(SubstrateLocationSemanticDocument).where(
            SubstrateLocationSemanticDocument.project_id == project_id,
            SubstrateLocationSemanticDocument.article_id == article_id,
        )
    ).all()
    existing_by_occurrence = {
        int(row.location_mention_occurrence_id): row for row in existing_rows
    }

    def create_row(draft: SemanticDocumentDraft) -> None:
        session.add(
            SubstrateLocationSemanticDocument(
                project_id=draft.project_id,
                article_id=draft.article_id,
                location_id=draft.entity_id,
                location_mention_id=draft.mention_id,
                location_mention_occurrence_id=draft.occurrence_id,
                document_kind=draft.document_kind,
                search_text=draft.search_text,
                source_hash=draft.source_hash,
                active=True,
                stale=False,
                embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
            )
        )

    def update_row(row: SubstrateLocationSemanticDocument, draft: SemanticDocumentDraft) -> None:
        row.location_id = draft.entity_id
        row.location_mention_id = draft.mention_id
        row.document_kind = draft.document_kind
        row.search_text = draft.search_text
        row.source_hash = draft.source_hash
        row.active = True
        row.stale = False
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_PENDING
        row.embedding_error = None
        row.embedding = None
        row.embedding_model = None
        row.embedding_dimensions = None
        row.embedded_at = None
        session.add(row)

    def deactivate_row(row: SubstrateLocationSemanticDocument) -> None:
        row.active = False
        row.stale = True
        session.add(row)

    def reactivate_row(row: SubstrateLocationSemanticDocument) -> None:
        row.active = True
        row.stale = False
        session.add(row)

    return apply_semantic_document_sync(
        expected_drafts=expected,
        inactive_occurrence_ids=inactive,
        existing_by_occurrence=existing_by_occurrence,
        create_row=create_row,
        update_row=update_row,
        deactivate_row=deactivate_row,
        reactivate_row=reactivate_row,
        summary_entity_type="location",
    )
