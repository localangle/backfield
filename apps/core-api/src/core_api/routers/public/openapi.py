"""Build the standalone consumer OpenAPI contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PUBLIC_PREFIX = "/public/v1"
PUBLIC_SCHEMA_PATH = f"{PUBLIC_PREFIX}/openapi.json"


def _schema_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            references.add(ref.rsplit("/", 1)[-1])
        for nested in value.values():
            references.update(_schema_references(nested))
    elif isinstance(value, list):
        for nested in value:
            references.update(_schema_references(nested))
    return references


def _reachable_schemas(paths: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    pending = list(_schema_references(paths))
    reachable: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reachable or name not in schemas:
            continue
        reachable.add(name)
        pending.extend(_schema_references(schemas[name]) - reachable)
    return {name: deepcopy(schemas[name]) for name in sorted(reachable)}


def build_public_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic, consumer-only OpenAPI document."""
    paths = schema.get("paths") or {}
    public_paths = {
        path: deepcopy(item)
        for path, item in paths.items()
        if isinstance(path, str)
        and path.startswith(PUBLIC_PREFIX)
        and path != PUBLIC_SCHEMA_PATH
    }
    sorted_paths = dict(sorted(public_paths.items()))
    source_components = schema.get("components") or {}
    source_schemas = source_components.get("schemas") or {}
    components = {
        "schemas": _reachable_schemas(sorted_paths, source_schemas),
        "securitySchemes": {
            "ProjectApiKey": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "Backfield project API key",
                "description": "Project-scoped Backfield API key.",
            }
        },
    }
    return {
        "openapi": schema.get("openapi", "3.1.0"),
        "info": {
            "title": "Backfield Public API",
            "version": "1.0.0",
            "description": "Stable consumer API for project-scoped Backfield data and runs.",
        },
        "servers": [
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
        ],
        "paths": sorted_paths,
        "components": components,
    }
