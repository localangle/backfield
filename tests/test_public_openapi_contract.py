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
    assert "/public/v1/openapi.json" not in paths


def test_public_openapi_is_stable_consumer_contract() -> None:
    document = export_public_openapi.export_public_openapi()
    assert document == export_public_openapi.export_public_openapi()
    assert document["info"]["title"] == "Backfield Public API"
    assert document["servers"] == [
        {
            "url": "https://api.{organization_slug}.backfield.news",
            "description": "Production",
            "variables": {
                "organization_slug": {
                    "default": "your-organization",
                    "description": "Backfield organization slug.",
                }
            },
        },
        {"url": "http://127.0.0.1:8004", "description": "Local development"},
    ]
    assert document["components"]["securitySchemes"] == {
        "ProjectApiKey": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Backfield project API key",
            "description": "Project-scoped Backfield API key.",
        }
    }

    forbidden_params = {
        "meta_type",
        "meta_category",
        "exclude_meta_type",
        "exclude_meta_category",
        "section",
        "source",
    }
    for path_item in document["paths"].values():
        for operation in path_item.values():
            assert operation["security"] == [{"ProjectApiKey": []}]
            assert not any(
                parameter["in"] == "header" and parameter["name"].lower() == "authorization"
                for parameter in operation.get("parameters", [])
            )
            assert forbidden_params.isdisjoint(
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "query"
            )
            for status_code in ("400", "401", "403", "404", "422", "503"):
                response = operation["responses"][status_code]
                assert "X-Request-ID" in response["headers"]
                schema = response["content"]["application/json"]["schema"]
                assert schema["$ref"].endswith("/PublicErrorResponse")

    component_names = set(document["components"]["schemas"])
    assert "HTTPValidationError" not in component_names


def test_public_openapi_removes_unreachable_component_schemas() -> None:
    source = export_public_openapi.export_public_openapi()
    source["components"]["schemas"]["InternalOnly"] = {
        "type": "object",
        "properties": {"secret": {"type": "string"}},
    }

    class StubApp:
        def openapi(self) -> dict[str, object]:
            return source

    document = export_public_openapi.export_public_openapi(app=StubApp())
    assert "InternalOnly" not in document["components"]["schemas"]
