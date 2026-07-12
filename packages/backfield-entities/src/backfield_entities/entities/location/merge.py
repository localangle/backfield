"""Merge one location canonical into another (relink substrates, delete source)."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    BackfieldProject,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from sqlmodel import Session, col, func, select

from backfield_entities.connections.rewire import rewire_connections_for_canonical_merge
from backfield_entities.entities.linking.substrate_actions import (
    link_substrate_to_canonical_atomic,
)
from backfield_entities.entities.location.link_identity import location_merge_pair_blocked


@dataclass(frozen=True)
class MergeLocationCanonicalResult:
    source_id: str
    target_id: str
    relinked_substrate_count: int
    source_deleted: bool
    relinked_substrates: tuple[tuple[int, int], ...]


def _organization_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def _linked_substrate_count(
    session: Session,
    *,
    project_ids: list[int],
    canonical_id: str,
) -> int:
    if not project_ids:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateLocation)
            .where(
                col(SubstrateLocation.project_id).in_(project_ids),
                SubstrateLocation.stylebook_location_canonical_id == canonical_id,
            )
        )
        or 0
    )


def merge_location_canonical_into(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    source_canonical_id: str,
    target_canonical_id: str,
    provenance: str = "stylebook_cleanup_merge",
) -> MergeLocationCanonicalResult:
    source_id = str(source_canonical_id)
    target_id = str(target_canonical_id)
    if source_id == target_id:
        raise ValueError("source and target canonical must differ")

    source = session.get(StylebookLocationCanonical, source_id)
    target = session.get(StylebookLocationCanonical, target_id)
    if source is None or int(source.stylebook_id) != int(stylebook_id):
        raise ValueError("source canonical not in this stylebook")
    if target is None or int(target.stylebook_id) != int(stylebook_id):
        raise ValueError("target canonical not in this stylebook")
    if location_merge_pair_blocked(
        source_label=str(source.label),
        source_location_type=source.location_type,
        target_label=str(target.label),
        target_location_type=target.location_type,
    ):
        raise ValueError(
            "These records look like different kinds of places "
            f"({source.label!r} vs {target.label!r}) and cannot be merged. "
            "If they really are the same place, fix the place kind on one record first."
        )

    project_ids = _organization_project_ids(session, organization_id=organization_id)
    linked = list(
        session.exec(
            select(SubstrateLocation).where(
                col(SubstrateLocation.project_id).in_(project_ids),
                SubstrateLocation.stylebook_location_canonical_id == source_id,
            )
        ).all()
    )

    relinked = 0
    relinked_substrates: list[tuple[int, int]] = []
    for loc in linked:
        link_substrate_to_canonical_atomic(
            session,
            stylebook_id=int(stylebook_id),
            location=loc,
            target_canonical_id=target_id,
            provenance=provenance,
        )
        relinked += 1
        if loc.id is not None and loc.project_id is not None:
            relinked_substrates.append((int(loc.project_id), int(loc.id)))

    remaining = _linked_substrate_count(
        session,
        project_ids=project_ids,
        canonical_id=source_id,
    )
    if remaining > 0:
        raise ValueError("source canonical still has linked places after merge")

    rewire_connections_for_canonical_merge(
        session,
        entity_type="location",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        project_ids=project_ids,
    )

    session.delete(source)
    return MergeLocationCanonicalResult(
        source_id=source_id,
        target_id=target_id,
        relinked_substrate_count=relinked,
        source_deleted=True,
        relinked_substrates=tuple(relinked_substrates),
    )


def canonical_has_linked_evidence(
    session: Session,
    *,
    organization_id: int,
    canonical_id: str,
) -> bool:
    project_ids = _organization_project_ids(session, organization_id=organization_id)
    return _linked_substrate_count(session, project_ids=project_ids, canonical_id=canonical_id) > 0
