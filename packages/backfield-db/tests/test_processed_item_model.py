"""Structural contracts for Agate processed-item persistence."""

from __future__ import annotations

from pathlib import Path

from backfield_db import AgateProcessedItem


def test_processed_item_model_has_run_status_index() -> None:
    table = AgateProcessedItem.__table__
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in table.indexes
    }

    assert indexes["ix_agate_processed_item_run_status"] == ("run_id", "status")
    assert "ix_agate_processed_item_run_id" not in indexes


def test_processed_item_index_migration_follows_current_head() -> None:
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migration = (versions / "066_agate_pi_run_status.py").read_text(encoding="utf-8")

    assert 'revision: str = "066_agate_pi_run_status"' in migration
    assert 'down_revision: str | None = "065_public_idempotency_enqueue"' in migration
    assert '"ix_agate_processed_item_run_status"' in migration
    assert "postgresql_concurrently=True" in migration
