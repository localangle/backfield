"""Tests for backfield init orchestration."""

from __future__ import annotations

import json

from backfield_cli.console import DOCS_URL, INTEGRATIONS_URL, MODELS_URL
from backfield_cli.init import (
    _maybe_open_browser,
    _resolve_open_browser,
    run_init,
)
from backfield_cli.init_config import InitConfig
from backfield_db.seed import SeedReport


def _write_repo_root(tmp_path) -> None:
    (tmp_path / "Makefile").write_text("", encoding="utf-8")
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("# example\n", encoding="utf-8")


def _noop_host_tooling(*_args, **_kwargs) -> None:
    return None


def _patch_init_stack(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "backfield_cli.init.ensure_host_python_tooling",
        _noop_host_tooling,
    )
    monkeypatch.setattr("backfield_cli.init.bring_up_stack", lambda _repo_root: None)
    monkeypatch.setattr("backfield_cli.init.run_compose_migrate", lambda _repo_root: None)
    monkeypatch.setattr(
        "backfield_cli.init.wait_for_api_readiness",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "backfield_cli.init.run_init_seed",
        lambda **_kwargs: SeedReport(
            organization_id=1,
            organization_slug="acme-news",
            organization_created=False,
            admin_user_id=2,
            admin_email="admin@example.com",
            admin_created=True,
        ),
    )


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
    monkeypatch.setattr("backfield_cli.init.ensure_host_python_tooling", _noop_host_tooling)

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
    monkeypatch.setattr("backfield_cli.init.ensure_host_python_tooling", _noop_host_tooling)
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
    monkeypatch.setattr("backfield_cli.init.ensure_host_python_tooling", _noop_host_tooling)
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
    assert MODELS_URL in output
    assert INTEGRATIONS_URL in output
    assert DOCS_URL in output


def test_run_init_does_not_open_browser_when_not_interactive(monkeypatch, tmp_path) -> None:
    _write_repo_root(tmp_path)
    opened: list[str] = []

    def _track_open(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("backfield_cli.init.webbrowser.open", _track_open)
    _patch_init_stack(monkeypatch, tmp_path)

    config = InitConfig.model_validate(
        {
            "admin_email": "admin@example.com",
            "admin_password": "pw-test",
            "skip_stack": True,
        }
    )

    assert run_init(config, repo_root=tmp_path, interactive=False) == 0
    assert opened == []


def test_run_init_opens_browser_when_interactive(monkeypatch, tmp_path) -> None:
    _write_repo_root(tmp_path)
    opened: list[str] = []

    def _track_open(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("backfield_cli.init.webbrowser.open", _track_open)
    _patch_init_stack(monkeypatch, tmp_path)

    config = InitConfig.model_validate(
        {
            "admin_email": "admin@example.com",
            "admin_password": "pw-test",
            "skip_stack": True,
        }
    )

    assert run_init(config, repo_root=tmp_path, interactive=True) == 0
    assert opened == [MODELS_URL]


def test_run_init_respects_open_browser_false(monkeypatch, tmp_path) -> None:
    _write_repo_root(tmp_path)
    opened: list[str] = []

    monkeypatch.setattr(
        "backfield_cli.init.webbrowser.open",
        lambda url: opened.append(url) or True,
    )
    _patch_init_stack(monkeypatch, tmp_path)

    config = InitConfig.model_validate(
        {
            "admin_email": "admin@example.com",
            "admin_password": "pw-test",
            "skip_stack": True,
            "open_browser": False,
        }
    )

    assert run_init(config, repo_root=tmp_path, interactive=True) == 0
    assert opened == []


def test_maybe_open_browser_swallows_errors(monkeypatch) -> None:
    def _boom(_url: str) -> bool:
        raise OSError("no browser")

    monkeypatch.setattr("backfield_cli.init.webbrowser.open", _boom)
    _maybe_open_browser(MODELS_URL, enabled=True)


def test_resolve_open_browser_honors_no_browser_flag() -> None:
    config = InitConfig.model_validate(
        {
            "admin_email": "admin@example.com",
            "admin_password": "pw-test",
        }
    )
    assert _resolve_open_browser(config, no_browser_flag=True) is False
    assert _resolve_open_browser(config, no_browser_flag=False) is True


def test_backfield_init_cli_no_browser(monkeypatch, tmp_path) -> None:
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
    opened: list[str] = []
    monkeypatch.setattr(
        "backfield_cli.init.webbrowser.open",
        lambda url: opened.append(url) or True,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("backfield_cli.init.is_interactive", lambda: True)
    _patch_init_stack(monkeypatch, tmp_path)

    assert (
        main(
            [
                "init",
                "--non-interactive",
                "--config",
                str(config_path),
                "--no-browser",
            ]
        )
        == 0
    )
    assert opened == []
