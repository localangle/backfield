"""Integration-style tests for Stylebook API (no Docker)."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _load_stylebook_app():
    module_path = (
        Path(__file__).resolve().parents[1] / "apps" / "stylebook-api" / "src" / "api" / "main.py"
    )
    spec = spec_from_file_location("stylebook_api_main", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


app = _load_stylebook_app()


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_geocode_chicago_no_auth_when_token_unset(monkeypatch, client: TestClient):
    monkeypatch.delenv("SERVICE_API_TOKEN", raising=False)
    # Re-import verify path uses env at request time — reload app dependency
    r = client.post("/v1/geocode/resolve", json={"query": "Chicago, IL"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("lat") is not None
