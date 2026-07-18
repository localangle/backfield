#!/usr/bin/env python3
"""Export the standalone Core API consumer contract."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "api" / "public.openapi.json"

# Importing Core API loads session signing; allow export without a live .env.
os.environ.setdefault("SESSION_SECRET", "openapi-export-session-secret")
os.environ.setdefault("SERVICE_API_TOKEN", "openapi-export")


def export_public_openapi(*, app: Any | None = None) -> dict[str, Any]:
    """Build the standalone public OpenAPI document from the Core API app."""
    from core_api.routers.public.openapi import build_public_openapi

    if app is None:
        # Import lazily so callers can supply a lightweight test application.
        from core_api.main import app as core_app

        app = core_app
    return build_public_openapi(app.openapi())


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
