"""GET .../cleanup/capabilities: what this key can do on the preview cleanup surface."""

from __future__ import annotations

from backfield_auth.gate import SCOPE_CLEANUP_APPLY, SCOPE_READ
from backfield_entities.cleanup.ceilings import all_ceilings
from backfield_entities.cleanup.check_reads import entity_name_for_check
from backfield_entities.cleanup.entity_models import ENTITY_NAMES, EntityName
from backfield_entities.cleanup.envelope import MAX_ITEMS_PER_REQUEST
from backfield_entities.cleanup.evidence import EVIDENCE_BATCH_MAX
from backfield_entities.cleanup.export import EXPORT_MAX_LIMIT
from backfield_entities.quality.check_runs import cleanup_algorithm_version
from backfield_entities.quality.checks import STYLEBOOK_CLEANUP_CHECKS
from fastapi import Depends
from pydantic import BaseModel, Field

from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    is_service_principal,
    require_cleanup_read,
)
from core_api.routers.public.cleanup.settings import snippet_max_chars

CLEANUP_CONTRACT_VERSION = "preview-1"
SUPPORTED_OPERATIONS = ("merges",)


class CapabilityCheck(BaseModel):
    id: str
    entity: EntityName
    kind: str
    algorithm_version: str


class CleanupLimits(BaseModel):
    export_max_limit: int
    evidence_batch_max: int
    snippet_max_chars: int = Field(description="0 means this instance returns no snippet text.")
    run_ceilings: dict[str, int] = Field(
        description="Most applied actions per run, by operation. Open a new run to continue."
    )
    apply_items_max: int = Field(description="Most items in one apply request.")


class CleanupCapabilitiesOut(BaseModel):
    contract_version: str
    stylebook_slug: str
    scopes: list[str]
    can_apply: bool
    entities: list[EntityName]
    checks: list[CapabilityCheck]
    queue_scopes: list[str] = Field(description="Queue scopes this key may request.")
    operations: list[str] = Field(description="Apply operations this instance supports.")
    limits: CleanupLimits


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
        entities=list(ENTITY_NAMES),
        checks=[
            CapabilityCheck(
                id=check.id,
                entity=entity_name_for_check(check),
                kind=check.kind,
                algorithm_version=cleanup_algorithm_version(check.id),
            )
            for check in STYLEBOOK_CLEANUP_CHECKS
        ],
        queue_scopes=["project", "stylebook"]
        if is_service_principal(context.auth)
        else ["project"],
        operations=list(SUPPORTED_OPERATIONS) if can_apply else [],
        limits=CleanupLimits(
            export_max_limit=EXPORT_MAX_LIMIT,
            evidence_batch_max=EVIDENCE_BATCH_MAX,
            snippet_max_chars=snippet_max_chars(),
            run_ceilings={str(k): v for k, v in all_ceilings().items()},
            apply_items_max=MAX_ITEMS_PER_REQUEST,
        ),
    )
