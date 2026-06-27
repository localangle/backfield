"""Keep the shared workspace venv able to import the operator CLI."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_TOOLING_PACKAGES = ("backfield-cli", "backfield-db")


def venv_python(repo_root: Path) -> Path:
    if sys.platform == "win32":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


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


def ensure_host_python_tooling(repo_root: Path, *, quiet: bool = False) -> None:
    """Ensure repo-root ``.venv`` can import ``backfield_cli``.

    A partial ``uv sync`` from a workspace member (or a stale editable install
    missing ``_editable_impl_backfield_cli.pth``) can leave the ``backfield``
    console script installed while the package is no longer importable. ``uv
    sync --all-packages`` alone does not always repair that state; reinstall the
    CLI packages when the import probe fails.
    """
    if cli_import_works(repo_root):
        return
    if shutil.which("uv") is None:
        raise FileNotFoundError(
            "The Backfield CLI is not importable from .venv and `uv` was not found on PATH. "
            "Run `make bootstrap` from the repo root."
        )

    cmd = [
        "uv",
        "sync",
        "--all-packages",
        *[arg for pkg in _TOOLING_PACKAGES for arg in ("--reinstall-package", pkg)],
    ]
    if quiet:
        cmd.append("--quiet")

    logger.info("Repairing workspace Python tooling (uv sync --all-packages)...")
    subprocess.run(cmd, cwd=repo_root, check=True)

    if not cli_import_works(repo_root):
        raise RuntimeError(
            "Could not repair the Backfield CLI in .venv. "
            "Run `make bootstrap` from the repo root and retry."
        )
