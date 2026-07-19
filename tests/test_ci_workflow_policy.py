"""Guardrails so forks get useful CI without private credentials or publishing."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CI = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
_RELEASE = (_REPO_ROOT / ".github" / "workflows" / "release-artifacts.yml").read_text(
    encoding="utf-8"
)


def test_ci_runs_credential_free_smoke_for_all_events() -> None:
    assert "smoke-fast:" in _CI
    assert "make smoke-fast" in _CI


def test_provider_smoke_is_gated_to_canonical_trusted_events() -> None:
    assert "smoke-handoff:" in _CI
    assert "github.repository == 'localangle/backfield'" in _CI
    assert "OPENAI_API_KEY" in _CI
    assert "ANTHROPIC_API_KEY" in _CI


def test_publish_jobs_require_canonical_repo_and_configuration() -> None:
    assert "github.repository == 'localangle/backfield'" in _CI
    assert "vars.AWS_ARTIFACT_PUBLISHER_ROLE_ARN != ''" in _CI
    assert "vars.BACKFIELD_ARTIFACT_BUCKET != ''" in _CI
    assert "github.repository == 'localangle/backfield'" in _RELEASE


def test_ci_sets_default_read_permissions() -> None:
    assert "permissions:" in _CI
    assert "contents: read" in _CI


def test_ci_pins_third_party_actions_to_shas() -> None:
    for line in _CI.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- uses:"):
            continue
        action = stripped.removeprefix("- uses:").strip()
        if action.startswith("./"):
            continue
        assert "@" in action, action
        pin = action.rsplit("@", 1)[1].split()[0]
        assert not pin.startswith("v"), f"mutable tag not allowed: {action}"
        assert len(pin) >= 40, f"expected commit SHA pin: {action}"


def test_publish_packages_all_three_ui_archives() -> None:
    assert "apps/api-playground/dist" in _CI
    assert "dist-artifacts/api-playground.tar.gz" in _CI
    assert "--api-playground dist-artifacts/api-playground.tar.gz" in _CI
    assert "--agate-ui dist-artifacts/agate-ui.tar.gz" in _CI
    assert "--stylebook-ui dist-artifacts/stylebook-ui.tar.gz" in _CI
