"""Shared liveness, readiness, and version helpers for Backfield HTTP services."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import Engine

CheckStatus = Literal["ok", "skipped", "error"]


@dataclass(frozen=True)
class BuildInfo:
    service: str
    version: str
    git_sha: str
    build_time: str


@dataclass(frozen=True)
class ReadinessReport:
    ok: bool
    service: str
    checks: dict[str, CheckStatus | str]


def _env_first(*names: str, default: str) -> str:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return default


def read_build_info(service_name: str) -> BuildInfo:
    """Read build metadata from environment with safe defaults."""
    return BuildInfo(
        service=service_name,
        version=_env_first("APP_VERSION", "BACKFIELD_APP_VERSION", default="0.1.0"),
        git_sha=_env_first("GIT_SHA", "BACKFIELD_GIT_SHA", default="unknown"),
        build_time=_env_first("BUILD_TIME", "BACKFIELD_BUILD_TIME", default="unknown"),
    )


def liveness_payload(service_name: str) -> dict[str, str | bool]:
    return {"ok": True, "service": service_name}


def version_payload(service_name: str) -> dict[str, str]:
    info = read_build_info(service_name)
    return {
        "service": info.service,
        "version": info.version,
        "git_sha": info.git_sha,
        "build_time": info.build_time,
    }


def check_database(engine: Engine) -> CheckStatus | str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 — readiness must not raise
        return f"error: {exc}"


def check_redis(redis_url: str | None = None) -> CheckStatus | str:
    url = (redis_url or os.environ.get("REDIS_URL") or "redis://localhost:6379/0").strip()
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        try:
            client.ping()
        finally:
            client.close()
        return "ok"
    except Exception as exc:  # noqa: BLE001 — readiness must not raise
        return f"error: {exc}"


def evaluate_readiness(
    service_name: str,
    *,
    engine: Engine,
    include_redis: bool,
    redis_url: str | None = None,
) -> ReadinessReport:
    checks: dict[str, CheckStatus | str] = {}

    db_status = check_database(engine)
    checks["database"] = db_status

    if include_redis:
        checks["redis"] = check_redis(redis_url)
    else:
        checks["redis"] = "skipped"

    ok = all(status == "ok" or status == "skipped" for status in checks.values())
    return ReadinessReport(ok=ok, service=service_name, checks=checks)


def readiness_payload(report: ReadinessReport) -> dict[str, object]:
    return {
        "ok": report.ok,
        "service": report.service,
        "checks": report.checks,
    }
