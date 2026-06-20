"""Find linked organizations whose substrate name is obviously unlike the canonical label."""

from __future__ import annotations

from backfield_db import (
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from sqlalchemy import text
from sqlmodel import Session, col, select

from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.entities.organization.name_mismatch import (
    organization_link_is_obvious_mismatch,
)
from backfield_entities.quality.dismissals import load_dismissed_keys
from backfield_entities.quality.finders._name_mismatch_common import (
    ORG_TRIGRAM_CANDIDATE_FLOOR,
    ORGANIZATION_NAME_MISMATCH_CHECK_ID,
    CanonicalMismatchAgg,
    load_organization_editorial_alias_keys,
    organization_project_ids,
)
from backfield_entities.quality.types import CleanupNameMismatchIssueRow


def _aggregate_organization_mismatches_sqlite(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> dict[str, CanonicalMismatchAgg]:
    project_ids = organization_project_ids(session, organization_id=organization_id)
    if not project_ids:
        return {}

    linked_rows = session.exec(
        select(
            SubstrateOrganization.name,
            SubstrateOrganization.stylebook_organization_canonical_id,
            StylebookOrganizationCanonical.id,
            StylebookOrganizationCanonical.label,
        )
        .join(
            StylebookOrganizationCanonical,
            col(StylebookOrganizationCanonical.id)
            == col(SubstrateOrganization.stylebook_organization_canonical_id),
        )
        .where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            col(SubstrateOrganization.project_id).in_(project_ids),
            SubstrateOrganization.canonical_link_status == CANONICAL_LINK_LINKED,
            SubstrateOrganization.stylebook_organization_canonical_id.is_not(None),
        )
    ).all()

    canonical_ids = sorted(
        {
            str(canon_id)
            for _name, _substrate_canon_id, canon_id, _label in linked_rows
            if canon_id is not None
        }
    )
    editorial_aliases = load_organization_editorial_alias_keys(
        session, canonical_ids=canonical_ids
    )

    agg: dict[str, CanonicalMismatchAgg] = {}
    for substrate_name, _substrate_canon_id, canon_id, canonical_label in linked_rows:
        if canon_id is None or not canonical_label:
            continue
        cid = str(canon_id)
        alias_keys = editorial_aliases.get(cid, frozenset())
        if not organization_link_is_obvious_mismatch(
            substrate_name=str(substrate_name or ""),
            canonical_label=str(canonical_label),
            editorial_alias_keys=alias_keys,
        ):
            continue
        agg.setdefault(cid, CanonicalMismatchAgg()).record(str(substrate_name or ""))
    return agg


def _aggregate_organization_mismatches_postgres(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> dict[str, CanonicalMismatchAgg]:
    project_ids = organization_project_ids(session, organization_id=organization_id)
    if not project_ids:
        return {}

    stmt = text(
        """
        SELECT
            s.name AS substrate_name,
            c.id AS canonical_id,
            c.label AS canonical_label
        FROM substrate_organization s
        INNER JOIN stylebook_organization_canonical c
            ON c.id = s.stylebook_organization_canonical_id
        WHERE c.stylebook_id = :stylebook_id
          AND s.project_id = ANY(:project_ids)
          AND s.canonical_link_status = :linked
          AND s.stylebook_organization_canonical_id IS NOT NULL
          AND lower(s.normalized_name) <> lower(c.label)
          AND similarity(lower(s.normalized_name), lower(c.label)) < :floor
        """
    )
    rows = session.execute(
        stmt,
        {
            "stylebook_id": stylebook_id,
            "project_ids": project_ids,
            "linked": CANONICAL_LINK_LINKED,
            "floor": ORG_TRIGRAM_CANDIDATE_FLOOR,
        },
    ).all()

    canonical_ids = sorted(
        {str(canon_id) for _name, canon_id, _label in rows if canon_id is not None}
    )
    editorial_aliases = load_organization_editorial_alias_keys(
        session, canonical_ids=canonical_ids
    )

    agg: dict[str, CanonicalMismatchAgg] = {}
    for substrate_name, canon_id, canonical_label in rows:
        if canon_id is None or not canonical_label:
            continue
        cid = str(canon_id)
        alias_keys = editorial_aliases.get(cid, frozenset())
        if not organization_link_is_obvious_mismatch(
            substrate_name=str(substrate_name or ""),
            canonical_label=str(canonical_label),
            editorial_alias_keys=alias_keys,
        ):
            continue
        agg.setdefault(cid, CanonicalMismatchAgg()).record(str(substrate_name or ""))
    return agg


def _aggregate_organization_mismatches(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> dict[str, CanonicalMismatchAgg]:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        return _aggregate_organization_mismatches_postgres(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
        )
    return _aggregate_organization_mismatches_sqlite(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )


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
        select(StylebookOrganizationCanonical).where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            col(StylebookOrganizationCanonical.id).in_(canonical_ids),
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
                entity_type="organization",
                status=str(canon.status or "active"),
                mismatched_linked_count=bucket.count,
                mismatched_examples=list(bucket.examples),
            )
        )
    out.sort(key=lambda row: (-row.mismatched_linked_count, row.label.lower()))
    return out


def count_organization_name_mismatches(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> int:
    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=ORGANIZATION_NAME_MISMATCH_CHECK_ID,
    )
    agg = _aggregate_organization_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    return sum(1 for cid in agg if cid not in dismissed)


def list_organization_name_mismatches(
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
        check_id=ORGANIZATION_NAME_MISMATCH_CHECK_ID,
    )
    agg = _aggregate_organization_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    rows = _canonical_rows_for_mismatches(session, stylebook_id=stylebook_id, agg=agg)
    rows = [row for row in rows if row.id not in dismissed]
    total = len(rows)
    return rows[offset : offset + limit], total
