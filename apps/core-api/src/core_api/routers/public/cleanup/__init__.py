"""Preview cleanup API (`/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup`).

Routes here carry the `cleanup-preview` tag, so they stay out of the published consumer contract
(see `routers/public/openapi.py`). See `docs/plan/stylebook-cleanup-api.md`.
"""

from __future__ import annotations

from backfield_entities.cleanup.check_reads import (
    CheckListOut,
    CheckResultsPage,
    CheckRunOut,
)
from backfield_entities.cleanup.evidence import BatchEvidence, CanonicalEvidence, PairComparison
from backfield_entities.cleanup.export import CleanupExportPage
from fastapi import APIRouter

from core_api.routers.public.cleanup.capabilities import (
    CleanupCapabilitiesOut,
    get_cleanup_capabilities,
)
from core_api.routers.public.cleanup.checks import (
    get_cleanup_check_latest_run,
    get_cleanup_check_results,
    get_cleanup_checks,
    post_cleanup_check_run,
)
from core_api.routers.public.cleanup.evidence import (
    get_cleanup_compare,
    get_cleanup_evidence,
    post_cleanup_evidence,
)
from core_api.routers.public.cleanup.export import get_cleanup_export
from core_api.routers.public.openapi import CLEANUP_PREVIEW_TAG

router = APIRouter(
    prefix="/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup",
    tags=[CLEANUP_PREVIEW_TAG],
)

router.get("/capabilities", response_model=CleanupCapabilitiesOut)(get_cleanup_capabilities)
router.get("/{entity}/export", response_model=CleanupExportPage)(get_cleanup_export)
router.get("/{entity}/{canonical_id}/evidence", response_model=CanonicalEvidence)(
    get_cleanup_evidence
)
router.post("/{entity}/evidence", response_model=BatchEvidence)(post_cleanup_evidence)
router.get("/{entity}/{canonical_id}/compare/{other_id}", response_model=PairComparison)(
    get_cleanup_compare
)
router.get("/checks", response_model=CheckListOut)(get_cleanup_checks)
router.get("/checks/{check_id}/results", response_model=CheckResultsPage)(get_cleanup_check_results)
router.post("/checks/{check_id}/runs", response_model=CheckRunOut)(post_cleanup_check_run)
router.get("/checks/{check_id}/runs/latest", response_model=CheckRunOut)(
    get_cleanup_check_latest_run
)
