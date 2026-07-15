#!/usr/bin/env python3
"""Export the Core API ``/public/v1`` OpenAPI document.

Writes ``docs/api/public.openapi.json`` (paths filtered to the public namespace).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "api" / "public.openapi.json"
PUBLIC_PREFIX = "/public/v1"

# Importing Core API loads session signing; allow export without a live .env.
os.environ.setdefault("SESSION_SECRET", "openapi-export-session-secret")
os.environ.setdefault("SERVICE_API_TOKEN", "openapi-export")


def filter_public_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` containing only ``/public/v1`` paths."""
    filtered = dict(schema)
    paths = schema.get("paths") or {}
    public_paths = {
        path: item
        for path, item in paths.items()
        if isinstance(path, str) and path.startswith(PUBLIC_PREFIX)
    }
    filtered["paths"] = dict(sorted(public_paths.items()))
    filtered["info"] = {
        **(schema.get("info") or {}),
        "title": "Backfield Public API",
        "description": (
            "Consumer-facing routes under /public/v1, extracted from Core API OpenAPI."
        ),
    }
    return filtered


def export_public_openapi(*, app: Any | None = None) -> dict[str, Any]:
    """Build the filtered public OpenAPI document from the Core API app."""
    if app is None:
        from core_api.main import app as core_app

        app = core_app
    return filter_public_openapi(app.openapi())


def write_public_openapi(output: Path = DEFAULT_OUTPUT, *, app: Any | None = None) -> Path:
    document = export_public_openapi(app=app)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    output = Path(args[0]) if args else DEFAULT_OUTPUT
    path = write_public_openapi(output)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
