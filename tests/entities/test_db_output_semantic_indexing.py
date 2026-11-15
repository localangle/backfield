"""Backfield Output semantic indexing setting and integration helpers."""

from __future__ import annotations

from backfield_entities.ingest.db_output_settings import DbOutputCanonicalSettings
from backfield_entities.ingest.semantic_indexing.db_output import (
    build_semantic_indexing_summary,
    semantic_entity_types_for_consolidated_domains,
    sync_semantic_documents_after_db_output,
)
from backfield_entities.ingest.semantic_indexing.embedding_contract import EmbeddingRunSummary
from backfield_entities.ingest.semantic_indexing.sync_contract import (
    SemanticSyncResult,
    SemanticSyncSummary,
)


def test_db_output_settings_semantic_indexing_defaults_off() -> None:
    settings = DbOutputCanonicalSettings.from_node_params({})
    assert settings.semantic_indexing_enabled is False


def test_db_output_settings_auto_connections_defaults_off() -> None:
    settings = DbOutputCanonicalSettings.from_node_params({})
    assert settings.auto_connections_enabled is False


def test_db_output_settings_connections_model_falls_back_to_adjudication() -> None:
    from backfield_entities.ingest.db_output_settings import resolved_connections_llm

    settings = DbOutputCanonicalSettings.from_node_params(
        {"adjudication_model": "gpt-test", "adjudication_ai_model_config_id": "cfg-1"}
    )
    model, config_id = resolved_connections_llm(settings)
    assert model == "gpt-test"
    assert config_id == "cfg-1"

    dedicated = DbOutputCanonicalSettings.from_node_params(
        {
            "connections_model": "gpt-conn",
            "connections_ai_model_config_id": "cfg-2",
            "adjudication_model": "gpt-test",
        }
    )
    model, config_id = resolved_connections_llm(dedicated)
    assert model == "gpt-conn"
    assert config_id == "cfg-2"


def test_db_output_settings_auto_connections_can_be_disabled() -> None:
    settings = DbOutputCanonicalSettings.from_node_params(
        {"auto_connections_enabled": False}
    )
    assert settings.auto_connections_enabled is False


def test_db_output_settings_semantic_indexing_can_be_enabled() -> None:
    settings = DbOutputCanonicalSettings.from_node_params({"semantic_indexing_enabled": True})
    assert settings.semantic_indexing_enabled is True


def test_semantic_entity_types_for_consolidated_domains() -> None:
    assert semantic_entity_types_for_consolidated_domains(("people",)) == ("person",)
    assert semantic_entity_types_for_consolidated_domains(("places",)) == ("location",)
    assert semantic_entity_types_for_consolidated_domains(("organizations",)) == (
        "organization",
    )
    assert semantic_entity_types_for_consolidated_domains(("people", "places")) == (
        "person",
        "location",
    )
    assert semantic_entity_types_for_consolidated_domains(
        ("people", "places", "organizations")
    ) == ("person", "location", "organization")
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


def test_sync_semantic_documents_after_db_output_unknown_domain() -> None:
    result = sync_semantic_documents_after_db_output(
        session=None,  # type: ignore[arg-type]
        project_id=1,
        article_id=1,
        consolidated_domain_keys=("works",),
    )
    assert result.summaries == ()


def test_sync_semantic_documents_after_db_output_retries_stale_data(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from backfield_entities.ingest.semantic_indexing import db_output as sem_db
    from sqlalchemy.orm.exc import StaleDataError

    attempts = {"n": 0}
    expected = SemanticSyncResult(
        summaries=(SemanticSyncSummary(entity_type="location", created=1, pending=1),)
    )

    def _fake_sync(session, *, project_id, article_id, entity_types):  # noqa: ARG001
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise StaleDataError(
                "UPDATE statement on table 'substrate_location_semantic_document' "
                "expected to update 7 row(s); 6 were matched."
            )
        return expected

    nested = MagicMock()
    nested.__enter__ = MagicMock(return_value=None)
    nested.__exit__ = MagicMock(return_value=False)
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=nested)
    session.expire_all = MagicMock()

    monkeypatch.setattr(sem_db, "sync_semantic_documents_for_article", _fake_sync)

    result = sync_semantic_documents_after_db_output(
        session,
        project_id=1,
        article_id=9,
        consolidated_domain_keys=("places",),
    )
    assert result is expected
    assert attempts["n"] == 2
    session.expire_all.assert_called_once()


def test_sync_semantic_documents_after_db_output_raises_after_stale_retries(
    monkeypatch,
) -> None:
    from unittest.mock import MagicMock

    from backfield_entities.ingest.semantic_indexing import db_output as sem_db
    from sqlalchemy.orm.exc import StaleDataError

    def _always_stale(session, **_kwargs):  # noqa: ARG001
        raise StaleDataError("expected to update 4 row(s); 3 were matched.")

    nested = MagicMock()
    nested.__enter__ = MagicMock(return_value=None)
    nested.__exit__ = MagicMock(return_value=False)
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=nested)

    monkeypatch.setattr(sem_db, "sync_semantic_documents_for_article", _always_stale)

    try:
        sync_semantic_documents_after_db_output(
            session,
            project_id=1,
            article_id=9,
            consolidated_domain_keys=("places",),
        )
        raise AssertionError("expected StaleDataError")
    except StaleDataError:
        pass
    assert session.begin_nested.call_count == 2
    assert session.expire_all.call_count == 2
