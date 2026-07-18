"""Public run trigger and status routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.runs.create import create_public_run
from core_api.routers.public.runs.detail import get_public_run
from core_api.routers.public.runs.schemas import PublicRunOut

router = APIRouter(prefix="/projects/{project_slug}/runs", tags=["public-runs"])

_RUN_POST_HEADERS = {
    "Location": {"description": "URL of the created run.", "schema": {"type": "string"}},
    "Retry-After": {
        "description": "Initial polling delay in seconds.",
        "schema": {"type": "integer"},
    },
    "Idempotency-Replayed": {
        "description": "Present with value `true` only when an existing run was returned.",
        "schema": {"type": "string"},
    },
}
_RUN_GET_HEADERS = {
    "Retry-After": {
        "description": "Polling delay in seconds while the run is pending or running.",
        "schema": {"type": "integer"},
    }
}

router.post(
    "",
    response_model=PublicRunOut,
    status_code=202,
    responses={202: {"headers": _RUN_POST_HEADERS}},
)(create_public_run)
router.get(
    "/{run_id}",
    response_model=PublicRunOut,
    responses={200: {"headers": _RUN_GET_HEADERS}},
)(get_public_run)
