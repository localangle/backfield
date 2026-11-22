"""Merge one location canonical into another (relink substrates, delete source)."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    BackfieldProject,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_events import record_canonical_merged, suppress_canonical_evidence_events
from sqlmodel import Session, col, func, select

from backfield_entities.connections.rewire import rewire_connections_for_canonical_merge
from backfield_entities.entities.linking.substrate_actions import (
    link_substrate_to_canonical_atomic,
)
from backfield_entities.entities.location.link_identity import location_merge_pair_blocked
from backfield_entities.entities.location.persist import seed_aliases_for_canonical_label
from backfield_entities.geo.geometry_bind import assign_geojson_geometry


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


def _preserve_source_geography_if_target_missing(
    session: Session,
    *,
    source: StylebookLocationCanonical,
    target: StylebookLocationCanonical,
) -> None:
    if target.geometry_json is not None or not isinstance(source.geometry_json, dict):
        return
    assign_geojson_geometry(session, target, dict(source.geometry_json))
    for field_name in (
        "formatted_address",
        "country_code",
        "subdivision_code",
        "city_name",
        "district_kind",
        "district_number",
        "district_key",
    ):
        if getattr(target, field_name) in (None, ""):
            setattr(target, field_name, getattr(source, field_name))
    session.add(target)


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

    # Approving the merge makes the removed record's label a reviewed alias of the keeper.
    # This is preserved even when the source has no linked substrates to relink.
    seed_aliases_for_canonical_label(
        session,
        canon_id=target_id,
        label=str(source.label),
        provenance=provenance,
    )
    _preserve_source_geography_if_target_missing(
        session,
        source=source,
        target=target,
    )
    session.flush()

    # The merged event subsumes the per-substrate relink evidence events below.
    suppress_canonical_evidence_events(
        session,
        entity_type="location",
        canonical_ids=[source_id, target_id],
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

    record_canonical_merged(
        session,
        stylebook_id=int(stylebook_id),
        entity_type="location",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        label=str(source.label),
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
