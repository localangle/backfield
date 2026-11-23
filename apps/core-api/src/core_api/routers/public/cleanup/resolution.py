"""GET .../cleanup/{entity}/{canonical_id}/resolution: where an old canonical id went."""

from __future__ import annotations

from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from backfield_entities.cleanup.redirects import CanonicalResolution, resolve_canonical
from fastapi import Depends
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    require_cleanup_read,
)


def get_cleanup_resolution(
    entity: EntityName,
    canonical_id: str,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> CanonicalResolution:
    """Follow a merged-away id to the canonical that replaced it.

    A canonical that still exists resolves to itself. An id that never existed also resolves to
    itself, with `merged` false, so check the canonical before trusting the answer.
    """
    models = cleanup_entity_models(entity)
    existing = session.get(models.canonical, canonical_id)
    if existing is not None and int(existing.stylebook_id) == context.stylebook_id:
        return CanonicalResolution(
            entity_type=models.singular,
            requested_id=canonical_id,
            resolved_id=canonical_id,
            merged=False,
        )
    return resolve_canonical(
        session,
        stylebook_id=context.stylebook_id,
        entity_type=models.singular,
        canonical_id=canonical_id,
    )
