"""Tests for HTTP path-prefix stripping middleware."""

from __future__ import annotations

import pytest
from backfield_auth.path_prefix import (
    PathPrefixMiddleware,
    http_path_prefix_from_env,
    install_path_prefix,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def test_http_path_prefix_from_env_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKFIELD_HTTP_PATH_PREFIX", raising=False)
    assert http_path_prefix_from_env() == ""

    monkeypatch.setenv("BACKFIELD_HTTP_PATH_PREFIX", "/api/agate/")
    assert http_path_prefix_from_env() == "/api/agate"

    monkeypatch.setenv("BACKFIELD_HTTP_PATH_PREFIX", "api/stylebook")
    assert http_path_prefix_from_env() == "/api/stylebook"


def test_path_prefix_middleware_strips_prefix() -> None:
    async def echo(request: Request) -> JSONResponse:
        return JSONResponse({"path": request.url.path})

    inner = Starlette(routes=[Route("/health", echo), Route("/", echo)])
    app = PathPrefixMiddleware(inner, prefix="/api/agate")
    client = TestClient(app)
    assert client.get("/api/agate/health").json() == {"path": "/health"}
    assert client.get("/api/agate/").json() == {"path": "/"}
    # Unprefixed paths pass through unchanged (CDN is expected to send the prefix).
    assert client.get("/health").json() == {"path": "/health"}


def test_install_path_prefix_noops_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKFIELD_HTTP_PATH_PREFIX", raising=False)

    async def echo(request: Request) -> JSONResponse:
        return JSONResponse({"path": request.url.path})

    app = Starlette(routes=[Route("/health", echo)])
    assert install_path_prefix(app) == ""
    assert TestClient(app).get("/health").json() == {"path": "/health"}
