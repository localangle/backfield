"""Organization canonical recall for ingest policy and LLM adjudication payloads."""

from __future__ import annotations

from backfield_db import (
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from sqlmodel import Session, col, select

from backfield_entities.entities.organization.types import (
    GENERATED_ACRONYM_PROVENANCE,
    multiword_organization_names_share_ambiguous_acronym,
    normalize_organization_text,
    normalize_organization_type,
    organization_match_key,
    organization_names_match_via_acronym,
    organization_substrate_alias_lookup_keys,
)
from backfield_entities.text.match_normalize import escape_ilike_metacharacters

ORGANIZATION_RECALL_MIN_SCORE = 40
ORGANIZATION_RECALL_DEFAULT_LIMIT = 24


def canonical_ids_from_organization_name_keys(
    session: Session,
    *,
    stylebook_id: int,
    name_or_norm: str,
    trusted_alias_only: bool = False,
) -> list[str]:
    """Canonical ids whose alias ``normalized_alias`` matches accent-insensitively.

    When ``trusted_alias_only`` is True, exclude machine-ingest and generated-acronym
    provenance so neither can independently drive exact linking.
    """
    lookup_keys = set(organization_substrate_alias_lookup_keys(name_or_norm))
    match_key = organization_match_key(name_or_norm)
    if not lookup_keys and not match_key:
        return []
    all_keys = set(lookup_keys)
    if match_key:
        all_keys.add(match_key)
    filters = [
        StylebookOrganizationCanonical.stylebook_id == stylebook_id,
        StylebookOrganizationCanonical.status == "active",
        col(StylebookOrganizationAlias.normalized_alias).in_(all_keys),
        StylebookOrganizationAlias.suppressed.is_(False),
    ]
    if trusted_alias_only:
        filters.extend(
            (
                StylebookOrganizationAlias.provenance != "substrate_ingest",
                StylebookOrganizationAlias.provenance != GENERATED_ACRONYM_PROVENANCE,
            )
        )
    stmt = (
        select(StylebookOrganizationCanonical.id, StylebookOrganizationAlias.normalized_alias)
        .join(
            StylebookOrganizationAlias,
            StylebookOrganizationAlias.organization_canonical_id
            == StylebookOrganizationCanonical.id,
        )
        .where(*filters)
    )
    out: list[str] = []
    seen: set[str] = set()
    for cid, norm_alias in session.exec(stmt).all():
        if cid is None:
            continue
        if match_key and organization_match_key(str(norm_alias or "")) != match_key:
            continue
        cid_str = str(cid)
        if cid_str not in seen:
            seen.add(cid_str)
            out.append(cid_str)
    if out or not match_key:
        return out

    tokens = match_key.split()
    if not tokens:
        return []
    search_tok = max((t for t in tokens if len(t) >= 2), key=len, default="")
    if len(search_tok) < 2:
        return []
    esc = escape_ilike_metacharacters(search_tok)
    pat = f"%{esc}%"
    scan_filters = [
        StylebookOrganizationCanonical.stylebook_id == stylebook_id,
        StylebookOrganizationCanonical.status == "active",
        StylebookOrganizationAlias.suppressed.is_(False),
        col(StylebookOrganizationAlias.normalized_alias).like(pat, escape="\\"),
    ]
    if trusted_alias_only:
        scan_filters.extend(
            (
                StylebookOrganizationAlias.provenance != "substrate_ingest",
                StylebookOrganizationAlias.provenance != GENERATED_ACRONYM_PROVENANCE,
            )
        )
    scan_stmt = (
        select(StylebookOrganizationCanonical.id, StylebookOrganizationAlias.normalized_alias)
        .join(
            StylebookOrganizationAlias,
            StylebookOrganizationAlias.organization_canonical_id
            == StylebookOrganizationCanonical.id,
        )
        .where(*scan_filters)
        .limit(120)
    )
    for cid, norm_alias in session.exec(scan_stmt).all():
        if cid is None:
            continue
        if organization_match_key(str(norm_alias or "")) != match_key:
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


def _organization_lookup_norms(
    organization: SubstrateOrganization,
    *,
    extra_lookup_names: tuple[str, ...] = (),
) -> tuple[str, ...]:
    norms: list[str] = []
    seen: set[str] = set()
    sources = [organization.normalized_name or organization.name, *extra_lookup_names]
    for source in sources:
        for key in organization_substrate_alias_lookup_keys(source):
            if key not in seen:
                seen.add(key)
                norms.append(key)
    return tuple(norms)


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
    elif (
        norm
        and label_norm
        and not multiword_organization_names_share_ambiguous_acronym(norm, label_norm)
        and organization_names_match_via_acronym(norm, label_norm)
    ):
        score = 90
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
    extra_lookup_names: tuple[str, ...] = (),
) -> list[tuple[str, str]]:
    """Ranked ``(canonical_id, label)`` for policy defer, LLM adjudication, and link UI."""
    lookup_norms = _organization_lookup_norms(
        organization,
        extra_lookup_names=extra_lookup_names,
    )
    if not lookup_norms:
        return []

    type_norm = _organization_type_norm(organization)
    scored: dict[str, tuple[int, str]] = {}

    exact_alias_ids: set[str] = set()
    for lookup_norm in lookup_norms:
        exact_alias_ids.update(
            canonical_ids_from_organization_name_keys(
                session,
                stylebook_id=stylebook_id,
                name_or_norm=lookup_norm,
            )
        )

    label_stmt = (
        select(StylebookOrganizationCanonical)
        .where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            StylebookOrganizationCanonical.status == "active",
        )
        .order_by(col(StylebookOrganizationCanonical.label).asc())
        .limit(max(limit * 8, 96))
    )
    for canon in session.exec(label_stmt).all():
        if canon.id is None:
            continue
        cid = str(canon.id)
        score = 0
        for lookup_norm in lookup_norms:
            score = max(
                score,
                _score_canonical_for_organization(
                    norm=lookup_norm,
                    type_norm=type_norm,
                    canon=canon,
                ),
            )
        if cid in exact_alias_ids:
            score = max(score, 100)
        if score < ORGANIZATION_RECALL_MIN_SCORE:
            continue
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
