"""Enrich processed-item ``merged_locations`` with persisted place and Stylebook link metadata."""

from __future__ import annotations

import copy
import json
from typing import Any

from api.processed_item_mention_occurrences import (
    build_mention_occurrences_for_row,
    sync_original_text_from_occurrences,
)
from backfield_db import (
    Stylebook,
    StylebookLocationCanonical,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_stylebook.canonical_link import CANONICAL_LINK_LINKED
from sqlmodel import Session, col, select


def _normalize_geometry_json(value: Any) -> Any:
    """Lightweight normalized JSON for equality (sorted keys, recursive)."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_normalize_geometry_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize_geometry_json(v) for k, v in sorted(value.items(), key=str)}
    return value


def geometries_json_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    return json.dumps(_normalize_geometry_json(a), sort_keys=True) == json.dumps(
        _normalize_geometry_json(b), sort_keys=True
    )


def geometry_differs_from_canonical(
    saved_geometry: dict[str, Any] | None,
    canonical_geometry: dict[str, Any] | None,
) -> bool:
    return not geometries_json_equal(saved_geometry, canonical_geometry)


def _identity_keys(location: Any, anchor: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(anchor, str) and anchor.strip():
        keys.add(anchor.strip())
    if not isinstance(location, dict):
        return keys
    for field in ("id", "mention_id"):
        raw = location.get(field)
        if raw is None or raw == "":
            continue
        keys.add(str(raw))
    return keys


def _apply_mention_editorial_to_place(
    place: dict[str, Any],
    mention: SubstrateLocationMention,
) -> dict[str, Any]:
    """Merge substrate mention editorial fields onto the review place payload."""
    out = copy.deepcopy(place)
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
) -> dict[int, list[SubstrateLocationMentionOccurrence]]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateLocationMentionOccurrence)
        .where(col(SubstrateLocationMentionOccurrence.location_mention_id).in_(mention_ids))
        .order_by(
            col(SubstrateLocationMentionOccurrence.location_mention_id),
            col(SubstrateLocationMentionOccurrence.occurrence_order).asc().nulls_last(),
            col(SubstrateLocationMentionOccurrence.id),
        )
    ).all()
    out: dict[int, list[SubstrateLocationMentionOccurrence]] = {}
    for row in rows:
        mid = int(row.location_mention_id)
        out.setdefault(mid, []).append(row)
    return out


def _load_mentions_by_location_for_article(
    session: Session,
    *,
    article_id: int | None,
) -> dict[int, SubstrateLocationMention]:
    if article_id is None:
        return {}
    rows = session.exec(
        select(SubstrateLocationMention).where(
            SubstrateLocationMention.article_id == article_id,
            col(SubstrateLocationMention.deleted).is_(False),
        )
    ).all()
    return {int(m.location_id): m for m in rows}


def _apply_persisted_geometry_to_place(
    place: dict[str, Any], geometry: dict[str, Any]
) -> dict[str, Any]:
    out = copy.deepcopy(place)
    prev_geocode = out.get("geocode")
    geocode: dict[str, Any]
    if isinstance(prev_geocode, dict):
        geocode = copy.deepcopy(prev_geocode)
    else:
        geocode = {"geocode_type": "manual", "result": {}}
    result = geocode.get("result")
    if not isinstance(result, dict):
        result = {}
        geocode["result"] = result
    else:
        result = copy.deepcopy(result)
        geocode["result"] = result
    result["geometry"] = copy.deepcopy(geometry)
    out["geocode"] = geocode
    return out


def _index_substrate_locations(
    locations: list[SubstrateLocation],
    *,
    run_id: str,
) -> dict[str, SubstrateLocation]:
    """Map raw_entry_id / anchor keys to substrate rows for this run."""
    by_key: dict[str, SubstrateLocation] = {}
    for loc in locations:
        details = loc.source_details_json if isinstance(loc.source_details_json, dict) else {}
        if str(details.get("run_id") or "") != run_id:
            continue
        raw_entry_id = details.get("raw_entry_id")
        if raw_entry_id is None or raw_entry_id == "":
            continue
        by_key[str(raw_entry_id)] = loc
    return by_key


def _load_substrate_locations_for_review(
    session: Session,
    *,
    project_id: int,
    run_id: str,
    article_id: int | None,
) -> dict[str, SubstrateLocation]:
    if project_id <= 0:
        return {}
    location_ids: list[int] = []
    if article_id is not None:
        mentions = session.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.article_id == article_id,
                col(SubstrateLocationMention.deleted).is_(False),
            )
        ).all()
        location_ids = [int(m.location_id) for m in mentions]
        if not location_ids:
            return {}
        rows = session.exec(
            select(SubstrateLocation).where(
                col(SubstrateLocation.id).in_(location_ids),
                SubstrateLocation.project_id == project_id,
            )
        ).all()
        return _index_substrate_locations(list(rows), run_id=run_id)

    rows = session.exec(
        select(SubstrateLocation).where(SubstrateLocation.project_id == project_id)
    ).all()
    return _index_substrate_locations(list(rows), run_id=run_id)


def _load_canonicals_by_id(
    session: Session, canonical_ids: set[str]
) -> dict[str, StylebookLocationCanonical]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(StylebookLocationCanonical).where(
            col(StylebookLocationCanonical.id).in_(list(canonical_ids))
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


def _pick_substrate_for_keys(
    by_key: dict[str, SubstrateLocation], keys: set[str]
) -> SubstrateLocation | None:
    for key in keys:
        hit = by_key.get(key)
        if hit is not None:
            return hit
    return None


def enrich_merged_locations_for_review(
    session: Session,
    *,
    project_id: int,
    run_id: str,
    article_id: int | None,
    merged_locations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach persisted place identity and Stylebook link summary to merged location rows."""
    if not merged_locations:
        return merged_locations

    by_key = _load_substrate_locations_for_review(
        session, project_id=project_id, run_id=run_id, article_id=article_id
    )
    mentions_by_location = _load_mentions_by_location_for_article(
        session, article_id=article_id
    )
    mention_ids = [
        int(m.id) for m in mentions_by_location.values() if m.id is not None
    ]
    occurrences_by_mention_id = _load_occurrences_by_mention_id(
        session, mention_ids=mention_ids
    )
    if not by_key:
        return merged_locations

    canonical_ids: set[str] = set()
    for loc in by_key.values():
        cid = loc.stylebook_location_canonical_id
        if cid and str(loc.canonical_link_status) == CANONICAL_LINK_LINKED:
            canonical_ids.add(str(cid))
    canons = _load_canonicals_by_id(session, canonical_ids)
    stylebook_ids = {int(c.stylebook_id) for c in canons.values()}
    stylebook_slugs = _load_stylebook_slugs_by_id(session, stylebook_ids)

    enriched: list[dict[str, Any]] = []
    for row in merged_locations:
        out = copy.deepcopy(row)
        loc_payload = out.get("location")
        keys = _identity_keys(loc_payload, out.get("anchor"))
        substrate = _pick_substrate_for_keys(by_key, keys)
        if substrate is None or substrate.id is None:
            enriched.append(out)
            continue

        out["persisted_location_id"] = int(substrate.id)
        cid = substrate.stylebook_location_canonical_id
        if cid and str(substrate.canonical_link_status) == CANONICAL_LINK_LINKED:
            canon = canons.get(str(cid))
            out["stylebook_location_canonical_id"] = str(cid)
            if canon is not None:
                sb_slug = stylebook_slugs.get(int(canon.stylebook_id))
                if sb_slug:
                    out["stylebook_slug"] = sb_slug
                saved_geom = (
                    substrate.geometry_json
                    if isinstance(substrate.geometry_json, dict)
                    else None
                )
                canon_geom = (
                    canon.geometry_json if isinstance(canon.geometry_json, dict) else None
                )
                out["stylebook_link"] = {
                    "label": str(canon.label),
                    "has_geometry": canon_geom is not None,
                    "geometry_differs": geometry_differs_from_canonical(saved_geom, canon_geom),
                }

        if isinstance(loc_payload, dict):
            mention = mentions_by_location.get(int(substrate.id))
            if mention is not None:
                loc_payload = _apply_mention_editorial_to_place(loc_payload, mention)
            if isinstance(substrate.geometry_json, dict):
                loc_payload = _apply_persisted_geometry_to_place(
                    loc_payload, substrate.geometry_json
                )
            db_rows: list[SubstrateLocationMentionOccurrence] | None = None
            if mention is not None and mention.id is not None:
                db_rows = occurrences_by_mention_id.get(int(mention.id))
            mention_occurrences = build_mention_occurrences_for_row(
                place=loc_payload,
                overlay_patch=None,
                db_rows=db_rows,
            )
            sync_original_text_from_occurrences(loc_payload, mention_occurrences)
            out["location"] = loc_payload
            out["mention_occurrences"] = mention_occurrences
        enriched.append(out)
    return enriched
