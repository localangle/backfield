"""Structural checks for repository documentation links."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:")


def _documentation_files() -> list[Path]:
    files = [
        _REPO_ROOT / "README.md",
        _REPO_ROOT / "AGENTS.md",
        *(_REPO_ROOT / "docs").rglob("*.md"),
        *(_REPO_ROOT / ".cursor" / "skills").glob("*/SKILL.md"),
        *(_REPO_ROOT / ".cursor" / "rules").glob("*.mdc"),
    ]
    return sorted(path for path in files if path.is_file())


def _local_link_targets(path: Path) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    for raw_target in _MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
        target = raw_target.strip().strip("<>")
        if not target or target.startswith("#") or target.startswith(_EXTERNAL_PREFIXES):
            continue

        file_part = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not file_part:
            continue
        targets.append((target, (path.parent / file_part).resolve()))
    return targets


@pytest.mark.parametrize(
    "path",
    _documentation_files(),
    ids=lambda path: str(path.relative_to(_REPO_ROOT)),
)
def test_local_documentation_links_resolve(path: Path) -> None:
    missing: list[str] = []
    for target, resolved in _local_link_targets(path):
        if not resolved.is_relative_to(_REPO_ROOT):
            missing.append(f"{target} -> outside repository ({resolved})")
        elif not resolved.exists():
            missing.append(f"{target} -> {resolved.relative_to(_REPO_ROOT)}")

    message = f"{path.relative_to(_REPO_ROOT)} has broken local links:\n"
    assert not missing, message + "\n".join(missing)
