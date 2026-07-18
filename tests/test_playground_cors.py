import pytest
from core_api.main import app as core_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from stylebook_api.main import app as stylebook_app


@pytest.mark.parametrize("app", [core_app, stylebook_app])
def test_tenant_playground_origin_is_allowed(app: FastAPI) -> None:
    response = TestClient(app).options(
        "/",
        headers={
            "Origin": "https://playground.example-newsroom.backfield.news",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://playground.example-newsroom.backfield.news"
    )
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize("app", [core_app, stylebook_app])
def test_unrelated_playground_origin_is_rejected(app: FastAPI) -> None:
    response = TestClient(app).options(
        "/",
        headers={
            "Origin": "https://playground.attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
