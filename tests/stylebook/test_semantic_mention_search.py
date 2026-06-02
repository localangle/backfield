"""Unit tests for semantic mention search helpers."""

from __future__ import annotations

import pytest

from backfield_stylebook.semantic_indexing.search import (
    _coerce_embedding_vector,
    cosine_similarity,
    search_person_semantic_mentions,
)
from backfield_stylebook.semantic_indexing.search_contract import PersonSemanticSearchFilters
from sqlmodel import Session, SQLModel, create_engine

from tests.stylebook.test_semantic_mention_search_fixtures import (
    seed_person_semantic_search_rows,
    set_person_semantic_doc_embedding,
)


def test_cosine_similarity_identical_vectors_score_one() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_coerce_embedding_vector_accepts_ndarray_like() -> None:
    class _FakeNdarray:
        def tolist(self) -> list[float]:
            return [1.0, 0.0]

    assert _coerce_embedding_vector(_FakeNdarray()) == [1.0, 0.0]


def test_coerce_embedding_vector_accepts_numpy_ndarray() -> None:
    np = pytest.importorskip("numpy")
    arr = np.array([1.0, 0.0], dtype=np.float32)
    assert _coerce_embedding_vector(arr) == [1.0, 0.0]


def test_search_person_semantic_mentions_orders_by_score_and_excludes_pending() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ids = seed_person_semantic_search_rows(session)
        set_person_semantic_doc_embedding(
            session,
            document_id=ids["ready_doc_id"],
            vector=[1.0, 0.0],
        )
        set_person_semantic_doc_embedding(
            session,
            document_id=ids["other_ready_doc_id"],
            vector=[0.0, 1.0],
        )
        session.commit()

        result = search_person_semantic_mentions(
            session,
            project_id=ids["project_id"],
            query_vector=[1.0, 0.0],
            filters=PersonSemanticSearchFilters(),
            limit=10,
            offset=0,
        )

    assert result.total == 2
    assert len(result.hits) == 2
    assert result.hits[0].score >= result.hits[1].score
    assert result.hits[0].entity_type == "person"
    assert result.hits[0].occurrence["mention_text"]


def test_search_person_semantic_mentions_quote_only_filter() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ids = seed_person_semantic_search_rows(session)
        set_person_semantic_doc_embedding(
            session,
            document_id=ids["ready_doc_id"],
            vector=[1.0, 0.0],
        )
        set_person_semantic_doc_embedding(
            session,
            document_id=ids["other_ready_doc_id"],
            vector=[0.9, 0.1],
        )
        session.commit()

        result = search_person_semantic_mentions(
            session,
            project_id=ids["project_id"],
            query_vector=[1.0, 0.0],
            filters=PersonSemanticSearchFilters(quote_status="quote_only"),
            limit=10,
            offset=0,
        )

    assert result.total == 1
    assert result.hits[0].occurrence["is_quote"] is True


def test_search_person_semantic_mentions_excludes_pending_and_inactive() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ids = seed_person_semantic_search_rows(session)
        set_person_semantic_doc_embedding(
            session,
            document_id=ids["ready_doc_id"],
            vector=[1.0, 0.0],
        )
        set_person_semantic_doc_embedding(
            session,
            document_id=ids["inactive_doc_id"],
            vector=[1.0, 0.0],
        )
        session.commit()

        result = search_person_semantic_mentions(
            session,
            project_id=ids["project_id"],
            query_vector=[1.0, 0.0],
            filters=PersonSemanticSearchFilters(),
            limit=10,
            offset=0,
        )

    assert result.total == 1
    assert result.hits[0].semantic_document_id == ids["ready_doc_id"]
