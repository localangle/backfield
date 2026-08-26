"""Focused checks for the connection-currentness data backfill."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import create_engine, text


class _BackfillOnlyOperations:
    """Run migration data statements while ignoring schema operations."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, statement: Any) -> None:
        self.connection.execute(statement)

    def __getattr__(self, _name: str) -> Any:
        return lambda *_args, **_kwargs: None


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "backfield-db"
        / "alembic"
        / "versions"
        / "079_connection_currentness.py"
    )
    spec = importlib.util.spec_from_file_location("connection_currentness_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_article_publication_date_backfills_evidence_reference_time() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE substrate_article "
                "(id INTEGER PRIMARY KEY, pub_date DATE NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE stylebook_connection_evidence "
                "(id INTEGER PRIMARY KEY, article_id INTEGER NULL, observed_at DATETIME NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO substrate_article (id, pub_date) "
                "VALUES (1, '2020-05-06'), (2, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stylebook_connection_evidence "
                "(id, article_id, observed_at) VALUES "
                "(1, 1, '2026-01-01 00:00:00'), "
                "(2, 2, '2026-02-01 00:00:00')"
            )
        )

        migration = _migration_module()
        migration.op = _BackfillOnlyOperations(connection)  # type: ignore[attr-defined]
        migration.upgrade()  # type: ignore[attr-defined]

        rows = connection.execute(
            text(
                "SELECT id, observed_at FROM stylebook_connection_evidence ORDER BY id"
            )
        ).all()

    assert str(rows[0].observed_at).startswith("2020-05-06")
    assert str(rows[1].observed_at).startswith("2026-02-01")
