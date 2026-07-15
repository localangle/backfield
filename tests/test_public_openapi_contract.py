"""Committed public OpenAPI artifact must match the export helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_public_openapi.py"
_SPEC = importlib.util.spec_from_file_location("export_public_openapi", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
export_public_openapi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(export_public_openapi)

COMMITTED = Path(__file__).resolve().parents[1] / "docs" / "api" / "public.openapi.json"


def test_public_openapi_artifact_matches_export() -> None:
    assert COMMITTED.is_file(), f"missing committed OpenAPI artifact: {COMMITTED}"
    generated = export_public_openapi.export_public_openapi()
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    assert committed == generated, (
        "docs/api/public.openapi.json is out of date; "
        "run: uv run python scripts/export_public_openapi.py"
    )


def test_public_openapi_paths_are_public_only() -> None:
    document = export_public_openapi.export_public_openapi()
    paths = document.get("paths") or {}
    assert paths, "expected at least one /public/v1 path"
    assert all(path.startswith("/public/v1") for path in paths)
