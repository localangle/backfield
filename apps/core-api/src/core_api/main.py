"""Core API — shared domain endpoints (import, entities). Auth testing routes included."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from backfield_auth.health_router import create_health_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core_api.env_bootstrap import run_env_bootstrap_if_configured
from core_api.routers import admin_org as admin_org_router
from core_api.routers import auth as auth_router
from core_api.routers import bootstrap as bootstrap_router
from core_api.routers import credentials as credentials_router
from core_api.routers import legacy_public as legacy_public_router
from core_api.routers import me as me_router
from core_api.routers import org_ai_models as org_ai_models_router
from core_api.routers import org_integration_secrets as org_integration_secrets_router
from core_api.routers import project_ai_models as project_ai_models_router
from core_api.routers import secure as secure_router
from core_api.routers.public import router as public_v1_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_env_bootstrap_if_configured()
    yield


app = FastAPI(title="Backfield Core API", version="0.1.0", lifespan=lifespan)

UI_ORIGINS = os.getenv("UI_ORIGINS", "http://localhost:5173,http://localhost:5175").split(",")
ALLOWED: list[str] = []
for origin in UI_ORIGINS:
    o = origin.strip()
    if not o:
        continue
    ALLOWED.append(o)
    if o.startswith("http://localhost") or o.startswith("http://127.0.0.1"):
        if ":5173" in o:
            ALLOWED.append(o.replace("localhost", "127.0.0.1"))
            ALLOWED.append(o.replace("127.0.0.1", "localhost"))
        if ":5175" in o:
            ALLOWED.append(o.replace("localhost", "127.0.0.1"))
            ALLOWED.append(o.replace("127.0.0.1", "localhost"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Cookie"],
    expose_headers=["Set-Cookie"],
)

app.include_router(legacy_public_router.router, prefix="/v1")
app.include_router(public_v1_router, prefix="/public/v1")
app.include_router(secure_router.router, prefix="/v1")
app.include_router(bootstrap_router.router, prefix="/v1")
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
