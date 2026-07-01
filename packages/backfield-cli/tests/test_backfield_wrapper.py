"""Tests for the repo-root scripts/backfield wrapper."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_backfield_wrapper_is_executable() -> None:
    script = _repo_root() / "scripts" / "backfield"
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR


def test_backfield_wrapper_heals_missing_editable_link() -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "backfield"
    venv_py = repo_root / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        return

    subprocess.run(
        [
            "uv",
            "sync",
            "--all-packages",
            "--reinstall-package",
            "backfield-cli",
            "--quiet",
        ],
        cwd=repo_root,
        check=True,
    )

    pth_files = list(
        (repo_root / ".venv" / "lib").glob("python*/site-packages/_editable_impl_backfield_cli.pth")
    )
    assert pth_files
    pth_files[0].unlink()

    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    result = subprocess.run(
        [str(script), "--help"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Backfield operator CLI" in result.stdout

    second = subprocess.run(
        [str(script), "--help"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr
