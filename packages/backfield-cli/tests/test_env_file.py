"""Tests for repo-root .env helpers."""

from __future__ import annotations

import stat

from backfield_cli.env_file import (
    ensure_repo_env_file,
    env_permissions_are_private,
    read_env_values,
    write_env_values,
)


def test_ensure_repo_env_file_generates_missing_secrets(tmp_path) -> None:
    repo_root = tmp_path
    (repo_root / ".env.example").write_text(
        "# example\nMASTER_ENCRYPTION_KEY=\nSESSION_SECRET=\n",
        encoding="utf-8",
    )

    report = ensure_repo_env_file(repo_root)

    assert report.created_env_file is True
    assert set(report.generated_keys) == {"MASTER_ENCRYPTION_KEY", "SESSION_SECRET"}
    values = read_env_values(repo_root / ".env")
    assert values["MASTER_ENCRYPTION_KEY"]
    assert values["SESSION_SECRET"]
    mode = stat.S_IMODE((repo_root / ".env").stat().st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0
    assert env_permissions_are_private(repo_root / ".env") is True


def test_ensure_repo_env_file_preserves_existing_secrets(tmp_path) -> None:
    repo_root = tmp_path
    env_path = repo_root / ".env"
    env_path.write_text(
        "MASTER_ENCRYPTION_KEY=existing-key\nSESSION_SECRET=existing-secret\n",
        encoding="utf-8",
    )

    report = ensure_repo_env_file(repo_root)

    assert report.created_env_file is False
    assert report.generated_keys == ()
    values = read_env_values(env_path)
    assert values["MASTER_ENCRYPTION_KEY"] == "existing-key"
    assert values["SESSION_SECRET"] == "existing-secret"


def test_write_env_values_updates_existing_keys(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# header\nMASTER_ENCRYPTION_KEY=old\nOTHER=value\n",
        encoding="utf-8",
    )

    write_env_values(env_path, {"MASTER_ENCRYPTION_KEY": "new"})

    text = env_path.read_text(encoding="utf-8")
    assert "MASTER_ENCRYPTION_KEY=new" in text
    assert "OTHER=value" in text
    assert "MASTER_ENCRYPTION_KEY=old" not in text
