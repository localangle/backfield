"""FastAPI router factory for shared health, readiness, and version endpoints."""

from __future__ import annotations

from collections.abc import Callable

from backfield_db.session import get_engine
from fastapi import APIRouter, Response
from sqlalchemy.engine import Engine

from backfield_auth.service_health import (
    evaluate_readiness,
    liveness_payload,
    readiness_payload,
    version_payload,
)


def create_health_router(
    service_name: str,
    *,
    include_redis: bool = True,
    engine_factory: Callable[[], Engine] | None = None,
) -> APIRouter:
    """Mount liveness, readiness, and version routes for a Backfield API service."""
    router = APIRouter(tags=["health"])
    _engine_factory = engine_factory or get_engine

    def _liveness() -> dict[str, str | bool]:
        return liveness_payload(service_name)

    @router.get("/health")
    def health() -> dict[str, str | bool]:
        return _liveness()

    @router.get("/healthz")
    def healthz() -> dict[str, str | bool]:
        return _liveness()

    @router.get("/readyz")
    def readyz(response: Response) -> dict[str, object]:
        report = evaluate_readiness(
            service_name,
            engine=_engine_factory(),
            include_redis=include_redis,
        )
        if not report.ok:
            response.status_code = 503
        return readiness_payload(report)

    @router.get("/version")
    def version() -> dict[str, str]:
        return version_payload(service_name)

    return router
