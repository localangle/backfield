"""DB-backed geocode cache: canonical (tier 1) then ``substrate_location_cache`` (tier 2)."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocationCache
from sqlmodel import Session, col, select

from backfield_stylebook.canonical_match_score import (
    AUTOLINK_MIN_SCORE,
    CanonicalMatchFeatures,
    SubstrateMatchInput,
    head_region_anchored_on_canonical_naming,
    policy_match_score,
)
from backfield_stylebook.substrate_location_cache_fingerprint import (
    normalize_substrate_cache_query,
    substrate_location_cache_query_fingerprint,
)


def _canonical_to_stylebook_match_dict(canon: StylebookLocationCanonical) -> dict[str, Any]:
    """Match dict shape for ``stylebook_match_to_geocoding_result`` in agate_utils."""
    gj = canon.geometry_json if isinstance(canon.geometry_json, dict) else None
    boundaries: list[dict[str, Any]] = [dict(gj)] if gj else []
    gt = (canon.geometry_type or (gj.get("type") if gj else None) or "Point")
    cid = int(canon.id)  # type: ignore[arg-type]
    return {
        "id": cid,
        "label": str(canon.label),
        "name": str(canon.label),
        "boundaries": boundaries,
        "type": gt,
        "bbox": None,
        "confidence": {"source": "canonical_db", "canonical_id": cid},
    }


def _substrate_cache_row_to_cache_match_dict(row: SubstrateLocationCache) -> dict[str, Any]:
    """Shape compatible with ``cache_match_to_geocoding_result``."""
    gj = row.geometry_json if isinstance(row.geometry_json, dict) else None
    boundaries: list[dict[str, Any]] = [dict(gj)] if gj else []
    gt = str(row.geometry_type or (gj.get("type") if gj else "Polygon"))
    rid = int(row.id)  # type: ignore[arg-type]
    return {
        "id": rid,
        "label": row.location_name,
        "name": row.location_name,
        "boundaries": boundaries,
        "type": gt,
        "bbox": None,
        "confidence": {"source": "location_cache", "cache_id": rid},
    }


def _alias_map_for_canonicals(
    session: Session, canonical_ids: list[int]
) -> dict[int, tuple[str, ...]]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(StylebookLocationAlias).where(
            col(StylebookLocationAlias.location_canonical_id).in_(canonical_ids),
            col(StylebookLocationAlias.suppressed).is_(False),
        )
    ).all()
    acc: dict[int, list[str]] = {cid: [] for cid in canonical_ids}
    for a in rows:
        cid = int(a.location_canonical_id)
        if cid not in acc:
            continue
        norm = (a.normalized_alias or "").strip().lower()
        if norm:
            acc[cid].append(norm)
    return {cid: tuple(sorted(set(strings))) for cid, strings in acc.items()}


def try_resolve_geocode_cache(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int,
    location_text: str,
    location_type: str | None,
) -> dict[str, Any] | None:
    """Return a **match dict** for geocode converters, or ``None``.

    Order: (1) single high-confidence canonical (label + aliases only); (2) substrate cache
    row with geometry; (3) miss.

    Match dicts work with ``stylebook_match_to_geocoding_result`` (tier 1) or
    ``cache_match_to_geocoding_result`` (tier 2); callers can distinguish via
    ``match["confidence"]["source"]`` (``canonical_db`` vs ``location_cache``).
    """
    lt = (location_type or "").strip().lower() or None
    normalized = normalize_substrate_cache_query(location_text)
    if not normalized:
        return None

    substrate = SubstrateMatchInput(
        name=location_text.strip(),
        normalized_name=normalized,
        geometry_json=None,
        formatted_address=None,
    )

    canons = list(
        session.exec(
            select(StylebookLocationCanonical).where(
                col(StylebookLocationCanonical.stylebook_id) == stylebook_id,
                col(StylebookLocationCanonical.status) == "active",
            )
        ).all()
    )
    ids = [int(c.id) for c in canons if c.id is not None]
    alias_map = _alias_map_for_canonicals(session, ids)

    scored: list[tuple[float, StylebookLocationCanonical]] = []
    for c in canons:
        if c.id is None:
            continue
        cid = int(c.id)
        gj = c.geometry_json if isinstance(c.geometry_json, dict) else None
        features = CanonicalMatchFeatures(
            canonical_id=cid,
            label=str(c.label),
            normalized_aliases=alias_map.get(cid, ()),
            geometry_json=gj,
            retrieval_string_hint=None,
        )
        score = policy_match_score(
            substrate,
            features,
            substrate_location_type=lt,
        )
        if score >= AUTOLINK_MIN_SCORE and head_region_anchored_on_canonical_naming(
            location_text, features
        ):
            scored.append((score, c))

    if len(scored) == 1:
        _, winner = scored[0]
        if isinstance(winner.geometry_json, dict):
            return _canonical_to_stylebook_match_dict(winner)
    elif len(scored) > 1:
        return None

    fingerprint = substrate_location_cache_query_fingerprint(
        project_id=project_id,
        normalized_query=normalized,
        location_type=lt,
    )
    row = session.exec(
        select(SubstrateLocationCache).where(
            col(SubstrateLocationCache.project_id) == project_id,
            col(SubstrateLocationCache.query_fingerprint) == fingerprint,
        )
    ).first()
    if row is None:
        return None
    gj = row.geometry_json if isinstance(row.geometry_json, dict) else None
    if not gj:
        return None
    return _substrate_cache_row_to_cache_match_dict(row)
