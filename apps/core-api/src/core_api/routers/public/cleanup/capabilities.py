"""GET .../cleanup/capabilities: what this key can do on the preview cleanup surface."""

from __future__ import annotations

from backfield_auth.gate import SCOPE_CLEANUP_APPLY, SCOPE_READ
from fastapi import Depends
from pydantic import BaseModel

from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    require_cleanup_read,
)

CLEANUP_CONTRACT_VERSION = "preview-1"


class CleanupCapabilitiesOut(BaseModel):
    contract_version: str
    stylebook_slug: str
    scopes: list[str]
    can_apply: bool


def get_cleanup_capabilities(
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
) -> CleanupCapabilitiesOut:
    """Return the preview contract version and what the calling key may do."""
    if context.auth["type"] == "service":
        scopes = [SCOPE_READ]
        can_apply = True
    else:
        scopes = list(context.auth.get("scopes") or [])
        can_apply = SCOPE_CLEANUP_APPLY in scopes
    return CleanupCapabilitiesOut(
        contract_version=CLEANUP_CONTRACT_VERSION,
        stylebook_slug=context.stylebook_slug,
        scopes=scopes,
        can_apply=can_apply,
    )
