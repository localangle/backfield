"""Organization canonical recall for ingest policy and LLM adjudication payloads."""

from __future__ import annotations

from backfield_db import (
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from sqlmodel import Session, col, select

from backfield_entities.entities.organization.types import (
    normalize_organization_text,
    normalize_organization_type,
)

ORGANIZATION_RECALL_MIN_SCORE = 40
ORGANIZATION_RECALL_DEFAULT_LIMIT = 24


def canonical_ids_from_organization_name_keys(
    session: Session,
    *,
    stylebook_id: int,
    name_or_norm: str,
) -> list[str]:
    """Canonical ids whose alias ``normalized_alias`` matches exactly."""
    norm = normalize_organization_text(name_or_norm)
    if not norm:
        return []
    stmt = (
        select(StylebookOrganizationCanonical.id)
        .join(
            StylebookOrganizationAlias,
            StylebookOrganizationAlias.organization_canonical_id
            == StylebookOrganizationCanonical.id,
        )
        .where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            StylebookOrganizationAlias.normalized_alias == norm,
            StylebookOrganizationAlias.suppressed.is_(False),
        )
    )
    out: list[str] = []
    seen: set[str] = set()
    for cid in session.exec(stmt).all():
        if cid is None:
            continue
        cid_str = str(cid)
        if cid_str not in seen:
            seen.add(cid_str)
            out.append(cid_str)
    return out


def _organization_name_norm(organization: SubstrateOrganization) -> str:
    return normalize_organization_text(organization.normalized_name or organization.name)


def _organization_type_norm(organization: SubstrateOrganization) -> str | None:
    return normalize_organization_type(organization.organization_type)


def _score_canonical_for_organization(
    *,
    norm: str,
    type_norm: str | None,
    canon: StylebookOrganizationCanonical,
) -> int:
    label_norm = normalize_organization_text(canon.label)
    score = 0
    if norm and label_norm == norm:
        score = 100
    elif norm and label_norm and (norm in label_norm or label_norm in norm):
        score = 60
    canon_type = normalize_organization_type(canon.organization_type)
    if type_norm and canon_type and type_norm == canon_type:
        score += 25
    return score


def retrieve_organization_canonical_candidates(
    session: Session,
    *,
    stylebook_id: int,
    organization: SubstrateOrganization,
    limit: int = ORGANIZATION_RECALL_DEFAULT_LIMIT,
) -> list[tuple[str, str]]:
    """Ranked ``(canonical_id, label)`` for policy defer, LLM adjudication, and link UI."""
    norm = _organization_name_norm(organization)
    if not norm:
        return []

    type_norm = _organization_type_norm(organization)
    scored: dict[str, tuple[int, str]] = {}

    exact_alias_ids = set(
        canonical_ids_from_organization_name_keys(
            session,
            stylebook_id=stylebook_id,
            name_or_norm=norm,
        )
    )
    candidate_ids: set[str] = set(exact_alias_ids)

    label_stmt = (
        select(StylebookOrganizationCanonical)
        .where(StylebookOrganizationCanonical.stylebook_id == stylebook_id)
        .order_by(col(StylebookOrganizationCanonical.label).asc())
        .limit(max(limit * 8, 96))
    )
    for canon in session.exec(label_stmt).all():
        if canon.id is None:
            continue
        cid = str(canon.id)
        score = _score_canonical_for_organization(norm=norm, type_norm=type_norm, canon=canon)
        if cid in exact_alias_ids:
            score = max(score, 100)
        if score < ORGANIZATION_RECALL_MIN_SCORE:
            continue
        candidate_ids.add(cid)
        prev = scored.get(cid)
        if prev is None or score > prev[0]:
            scored[cid] = (score, str(canon.label))

    ranked = sorted(scored.items(), key=lambda item: (-item[1][0], item[1][1].lower()))
    out: list[tuple[str, str]] = []
    for cid, (_score, label) in ranked:
        out.append((cid, label))
        if len(out) >= limit:
            break
    return out
