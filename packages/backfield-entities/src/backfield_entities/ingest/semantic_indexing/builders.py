"""Entity-type dispatch for semantic document builders."""

from __future__ import annotations

from backfield_entities.ingest.semantic_indexing.contracts import (
    SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES,
    SemanticDocumentUnsupportedType,
)
from backfield_entities.ingest.semantic_indexing.location import (
    build_location_occurrence_document,
    build_location_occurrence_documents,
)
from backfield_entities.ingest.semantic_indexing.organization import (
    build_organization_occurrence_document,
    build_organization_occurrence_documents,
)
from backfield_entities.ingest.semantic_indexing.person import (
    build_person_occurrence_document,
    build_person_occurrence_documents,
)
from backfield_entities.registry.entity_types import EntityType

__all__ = [
    "SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES",
    "SemanticDocumentUnsupportedType",
    "build_location_occurrence_document",
    "build_location_occurrence_documents",
    "build_organization_occurrence_document",
    "build_organization_occurrence_documents",
    "build_person_occurrence_document",
    "build_person_occurrence_documents",
    "semantic_builder_supported",
    "unsupported_semantic_builder_type",
]


def semantic_builder_supported(entity_type: EntityType | str) -> bool:
    return entity_type in SUPPORTED_SEMANTIC_BUILDER_ENTITY_TYPES


def unsupported_semantic_builder_type(
    entity_type: EntityType | str,
) -> SemanticDocumentUnsupportedType:
    return SemanticDocumentUnsupportedType(entity_type=entity_type)
