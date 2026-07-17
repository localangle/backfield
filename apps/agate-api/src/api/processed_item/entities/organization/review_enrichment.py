"""Enrich processed-item ``merged_organizations`` with persisted org and Stylebook link metadata."""

from __future__ import annotations

import copy
import re
from typing import Any

from api.processed_item.entities.review_identity import (
    add_unique_index,
    is_safe_legacy_raw_entry_id,
    ordered_row_keys,
    source_raw_entry_id,
)
from api.processed_item.mention_occurrences import (
    build_mention_occurrences_for_row,
)
from backfield_db import (
    Stylebook,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.entities.organization.types import organization_identity_fingerprint
from sqlmodel import Session, col, select

_WS_RE = re.compile(r"\s+")


def _normalize_name(value: str) -> str:
    return _WS_RE.sub(" ", value.strip().lower())


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _organization_fingerprint(organization: Any) -> str | None:
    if not isinstance(organization, dict):
        return None
    name = organization.get("name")
    org_type = _optional_text(organization.get("type"))
    if isinstance(name, str) and name.strip():
        return organization_identity_fingerprint(
            normalized_name=_normalize_name(name),
            organization_type=org_type,
        )
    return None


def _apply_mention_editorial_to_organization(
    organization: dict[str, Any],
    mention: SubstrateOrganizationMention,
) -> dict[str, Any]:
    out = copy.deepcopy(organization)
    role = mention.role_in_story
    if isinstance(role, str) and role.strip():
        out["role_in_story"] = role.strip()
    nature = mention.nature
    if isinstance(nature, str) and nature.strip():
        out["nature"] = nature.strip()
    tags = mention.nature_secondary_tags_json
    if isinstance(tags, list) and tags:
        out["nature_secondary_tags"] = copy.deepcopy(tags)
    return out


def _load_occurrences_by_mention_id(
    session: Session,
    *,
    mention_ids: list[int],
) -> dict[int, list[SubstrateOrganizationMentionOccurrence]]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateOrganizationMentionOccurrence)
        .where(col(SubstrateOrganizationMentionOccurrence.organization_mention_id).in_(mention_ids))
        .order_by(
            col(SubstrateOrganizationMentionOccurrence.organization_mention_id),
            col(SubstrateOrganizationMentionOccurrence.occurrence_order).asc().nulls_last(),
            col(SubstrateOrganizationMentionOccurrence.id),
        )
    ).all()
    out: dict[int, list[SubstrateOrganizationMentionOccurrence]] = {}
    for row in rows:
        mid = int(row.organization_mention_id)
        out.setdefault(mid, []).append(row)
    return out


def _load_mentions_by_organization_for_article(
    session: Session,
    *,
    article_id: int | None,
) -> dict[int, SubstrateOrganizationMention]:
    if article_id is None:
        return {}
    rows = session.exec(
        select(SubstrateOrganizationMention).where(
            SubstrateOrganizationMention.article_id == article_id,
            col(SubstrateOrganizationMention.deleted).is_(False),
        )
    ).all()
    return {int(m.organization_id): m for m in rows}


def _load_substrate_organizations_for_review(
    session: Session,
    *,
    project_id: int,
    article_id: int | None,
) -> list[SubstrateOrganization]:
    if project_id <= 0:
        return []
    organization_ids: list[int] = []
    if article_id is not None:
        mentions = session.exec(
            select(SubstrateOrganizationMention).where(
                SubstrateOrganizationMention.article_id == article_id,
                col(SubstrateOrganizationMention.deleted).is_(False),
            )
        ).all()
        organization_ids = [int(m.organization_id) for m in mentions]
        if not organization_ids:
            return []
        rows = session.exec(
            select(SubstrateOrganization).where(
                col(SubstrateOrganization.id).in_(organization_ids),
                SubstrateOrganization.project_id == project_id,
            )
        ).all()
        return list(rows)

    # Without a persisted article scope, do not fan in run-wide substrate rows (batch runs
    # would otherwise bleed entities from sibling items onto failed or in-flight items).
    return []


def _load_canonicals_by_id(
    session: Session, canonical_ids: set[str]
) -> dict[str, StylebookOrganizationCanonical]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(StylebookOrganizationCanonical).where(
            col(StylebookOrganizationCanonical.id).in_(list(canonical_ids))
        )
    ).all()
    return {str(row.id): row for row in rows}


def _load_stylebook_slugs_by_id(
    session: Session, stylebook_ids: set[int]
) -> dict[int, str]:
    if not stylebook_ids:
        return {}
    rows = session.exec(
        select(Stylebook).where(col(Stylebook.id).in_(list(stylebook_ids)))
    ).all()
    out: dict[int, str] = {}
    for row in rows:
        if row.id is not None:
            out[int(row.id)] = str(row.slug)
    return out


def _pick_unclaimed_organization(
    index: dict[str, SubstrateOrganization | None],
    keys: list[str],
    claimed_ids: set[int],
) -> SubstrateOrganization | None:
    for key in keys:
        hit = index.get(key)
        if hit is not None and hit.id is not None and int(hit.id) not in claimed_ids:
            return hit
    return None


def _build_organization_indexes(
    organizations: list[SubstrateOrganization],
    *,
    mentions_by_organization: dict[int, SubstrateOrganizationMention],
    run_id: str,
) -> tuple[
    dict[str, SubstrateOrganization | None],
    dict[str, SubstrateOrganization | None],
    dict[str, SubstrateOrganization | None],
]:
    article_anchor_index: dict[str, SubstrateOrganization | None] = {}
    fingerprint_index: dict[str, SubstrateOrganization | None] = {}
    legacy_anchor_index: dict[str, SubstrateOrganization | None] = {}
    for organization in organizations:
        if organization.id is None:
            continue
        mention = mentions_by_organization.get(int(organization.id))
        article_anchor = source_raw_entry_id(
            mention.source_details_json if mention is not None else None,
            run_id=run_id,
        )
        add_unique_index(
            article_anchor_index,
            key=article_anchor,
            entity=organization,
        )
        fingerprint = (
            organization.identity_fingerprint.strip()
            if isinstance(organization.identity_fingerprint, str)
            else ""
        )
        add_unique_index(
            fingerprint_index,
            key=fingerprint or None,
            entity=organization,
        )
        legacy_anchor = source_raw_entry_id(organization.source_details_json, run_id=run_id)
        if legacy_anchor and is_safe_legacy_raw_entry_id(legacy_anchor):
            add_unique_index(
                legacy_anchor_index,
                key=legacy_anchor,
                entity=organization,
            )
    return article_anchor_index, fingerprint_index, legacy_anchor_index


def _organization_payload_from_substrate(organization: SubstrateOrganization) -> dict[str, Any]:
    return {
        "id": f"user_organization:{int(organization.id)}" if organization.id is not None else None,
        "name": str(organization.name),
        "type": organization.organization_type,
    }


def _attach_organization_identity(
    out: dict[str, Any],
    *,
    organization: SubstrateOrganization,
    canons: dict[str, StylebookOrganizationCanonical],
    stylebook_slugs: dict[int, str],
) -> None:
    if organization.id is None:
        return
    out["persisted_organization_id"] = int(organization.id)
    cid = organization.stylebook_organization_canonical_id
    if cid and str(organization.canonical_link_status) == CANONICAL_LINK_LINKED:
        canon = canons.get(str(cid))
        out["stylebook_organization_canonical_id"] = str(cid)
        if canon is not None:
            sb_slug = stylebook_slugs.get(int(canon.stylebook_id))
            if sb_slug:
                out["stylebook_slug"] = sb_slug
            out["stylebook_link"] = {"label": str(canon.label)}
    link_status = str(organization.canonical_link_status or "")
    if link_status:
        out["canonical_link_status"] = link_status


def _appended_organization_anchor(
    organization: SubstrateOrganization,
    mention: SubstrateOrganizationMention | None,
) -> str:
    article_anchor = source_raw_entry_id(
        mention.source_details_json if mention is not None else None
    )
    if article_anchor:
        return article_anchor
    legacy_anchor = source_raw_entry_id(organization.source_details_json)
    if legacy_anchor and is_safe_legacy_raw_entry_id(legacy_anchor):
        return legacy_anchor
    return f"user_organization:{int(organization.id)}"


def enrich_merged_organizations_for_review(
    session: Session,
    *,
    project_id: int,
    run_id: str,
    article_id: int | None,
    merged_organizations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach persisted organization identity and Stylebook link summary to merged rows."""
    organizations = _load_substrate_organizations_for_review(
        session, project_id=project_id, article_id=article_id
    )
    mentions_by_organization = _load_mentions_by_organization_for_article(
        session, article_id=article_id
    )
    mention_ids = [
        int(m.id) for m in mentions_by_organization.values() if m.id is not None
    ]
    occurrences_by_mention_id = _load_occurrences_by_mention_id(
        session, mention_ids=mention_ids
    )
    if not organizations:
        return merged_organizations

    canonical_ids: set[str] = set()
    for organization in organizations:
        cid = organization.stylebook_organization_canonical_id
        if cid and str(organization.canonical_link_status) == CANONICAL_LINK_LINKED:
            canonical_ids.add(str(cid))
    canons = _load_canonicals_by_id(session, canonical_ids)
    stylebook_ids = {int(c.stylebook_id) for c in canons.values()}
    stylebook_slugs = _load_stylebook_slugs_by_id(session, stylebook_ids)
    article_anchor_index, fingerprint_index, legacy_anchor_index = _build_organization_indexes(
        organizations,
        mentions_by_organization=mentions_by_organization,
        run_id=run_id,
    )

    enriched: list[dict[str, Any]] = []
    matched_organization_ids: set[int] = set()
    for row in merged_organizations:
        out = copy.deepcopy(row)
        organization_payload = out.get("organization")
        keys = ordered_row_keys(organization_payload, out.get("anchor"))
        substrate = _pick_unclaimed_organization(
            article_anchor_index,
            keys,
            matched_organization_ids,
        )
        if substrate is None:
            fingerprint = _organization_fingerprint(organization_payload)
            substrate = _pick_unclaimed_organization(
                fingerprint_index,
                [fingerprint] if fingerprint else [],
                matched_organization_ids,
            )
        if substrate is None:
            safe_legacy_keys = [key for key in keys if is_safe_legacy_raw_entry_id(key)]
            substrate = _pick_unclaimed_organization(
                legacy_anchor_index,
                safe_legacy_keys,
                matched_organization_ids,
            )
        if substrate is None or substrate.id is None:
            enriched.append(out)
            continue

        mention = mentions_by_organization.get(int(substrate.id))
        matched_organization_ids.add(int(substrate.id))
        _attach_organization_identity(
            out,
            organization=substrate,
            canons=canons,
            stylebook_slugs=stylebook_slugs,
        )

        if isinstance(organization_payload, dict):
            if mention is not None:
                organization_payload = _apply_mention_editorial_to_organization(
                    organization_payload, mention
                )
            db_rows: list[SubstrateOrganizationMentionOccurrence] | None = None
            if mention is not None and mention.id is not None:
                db_rows = occurrences_by_mention_id.get(int(mention.id))
            mention_occurrences = build_mention_occurrences_for_row(
                place=organization_payload,
                overlay_patch=None,
                db_rows=db_rows,
            )
            out["organization"] = organization_payload
            out["mention_occurrences"] = mention_occurrences
        enriched.append(out)

    for substrate in organizations:
        if substrate.id is None or int(substrate.id) in matched_organization_ids:
            continue
        mention = mentions_by_organization.get(int(substrate.id))
        if article_id is not None and mention is None:
            continue
        organization_payload = _organization_payload_from_substrate(substrate)
        if mention is not None:
            organization_payload = _apply_mention_editorial_to_organization(
                organization_payload, mention
            )
        db_rows: list[SubstrateOrganizationMentionOccurrence] | None = None
        if mention is not None and mention.id is not None:
            db_rows = occurrences_by_mention_id.get(int(mention.id))
        mention_occurrences = build_mention_occurrences_for_row(
            place=organization_payload,
            overlay_patch=None,
            db_rows=db_rows,
        )
        appended = {
            "anchor": _appended_organization_anchor(substrate, mention),
            "source": "user",
            "node_id": None,
            "index_in_node": None,
            "stale": False,
            "organization": organization_payload,
            "mention_occurrences": mention_occurrences,
        }
        _attach_organization_identity(
            appended,
            organization=substrate,
            canons=canons,
            stylebook_slugs=stylebook_slugs,
        )
        enriched.append(appended)
    return enriched
