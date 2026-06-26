"""Tests for standalone database migrations."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from backfield_db.migrate import alembic_root, build_alembic_config, main, run_migrations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def test_alembic_root_contains_ini() -> None:
    root = alembic_root()
    assert (root / "alembic.ini").is_file()
    assert (root / "alembic").is_dir()


def test_build_alembic_config_points_at_repo_chain() -> None:
    cfg = build_alembic_config()
    script_location = Path(cfg.get_main_option("script_location") or "")
    if not script_location.is_absolute():
        script_location = alembic_root() / script_location
    assert script_location.is_dir()


def test_migrate_exits_nonzero_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backfield_db.migrate.ensure_database_exists", lambda: None)

    def _boom(_cfg, _rev) -> None:
        raise RuntimeError("forced migration failure")

    monkeypatch.setattr("backfield_db.migrate.command.upgrade", _boom)
    assert main() == 1


def test_migrate_exits_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backfield_db.migrate.ensure_database_exists", lambda: None)
    monkeypatch.setattr("backfield_db.migrate.command.upgrade", lambda _cfg, _rev: None)
    assert main() == 0


def test_run_migrations_against_fresh_postgres_creates_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = os.environ.get(
        "BACKFIELD_MIGRATE_TEST_ADMIN_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5433/postgres",
    )
    if not admin_url.startswith("postgresql"):
        pytest.skip("postgres-only migration integration test")

    try:
        admin_engine = create_engine(admin_url)
        with admin_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("postgres not available for migration integration test")

    db_name = f"backfield_migrate_test_{uuid.uuid4().hex[:10]}"
    with admin_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    target_url = admin_url.rsplit("/", 1)[0] + f"/{db_name}"
    monkeypatch.setenv("BACKFIELD_DATABASE_URL_DIRECT", target_url)
    monkeypatch.delenv("BACKFIELD_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    try:
        run_migrations()
        with create_engine(target_url).connect() as conn:
            extensions = {
                row[0]
                for row in conn.execute(
                    text("SELECT extname FROM pg_extension ORDER BY extname")
                )
            }
        assert {"postgis", "vector", "h3"} <= extensions
    finally:
        with admin_engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
                )
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
