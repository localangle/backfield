import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _reload_apps_with_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> tuple[FastAPI, FastAPI]:
    for key, value in env.items():
        if value == "":
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    # Ensure defaults are empty when tests omit the optional regex override.
    if "PLAYGROUND_ORIGIN_REGEX" not in env:
        monkeypatch.setenv("PLAYGROUND_ORIGIN_REGEX", "")

    import core_api.main as core_main
    import stylebook_api.main as stylebook_main

    core_main = importlib.reload(core_main)
    stylebook_main = importlib.reload(stylebook_main)
    return core_main.app, stylebook_main.app


@pytest.fixture
def playground_apps(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, FastAPI]:
    return _reload_apps_with_env(
        monkeypatch,
        PLAYGROUND_ORIGIN="https://playground.example-newsroom.backfield.news",
        PLAYGROUND_ORIGIN_REGEX="",
    )


@pytest.mark.parametrize("app_index", [0, 1])
def test_exact_playground_origin_is_allowed(
    playground_apps: tuple[FastAPI, FastAPI],
    app_index: int,
) -> None:
    app = playground_apps[app_index]
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


@pytest.mark.parametrize("app_index", [0, 1])
def test_foreign_tenant_playground_origin_is_rejected(
    playground_apps: tuple[FastAPI, FastAPI],
    app_index: int,
) -> None:
    app = playground_apps[app_index]
    response = TestClient(app).options(
        "/",
        headers={
            "Origin": "https://playground.other-newsroom.backfield.news",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("app_index", [0, 1])
def test_unrelated_playground_origin_is_rejected(
    playground_apps: tuple[FastAPI, FastAPI],
    app_index: int,
) -> None:
    app = playground_apps[app_index]
    response = TestClient(app).options(
        "/",
        headers={
            "Origin": "https://playground.attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("app_index", [0, 1])
def test_localhost_playground_origin_remains_allowed_without_regex(
    monkeypatch: pytest.MonkeyPatch,
    app_index: int,
) -> None:
    apps = _reload_apps_with_env(
        monkeypatch,
        PLAYGROUND_ORIGIN="",
        PLAYGROUND_ORIGIN_REGEX="",
        UI_ORIGINS="http://localhost:5173,http://localhost:5175,http://localhost:5176",
        UI_ORIGIN="http://localhost:5175",
    )
    app = apps[app_index]
    response = TestClient(app).options(
        "/",
        headers={
            "Origin": "http://localhost:5176",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5176"
    assert response.headers["access-control-allow-credentials"] == "true"
