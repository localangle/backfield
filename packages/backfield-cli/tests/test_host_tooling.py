"""Tests for host Python tooling repair."""

from __future__ import annotations

from pathlib import Path

from backfield_cli import host_tooling


def test_cli_import_works_false_when_venv_missing(tmp_path: Path) -> None:
    assert host_tooling.cli_import_works(tmp_path) is False


def test_ensure_host_python_tooling_skips_when_import_ok(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(host_tooling, "cli_import_works", lambda _root: True)
    calls: list[list[str]] = []

    def _fail(*_args, **_kwargs):
        raise AssertionError("uv sync should not run when import works")

    monkeypatch.setattr(host_tooling.subprocess, "run", _fail)
    host_tooling.ensure_host_python_tooling(tmp_path)


def test_ensure_host_python_tooling_reinstalls_when_import_broken(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state = {"imports": False}
    calls: list[list[str]] = []

    def _import_ok(_root: Path) -> bool:
        return state["imports"]

    def _run(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["cwd"] == tmp_path
        assert cmd[:3] == ["uv", "sync", "--all-packages"]
        state["imports"] = True
        return None

    monkeypatch.setattr(host_tooling, "cli_import_works", _import_ok)
    monkeypatch.setattr(host_tooling.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(host_tooling.subprocess, "run", _run)

    host_tooling.ensure_host_python_tooling(tmp_path)

    assert len(calls) == 1


def test_ensure_host_python_tooling_raises_when_uv_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(host_tooling, "cli_import_works", lambda _root: False)
    monkeypatch.setattr(host_tooling.shutil, "which", lambda _name: None)

    try:
        host_tooling.ensure_host_python_tooling(tmp_path)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "make bootstrap" in str(exc)
