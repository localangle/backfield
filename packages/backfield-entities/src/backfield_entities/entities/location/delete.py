"""Delete a location canonical and requeue linked substrates as pending."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    BackfieldProject,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_events import record_canonical_deleted, suppress_canonical_evidence_events
from sqlmodel import Session, col, select

from backfield_entities.activity import (
    EVENT_CANONICAL_DELETED,
    log_stylebook_activity_safe,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING


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
    with review reason ``reset_pending_after_canonical_deleted``.
    """
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        raise LookupError("Canonical location not found")

    # The delete event subsumes the per-substrate evidence changes below.
    suppress_canonical_evidence_events(
        session,
        entity_type="location",
        canonical_ids=[str(canon.id)],
    )

    pid_rows = session.exec(
        select(BackfieldProject.id).where(
            BackfieldProject.organization_id == int(organization_id)
        )
    ).all()
    project_ids = [int(r) for r in pid_rows if r is not None]
    linked = session.exec(
        select(SubstrateLocation).where(
            col(SubstrateLocation.project_id).in_(project_ids),
            SubstrateLocation.stylebook_location_canonical_id == str(canon.id),
        )
    ).all() if project_ids else []

    linked_ids = sorted(int(loc.id) for loc in linked if loc.id is not None)
    if expected_substrate_ids is not None and linked_ids != sorted(expected_substrate_ids):
        raise ValueError("stale_preview: linked substrates changed")

    for loc in linked:
        loc.stylebook_location_canonical_id = None
        loc.canonical_link_status = CANONICAL_LINK_PENDING
        loc.canonical_review_reasons_json = [
            {
                "code": "reset_pending_after_canonical_deleted",
                "deleted_canonical_id": str(canon.id),
            }
        ]
        session.add(loc)

    deleted_id = str(canon.id)
    label = str(canon.label)
    log_stylebook_activity_safe(
        session,
        stylebook_id=int(stylebook_id),
        actor_type="user" if actor_user_id is not None else "system",
        actor_user_id=actor_user_id,
        source=source,  # type: ignore[arg-type]
        event_type=EVENT_CANONICAL_DELETED,
        entity_type="location",
        entity_id=deleted_id,
        entity_label=label,
        payload_json={"unlinked_substrate_count": len(linked_ids)},
    )
    record_canonical_deleted(
        session,
        stylebook_id=int(stylebook_id),
        entity_type="location",
        canonical_id=deleted_id,
        label=label,
    )
    session.delete(canon)
    return DeleteCanonicalAndRequeueResult(
        canonical_id=deleted_id,
        label=label,
        unlinked_substrate_ids=linked_ids,
        unlinked_substrate_count=len(linked_ids),
    )
