"""Preview cleanup API (`/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup`).

Routes here carry the `cleanup-preview` tag, so they stay out of the published consumer contract
(see `routers/public/openapi.py`). See `docs/plan/stylebook-cleanup-api.md`.
"""

from __future__ import annotations

from fastapi import APIRouter

from core_api.routers.public.cleanup.capabilities import (
    CleanupCapabilitiesOut,
    get_cleanup_capabilities,
)
from core_api.routers.public.openapi import CLEANUP_PREVIEW_TAG

router = APIRouter(
    prefix="/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup",
    tags=[CLEANUP_PREVIEW_TAG],
)

router.get("/capabilities", response_model=CleanupCapabilitiesOut)(get_cleanup_capabilities)
