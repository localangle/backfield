"""Tests for backfield stack lifecycle subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest
from backfield_cli import stack, stack_cmd
from backfield_cli.main import main


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("", encoding="utf-8")
    (tmp_path / ".env").write_text("FOO=bar\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def captured_commands(monkeypatch):
    commands: list[list[str]] = []

    def _run(command, **_kwargs):
        commands.append(list(command))
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(stack_cmd.subprocess, "run", _run)
    return commands


def _compose_prefix(repo_root: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(repo_root / "infra" / "docker-compose.yml"),
        "--env-file",
        str(repo_root / ".env"),
    ]


def test_up_foreground_builds(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["up"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["up", "--build"]]


def test_up_detached(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["up", "--detached"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["up", "-d", "--build"]]


def test_up_no_build(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["up", "--no-build"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["up"]]


def test_down(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["down"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["down"]]


def test_logs_follows_by_default(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["logs"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["logs", "-f"]]


def test_logs_no_follow_with_service_filter(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["logs", "--no-follow", "agate-api", "worker"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["logs", "agate-api", "worker"]]


def test_ps(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["ps"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["ps"]]


def test_restart_with_services(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["restart", "worker"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["restart", "worker"]]


def test_compose_file_flag_overrides_discovery(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    other = tmp_path / "other"
    (other / "infra").mkdir(parents=True)
    custom = other / "infra" / "docker-compose.yml"
    custom.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.chdir(repo_root)

    assert main(["ps", "--compose-file", str(custom)]) == 0
    assert captured_commands == [
        [
            "docker",
            "compose",
            "-f",
            str(custom.resolve()),
            "--env-file",
            str(other / ".env"),
            "ps",
        ]
    ]


def test_compose_context_precedence(monkeypatch, tmp_path) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)

    env_target = tmp_path / "env_loc"
    (env_target / "infra").mkdir(parents=True)
    env_compose = env_target / "infra" / "docker-compose.yml"
    env_compose.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setenv(stack.COMPOSE_FILE_ENV, str(env_compose))

    flag_target = tmp_path / "flag_loc"
    (flag_target / "infra").mkdir(parents=True)
    flag_compose = flag_target / "infra" / "docker-compose.yml"
    flag_compose.write_text("services: {}\n", encoding="utf-8")

    # Explicit flag wins over env var.
    assert stack.resolve_compose_context(str(flag_compose)).compose_file == flag_compose.resolve()
    # Env var wins over discovery.
    assert stack.resolve_compose_context(None).compose_file == env_compose.resolve()
    # Discovery fallback when nothing is set.
    monkeypatch.delenv(stack.COMPOSE_FILE_ENV)
    assert stack.resolve_compose_context(None).compose_file == (
        repo_root / "infra" / "docker-compose.yml"
    )


def test_reset_db_requires_confirmation(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(stack_cmd.sys.stdin, "isatty", lambda: False)

    assert main(["reset-db"]) == 1
    assert captured_commands == []


def test_reset_db_with_yes(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["reset-db", "--yes"]) == 0
    assert captured_commands == [_compose_prefix(repo_root) + ["down", "-v"]]


def test_clear_entity_data_requires_confirmation(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(stack_cmd.sys.stdin, "isatty", lambda: False)

    assert main(["clear-entity-data"]) == 1
    assert captured_commands == []


def test_clear_entity_data_with_yes_runs_script(monkeypatch, tmp_path, captured_commands) -> None:
    repo_root = _make_repo(tmp_path)
    script = repo_root / stack_cmd.CLEAR_ENTITY_DATA_SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('cleared')\n", encoding="utf-8")
    monkeypatch.chdir(repo_root)

    assert main(["clear-entity-data", "--yes"]) == 0
    assert len(captured_commands) == 1
    assert captured_commands[0][0] == stack_cmd.sys.executable
    assert captured_commands[0][1] == str(script)
