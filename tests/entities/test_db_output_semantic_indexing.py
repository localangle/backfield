"""Backfield Output semantic indexing setting and integration helpers."""

from __future__ import annotations

from backfield_entities.db_output_settings import DbOutputCanonicalSettings
from backfield_entities.semantic_indexing.db_output import (
    build_semantic_indexing_summary,
    semantic_entity_types_for_consolidated_domains,
    sync_semantic_documents_after_db_output,
)
from backfield_entities.semantic_indexing.embedding_contract import EmbeddingRunSummary
from backfield_entities.semantic_indexing.sync_contract import (
    SemanticSyncResult,
    SemanticSyncSummary,
)


def test_db_output_settings_semantic_indexing_defaults_off() -> None:
    settings = DbOutputCanonicalSettings.from_node_params({})
    assert settings.semantic_indexing_enabled is False


def test_db_output_settings_semantic_indexing_can_be_enabled() -> None:
    settings = DbOutputCanonicalSettings.from_node_params({"semantic_indexing_enabled": True})
    assert settings.semantic_indexing_enabled is True


def test_semantic_entity_types_for_consolidated_domains() -> None:
    assert semantic_entity_types_for_consolidated_domains(("people",)) == ("person",)
    assert semantic_entity_types_for_consolidated_domains(("places",)) == ("location",)
    assert semantic_entity_types_for_consolidated_domains(("people", "places")) == (
        "person",
        "location",
    )
    assert semantic_entity_types_for_consolidated_domains(()) == ()


def test_build_semantic_indexing_summary_not_enabled() -> None:
    summary = build_semantic_indexing_summary(enabled=False)
    assert summary == {"enabled": False, "status": "not_enabled", "domains": []}


def test_build_semantic_indexing_summary_succeeded() -> None:
    sync_result = SemanticSyncResult(
        summaries=(
            SemanticSyncSummary(entity_type="person", created=2, pending=2),
            SemanticSyncSummary(entity_type="location", created=1, pending=1),
        )
    )
    summary = build_semantic_indexing_summary(enabled=True, sync_result=sync_result)
    assert summary["enabled"] is True
    assert summary["status"] == "succeeded"
    assert len(summary["domains"]) == 2
    assert summary["domains"][0]["entity_type"] == "person"
    assert summary["domains"][0]["created"] == 2


def test_build_semantic_indexing_summary_failed() -> None:
    summary = build_semantic_indexing_summary(enabled=True, error="provider timeout")
    assert summary["enabled"] is True
    assert summary["status"] == "failed"
    assert summary["error"] == "provider timeout"
    assert summary["domains"] == []


def test_build_semantic_indexing_summary_with_embedding_partial() -> None:
    sync_result = SemanticSyncResult(
        summaries=(SemanticSyncSummary(entity_type="person", created=1, pending=1),)
    )
    embedding = EmbeddingRunSummary(
        status="not_configured",
        pending=1,
        error="No embedding model configured.",
    )
    summary = build_semantic_indexing_summary(
        enabled=True,
        sync_result=sync_result,
        embedding=embedding,
    )
    assert summary["status"] == "partial"
    assert summary["embedding"]["status"] == "not_configured"


def test_sync_semantic_documents_after_db_output_no_supported_domains() -> None:
    result = sync_semantic_documents_after_db_output(
        session=None,  # type: ignore[arg-type]
        project_id=1,
        article_id=1,
        consolidated_domain_keys=("organizations",),
    )
    assert result.summaries == ()
