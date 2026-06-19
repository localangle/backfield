"""Evidence counts for stylebook canonical rows."""

from __future__ import annotations

from backfield_db import (
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstratePerson,
    SubstratePersonMention,
)
from sqlmodel import Session, col, func, select


def mention_counts_by_location_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocationMention.id)),
        )
        .select_from(SubstrateLocationMention)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


def linked_substrate_counts_by_location_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocation.id)),
        )
        .where(
            col(SubstrateLocation.project_id).in_(project_ids),
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


def attach_location_canonical_evidence_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows: list,
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (mention_counts, linked_substrate_counts) keyed by canonical id."""
    cids = [str(row.id) for row in rows if getattr(row, "id", None) is not None]
    mention = mention_counts_by_location_canonical(
        session, project_ids=project_ids, canonical_ids=cids
    )
    linked = linked_substrate_counts_by_location_canonical(
        session, project_ids=project_ids, canonical_ids=cids
    )
    return mention, linked


def mention_counts_by_person_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePersonMention.id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


def linked_substrate_counts_by_person_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePerson.id)),
        )
        .where(
            col(SubstratePerson.project_id).in_(project_ids),
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


def mention_counts_by_organization_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateOrganization.stylebook_organization_canonical_id,
            func.count(col(SubstrateOrganizationMention.id)),
        )
        .select_from(SubstrateOrganizationMention)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out


def linked_substrate_counts_by_organization_canonical(
    session: Session, *, project_ids: list[int], canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids or not project_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateOrganization.stylebook_organization_canonical_id,
            func.count(col(SubstrateOrganization.id)),
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
    ).all()
    out: dict[str, int] = {}
    for cid, cnt in rows:
        if cid is not None:
            out[str(cid)] = int(cnt)
    return out
