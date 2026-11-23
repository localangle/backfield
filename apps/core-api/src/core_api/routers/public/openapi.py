"""Build the standalone consumer OpenAPI contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PUBLIC_PREFIX = "/public/v1"
PUBLIC_SCHEMA_PATH = f"{PUBLIC_PREFIX}/openapi.json"
# Routes in preview carry this tag. They work and appear in the app's own schema, but stay out of
# the consumer contract until they graduate.
CLEANUP_PREVIEW_TAG = "cleanup-preview"
HIDDEN_PREVIEW_TAGS = frozenset({CLEANUP_PREVIEW_TAG})
_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


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


def _without_preview_operations(path_item: dict[str, Any]) -> dict[str, Any] | None:
    """Drop preview-tagged operations; return None when no operation is left on the path."""
    kept: dict[str, Any] = {}
    kept_any_operation = False
    for key, value in path_item.items():
        if key not in _HTTP_METHODS:
            kept[key] = value
            continue
        tags = set(value.get("tags") or []) if isinstance(value, dict) else set()
        if tags & HIDDEN_PREVIEW_TAGS:
            continue
        kept[key] = value
        kept_any_operation = True
    return kept if kept_any_operation else None


def build_public_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic, consumer-only OpenAPI document."""
    paths = schema.get("paths") or {}
    public_paths: dict[str, Any] = {}
    for path, item in paths.items():
        if not (
            isinstance(path, str) and path.startswith(PUBLIC_PREFIX) and path != PUBLIC_SCHEMA_PATH
        ):
            continue
        visible_item = _without_preview_operations(deepcopy(item))
        if visible_item is not None:
            public_paths[path] = visible_item
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
