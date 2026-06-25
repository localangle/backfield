"""Public run trigger and status routes."""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.runs.create import create_public_run
from core_api.routers.public.runs.detail import get_public_run
from core_api.routers.public.runs.schemas import PublicRunOut

router = APIRouter(prefix="/projects/{project_slug}/runs", tags=["public-runs"])

router.post("", response_model=PublicRunOut)(create_public_run)
router.get("/{run_id}", response_model=PublicRunOut)(get_public_run)
