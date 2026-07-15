"""Authentication implementations must live in backfield-auth."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN = (
    "URLSafeTimedSerializer",
    "dev-secret-key",
)


def test_no_duplicate_session_auth_outside_backfield_auth() -> None:
    roots = [
        _REPO_ROOT / "packages" / "backfield-agate" / "src",
        _REPO_ROOT / "apps",
    ]
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            if "backfield_auth" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in _FORBIDDEN):
                offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []
