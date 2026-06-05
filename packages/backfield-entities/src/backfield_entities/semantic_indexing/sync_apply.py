"""Shared compare-and-upsert logic for semantic document synchronization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from backfield_db.semantic_indexing import (
    SEMANTIC_EMBEDDING_STATUS_FAILED,
)

from backfield_stylebook.semantic_indexing.contracts import (
    SemanticBuilderEntityType,
    SemanticDocumentDraft,
)
from backfield_stylebook.semantic_indexing.sync_contract import SemanticSyncSummary


class _SemanticDocumentRow(Protocol):
    source_hash: str
    embedding_status: str
    active: bool
    stale: bool
    search_text: str
    document_kind: str


def apply_semantic_document_sync(
    *,
    expected_drafts: dict[int, SemanticDocumentDraft],
    inactive_occurrence_ids: set[int],
    existing_by_occurrence: dict[int, _SemanticDocumentRow],
    create_row: Callable[[SemanticDocumentDraft], None],
    update_row: Callable[[_SemanticDocumentRow, SemanticDocumentDraft], None],
    deactivate_row: Callable[[_SemanticDocumentRow], None],
    reactivate_row: Callable[[_SemanticDocumentRow], None],
    summary_entity_type: SemanticBuilderEntityType,
) -> SemanticSyncSummary:
    summary = SemanticSyncSummary(entity_type=summary_entity_type)

    seen_occurrence_ids = set(expected_drafts) | inactive_occurrence_ids
    for occurrence_id, draft in expected_drafts.items():
        existing = existing_by_occurrence.get(occurrence_id)
        if existing is None:
            create_row(draft)
            summary.created += 1
            summary.pending += 1
            continue

        if existing.source_hash == draft.source_hash:
            if not existing.active or existing.stale:
                reactivate_row(existing)
                if existing.embedding_status == SEMANTIC_EMBEDDING_STATUS_FAILED:
                    summary.failed_unchanged += 1
                else:
                    summary.unchanged += 1
            elif existing.embedding_status == SEMANTIC_EMBEDDING_STATUS_FAILED:
                summary.failed_unchanged += 1
            else:
                summary.unchanged += 1
            continue

        update_row(existing, draft)
        summary.updated += 1
        summary.pending += 1

    for occurrence_id in inactive_occurrence_ids:
        existing = existing_by_occurrence.get(occurrence_id)
        if existing is None:
            continue
        if existing.active or not existing.stale:
            deactivate_row(existing)
            summary.deactivated += 1

    for occurrence_id, existing in existing_by_occurrence.items():
        if occurrence_id in seen_occurrence_ids:
            continue
        if existing.active or not existing.stale:
            deactivate_row(existing)
            summary.deactivated += 1

    return summary
