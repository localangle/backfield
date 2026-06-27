"""Keep the shared workspace venv able to import the operator CLI."""

from __future__ import annotations

import logging
import shutil
import stat
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_TOOLING_PACKAGES = ("backfield-cli", "backfield-db")


def venv_python(repo_root: Path) -> Path:
    if sys.platform == "win32":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


def cli_shim_source(repo_root: Path) -> Path:
    return repo_root / "scripts" / "backfield"


def cli_shim_target(repo_root: Path) -> Path:
    if sys.platform == "win32":
        return repo_root / ".venv" / "Scripts" / "backfield.bat"
    return repo_root / ".venv" / "bin" / "backfield"


def install_cli_shim(repo_root: Path) -> None:
    """Copy the project launcher script to ``.venv/bin/backfield``."""
    source = cli_shim_source(repo_root)
    target = cli_shim_target(repo_root)
    if not source.is_file():
        raise FileNotFoundError(f"Missing CLI wrapper script: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    mode = target.stat().st_mode
    target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def cli_import_works(repo_root: Path) -> bool:
    python = venv_python(repo_root)
    if not python.is_file():
        return False
    result = subprocess.run(
        [str(python), "-c", "import backfield_cli"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _repair_cli_import(repo_root: Path, *, quiet: bool) -> None:
    if shutil.which("uv") is None:
        raise FileNotFoundError(
            "The Backfield CLI is not importable from .venv and `uv` was not found on PATH. "
            "Run `make bootstrap` from the repo root."
        )

    base_cmd = ["uv", "sync", "--all-packages"]
    if quiet:
        base_cmd.append("--quiet")

    logger.info("Repairing workspace Python tooling (uv sync --all-packages)...")
    subprocess.run(base_cmd, cwd=repo_root, check=True)

    if cli_import_works(repo_root):
        return

    reinstall_cmd = [
        *base_cmd,
        *[arg for pkg in _TOOLING_PACKAGES for arg in ("--reinstall-package", pkg)],
    ]
    logger.info("Reinstalling backfield-cli and backfield-db...")
    subprocess.run(reinstall_cmd, cwd=repo_root, check=True)

    if not cli_import_works(repo_root):
        raise RuntimeError(
            "Could not repair the Backfield CLI in .venv. "
            "Run `make bootstrap` from the repo root and retry."
        )


def ensure_host_python_tooling(repo_root: Path, *, quiet: bool = False) -> None:
    """Ensure ``.venv`` can import ``backfield_cli`` and expose the project launcher.

    Called from ``backfield init`` — repairs a stale editable install only when
    the import probe fails, then copies ``scripts/backfield`` into the venv.
    """
    if not cli_import_works(repo_root):
        _repair_cli_import(repo_root, quiet=quiet)

    install_cli_shim(repo_root)
