"""Merge one location canonical into another (relink substrates, delete source)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backfield_db import (
    BackfieldProject,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    SubstrateLocation,
)
from backfield_events import record_canonical_merged, suppress_canonical_evidence_events
from sqlalchemy import inspect as sqlalchemy_inspect
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
    transferred_alias_count: int = 0
    transferred_meta_count: int = 0
    # The source's geography when the survivor kept its own, so a caller never loses it silently.
    unapplied_source_geometry: dict[str, Any] | None = None


GeometryWinner = Literal["target", "source"]

_GEOGRAPHY_FIELDS = (
    "formatted_address",
    "country_code",
    "subdivision_code",
    "city_name",
    "district_kind",
    "district_number",
    "district_key",
)


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


def _apply_source_geography(
    session: Session,
    *,
    source: StylebookLocationCanonical,
    target: StylebookLocationCanonical,
    overwrite_fields: bool,
) -> None:
    assign_geojson_geometry(session, target, dict(source.geometry_json or {}))
    for field_name in _GEOGRAPHY_FIELDS:
        source_value = getattr(source, field_name)
        if overwrite_fields and source_value not in (None, ""):
            setattr(target, field_name, source_value)
        elif getattr(target, field_name) in (None, ""):
            setattr(target, field_name, source_value)
    session.add(target)


def _merge_geography(
    session: Session,
    *,
    source: StylebookLocationCanonical,
    target: StylebookLocationCanonical,
    geometry_winner: GeometryWinner,
) -> dict[str, Any] | None:
    """Keep or replace the survivor's geography; return the source geometry left unused."""
    if not isinstance(source.geometry_json, dict):
        return None
    source_geometry = dict(source.geometry_json)
    if target.geometry_json is None:
        _apply_source_geography(session, source=source, target=target, overwrite_fields=False)
        return None
    if geometry_winner == "source":
        _apply_source_geography(session, source=source, target=target, overwrite_fields=True)
        return None
    return source_geometry if source_geometry != target.geometry_json else None


def _alias_state(
    session: Session, *, canonical_id: str
) -> dict[str, tuple[str, str, bool]]:
    rows = session.exec(
        select(StylebookLocationAlias).where(
            StylebookLocationAlias.location_canonical_id == canonical_id
        )
    ).all()
    return {
        str(row.normalized_alias): (str(row.alias_text), str(row.provenance), bool(row.suppressed))
        for row in rows
    }


def _restore_alias_state(
    session: Session, *, canonical_id: str, state: dict[str, tuple[str, str, bool]]
) -> None:
    """Undo any rewrite of aliases the survivor already held (upserts refresh text and flags)."""
    rows = session.exec(
        select(StylebookLocationAlias).where(
            StylebookLocationAlias.location_canonical_id == canonical_id,
            col(StylebookLocationAlias.normalized_alias).in_(state),
        )
    ).all()
    for row in rows:
        alias_text, provenance, suppressed = state[str(row.normalized_alias)]
        row.alias_text = alias_text
        row.provenance = provenance
        row.suppressed = suppressed
        session.add(row)


def _transfer_aliases(
    session: Session,
    *,
    source: StylebookLocationCanonical,
    target: StylebookLocationCanonical,
    provenance: str,
) -> int:
    """Move every source alias and the source label to the survivor as reviewed aliases.

    Aliases the survivor already holds keep their own text, provenance, and suppression.
    """
    source_rows = list(
        session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == str(source.id)
            )
        ).all()
    )
    target_norms = {
        str(row.normalized_alias)
        for row in session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == str(target.id)
            )
        ).all()
    }
    transferred = 0
    for source_alias in source_rows:
        normalized_alias = str(source_alias.normalized_alias)
        if normalized_alias in target_norms:
            session.delete(source_alias)
            continue
        source_alias.location_canonical_id = str(target.id)
        source_alias.provenance = provenance
        session.add(source_alias)
        target_norms.add(normalized_alias)
        transferred += 1
    session.flush()

    # Approving the merge makes the removed record's label a reviewed alias of the keeper,
    # even when the source has no linked substrates to relink.
    before_label_seed = _alias_state(session, canonical_id=str(target.id))
    seed_aliases_for_canonical_label(
        session, canon_id=str(target.id), label=str(source.label), provenance=provenance
    )
    session.flush()
    _restore_alias_state(session, canonical_id=str(target.id), state=before_label_seed)
    return transferred


def _meta_value(row: StylebookLocationMeta) -> tuple[object, ...]:
    return (row.value_type, row.value_text, row.value_number, row.value_boolean)


def _preflight_meta_merge(
    session: Session, *, source_id: str, target_id: str
) -> tuple[list[StylebookLocationMeta], dict[str, StylebookLocationMeta]]:
    source_rows = list(
        session.exec(
            select(StylebookLocationMeta).where(
                StylebookLocationMeta.stylebook_location_canonical_id == source_id
            )
        ).all()
    )
    target_by_type = {
        str(row.meta_type): row
        for row in session.exec(
            select(StylebookLocationMeta).where(
                StylebookLocationMeta.stylebook_location_canonical_id == target_id
            )
        ).all()
    }
    for source_row in source_rows:
        target_row = target_by_type.get(str(source_row.meta_type))
        if target_row is not None and _meta_value(source_row) != _meta_value(target_row):
            raise ValueError(
                f"location metadata conflict for {source_row.meta_type!r}; "
                "resolve it before merging"
            )
    return source_rows, target_by_type


def _transfer_meta(
    session: Session,
    *,
    source_rows: list[StylebookLocationMeta],
    target_by_type: dict[str, StylebookLocationMeta],
    target_id: str,
) -> int:
    transferred = 0
    for source_row in source_rows:
        target_row = target_by_type.get(str(source_row.meta_type))
        if target_row is None:
            source_row.stylebook_location_canonical_id = target_id
            session.add(source_row)
            transferred += 1
            continue
        target_row.added = bool(target_row.added or source_row.added)
        target_row.edited = bool(target_row.edited or source_row.edited)
        session.add(target_row)
        # The duplicate source row is removed with the source canonical.
    return transferred


def merge_location_canonical_into(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    source_canonical_id: str,
    target_canonical_id: str,
    provenance: str = "stylebook_cleanup_merge",
    geometry_winner: GeometryWinner = "target",
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

    source_meta, target_meta_by_type = _preflight_meta_merge(
        session, source_id=source_id, target_id=target_id
    )
    # Move aliases, metadata, and connections before relinking. Relinking the last substrate can
    # prune an ingest-only source canonical, which would close its connections and delete
    # source-owned rows before the merge could preserve them.
    transferred_alias_count = _transfer_aliases(
        session, source=source, target=target, provenance=provenance
    )
    preserved_alias_state = _alias_state(session, canonical_id=target_id)
    transferred_meta_count = _transfer_meta(
        session,
        source_rows=source_meta,
        target_by_type=target_meta_by_type,
        target_id=target_id,
    )
    unapplied_source_geometry = _merge_geography(
        session, source=source, target=target, geometry_winner=geometry_winner
    )
    session.flush()

    # The merged event subsumes the per-substrate relink evidence events below.
    suppress_canonical_evidence_events(
        session,
        entity_type="location",
        canonical_ids=[source_id, target_id],
    )

    project_ids = _organization_project_ids(session, organization_id=organization_id)
    rewire_connections_for_canonical_merge(
        session,
        entity_type="location",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        project_ids=project_ids,
    )
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
    _restore_alias_state(session, canonical_id=target_id, state=preserved_alias_state)

    remaining = _linked_substrate_count(
        session,
        project_ids=project_ids,
        canonical_id=source_id,
    )
    if remaining > 0:
        raise ValueError("source canonical still has linked places after merge")

    record_canonical_merged(
        session,
        stylebook_id=int(stylebook_id),
        entity_type="location",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        label=str(source.label),
    )
    # Relinking the last substrate may already have pruned the source; delete it only once.
    if source not in session.deleted and sqlalchemy_inspect(source).persistent:
        session.delete(source)
    return MergeLocationCanonicalResult(
        source_id=source_id,
        target_id=target_id,
        relinked_substrate_count=relinked,
        source_deleted=True,
        relinked_substrates=tuple(relinked_substrates),
        transferred_alias_count=transferred_alias_count,
        transferred_meta_count=transferred_meta_count,
        unapplied_source_geometry=unapplied_source_geometry,
    )


def canonical_has_linked_evidence(
    session: Session,
    *,
    organization_id: int,
    canonical_id: str,
) -> bool:
    project_ids = _organization_project_ids(session, organization_id=organization_id)
    return _linked_substrate_count(session, project_ids=project_ids, canonical_id=canonical_id) > 0
