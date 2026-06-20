"""Find linked people whose substrate name is obviously unlike the canonical label."""

from __future__ import annotations

from backfield_db import (
    StylebookPersonCanonical,
    SubstratePerson,
)
from sqlmodel import Session, col, select

from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.entities.person.name_mismatch import person_link_is_obvious_mismatch
from backfield_entities.quality.dismissals import load_dismissed_keys
from backfield_entities.quality.finders._name_mismatch_common import (
    PERSON_NAME_MISMATCH_CHECK_ID,
    CanonicalMismatchAgg,
    load_person_editorial_alias_keys,
    organization_project_ids,
)
from backfield_entities.quality.types import CleanupNameMismatchIssueRow


def _aggregate_person_mismatches(
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
            SubstratePerson.name,
            SubstratePerson.stylebook_person_canonical_id,
            StylebookPersonCanonical.id,
            StylebookPersonCanonical.label,
        )
        .join(
            StylebookPersonCanonical,
            col(StylebookPersonCanonical.id) == col(SubstratePerson.stylebook_person_canonical_id),
        )
        .where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            col(SubstratePerson.project_id).in_(project_ids),
            SubstratePerson.canonical_link_status == CANONICAL_LINK_LINKED,
            SubstratePerson.stylebook_person_canonical_id.is_not(None),
        )
    ).all()

    canonical_ids = sorted(
        {
            str(canon_id)
            for _name, _substrate_canon_id, canon_id, _label in linked_rows
            if canon_id is not None
        }
    )
    editorial_aliases = load_person_editorial_alias_keys(session, canonical_ids=canonical_ids)

    agg: dict[str, CanonicalMismatchAgg] = {}
    for substrate_name, _substrate_canon_id, canon_id, canonical_label in linked_rows:
        if canon_id is None or not canonical_label:
            continue
        cid = str(canon_id)
        alias_keys = editorial_aliases.get(cid, frozenset())
        if not person_link_is_obvious_mismatch(
            substrate_name=str(substrate_name or ""),
            canonical_label=str(canonical_label),
            editorial_alias_keys=alias_keys,
        ):
            continue
        agg.setdefault(cid, CanonicalMismatchAgg()).record(str(substrate_name or ""))
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
        select(StylebookPersonCanonical).where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
            col(StylebookPersonCanonical.id).in_(canonical_ids),
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
                entity_type="person",
                status=str(canon.status or "active"),
                mismatched_linked_count=bucket.count,
                mismatched_examples=list(bucket.examples),
            )
        )
    out.sort(key=lambda row: (-row.mismatched_linked_count, row.label.lower()))
    return out


def count_person_name_mismatches(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> int:
    dismissed = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=PERSON_NAME_MISMATCH_CHECK_ID,
    )
    agg = _aggregate_person_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    return sum(1 for cid in agg if cid not in dismissed)


def list_person_name_mismatches(
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
        check_id=PERSON_NAME_MISMATCH_CHECK_ID,
    )
    agg = _aggregate_person_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    rows = _canonical_rows_for_mismatches(session, stylebook_id=stylebook_id, agg=agg)
    rows = [row for row in rows if row.id not in dismissed]
    total = len(rows)
    return rows[offset : offset + limit], total


def count_person_name_mismatches_postgres(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
) -> int:
    return count_person_name_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )


def list_person_name_mismatches_postgres(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    limit: int,
    offset: int,
) -> tuple[list[CleanupNameMismatchIssueRow], int]:
    return list_person_name_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
