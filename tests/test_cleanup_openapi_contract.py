"""The committed cleanup contract matches the export and lists exactly the routes that are built."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_cleanup_openapi.py"
_SPEC = importlib.util.spec_from_file_location("export_cleanup_openapi", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
export_cleanup_openapi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(export_cleanup_openapi)

COMMITTED = Path(__file__).resolve().parents[1] / "docs" / "api" / "cleanup.openapi.json"
CLEANUP_PREFIX = "/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup"

EXPECTED_OPERATIONS = {
    ("get", "/candidates/{entity}"),
    ("get", "/candidates/{entity}/count"),
    ("get", "/candidates/{entity}/types"),
    ("get", "/candidates/{entity}/{candidate_id}/evidence"),
    ("get", "/capabilities"),
    ("get", "/checks"),
    ("get", "/checks/{check_id}/results"),
    ("post", "/checks/{check_id}/runs"),
    ("get", "/checks/{check_id}/runs/latest"),
    ("get", "/dismissals"),
    ("get", "/actions/{action_id}"),
    ("get", "/runs"),
    ("post", "/runs"),
    ("get", "/runs/{run_id}"),
    ("post", "/runs/{run_id}/close"),
    ("get", "/runs/{run_id}/actions"),
    ("post", "/{entity}/merges"),
    ("get", "/{entity}/{canonical_id}/resolution"),
    ("post", "/{entity}/evidence"),
    ("get", "/{entity}/export"),
    ("get", "/{entity}/integrity"),
    ("get", "/{entity}/{canonical_id}/compare/{other_id}"),
    ("get", "/{entity}/{canonical_id}/evidence"),
}


def _operations(document: dict) -> set[tuple[str, str]]:
    return {
        (method, path.removeprefix(CLEANUP_PREFIX))
        for path, item in document["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }


def test_cleanup_openapi_artifact_matches_export() -> None:
    assert COMMITTED.is_file(), f"missing committed OpenAPI artifact: {COMMITTED}"
    generated = export_cleanup_openapi.export_cleanup_openapi()
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    assert committed == generated, (
        "docs/api/cleanup.openapi.json is out of date; "
        "run: uv run python scripts/export_cleanup_openapi.py"
    )


def test_cleanup_contract_lists_exactly_the_built_routes() -> None:
    document = export_cleanup_openapi.export_cleanup_openapi()
    assert _operations(document) == EXPECTED_OPERATIONS
    assert all(path.startswith(CLEANUP_PREFIX) for path in document["paths"])
