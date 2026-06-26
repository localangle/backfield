"""Tests for the backfield CLI."""

from __future__ import annotations

import json

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


def test_backfield_seed_subcommand_delegates(monkeypatch, capsys) -> None:
    captured: dict[str, str] = {}

    def _fake_run_seed(**kwargs):
        captured.update(kwargs)
        from backfield_db.seed import SeedReport

        return SeedReport(
            organization_id=1,
            organization_slug=kwargs["org_slug"],
            organization_created=True,
            admin_user_id=2,
            admin_email=kwargs["admin_email"],
            admin_created=True,
        )

    monkeypatch.setattr("backfield_cli.seed.run_seed", _fake_run_seed)
    assert (
        main(
            [
                "seed",
                "--admin-email",
                "admin@example.com",
                "--admin-password",
                "pw-test",
                "--json",
            ]
        )
        == 0
    )
    assert captured["admin_email"] == "admin@example.com"
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["admin_created"] is True


def test_backfield_seed_subcommand_requires_password(monkeypatch) -> None:
    monkeypatch.setattr("backfield_cli.seed.run_seed", lambda **_kwargs: None)
    assert main(["seed", "--admin-email", "admin@example.com"]) == 1
