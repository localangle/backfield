"""Shared credential resolution for CLI commands."""

from __future__ import annotations

from pathlib import Path


def resolve_admin_password(
    *,
    password: str | None,
    password_file: str | None,
    env_password: str | None = None,
) -> str:
    if password_file:
        return Path(password_file).read_text(encoding="utf-8").strip()
    if password is not None and password != "":
        return password
    if env_password is not None and env_password != "":
        return env_password
    raise ValueError(
        "admin password is required (--admin-password, --admin-password-file, or env)"
    )
