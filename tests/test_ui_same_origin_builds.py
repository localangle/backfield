"""Same-origin UI production build contract tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

_UI_APPS: tuple[tuple[str, Path], ...] = (
    ("agate-ui", _REPO_ROOT / "apps" / "agate-ui"),
    ("stylebook-ui", _REPO_ROOT / "apps" / "stylebook-ui"),
)

_FORBIDDEN_BAKED_HOST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://localhost:\d+"),
    re.compile(r"https?://127\.0\.0\.1:\d+"),
    re.compile(r"https?://flowbuilder[^\"'\s]*"),
)

_EXPECTED_RELATIVE_BASES: tuple[str, ...] = (
    "/api/agate",
    "/api/stylebook",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(("name", "app_dir"), _UI_APPS)
def test_ui_has_env_production_with_relative_bases(name: str, app_dir: Path) -> None:
    env_path = app_dir / ".env.production"
    assert env_path.is_file(), f"{name} missing .env.production"
    text = _read(env_path)
    assert "/api/agate" in text
    assert "/api/stylebook" in text
    assert "VITE_AUTH_API_BASE=" in text


def test_agate_ui_env_development_sets_stylebook_origin() -> None:
    env_path = _REPO_ROOT / "apps" / "agate-ui" / ".env.development"
    assert env_path.is_file()
    text = _read(env_path)
    assert "VITE_STYLEBOOK_UI_ORIGIN=http://localhost:5175" in text.replace(" ", "")


def test_stylebook_ui_env_development_sets_agate_origin() -> None:
    env_path = _REPO_ROOT / "apps" / "stylebook-ui" / ".env.development"
    assert env_path.is_file()
    text = _read(env_path)
    assert "VITE_AGATE_UI_ORIGIN=http://localhost:5173" in text.replace(" ", "")


@pytest.mark.parametrize(("name", "app_dir"), _UI_APPS)
def test_ui_app_makefile_documents_same_origin_build(name: str, app_dir: Path) -> None:
    makefile = app_dir / "Makefile"
    if not makefile.is_file():
        pytest.skip(f"{name} has no app Makefile")
    text = _read(makefile)
    assert "build-prd" in text
    assert "flowbuilder" not in text.lower()


def test_root_makefile_declares_ui_build_targets() -> None:
    makefile = _read(_REPO_ROOT / "Makefile")
    assert "agate-ui-build:" in makefile
    assert "stylebook-ui-build:" in makefile
    assert "ui-build:" in makefile


def test_agate_ui_docs_have_no_legacy_flowbuilder_paths() -> None:
    for path in (_REPO_ROOT / "apps" / "agate-ui").glob("*"):
        if path.suffix not in {".md", ""} and path.name != "Makefile":
            continue
        if path.name == "Makefile" or path.suffix == ".md":
            text = _read(path)
            assert "flowbuilder-ui" not in text
            assert "build-flowbuilder-ui-prd" not in text


def _dist_asset_files(dist_dir: Path) -> list[Path]:
    assets = dist_dir / "assets"
    if assets.is_dir():
        return sorted(p for p in assets.iterdir() if p.suffix == ".js")
    return sorted(p for p in dist_dir.rglob("*.js") if p.is_file())


@pytest.mark.parametrize(("name", "app_dir"), _UI_APPS)
def test_ui_prod_bundle_has_no_baked_absolute_api_hosts(name: str, app_dir: Path) -> None:
    dist_dir = app_dir / "dist"
    if not dist_dir.is_dir():
        pytest.skip(f"run make {name}-build first")

    js_files = _dist_asset_files(dist_dir)
    assert js_files, f"{name} dist has no JS assets"

    for js_path in js_files:
        content = js_path.read_text(encoding="utf-8", errors="replace")
        for pattern in _FORBIDDEN_BAKED_HOST_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"{name} bundle {js_path.name} bakes absolute host {match.group(0)!r}"
            )


@pytest.mark.parametrize(("name", "app_dir"), _UI_APPS)
def test_ui_prod_bundle_uses_relative_api_bases(name: str, app_dir: Path) -> None:
    dist_dir = app_dir / "dist"
    if not dist_dir.is_dir():
        pytest.skip(f"run make {name}-build first")

    js_files = _dist_asset_files(dist_dir)
    assert js_files
    combined = "\n".join(
        js_path.read_text(encoding="utf-8", errors="replace") for js_path in js_files
    )
    for base in _EXPECTED_RELATIVE_BASES:
        assert base in combined, f"{name} bundle missing relative base {base!r}"
