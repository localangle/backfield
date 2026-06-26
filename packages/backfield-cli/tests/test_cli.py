"""Tests for the backfield CLI."""

from __future__ import annotations

from backfield_cli.main import main


def test_backfield_migrate_subcommand_delegates(monkeypatch) -> None:
    monkeypatch.setattr("backfield_db.migrate.ensure_database_exists", lambda: None)
    monkeypatch.setattr("backfield_db.migrate.command.upgrade", lambda _cfg, _rev: None)
    assert main(["migrate"]) == 0


def test_backfield_migrate_subcommand_nonzero_on_failure(monkeypatch) -> None:
    monkeypatch.setattr("backfield_db.migrate.ensure_database_exists", lambda: None)

    def _boom(_cfg, _rev) -> None:
        raise RuntimeError("fail")

    monkeypatch.setattr("backfield_db.migrate.command.upgrade", _boom)
    assert main(["migrate"]) == 1
