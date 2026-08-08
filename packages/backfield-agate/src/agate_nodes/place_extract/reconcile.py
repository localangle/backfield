"""Cross-chunk place stitching before GeocodeAgent."""

from __future__ import annotations

from typing import Any

from backfield_entities.text.match_normalize import normalize_match_text

from agate_nodes.extraction.grounding import ChunkCandidate, union_mention_texts


def _loc_key(place: dict[str, Any]) -> str:
    return normalize_match_text(str(place.get("location") or ""))


def _type_key(place: dict[str, Any]) -> str:
    return str(place.get("type") or "").strip().lower()


def _mention_texts(place: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for mention in place.get("mentions") or []:
        if isinstance(mention, dict):
            text = mention.get("text")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    original = place.get("original_text")
    if isinstance(original, str) and original.strip():
        out.append(original.strip())
    return out


def _jurisdiction_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_c = left.get("components") if isinstance(left.get("components"), dict) else {}
    right_c = right.get("components") if isinstance(right.get("components"), dict) else {}
    for key in ("city", "state", "country"):
        lv = normalize_match_text(str(left_c.get(key) or ""))
        rv = normalize_match_text(str(right_c.get(key) or ""))
        if lv and rv and lv != rv:
            return False
    return True


def _merge_place(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    left = _loc_key(merged)
    right = _loc_key(other)
    if len(right) > len(left):
        merged["location"] = other.get("location")
        if other.get("components"):
            merged["components"] = other["components"]
    for key in ("description", "geocode_hints", "nature", "type", "address_place_kind"):
        if not merged.get(key) and other.get(key):
            merged[key] = other[key]
    mention_texts = union_mention_texts(_mention_texts(merged), _mention_texts(other))
    mentions = [{"text": text} for text in mention_texts]
    merged["mentions"] = mentions
    if mentions:
        merged["original_text"] = mentions[0]["text"]
    return merged


def _short_name_of(full: str, short: str) -> bool:
    if not full or not short or full == short:
        return False
    if short in full:
        return True
    # Token containment: every short token appears in full.
    short_tokens = short.split()
    full_tokens = set(full.split())
    return bool(short_tokens) and all(tok in full_tokens for tok in short_tokens)


def stitch_place_candidates(
    candidates: list[ChunkCandidate[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], int]:
    owned = [c for c in candidates if c.owned and isinstance(c.payload, dict)]
    clusters: list[dict[str, Any]] = []
    unresolved = 0

    for candidate in sorted(owned, key=lambda c: (c.evidence.start if c.evidence else 0)):
        place = dict(candidate.payload)
        key = _loc_key(place)
        if not key:
            continue
        exact = [
            idx
            for idx, cluster in enumerate(clusters)
            if _loc_key(cluster) == key
            and _type_key(cluster) == _type_key(place)
            and _jurisdiction_compatible(cluster, place)
        ]
        if len(exact) == 1:
            clusters[exact[0]] = _merge_place(clusters[exact[0]], place)
            continue
        if exact:
            clusters.append(place)
            continue

        shortened = [
            idx
            for idx, cluster in enumerate(clusters)
            if _type_key(cluster) == _type_key(place)
            and _jurisdiction_compatible(cluster, place)
            and (
                _short_name_of(_loc_key(cluster), key)
                or _short_name_of(key, _loc_key(cluster))
            )
        ]
        if len(shortened) == 1:
            clusters[shortened[0]] = _merge_place(clusters[shortened[0]], place)
            continue
        if len(shortened) > 1:
            unresolved += 1
            continue
        clusters.append(place)

    return clusters, unresolved
