"""Delete a location canonical and requeue linked substrates as pending."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import StylebookLocationCanonical
from sqlmodel import Session

from backfield_entities.cleanup.entity_models import cleanup_entity_models
from backfield_entities.cleanup.removal_ops import RemovalActivity, delete_canonical


@dataclass(frozen=True)
class DeleteCanonicalAndRequeueResult:
    canonical_id: str
    label: str
    unlinked_substrate_ids: list[int]
    unlinked_substrate_count: int


def delete_location_canonical_and_requeue(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    canonical_id: str,
    actor_user_id: int | None = None,
    source: str = "manual_ui",
    expected_substrate_ids: list[int] | None = None,
) -> DeleteCanonicalAndRequeueResult:
    """Delete a stylebook location canonical and return linked substrates to pending.

    Matches Stylebook UI delete semantics: linked substrates across all org
    projects are unlinked (``canonical_id=None``, ``canonical_link_status=pending``)
    with review reason ``reset_pending_after_canonical_deleted``. The work is shared with the
    other entity kinds and the cleanup API (``cleanup/removal_ops.py``).
    """
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise LookupError("Canonical location not found")
    outcome = delete_canonical(
        session,
        cleanup_entity_models("locations"),
        canon,
        stylebook_id=int(stylebook_id),
        organization_id=int(organization_id),
        activity=RemovalActivity(
            actor_type="user" if actor_user_id is not None else "system",
            actor_user_id=actor_user_id,
            source=source,
        ),
        expected_record_ids=expected_substrate_ids,
    )
    record_ids = sorted(record_id for _, record_id in outcome.released_records)
    return DeleteCanonicalAndRequeueResult(
        canonical_id=outcome.canonical_id,
        label=outcome.label,
        unlinked_substrate_ids=record_ids,
        unlinked_substrate_count=len(record_ids),
    )
