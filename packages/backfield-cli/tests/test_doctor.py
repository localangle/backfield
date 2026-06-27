"""Tests for backfield doctor."""

from __future__ import annotations

from pathlib import Path

from backfield_cli import doctor


def test_run_checks_reports_missing_repo(tmp_path: Path) -> None:
    _repo_root, results = doctor.run_checks(tmp_path)
    assert _repo_root is None
    assert results[0].name == "repo root"
    assert results[0].ok is False


def test_run_checks_passes_in_real_repo() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    found_root, results = doctor.run_checks(repo_root)
    assert found_root == repo_root
    names = {result.name for result in results}
    assert "repo root" in names
    assert "uv" in names
    assert "docker" in names
    assert ".venv" in names
    assert "backfield_cli import" in names
    assert "compose file" in names
    assert "project launcher" in names
