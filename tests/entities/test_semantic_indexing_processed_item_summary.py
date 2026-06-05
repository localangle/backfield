"""Unit tests for processed item semantic indexing summary."""

from __future__ import annotations

from datetime import UTC, datetime

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstratePersonSemanticDocument,
)
from backfield_db.semantic_indexing import (
    SEMANTIC_EMBEDDING_STATUS_PENDING,
    SEMANTIC_EMBEDDING_STATUS_READY,
)
from backfield_entities.ingest.semantic_indexing.processed_item import (
    build_processed_item_semantic_indexing_summary,
    extract_db_output_semantic_indexing,
)
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select


def _seed_project(session: Session) -> tuple[int, int]:
    session.add(BackfieldOrganization(name="Org", slug="org-pi-sem"))
    session.commit()
    org = session.exec(
        select(BackfieldOrganization).where(BackfieldOrganization.slug == "org-pi-sem")
    ).one()
    oid = int(org.id)
    session.add(BackfieldProject(organization_id=oid, name="Proj", slug=f"proj-pi-sem-{oid}"))
    session.commit()
    proj = session.exec(
        select(BackfieldProject).where(BackfieldProject.slug == f"proj-pi-sem-{oid}")
    ).one()
    return oid, int(proj.id)


def test_extract_db_output_semantic_indexing_from_stylebook_output() -> None:
    raw = extract_db_output_semantic_indexing(
        {
            "stylebook_output": {
                "semantic_indexing": {"enabled": True, "status": "succeeded", "domains": []},
            }
        }
    )
    assert raw is not None
    assert raw["enabled"] is True


def test_build_summary_not_enabled_when_toggle_off() -> None:
    summary = build_processed_item_semantic_indexing_summary(
        None,
        project_id=1,
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "semantic_indexing": {"enabled": False, "status": "not_enabled", "domains": []},
            }
        },
    )
    assert summary["status"] == "not_enabled"
    assert summary["enabled"] is False


def test_build_summary_running_and_pending_follow_item_status() -> None:
    running = build_processed_item_semantic_indexing_summary(
        None,
        project_id=1,
        item_status="running",
        result_obj=None,
    )
    pending = build_processed_item_semantic_indexing_summary(
        None,
        project_id=1,
        item_status="pending",
        result_obj=None,
    )
    assert running["status"] == "running"
    assert pending["status"] == "pending"


def test_build_summary_succeeded_with_embedding_counts() -> None:
    updated = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    summary = build_processed_item_semantic_indexing_summary(
        None,
        project_id=1,
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "semantic_indexing": {
                    "enabled": True,
                    "status": "succeeded",
                    "domains": [{"entity_type": "person", "created": 2, "pending": 0}],
                    "embedding": {
                        "status": "succeeded",
                        "indexed": 2,
                        "failed": 0,
                        "pending": 0,
                        "embedding_model": "openai/text-embedding-3-small",
                    },
                }
            }
        },
        item_updated_at=updated,
    )
    assert summary["status"] == "succeeded"
    assert summary["indexed_count"] == 2
    assert summary["embedding_model"] == "openai/text-embedding-3-small"
    assert summary["indexed_at"] == updated


def test_build_summary_partial_when_pending_docs_remain() -> None:
    summary = build_processed_item_semantic_indexing_summary(
        None,
        project_id=1,
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "semantic_indexing": {
                    "enabled": True,
                    "status": "partial",
                    "domains": [{"entity_type": "person", "created": 1, "pending": 1}],
                    "embedding": {
                        "status": "not_configured",
                        "indexed": 0,
                        "failed": 0,
                        "pending": 1,
                        "error": "No embedding model configured.",
                    },
                }
            }
        },
    )
    assert summary["status"] == "partial"
    assert summary["pending_count"] >= 1
    assert summary["error"] == "No embedding model configured."


def test_build_summary_failed_from_sync_error() -> None:
    summary = build_processed_item_semantic_indexing_summary(
        None,
        project_id=1,
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "semantic_indexing": {
                    "enabled": True,
                    "status": "failed",
                    "error": "provider timeout",
                    "domains": [],
                }
            }
        },
    )
    assert summary["status"] == "failed"
    assert summary["error"] == "provider timeout"


def test_build_summary_prefers_db_counts_and_embedded_at() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    embedded_at = datetime(2026, 6, 1, 15, 30, tzinfo=UTC)

    with Session(engine) as session:
        _oid, pid = _seed_project(session)
        article = SubstrateArticle(project_id=pid, headline="H", text="Body")
        session.add(article)
        session.commit()
        session.refresh(article)
        aid = int(article.id)

        session.add(
            SubstratePersonSemanticDocument(
                project_id=pid,
                article_id=aid,
                person_id=1,
                person_mention_id=1,
                person_mention_occurrence_id=1,
                search_text="Mayor Jane Smith",
                source_hash="abc",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_READY,
                embedding_model="openai/text-embedding-3-small",
                embedded_at=embedded_at,
            )
        )
        session.add(
            SubstratePersonSemanticDocument(
                project_id=pid,
                article_id=aid,
                person_id=2,
                person_mention_id=2,
                person_mention_occurrence_id=2,
                search_text="John Doe",
                source_hash="def",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
            )
        )
        session.commit()

        summary = build_processed_item_semantic_indexing_summary(
            session,
            project_id=pid,
            item_status="succeeded",
            result_obj={
                "stylebook_output": {
                    "semantic_indexing": {
                        "enabled": True,
                        "status": "succeeded",
                        "domains": [{"entity_type": "person", "created": 2}],
                        "embedding": {"status": "succeeded", "indexed": 2},
                    }
                }
            },
            article_id=aid,
        )

    assert summary["status"] == "partial"
    assert summary["indexed_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["document_count"] == 2
    indexed_at = summary["indexed_at"]
    assert indexed_at is not None
    if indexed_at.tzinfo is None:
        assert indexed_at == embedded_at.replace(tzinfo=None)
    else:
        assert indexed_at == embedded_at


def test_build_summary_reflects_db_when_output_says_not_enabled() -> None:
    """Later re-index can populate docs even when Backfield Output ran with indexing off."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    embedded_at = datetime(2026, 6, 3, 21, 33, tzinfo=UTC)

    with Session(engine) as session:
        _oid, pid = _seed_project(session)
        article = SubstrateArticle(project_id=pid, headline="H", text="Body")
        session.add(article)
        session.commit()
        session.refresh(article)
        aid = int(article.id)

        session.add(
            SubstratePersonSemanticDocument(
                project_id=pid,
                article_id=aid,
                person_id=1,
                person_mention_id=1,
                person_mention_occurrence_id=1,
                search_text="Indexed later",
                source_hash="abc",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_READY,
                embedding_model="openai/text-embedding-3-small",
                embedded_at=embedded_at,
            )
        )
        session.commit()

        summary = build_processed_item_semantic_indexing_summary(
            session,
            project_id=pid,
            item_status="succeeded",
            result_obj={
                "stylebook_output": {
                    "semantic_indexing": {
                        "enabled": False,
                        "status": "not_enabled",
                        "domains": [],
                    }
                }
            },
            article_id=aid,
        )

    assert summary["status"] == "succeeded"
    assert summary["enabled"] is True
    assert summary["indexed_count"] == 1
    assert summary["document_count"] == 1
