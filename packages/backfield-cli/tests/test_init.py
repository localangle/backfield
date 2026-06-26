"""Tests for backfield init orchestration."""

from __future__ import annotations

import json

from backfield_cli.init import run_init
from backfield_cli.init_config import InitConfig
from backfield_db.seed import SeedReport


def _write_repo_root(tmp_path) -> None:
    (tmp_path / "Makefile").write_text("", encoding="utf-8")
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("# example\n", encoding="utf-8")


def test_run_init_non_interactive_orchestration(monkeypatch, tmp_path) -> None:
    _write_repo_root(tmp_path)
    monkeypatch.chdir(tmp_path)

    calls: dict[str, int] = {"up": 0, "migrate": 0, "ready": 0, "seed": 0}

    def _up(_repo_root) -> None:
        calls["up"] += 1

    def _migrate(_repo_root) -> None:
        calls["migrate"] += 1

    def _ready(repo_root, **_kwargs) -> None:
        calls["ready"] += 1
        assert repo_root == tmp_path

    def _seed(**kwargs):
        calls["seed"] += 1
        assert kwargs["admin_email"] == "admin@example.com"
        assert kwargs["org_name"] == "Acme News"
        return SeedReport(
            organization_id=1,
            organization_slug="default",
            organization_created=False,
            admin_user_id=2,
            admin_email="admin@example.com",
            admin_created=True,
        )

    monkeypatch.setattr("backfield_cli.init.bring_up_stack", _up)
    monkeypatch.setattr("backfield_cli.init.run_compose_migrate", _migrate)
    monkeypatch.setattr("backfield_cli.init.wait_for_api_readiness", _ready)
    monkeypatch.setattr("backfield_cli.init.run_init_seed", _seed)

    config = InitConfig.model_validate(
        {
            "admin_email": "admin@example.com",
            "admin_password": "pw-test",
            "org_name": "Acme News",
            "stylebook_name": "Acme Stylebook",
        }
    )

    assert run_init(config, repo_root=tmp_path) == 0
    assert calls == {"up": 1, "migrate": 1, "ready": 1, "seed": 1}


def test_run_init_skip_stack(monkeypatch, tmp_path) -> None:
    _write_repo_root(tmp_path)

    def _fail(_repo_root) -> None:
        raise AssertionError("bring_up_stack should not run")

    monkeypatch.setattr("backfield_cli.init.bring_up_stack", _fail)
    monkeypatch.setattr("backfield_cli.init.run_compose_migrate", lambda _repo_root: None)
    monkeypatch.setattr("backfield_cli.init.wait_for_api_readiness", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "backfield_cli.init.run_init_seed",
        lambda **_kwargs: SeedReport(
            organization_id=1,
            organization_slug="default",
            organization_created=False,
            admin_user_id=2,
            admin_email="admin@example.com",
            admin_created=False,
        ),
    )

    config = InitConfig.model_validate(
        {
            "admin_email": "admin@example.com",
            "admin_password": "pw-test",
            "skip_stack": True,
        }
    )

    assert run_init(config, repo_root=tmp_path) == 0


def test_backfield_init_cli_non_interactive(monkeypatch, tmp_path, capsys) -> None:
    from backfield_cli.main import main

    _write_repo_root(tmp_path)
    config_path = tmp_path / "init.json"
    config_path.write_text(
        json.dumps(
            {
                "admin_email": "admin@example.com",
                "admin_password": "pw-test",
                "skip_stack": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("backfield_cli.init.run_compose_migrate", lambda _repo_root: None)
    monkeypatch.setattr("backfield_cli.init.wait_for_api_readiness", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "backfield_cli.init.run_init_seed",
        lambda **_kwargs: SeedReport(
            organization_id=1,
            organization_slug="default",
            organization_created=False,
            admin_user_id=2,
            admin_email="admin@example.com",
            admin_created=True,
        ),
    )

    assert (
        main(
            [
                "init",
                "--non-interactive",
                "--config",
                str(config_path),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "http://localhost:5173/settings/integrations" in output
