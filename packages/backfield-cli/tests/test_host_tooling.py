"""Tests for host Python tooling repair."""

from __future__ import annotations

import stat
from pathlib import Path

from backfield_cli import host_tooling


def test_cli_import_works_false_when_venv_missing(tmp_path: Path) -> None:
    assert host_tooling.cli_import_works(tmp_path) is False


def test_ensure_host_python_tooling_skips_sync_when_import_ok(
    monkeypatch,
    tmp_path: Path,
) -> None:
    shim_calls: list[Path] = []

    def _install_shim(root: Path) -> None:
        shim_calls.append(root)

    monkeypatch.setattr(host_tooling, "cli_runtime_works", lambda _root: True)
    monkeypatch.setattr(host_tooling, "install_cli_shim", _install_shim)

    def _fail(*_args, **_kwargs):
        raise AssertionError("uv sync should not run when import works")

    monkeypatch.setattr(host_tooling.subprocess, "run", _fail)
    host_tooling.ensure_host_python_tooling(tmp_path)

    assert shim_calls == [tmp_path]


def test_install_cli_shim_copies_wrapper(tmp_path: Path) -> None:
    repo_root = tmp_path
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir()
    wrapper = scripts_dir / "backfield"
    wrapper.write_text("#!/bin/sh\necho ok\n")
    wrapper.chmod(0o644)

    venv_bin = repo_root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)

    host_tooling.install_cli_shim(repo_root)

    target = venv_bin / "backfield"
    assert target.is_file()
    assert target.read_text() == wrapper.read_text()
    assert target.stat().st_mode & stat.S_IXUSR


def test_ensure_host_python_tooling_reinstalls_when_import_broken(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state = {"imports": False, "sync_calls": 0}
    calls: list[list[str]] = []
    shim_calls: list[Path] = []

    def _import_ok(_root: Path) -> bool:
        return state["imports"]

    def _run(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["cwd"] == tmp_path
        assert cmd[:3] == ["uv", "sync", "--all-packages"]
        assert "VIRTUAL_ENV" not in kwargs.get("env", {})
        state["sync_calls"] += 1
        if state["sync_calls"] >= 2:
            state["imports"] = True
        return None

    def _install_shim(root: Path) -> None:
        shim_calls.append(root)

    monkeypatch.setattr(host_tooling, "cli_runtime_works", _import_ok)
    monkeypatch.setattr(host_tooling, "install_cli_shim", _install_shim)
    monkeypatch.setattr(host_tooling.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(host_tooling.subprocess, "run", _run)

    host_tooling.ensure_host_python_tooling(tmp_path)

    assert len(calls) == 2
    assert "--reinstall-package" in calls[1]
    assert "backfield-auth" in calls[1]
    assert shim_calls == [tmp_path]


def test_ensure_host_python_tooling_full_reinstall_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state = {"imports": False, "sync_calls": 0}
    calls: list[list[str]] = []

    def _import_ok(_root: Path) -> bool:
        return state["imports"]

    def _run(cmd, **_kwargs):
        calls.append(cmd)
        state["sync_calls"] += 1
        if "--reinstall" in cmd and "--reinstall-package" not in cmd:
            state["imports"] = True
        return None

    monkeypatch.setattr(host_tooling, "cli_runtime_works", _import_ok)
    monkeypatch.setattr(host_tooling, "install_cli_shim", lambda _root: None)
    monkeypatch.setattr(host_tooling.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(host_tooling.subprocess, "run", _run)

    host_tooling.ensure_host_python_tooling(tmp_path)

    assert len(calls) == 3
    assert calls[2][-1] == "--reinstall"


def test_ensure_host_python_tooling_raises_when_uv_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(host_tooling, "cli_runtime_works", lambda _root: False)
    monkeypatch.setattr(host_tooling.shutil, "which", lambda _name: None)

    try:
        host_tooling.ensure_host_python_tooling(tmp_path)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "make bootstrap" in str(exc)
