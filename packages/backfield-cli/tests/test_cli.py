"""Tests for the backfield CLI."""

from __future__ import annotations

import json

from backfield_cli.main import main
from backfield_db.tenancy_audit import (
    TenancyAuditBlocker,
    TenancyAuditReport,
    TenancyBlockerCode,
)
from sqlalchemy import create_engine


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

    monkeypatch.setattr("backfield_db.seed.run_seed", _fake_run_seed)
    assert (
        main(
            [
                "seed",
                "--admin-email",
                "admin@example.com",
                "--admin-password",
                "pw-test-99",
                "--json",
            ]
        )
        == 0
    )
    assert captured["admin_email"] == "admin@example.com"
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["admin_created"] is True


def test_backfield_seed_subcommand_requires_password(monkeypatch) -> None:
    monkeypatch.setattr("backfield_db.seed.run_seed", lambda **_kwargs: None)
    assert main(["seed", "--admin-email", "admin@example.com"]) == 1


def test_tenancy_audit_json_exits_nonzero_for_blockers(monkeypatch, capsys) -> None:
    report = TenancyAuditReport(
        ok=False,
        blocker_count=1,
        blockers=[
            TenancyAuditBlocker(
                code=TenancyBlockerCode.ORPHAN_PROJECT,
                message="project 1 has no workspace",
                project_id=1,
            )
        ],
    )
    monkeypatch.setattr("backfield_cli.tenancy_audit.get_engine", lambda: create_engine("sqlite://"))
    monkeypatch.setattr("backfield_cli.tenancy_audit.audit_tenancy", lambda _session: report)

    assert main(["tenancy-audit", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["blocker_count"] == 1
    assert payload["blockers"][0]["code"] == "orphan_project"


def test_tenancy_audit_json_exits_zero_when_clean(monkeypatch, capsys) -> None:
    report = TenancyAuditReport(ok=True, blocker_count=0, blockers=[])
    monkeypatch.setattr("backfield_cli.tenancy_audit.get_engine", lambda: create_engine("sqlite://"))
    monkeypatch.setattr("backfield_cli.tenancy_audit.audit_tenancy", lambda _session: report)

    assert main(["tenancy-audit", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "blocker_count": 0, "blockers": []}


def test_repair_s3_article_sources_dry_run_json(monkeypatch, capsys) -> None:
    from backfield_entities.ingest.article_external_identity import S3ArticleSourceRepairReport

    report = S3ArticleSourceRepairReport(scanned=3, updated=2, unchanged=1)
    monkeypatch.setattr(
        "backfield_cli.repair_s3_article_sources.get_engine",
        lambda: create_engine("sqlite://"),
    )
    monkeypatch.setattr(
        "backfield_cli.repair_s3_article_sources.repair_s3_article_external_sources",
        lambda _session, **_kwargs: report,
    )

    assert main(["repair-s3-article-sources", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned"] == 3
    assert payload["updated"] == 2
    assert payload["unchanged"] == 1


def test_repair_orphan_connections_dry_run_json(monkeypatch, capsys) -> None:
    from backfield_entities.connections.lifecycle import RepairOrphanConnectionsResult

    report = RepairOrphanConnectionsResult(
        closed_count=4,
        rewired_count=2,
        inspected_count=6,
    )
    monkeypatch.setattr(
        "backfield_cli.repair_orphan_connections.get_engine",
        lambda: create_engine("sqlite://"),
    )
    monkeypatch.setattr(
        "backfield_cli.repair_orphan_connections.repair_orphan_open_connections",
        lambda _session, **_kwargs: report,
    )

    assert main(["repair-orphan-connections", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "mode": "dry-run",
        "stylebook_id": None,
        "inspected_count": 6,
        "rewired_count": 2,
        "closed_count": 4,
    }


def test_migrate_connection_kg_inventory_json(monkeypatch, capsys) -> None:
    from backfield_entities.connections.migrate_kg_phase_a import ConnectionKgMigrateReport

    report = ConnectionKgMigrateReport(
        apply=False,
        inventory_only=True,
        connection_total=12,
        null_nature_count=2,
    )
    monkeypatch.setattr(
        "backfield_cli.migrate_connection_kg.get_engine",
        lambda: create_engine("sqlite://"),
    )
    monkeypatch.setattr(
        "backfield_cli.migrate_connection_kg.migrate_connections_kg_phase_a",
        lambda _session, **_kwargs: report,
    )

    assert main(["migrate-connection-kg", "--inventory-only", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["connection_total"] == 12
    assert payload["inventory_only"] is True
