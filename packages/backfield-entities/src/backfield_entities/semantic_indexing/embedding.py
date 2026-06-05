"""Collect pending semantic documents and apply embedding batch results."""

from __future__ import annotations

from datetime import UTC, datetime

from backfield_db import SubstrateLocationSemanticDocument, SubstratePersonSemanticDocument
from backfield_db.semantic_indexing import (
    SEMANTIC_EMBEDDING_STATUS_FAILED,
    SEMANTIC_EMBEDDING_STATUS_PENDING,
    SEMANTIC_EMBEDDING_STATUS_READY,
)
from sqlmodel import Session, col, select

from backfield_entities.semantic_indexing.contracts import SemanticBuilderEntityType
from backfield_entities.semantic_indexing.embedding_contract import (
    DEFAULT_SEMANTIC_EMBEDDING_BATCH_SIZE,
    EmbeddingApplySummary,
    EmbeddingBatchPlan,
    EmbeddingVectorOutcome,
    PendingSemanticDocument,
)


def _collect_person_pending(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> list[PendingSemanticDocument]:
    rows = session.exec(
        select(SubstratePersonSemanticDocument).where(
            SubstratePersonSemanticDocument.project_id == project_id,
            SubstratePersonSemanticDocument.article_id == article_id,
            SubstratePersonSemanticDocument.active.is_(True),
            col(SubstratePersonSemanticDocument.embedding_status).in_(
                (SEMANTIC_EMBEDDING_STATUS_PENDING, SEMANTIC_EMBEDDING_STATUS_FAILED)
            ),
        )
    ).all()
    pending: list[PendingSemanticDocument] = []
    for row in rows:
        if row.id is None:
            continue
        pending.append(
            PendingSemanticDocument(
                entity_type="person",
                document_id=int(row.id),
                search_text=str(row.search_text),
            )
        )
    return pending


def _collect_location_pending(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> list[PendingSemanticDocument]:
    rows = session.exec(
        select(SubstrateLocationSemanticDocument).where(
            SubstrateLocationSemanticDocument.project_id == project_id,
            SubstrateLocationSemanticDocument.article_id == article_id,
            SubstrateLocationSemanticDocument.active.is_(True),
            col(SubstrateLocationSemanticDocument.embedding_status).in_(
                (SEMANTIC_EMBEDDING_STATUS_PENDING, SEMANTIC_EMBEDDING_STATUS_FAILED)
            ),
        )
    ).all()
    pending: list[PendingSemanticDocument] = []
    for row in rows:
        if row.id is None:
            continue
        pending.append(
            PendingSemanticDocument(
                entity_type="location",
                document_id=int(row.id),
                search_text=str(row.search_text),
            )
        )
    return pending


def collect_pending_semantic_documents(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    entity_types: tuple[SemanticBuilderEntityType, ...],
) -> list[PendingSemanticDocument]:
    """Load active pending or retryable failed semantic documents for one article."""
    documents: list[PendingSemanticDocument] = []
    for entity_type in entity_types:
        if entity_type == "person":
            documents.extend(
                _collect_person_pending(session, project_id=project_id, article_id=article_id)
            )
        elif entity_type == "location":
            documents.extend(
                _collect_location_pending(session, project_id=project_id, article_id=article_id)
            )
    return documents


def plan_embedding_batches(
    documents: list[PendingSemanticDocument],
    *,
    batch_size: int = DEFAULT_SEMANTIC_EMBEDDING_BATCH_SIZE,
) -> list[EmbeddingBatchPlan]:
    """Split pending documents into fixed-size provider batches."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not documents:
        return []
    plans: list[EmbeddingBatchPlan] = []
    for start in range(0, len(documents), batch_size):
        chunk = documents[start : start + batch_size]
        plans.append(EmbeddingBatchPlan(documents=tuple(chunk)))
    return plans


def _apply_person_outcome(
    row: SubstratePersonSemanticDocument,
    *,
    vector: list[float] | None,
    error_message: str | None,
    embedding_model: str,
    embedding_dimensions: int | None,
) -> None:
    if vector is not None:
        row.embedding = vector
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_READY
        row.embedding_model = embedding_model
        row.embedding_dimensions = embedding_dimensions
        row.embedding_error = None
        row.embedded_at = datetime.now(UTC)
    else:
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_FAILED
        row.embedding_error = (error_message or "Embedding failed.")[:2000]


def _apply_location_outcome(
    row: SubstrateLocationSemanticDocument,
    *,
    vector: list[float] | None,
    error_message: str | None,
    embedding_model: str,
    embedding_dimensions: int | None,
) -> None:
    if vector is not None:
        row.embedding = vector
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_READY
        row.embedding_model = embedding_model
        row.embedding_dimensions = embedding_dimensions
        row.embedding_error = None
        row.embedded_at = datetime.now(UTC)
    else:
        row.embedding_status = SEMANTIC_EMBEDDING_STATUS_FAILED
        row.embedding_error = (error_message or "Embedding failed.")[:2000]


def apply_embedding_batch_outcomes(
    session: Session,
    *,
    outcomes: list[EmbeddingVectorOutcome],
    embedding_model: str,
    embedding_dimensions: int | None,
) -> EmbeddingApplySummary:
    """Write embedding vectors or failure metadata onto semantic document rows."""
    summary = EmbeddingApplySummary()
    for outcome in outcomes:
        doc = outcome.document
        if doc.entity_type == "person":
            row = session.get(SubstratePersonSemanticDocument, doc.document_id)
        else:
            row = session.get(SubstrateLocationSemanticDocument, doc.document_id)
        if row is None or not row.active:
            summary.skipped += 1
            continue
        if doc.entity_type == "person":
            _apply_person_outcome(
                row,
                vector=outcome.vector,
                error_message=outcome.error_message,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
            )
        else:
            _apply_location_outcome(
                row,
                vector=outcome.vector,
                error_message=outcome.error_message,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
            )
        session.add(row)
        if outcome.vector is not None:
            summary.indexed += 1
        else:
            summary.failed += 1
    return summary
