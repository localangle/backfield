"""Location canonical recall for ingest policy, link suggestions, and alias lookup."""

from __future__ import annotations

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical
from sqlmodel import Session, col, select

from backfield_entities.canonical.match_score import _loose_key
from backfield_entities.text.match_normalize import (
    alias_lookup_keys,
    escape_ilike_metacharacters,
    match_fold_key,
    normalize_match_text,
)


def location_alias_lookup_keys(value: str | None) -> tuple[str, ...]:
    """Alias keys stored on canonical labels and linked substrate names."""
    keys: set[str] = set(alias_lookup_keys(value))
    norm = normalize_match_text(value)
    if norm:
        loose = _loose_key(norm)
        if loose:
            keys.add(loose)
    return tuple(sorted(keys))


def canonical_ids_from_location_name_keys(
    session: Session,
    *,
    stylebook_id: int,
    name_or_norm: str,
    trusted_alias_only: bool = False,
) -> list[str]:
    """Canonical ids whose alias ``normalized_alias`` matches accent-insensitively.

    When ``trusted_alias_only`` is True, exclude ``substrate_ingest`` provenance so
    machine-written aliases cannot exact-match without editorial confirmation.
    """
    keys = set(location_alias_lookup_keys(name_or_norm))
    match_key = match_fold_key(name_or_norm)
    if not keys and not match_key:
        return []
    lookup_keys = set(keys)
    if match_key:
        lookup_keys.add(match_key)

    filters = [
        StylebookLocationCanonical.stylebook_id == stylebook_id,
        col(StylebookLocationAlias.normalized_alias).in_(lookup_keys),
        StylebookLocationAlias.suppressed.is_(False),
    ]
    if trusted_alias_only:
        filters.append(StylebookLocationAlias.provenance != "substrate_ingest")
    stmt = (
        select(StylebookLocationCanonical.id, StylebookLocationAlias.normalized_alias)
        .join(
            StylebookLocationAlias,
            StylebookLocationAlias.location_canonical_id == StylebookLocationCanonical.id,
        )
        .where(*filters)
    )
    out: list[str] = []
    seen: set[str] = set()
    for cid, norm_alias in session.exec(stmt).all():
        if cid is None:
            continue
        if match_key and match_fold_key(str(norm_alias or "")) != match_key:
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
        StylebookLocationCanonical.stylebook_id == stylebook_id,
        StylebookLocationAlias.suppressed.is_(False),
        col(StylebookLocationAlias.normalized_alias).like(pat, escape="\\"),
    ]
    if trusted_alias_only:
        scan_filters.append(StylebookLocationAlias.provenance != "substrate_ingest")
    scan_stmt = (
        select(StylebookLocationCanonical.id, StylebookLocationAlias.normalized_alias)
        .join(
            StylebookLocationAlias,
            StylebookLocationAlias.location_canonical_id == StylebookLocationCanonical.id,
        )
        .where(*scan_filters)
        .limit(120)
    )
    for cid, norm_alias in session.exec(scan_stmt).all():
        if cid is None:
            continue
        if match_fold_key(str(norm_alias or "")) != match_key:
            continue
        cid_str = str(cid)
        if cid_str not in seen:
            seen.add(cid_str)
            out.append(cid_str)
    return out
