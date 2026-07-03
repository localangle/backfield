"""Evidence sampling for questionable organization canonical review."""

from __future__ import annotations

from backfield_db import (
    BackfieldProject,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from sqlmodel import Session, col, func, select

MAX_SAMPLE_MENTIONS = 3
_MAX_MENTION_TEXT_LEN = 220


def organization_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def _normalize_sample_text(value: str | None) -> str:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) > _MAX_MENTION_TEXT_LEN:
        return cleaned[: _MAX_MENTION_TEXT_LEN - 1] + "…"
    return cleaned


def _accumulate_sample(
    bucket: dict[str, list[str]],
    *,
    canonical_id: str,
    mention_text: str | None,
) -> None:
    normalized = _normalize_sample_text(mention_text)
    if not normalized:
        return
    existing = bucket.setdefault(canonical_id, [])
    if normalized in existing:
        return
    if len(existing) >= MAX_SAMPLE_MENTIONS:
        return
    existing.append(normalized)


def sample_mention_texts_for_organization_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not project_ids or not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstrateOrganization.stylebook_organization_canonical_id,
            SubstrateOrganizationMentionOccurrence.mention_text,
        )
        .select_from(SubstrateOrganizationMentionOccurrence)
        .join(
            SubstrateOrganizationMention,
            SubstrateOrganizationMention.id
            == SubstrateOrganizationMentionOccurrence.organization_mention_id,
        )
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            col(SubstrateOrganization.project_id).in_(project_ids),
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
            SubstrateOrganizationMentionOccurrence.suppressed == False,  # noqa: E712
        )
        .order_by(col(SubstrateOrganizationMentionOccurrence.id).desc())
    ).all()
    bucket: dict[str, list[str]] = {}
    for canonical_id, mention_text in rows:
        if canonical_id is None:
            continue
        _accumulate_sample(
            bucket,
            canonical_id=str(canonical_id),
            mention_text=str(mention_text or ""),
        )
    return {key: tuple(values) for key, values in bucket.items()}


def mention_counts_for_organization_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
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
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def linked_substrate_counts_for_organization_canonicals(
    session: Session,
    *,
    project_ids: list[int],
    canonical_ids: list[str],
) -> dict[str, int]:
    if not project_ids or not canonical_ids:
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
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}
