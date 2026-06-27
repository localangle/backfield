"""Unit tests for shared service health, readiness, and version helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from backfield_auth.health_router import create_health_router
from backfield_auth.service_health import (
    check_database,
    check_redis,
    evaluate_readiness,
    liveness_payload,
    read_build_info,
    version_payload,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def test_read_build_info_defaults() -> None:
    info = read_build_info("agate-api")
    assert info.service == "agate-api"
    assert info.version == "0.1.0"
    assert info.git_sha == "unknown"
    assert info.build_time == "unknown"


def test_read_build_info_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v1.2.3")
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("BUILD_TIME", "2026-06-26T00:00:00Z")
    info = read_build_info("core-api")
    assert info.version == "v1.2.3"
    assert info.git_sha == "abc123"
    assert info.build_time == "2026-06-26T00:00:00Z"


def test_liveness_and_version_payload() -> None:
    assert liveness_payload("stylebook-api") == {"ok": True, "service": "stylebook-api"}
    version = version_payload("stylebook-api")
    assert set(version) == {"service", "version", "git_sha", "build_time"}
    assert version["service"] == "stylebook-api"


def test_check_database_ok(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'health.db'}")
    assert check_database(engine) == "ok"


def test_check_database_error() -> None:
    engine = create_engine("sqlite:////nonexistent/path/health.db")
    result = check_database(engine)
    assert isinstance(result, str)
    assert result.startswith("error:")


def test_evaluate_readiness_skips_redis(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ready.db'}")
    report = evaluate_readiness("core-api", engine=engine, include_redis=False)
    assert report.ok is True
    assert report.checks["database"] == "ok"
    assert report.checks["redis"] == "skipped"


def test_evaluate_readiness_fails_when_database_down() -> None:
    engine = create_engine("sqlite:////nonexistent/path/ready.db")
    report = evaluate_readiness("core-api", engine=engine, include_redis=False)
    assert report.ok is False
    assert str(report.checks["database"]).startswith("error:")


def test_evaluate_readiness_fails_when_redis_down(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ready-redis.db'}")
    monkeypatch.setattr(
        "backfield_auth.service_health.check_redis",
        lambda redis_url=None: "error: connection refused",
    )
    report = evaluate_readiness("agate-api", engine=engine, include_redis=True)
    assert report.ok is False
    assert report.checks["redis"] == "error: connection refused"


def test_check_redis_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = MagicMock()
    monkeypatch.setattr("redis.from_url", lambda *args, **kwargs: mock_client)
    assert check_redis("redis://example:6379/0") == "ok"
    mock_client.ping.assert_called_once()
    mock_client.close.assert_called_once()


def _sqlite_engine_factory(path) -> Engine:
    return create_engine(f"sqlite:///{path}")


def test_health_router_endpoints(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "router.db"
    monkeypatch.setenv("APP_VERSION", "v9.9.9")
    monkeypatch.setattr(
        "backfield_auth.service_health.check_redis",
        lambda redis_url=None: "ok",
    )

    app = FastAPI()
    app.include_router(
        create_health_router(
            "test-api",
            include_redis=True,
            engine_factory=lambda: _sqlite_engine_factory(db_path),
        )
    )
    client = TestClient(app)

    assert client.get("/health").json() == {"ok": True, "service": "test-api"}
    assert client.get("/healthz").json() == {"ok": True, "service": "test-api"}

    ready = client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert body["ok"] is True
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"

    version = client.get("/version").json()
    assert version["service"] == "test-api"
    assert version["version"] == "v9.9.9"
    assert version["git_sha"] == "unknown"
    assert version["build_time"] == "unknown"


def test_health_router_readyz_returns_503_when_not_ready(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "router-not-ready.db"
    monkeypatch.setattr(
        "backfield_auth.service_health.check_redis",
        lambda redis_url=None: "error: down",
    )

    app = FastAPI()
    app.include_router(
        create_health_router(
            "test-api",
            include_redis=True,
            engine_factory=lambda: _sqlite_engine_factory(db_path),
        )
    )
    client = TestClient(app)

    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["ok"] is False
