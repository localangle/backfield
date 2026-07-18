"""Core API — shared domain endpoints (import, entities). Auth testing routes included."""

from __future__ import annotations

import os

from backfield_auth.health_router import create_health_router
from backfield_auth.request_logging_middleware import RequestLoggingMiddleware
from backfield_auth.structured_logging import configure_structured_logging
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from core_api.routers import admin_org as admin_org_router
from core_api.routers import auth as auth_router
from core_api.routers import credentials as credentials_router
from core_api.routers import legacy_public as legacy_public_router
from core_api.routers import me as me_router
from core_api.routers import org_ai_models as org_ai_models_router
from core_api.routers import org_integration_secrets as org_integration_secrets_router
from core_api.routers import project_ai_models as project_ai_models_router
from core_api.routers import secure as secure_router
from core_api.routers.public import router as public_v1_router
from core_api.routers.public.errors import (
    public_http_exception_handler,
    public_validation_exception_handler,
)
from core_api.routers.public.openapi import build_public_openapi

configure_structured_logging("core-api")


app = FastAPI(title="Backfield Core API", version="0.1.0")

UI_ORIGINS = os.getenv(
    "UI_ORIGINS",
    "http://localhost:5173,http://localhost:5175,http://localhost:5176",
).split(",")
PLAYGROUND_ORIGIN = os.getenv(
    "PLAYGROUND_ORIGIN",
    "",
)
PLAYGROUND_ORIGIN_REGEX = os.getenv(
    "PLAYGROUND_ORIGIN_REGEX",
    r"https://playground\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.backfield\.news",
).strip()
ALLOWED: list[str] = []
for origin in [*UI_ORIGINS, PLAYGROUND_ORIGIN]:
    o = origin.strip()
    if not o:
        continue
    ALLOWED.append(o)
    if o.startswith("http://localhost") or o.startswith("http://127.0.0.1"):
        ALLOWED.append(o.replace("localhost", "127.0.0.1"))
        ALLOWED.append(o.replace("127.0.0.1", "localhost"))

ALLOWED = list(dict.fromkeys(ALLOWED))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED or ["http://localhost:5173"],
    allow_origin_regex=PLAYGROUND_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=[
        "Set-Cookie",
        "X-Request-ID",
        "Location",
        "Retry-After",
        "Idempotency-Replayed",
        "RateLimit-Limit",
        "RateLimit-Remaining",
        "RateLimit-Reset",
    ],
)
app.add_middleware(RequestLoggingMiddleware, service_name="core-api")
app.add_exception_handler(HTTPException, public_http_exception_handler)
app.add_exception_handler(RequestValidationError, public_validation_exception_handler)


@app.get("/public/v1/openapi.json", include_in_schema=False)
def public_openapi() -> dict[str, object]:
    """Serve the standalone public API contract without authentication."""
    return build_public_openapi(app.openapi())

app.include_router(legacy_public_router.router, prefix="/v1")
app.include_router(public_v1_router, prefix="/public/v1")
app.include_router(secure_router.router, prefix="/v1")
app.include_router(admin_org_router.router, prefix="/v1")
app.include_router(org_ai_models_router.router, prefix="/v1")
app.include_router(org_integration_secrets_router.router, prefix="/v1")
app.include_router(credentials_router.router, prefix="/v1")
app.include_router(project_ai_models_router.router, prefix="/v1")
app.include_router(me_router.router, prefix="/v1")
app.include_router(auth_router.router, prefix="/v1")
app.include_router(create_health_router("core-api", include_redis=True))


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Backfield Core API", "version": "0.1.0"}
