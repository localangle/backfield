"""Find linked locations whose substrate name is obviously unlike the canonical label."""

from __future__ import annotations

from backfield_db import (
    StylebookLocationCanonical,
    SubstrateLocation,
)
from sqlmodel import Session, col, select

from backfield_entities.canonical.jurisdiction import place_extract_components_from_entry
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.entities.location.link_identity import location_link_is_obvious_mismatch
from backfield_entities.quality.dismissals import load_dismissed_keys
from backfield_entities.quality.finders._name_mismatch_common import (
    LOCATION_NAME_MISMATCH_CHECK_ID,
    CanonicalMismatchAgg,
    load_location_editorial_alias_keys,
    organization_project_ids,
)
from backfield_entities.quality.types import CleanupNameMismatchIssueRow


def _aggregate_location_mismatches(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> dict[str, CanonicalMismatchAgg]:
    project_ids = organization_project_ids(session, organization_id=organization_id)
    if not project_ids:
        return {}

    linked_rows = session.exec(
        select(SubstrateLocation, StylebookLocationCanonical)
        .join(
            StylebookLocationCanonical,
            col(StylebookLocationCanonical.id)
            == col(SubstrateLocation.stylebook_location_canonical_id),
        )
        .where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            col(SubstrateLocation.project_id).in_(project_ids),
            SubstrateLocation.canonical_link_status == CANONICAL_LINK_LINKED,
            SubstrateLocation.stylebook_location_canonical_id.is_not(None),
        )
    ).all()

    canonical_ids = sorted(
        {
            str(canon.id)
            for _loc, canon in linked_rows
            if canon.id is not None
        }
    )
    editorial_aliases = load_location_editorial_alias_keys(session, canonical_ids=canonical_ids)

    agg: dict[str, CanonicalMismatchAgg] = {}
    for loc, canon in linked_rows:
        if canon.id is None or not canon.label:
            continue
        cid = str(canon.id)
        alias_keys = editorial_aliases.get(cid, frozenset())
        comps = place_extract_components_from_entry(loc, None)
        if not location_link_is_obvious_mismatch(
            substrate_name=str(loc.name or ""),
            substrate_normalized_name=str(loc.normalized_name or ""),
            substrate_location_type=loc.location_type,
            components=comps,
            formatted_address=loc.formatted_address,
            geometry_type=loc.geometry_type,
            canonical_label=str(canon.label),
            canonical_location_type=canon.location_type,
            editorial_alias_keys=alias_keys,
        ):
            continue
        agg.setdefault(cid, CanonicalMismatchAgg()).record(str(loc.name or ""))
    return agg


def _canonical_rows_for_mismatches(
    session: Session,
    *,
    stylebook_id: int,
    agg: dict[str, CanonicalMismatchAgg],
) -> list[CleanupNameMismatchIssueRow]:
    if not agg:
        return []
    canonical_ids = list(agg.keys())
    canon_rows = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            col(StylebookLocationCanonical.id).in_(canonical_ids),
        )
    ).all()
    by_id = {str(row.id): row for row in canon_rows if row.id is not None}
    out: list[CleanupNameMismatchIssueRow] = []
    for cid, bucket in agg.items():
        canon = by_id.get(cid)
        if canon is None or canon.id is None:
            continue
        out.append(
            CleanupNameMismatchIssueRow(
                id=str(canon.id),
                slug=str(canon.slug),
                label=str(canon.label),
                entity_type="location",
                status=str(canon.status or "active"),
                location_type=str(canon.location_type) if canon.location_type else None,
                mismatched_linked_count=bucket.count,
                mismatched_examples=list(bucket.examples),
            )
        )
    out.sort(key=lambda row: (-row.mismatched_linked_count, row.label.lower()))
    return out


def count_location_name_mismatches(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> int:
    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=LOCATION_NAME_MISMATCH_CHECK_ID,
    )
    agg = _aggregate_location_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    return sum(1 for cid in agg if cid not in dismissed)


def list_location_name_mismatches(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    limit: int,
    offset: int,
) -> tuple[list[CleanupNameMismatchIssueRow], int]:
    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=LOCATION_NAME_MISMATCH_CHECK_ID,
    )
    agg = _aggregate_location_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    rows = _canonical_rows_for_mismatches(session, stylebook_id=stylebook_id, agg=agg)
    rows = [row for row in rows if row.id not in dismissed]
    total = len(rows)
    return rows[offset : offset + limit], total
