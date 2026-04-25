"""DB-backed geocode cache: canonical (tier 1) then ``substrate_location_cache`` (tier 2)."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocationCache
from sqlmodel import Session, col, select

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


def _canonical_matches_normalized_query(
    c: StylebookLocationCanonical,
    *,
    normalized_query: str,
    alias_map: dict[int, tuple[str, ...]],
) -> bool:
    """True when normalized query equals normalized label or any normalized alias string."""
    if c.id is None:
        return False
    cid = int(c.id)
    if normalize_substrate_cache_query(str(c.label)) == normalized_query:
        return True
    for raw_alias in alias_map.get(cid, ()):
        if normalize_substrate_cache_query(raw_alias) == normalized_query:
            return True
    return False


def try_resolve_geocode_cache(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int,
    location_text: str,
    location_type: str | None,
) -> dict[str, Any] | None:
    """Return a **match dict** for geocode converters, or ``None``.

    Order: (1) **exact** normalized string match on canonical **label** or a non-suppressed
    **alias** (same ``normalize_substrate_cache_query`` as ingest / tier-2 fingerprint); at
    most one canonical may match, else ambiguous → miss; (2) ``substrate_location_cache`` by
    fingerprint; (3) miss.

    Tier 1 intentionally favors **precision over recall** (no fuzzy string scoring); misses
    accumulate cache rows / aliases over time.

    Match dicts work with ``stylebook_match_to_geocoding_result`` (tier 1) or
    ``cache_match_to_geocoding_result`` (tier 2); callers can distinguish via
    ``match["confidence"]["source"]`` (``canonical_db`` vs ``location_cache``).
    """
    lt = (location_type or "").strip().lower() or None
    normalized = normalize_substrate_cache_query(location_text)
    if not normalized:
        return None

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

    winners: list[StylebookLocationCanonical] = []
    for c in canons:
        if not _canonical_matches_normalized_query(
            c, normalized_query=normalized, alias_map=alias_map
        ):
            continue
        winners.append(c)

    if len(winners) == 1:
        winner = winners[0]
        if isinstance(winner.geometry_json, dict):
            return _canonical_to_stylebook_match_dict(winner)
    # len 0 → fall through; len > 1 → ambiguous, treat as miss for tier 1

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
