"""Schema contract tests for substrate semantic document tables (Issue 2)."""

from __future__ import annotations

from backfield_db import SubstrateLocationSemanticDocument, SubstratePersonSemanticDocument
from backfield_db.pgvector import _PostgresVector
from backfield_db.semantic_indexing import (
    SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
    SEMANTIC_EMBEDDING_STATUS_PENDING,
)
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def _index_names(model: type[object]) -> set[str]:
    return {index.name for index in model.__table__.indexes if index.name}


def test_person_semantic_document_one_row_per_occurrence() -> None:
    assert _unique_constraint_columns(
        SubstratePersonSemanticDocument,
        "uq_substrate_person_sem_doc_occurrence",
    ) == ("person_mention_occurrence_id",)


def test_location_semantic_document_one_row_per_occurrence() -> None:
    assert _unique_constraint_columns(
        SubstrateLocationSemanticDocument,
        "uq_substrate_location_sem_doc_occurrence",
    ) == ("location_mention_occurrence_id",)


def test_semantic_document_defaults() -> None:
    row = SubstratePersonSemanticDocument(
        project_id=1,
        article_id=2,
        person_id=3,
        person_mention_id=4,
        person_mention_occurrence_id=5,
        search_text="Jane Doe said hello.",
        source_hash="abc123",
    )
    assert row.document_kind == SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE
    assert row.embedding_status == SEMANTIC_EMBEDDING_STATUS_PENDING
    assert row.active is True
    assert row.stale is False
    assert row.embedding is None


def test_semantic_document_project_lookup_indexes() -> None:
    person_indexes = _index_names(SubstratePersonSemanticDocument)
    assert "idx_substrate_person_sem_doc_project_article" in person_indexes
    assert "idx_substrate_person_sem_doc_project_person" in person_indexes
    assert "idx_substrate_person_sem_doc_project_status" in person_indexes
    assert "idx_substrate_person_sem_doc_project_active" in person_indexes

    location_indexes = _index_names(SubstrateLocationSemanticDocument)
    assert "idx_substrate_location_sem_doc_project_location" in location_indexes


def test_semantic_document_foreign_keys_to_substrate_chain() -> None:
    person_table = SubstratePersonSemanticDocument.__table__
    fk_targets = {
        (column.name, fk.target_fullname)
        for column in person_table.columns
        for fk in column.foreign_keys
    }
    assert ("project_id", "backfield_project.id") in fk_targets
    assert ("article_id", "substrate_article.id") in fk_targets
    assert ("person_id", "substrate_person.id") in fk_targets
    assert ("person_mention_id", "substrate_person_mention.id") in fk_targets
    assert ("person_mention_occurrence_id", "substrate_person_mention_occurrence.id") in fk_targets


def test_embedding_column_uses_pgvector_on_postgres() -> None:
    col = SubstratePersonSemanticDocument.__table__.c.embedding
    assert isinstance(col.type, _PostgresVector)
    assert col.type.dimensions == 1536  # type: ignore[attr-defined]
