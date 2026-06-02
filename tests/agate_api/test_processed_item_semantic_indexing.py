"""API tests for processed item semantic indexing summary."""

from __future__ import annotations

from datetime import UTC, datetime

from api.routers.runs import ProcessedItemSemanticIndexingOut, _processed_item_semantic_indexing
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel


def test_processed_item_semantic_indexing_out_shape() -> None:
    out = ProcessedItemSemanticIndexingOut.model_validate(
        {
            "status": "partial",
            "enabled": True,
            "document_count": 2,
            "indexed_count": 1,
            "pending_count": 1,
            "failed_count": 0,
            "indexed_at": datetime(2026, 6, 1, tzinfo=UTC),
            "embedding_model": "openai/text-embedding-3-small",
            "error": None,
        }
    )
    assert out.status == "partial"
    assert out.indexed_count == 1


def test_processed_item_semantic_indexing_helper_not_enabled() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        out = _processed_item_semantic_indexing(
            session,
            project_id=1,
            item_status="succeeded",
            output_obj={"stylebook_output": {"success": True}},
            article_id=None,
            item_updated_at=datetime.now(UTC),
        )
    assert out.status == "not_enabled"
    assert out.enabled is False


def test_processed_item_semantic_indexing_helper_does_not_change_item_status() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        out = _processed_item_semantic_indexing(
            session,
            project_id=1,
            item_status="succeeded",
            output_obj={
                "stylebook_output": {
                    "semantic_indexing": {
                        "enabled": True,
                        "status": "failed",
                        "error": "embedding provider down",
                        "domains": [],
                    }
                }
            },
            article_id=None,
            item_updated_at=datetime.now(UTC),
        )
    assert out.status == "failed"
    assert out.error == "embedding provider down"
