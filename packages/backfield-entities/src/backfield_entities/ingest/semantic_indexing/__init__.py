"""Deterministic semantic document builders from persisted substrate rows."""

from backfield_entities.ingest.semantic_indexing.builders import (
    SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES,
    build_location_occurrence_document,
    build_location_occurrence_documents,
    build_organization_occurrence_document,
    build_organization_occurrence_documents,
    build_person_occurrence_document,
    build_person_occurrence_documents,
    semantic_builder_supported,
    unsupported_semantic_builder_type,
)
from backfield_entities.ingest.semantic_indexing.contracts import (
    DEFAULT_DOCUMENT_KIND,
    SKIP_ARTICLE_DELETED,
    SKIP_MENTION_DELETED,
    SKIP_OCCURRENCE_SUPPRESSED,
    SemanticDocumentBuildSkip,
    SemanticDocumentDraft,
    SemanticDocumentSourceKey,
    SemanticDocumentUnsupportedType,
)
from backfield_entities.ingest.semantic_indexing.sync import (
    sync_semantic_documents_for_article,
    sync_semantic_documents_for_entity_type,
    sync_semantic_documents_for_scope,
)
from backfield_entities.ingest.semantic_indexing.sync_contract import (
    SemanticSyncResult,
    SemanticSyncScope,
    SemanticSyncSummary,
)

__all__ = [
    "DEFAULT_DOCUMENT_KIND",
    "SKIP_ARTICLE_DELETED",
    "SKIP_MENTION_DELETED",
    "SKIP_OCCURRENCE_SUPPRESSED",
    "SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES",
    "SemanticDocumentBuildSkip",
    "SemanticDocumentDraft",
    "SemanticDocumentSourceKey",
    "SemanticDocumentUnsupportedType",
    "SemanticSyncResult",
    "SemanticSyncScope",
    "SemanticSyncSummary",
    "build_location_occurrence_document",
    "build_location_occurrence_documents",
    "build_organization_occurrence_document",
    "build_organization_occurrence_documents",
    "build_person_occurrence_document",
    "build_person_occurrence_documents",
    "semantic_builder_supported",
    "sync_semantic_documents_for_article",
    "sync_semantic_documents_for_entity_type",
    "sync_semantic_documents_for_scope",
    "unsupported_semantic_builder_type",
]
