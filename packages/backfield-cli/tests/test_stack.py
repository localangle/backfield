"""Tests for docker compose stack helpers."""

from __future__ import annotations

from pathlib import Path

from backfield_cli import stack


def test_compose_command_uses_repo_compose_file(tmp_path: Path) -> None:
    compose_file = tmp_path / "infra" / "docker-compose.yml"
    compose_file.parent.mkdir()
    compose_file.write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".env").write_text("FOO=bar\n", encoding="utf-8")

    command = stack.compose_command(tmp_path, "ps")

    assert command == [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "--env-file",
        str(tmp_path / ".env"),
        "ps",
    ]


def test_check_service_readiness_runs_exec_python_probe(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "infra").mkdir(parents=True)
    (repo_root / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repo_root / ".env").write_text("FOO=bar\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def _run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(stack.subprocess, "run", _run)

    assert stack._check_service_readiness(repo_root, "agate-api", 8000) is True

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:7] == [
        "docker",
        "compose",
        "-f",
        str(repo_root / "infra" / "docker-compose.yml"),
        "--env-file",
        str(repo_root / ".env"),
        "exec",
    ]
    assert command[7:10] == ["-T", "agate-api", "python"]
    assert "http://127.0.0.1:8000/readyz" in command[-1]


def test_wait_for_api_readiness_succeeds_when_all_services_ready(
    monkeypatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "infra").mkdir(parents=True)
    (repo_root / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repo_root / ".env").write_text("FOO=bar\n", encoding="utf-8")

    monkeypatch.setattr(stack, "_check_service_readiness", lambda *_args, **_kwargs: True)
    sleeps: list[float] = []
    monkeypatch.setattr(stack.time, "sleep", lambda seconds: sleeps.append(seconds))

    stack.wait_for_api_readiness(repo_root, timeout_seconds=5)

    assert sleeps == []


def test_wait_for_api_readiness_times_out(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "infra").mkdir(parents=True)
    (repo_root / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repo_root / ".env").write_text("FOO=bar\n", encoding="utf-8")

    monkeypatch.setattr(stack, "_check_service_readiness", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(stack.time, "sleep", lambda _seconds: None)

    deadline = [-5.0]

    def _monotonic() -> float:
        deadline[0] += 1.0
        return deadline[0]

    monkeypatch.setattr(stack.time, "monotonic", _monotonic)

    try:
        stack.wait_for_api_readiness(repo_root, timeout_seconds=5, poll_interval_seconds=0.01)
    except TimeoutError as exc:
        assert "agate-api: not ready" in str(exc)
    else:
        raise AssertionError("expected TimeoutError")
