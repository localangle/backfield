"""Every keyed cleanup route needs the cleanup:read scope."""

from __future__ import annotations

from tests.core_api.cleanup_fixtures import CLEANUP_BASE, create_cleanup_key

SCHEMA_BASE = "/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup"


def _concrete_url(schema_path: str) -> str:
    path = schema_path.replace(SCHEMA_BASE, CLEANUP_BASE)
    for placeholder, value in (
        ("{entity}", "locations"),
        ("{check_id}", "any-check"),
        ("{canonical_id}", "1"),
        ("{other_id}", "2"),
        ("{candidate_id}", "1"),
    ):
        path = path.replace(placeholder, value)
    return path


def test_every_cleanup_route_requires_the_cleanup_read_scope(cleanup_client, cleanup_world) -> None:
    allowed = create_cleanup_key(cleanup_client)
    without_scope = create_cleanup_key(cleanup_client, scopes=["read"])
    schema = cleanup_client.get(f"{CLEANUP_BASE}/openapi.json", headers=allowed).json()
    assert len(schema["paths"]) >= 15

    for schema_path, methods in schema["paths"].items():
        for method in methods:
            response = cleanup_client.request(
                method.upper(), _concrete_url(schema_path), headers=without_scope, json={}
            )
            assert response.status_code == 403, (method, schema_path, response.status_code)
