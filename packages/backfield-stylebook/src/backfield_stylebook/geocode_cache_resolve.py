"""DB-backed geocode cache: canonical (tier 1) then ``substrate_location_cache`` (tier 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocationCache
from sqlmodel import Session, col, select

from backfield_stylebook.canonical_link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_stylebook.canonical_retrieval import (
    load_canonical_match_features,
    retrieve_candidate_canonical_ids,
)
from backfield_stylebook.substrate_location_cache_fingerprint import (
    normalize_substrate_cache_query,
    substrate_location_cache_query_fingerprint,
)

_DEFAULT_ADJUDICATION_CANDIDATE_LIMIT: int = 18


def _canonical_to_stylebook_match_dict(canon: StylebookLocationCanonical) -> dict[str, Any]:
    """Match dict shape for ``stylebook_match_to_geocoding_result`` in agate_utils."""
    gj = canon.geometry_json if isinstance(canon.geometry_json, dict) else None
    boundaries: list[dict[str, Any]] = [dict(gj)] if gj else []
    gt = (canon.geometry_type or (gj.get("type") if gj else None) or "Point")
    cid = str(canon.id)
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
    session: Session, canonical_ids: list[str]
) -> dict[str, tuple[str, ...]]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(StylebookLocationAlias).where(
            col(StylebookLocationAlias.location_canonical_id).in_(canonical_ids),
            col(StylebookLocationAlias.suppressed).is_(False),
        )
    ).all()
    acc: dict[str, list[str]] = {cid: [] for cid in canonical_ids}
    for a in rows:
        cid = str(a.location_canonical_id)
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
    alias_map: dict[str, tuple[str, ...]],
) -> bool:
    """True when normalized query equals normalized label or any normalized alias string."""
    if c.id is None:
        return False
    cid = str(c.id)
    if normalize_substrate_cache_query(str(c.label)) == normalized_query:
        return True
    for raw_alias in alias_map.get(cid, ()):
        if normalize_substrate_cache_query(raw_alias) == normalized_query:
            return True
    return False


def _tier1_exact_winners(
    session: Session,
    stylebook_id: int,
    normalized_query: str,
) -> list[StylebookLocationCanonical]:
    canons = list(
        session.exec(
            select(StylebookLocationCanonical).where(
                col(StylebookLocationCanonical.stylebook_id) == stylebook_id,
                col(StylebookLocationCanonical.status) == "active",
            )
        ).all()
    )
    ids = [str(c.id) for c in canons if c.id is not None]
    alias_map = _alias_map_for_canonicals(session, ids)
    winners: list[StylebookLocationCanonical] = []
    for c in canons:
        if not _canonical_matches_normalized_query(
            c, normalized_query=normalized_query, alias_map=alias_map
        ):
            continue
        winners.append(c)
    return winners


def _strict_type_pair_allowed(substrate_lt: str | None, canonical_lt: str | None) -> bool:
    """Gate tier-1 singleton auto-hit using Stylebook link policy."""
    if not link_pair_allowed(substrate_lt, canonical_lt):
        return False
    if autolink_container_to_fine_denied(substrate_lt, canonical_lt):
        return False
    return True


def _substrate_cache_passes_component_sanity(
    row: SubstrateLocationCache,
    *,
    normalized_query: str,
    components: dict[str, Any],
) -> bool:
    """Cheap check: state abbreviation from PlaceExtract should appear in cache row strings."""
    state_info = components.get("state")
    if not isinstance(state_info, dict):
        return True
    abbr = state_info.get("abbr")
    if not isinstance(abbr, str) or not abbr.strip():
        return True
    needle = abbr.strip().lower()
    parts = [
        normalized_query,
        normalize_substrate_cache_query(str(row.location_name or "")),
        normalize_substrate_cache_query(str(row.formatted_address or "")),
        normalize_substrate_cache_query(str(row.query_text or "")),
    ]
    hay = " ".join(p for p in parts if p)
    return needle in hay


@dataclass(frozen=True)
class GeocodeCacheStrictOutcome:
    """Result of strict DB cache resolution (deterministic tiers only)."""

    match_dict: dict[str, Any] | None
    ambiguous_tier1: bool
    tier2_sanity_failed: bool


def resolve_geocode_cache_strict_with_outcome(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int,
    location_text: str,
    location_type: str | None,
    components: dict[str, Any] | None = None,
) -> GeocodeCacheStrictOutcome:
    """Strict tiers only; no LLM. Tier 2 is skipped when tier 1 is ambiguous."""

    lt = (location_type or "").strip().lower() or None
    substrate_lt = lt
    normalized = normalize_substrate_cache_query(location_text)
    if not normalized:
        return GeocodeCacheStrictOutcome(None, False, False)

    winners = _tier1_exact_winners(session, stylebook_id, normalized)

    if len(winners) > 1:
        return GeocodeCacheStrictOutcome(None, True, False)

    if len(winners) == 1:
        winner = winners[0]
        canon_lt = (winner.location_type or "").strip().lower() or None
        geom_ok = isinstance(winner.geometry_json, dict)
        if geom_ok and _strict_type_pair_allowed(substrate_lt, canon_lt):
            return GeocodeCacheStrictOutcome(
                _canonical_to_stylebook_match_dict(winner),
                False,
                False,
            )

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
        return GeocodeCacheStrictOutcome(None, False, False)
    gj = row.geometry_json if isinstance(row.geometry_json, dict) else None
    if not gj:
        return GeocodeCacheStrictOutcome(None, False, False)
    if isinstance(components, dict) and components:
        sane = _substrate_cache_passes_component_sanity(
            row,
            normalized_query=normalized,
            components=components,
        )
        if not sane:
            return GeocodeCacheStrictOutcome(None, False, True)
    return GeocodeCacheStrictOutcome(_substrate_cache_row_to_cache_match_dict(row), False, False)


def try_resolve_geocode_cache(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int,
    location_text: str,
    location_type: str | None,
    components: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a **match dict** for geocode converters, or ``None``.

    Same contract as historical callers; forwards to
    :func:`resolve_geocode_cache_strict_with_outcome`.

    Order: (1) **exact** normalized string match on canonical **label** or a non-suppressed
    **alias**; exactly one canonical must match and pass **type policy** gate; (2) ambiguous
    tier 1 → ``None`` (**no** tier 2); (3) ``substrate_location_cache`` by fingerprint with
    optional **component sanity** when ``components`` is provided; (4) miss.

    Match dicts work with ``stylebook_match_to_geocoding_result`` (tier 1) or
    ``cache_match_to_geocoding_result`` (tier 2); callers can distinguish via
    ``match["confidence"]["source"]`` (``canonical_db`` vs ``location_cache``).
    """
    return resolve_geocode_cache_strict_with_outcome(
        session,
        project_id=project_id,
        stylebook_id=stylebook_id,
        location_text=location_text,
        location_type=location_type,
        components=components,
    ).match_dict


def materialize_canonical_match_dict(
    session: Session,
    *,
    stylebook_id: int,
    canonical_id: str,
) -> dict[str, Any] | None:
    """Load active canonical geometry into converter match dict shape, or ``None``."""
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None:
        return None
    if int(canon.stylebook_id) != int(stylebook_id):
        return None
    if (canon.status or "").strip().lower() != "active":
        return None
    if not isinstance(canon.geometry_json, dict):
        return None
    return _canonical_to_stylebook_match_dict(canon)


def build_geocode_cache_adjudication_candidates(
    session: Session,
    *,
    stylebook_id: int,
    location_text: str,
    location_type: str | None,
    components: dict[str, Any] | None = None,
    limit: int = _DEFAULT_ADJUDICATION_CANDIDATE_LIMIT,
) -> list[dict[str, Any]]:
    """Permissive canonical recall for LLM adjudication (no substrate-type filtering).

    Prefers tier-1 ambiguous exact winners first, then merges trigram alias recall with
    ``substrate_location_type=None``.
    """
    _ = components
    normalized = normalize_substrate_cache_query(location_text)
    if not normalized:
        return []

    winners = _tier1_exact_winners(session, stylebook_id, normalized)
    ordered_ids: list[str] = []
    seen: set[str] = set()

    if len(winners) > 1:
        for w in winners:
            if w.id is None:
                continue
            cid = str(w.id)
            if cid not in seen:
                seen.add(cid)
                ordered_ids.append(cid)

    recall = retrieve_candidate_canonical_ids(
        session,
        stylebook_id=stylebook_id,
        query_text=location_text,
        normalized_query=normalized,
        formatted_address=None,
        limit=max(limit, 24),
        substrate_location_type=None,
    )
    for cid, _hint in recall:
        if cid not in seen:
            seen.add(cid)
            ordered_ids.append(cid)
        if len(ordered_ids) >= limit:
            break

    ordered_ids = ordered_ids[:limit]
    if not ordered_ids:
        return []

    features = load_canonical_match_features(session, canonical_ids=ordered_ids)
    out: list[dict[str, Any]] = []
    for cid in ordered_ids:
        tup = features.get(cid)
        if tup is None:
            continue
        canon, alias_tuple = tup
        aliases = list(alias_tuple)[:8]
        out.append(
            {
                "id": str(canon.id),
                "label": str(canon.label),
                "location_type": canon.location_type,
                "formatted_address": canon.formatted_address,
                "aliases": aliases,
            }
        )
    return out


def try_resolve_substrate_location_cache_geometry(
    session: Session,
    *,
    project_id: int,
    location_text: str,
) -> dict[str, Any] | None:
    """Return GeoJSON geometry from tier-2 cache only (no canonical tier).

    Uses ``location_type="city"`` in the fingerprint so container admin strings share a stable
    bucket distinct from POI queries with the same free text.
    """
    normalized = normalize_substrate_cache_query(location_text)
    if not normalized:
        return None
    fingerprint = substrate_location_cache_query_fingerprint(
        project_id=project_id,
        normalized_query=normalized,
        location_type="city",
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
    return dict(gj) if gj else None
