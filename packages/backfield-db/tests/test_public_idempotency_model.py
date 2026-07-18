"""Structural contract for public idempotency persistence."""

from __future__ import annotations

from pathlib import Path

from backfield_db import BackfieldPublicIdempotencyRecord


def test_public_idempotency_model_has_safe_storage_and_indexes() -> None:
    table = BackfieldPublicIdempotencyRecord.__table__

    assert table.name == "backfield_public_idempotency_record"
    assert set(table.columns.keys()) == {
        "id",
        "project_id",
        "operation",
        "idempotency_key",
        "request_hash",
        "run_id",
        "created_at",
        "expires_at",
    }
    assert "body" not in " ".join(table.columns.keys())
    names = {constraint.name for constraint in table.constraints} | {
        index.name for index in table.indexes
    }
    assert {
        "uq_backfield_public_idempotency_scope",
        "ix_backfield_public_idempotency_expires",
        "ix_backfield_public_idempotency_run",
    }.issubset(names)


def test_public_idempotency_migration_follows_current_head() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "064_public_idempotency.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: Union[str, None] = "063_stylebook_activity"' in migration
    assert '"backfield_public_idempotency_record"' in migration
    assert '"uq_backfield_public_idempotency_scope"' in migration
    assert '"ix_backfield_public_idempotency_expires"' in migration
