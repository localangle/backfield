"""High-precision detection of obviously wrong location substrate-to-canonical links."""

from __future__ import annotations

import re
from typing import Any

from backfield_entities.canonical.link_matrix import types_are_comparable
from backfield_entities.ingest.geocode_cache.fingerprint import normalize_substrate_cache_query
from backfield_entities.ingest.geocode_cache.sanity import cache_hit_sane_for_substrate

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_LOCATION_STOP_WORDS: frozenset[str] = frozenset(
    {
        "al",
        "ak",
        "az",
        "ar",
        "ca",
        "co",
        "ct",
        "de",
        "fl",
        "ga",
        "hi",
        "id",
        "il",
        "in",
        "ia",
        "ks",
        "ky",
        "la",
        "ma",
        "md",
        "me",
        "mi",
        "mn",
        "mo",
        "ms",
        "mt",
        "nc",
        "nd",
        "ne",
        "nh",
        "nj",
        "nm",
        "nv",
        "ny",
        "oh",
        "ok",
        "or",
        "pa",
        "ri",
        "sc",
        "sd",
        "tn",
        "tx",
        "ut",
        "va",
        "vt",
        "wa",
        "wi",
        "wv",
        "wy",
        "dc",
        "usa",
        "us",
        "st",
        "street",
        "ave",
        "avenue",
        "rd",
        "road",
        "blvd",
        "boulevard",
        "dr",
        "drive",
        "ln",
        "lane",
        "ct",
        "court",
        "pl",
        "place",
        "the",
        "of",
        "and",
        "chicago",
        "illinois",
    }
)


def normalize_location_alias_key(value: str | None) -> str:
    """Normalized alias key for location substrate names."""
    return " ".join(str(value or "").strip().lower().split())


def _compare_key(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", (text or "").strip().lower()).strip()


def _first_segment_key(text: str) -> str:
    first = str(text or "").split(",")[0]
    return _compare_key(normalize_substrate_cache_query(first))


def _meaningful_location_tokens(text: str) -> frozenset[str]:
    key = _compare_key(text)
    if not key:
        return frozenset()
    return frozenset(
        token
        for token in key.split()
        if len(token) >= 2 and token not in _LOCATION_STOP_WORDS
    )


def _strip_leading_the(head: str) -> str:
    tokens = head.split()
    if len(tokens) > 1 and tokens[0] == "the":
        return " ".join(tokens[1:])
    return head


def location_names_share_obvious_identity(
    substrate_name: str,
    canonical_label: str,
) -> bool:
    """True when names clearly refer to the same place despite type or tail variance."""
    if _compare_key(substrate_name) == _compare_key(canonical_label):
        return True

    sub_seg = _strip_leading_the(_first_segment_key(substrate_name))
    canon_seg = _strip_leading_the(_first_segment_key(canonical_label))
    if sub_seg and sub_seg == canon_seg and len(sub_seg) >= 4:
        return True
    sub_head_blob = _compare_key(str(substrate_name or "").split(",")[0])
    canon_head_blob = _compare_key(str(canonical_label or "").split(",")[0])
    if sub_head_blob and canon_head_blob:
        if len(sub_seg) >= 8 and len(canon_seg) >= 8:
            if sub_seg in canon_head_blob and len(sub_seg) >= 0.55 * len(sub_head_blob):
                return True
            if canon_seg in sub_head_blob and len(canon_seg) >= 0.55 * len(canon_head_blob):
                return True
    head_shared = _meaningful_location_tokens(
        str(substrate_name or "").split(",")[0]
    ) & _meaningful_location_tokens(str(canonical_label or "").split(",")[0])
    return len(head_shared) >= 2


def location_merge_pair_blocked(
    *,
    source_label: str,
    source_location_type: str | None,
    target_label: str,
    target_location_type: str | None,
) -> bool:
    """True when merging these canonicals would be an obvious scale/kind error.

    Blocks merges across deny-listed ``location_type`` pairs (e.g. a venue ``place``
    into its containing ``city``) unless the labels clearly name the same place —
    the identity escape hatch keeps mistyped rows of the same place mergeable.
    """
    if types_are_comparable(source_location_type, target_location_type):
        return False
    return not location_names_share_obvious_identity(source_label, target_label)


def location_link_is_obvious_mismatch(
    *,
    substrate_name: str,
    substrate_normalized_name: str,
    substrate_location_type: str | None,
    components: dict[str, Any] | None,
    formatted_address: str | None,
    geometry_type: str | None,
    canonical_label: str,
    canonical_location_type: str | None,
    editorial_alias_keys: frozenset[str] | set[str] | None = None,
) -> bool:
    """True when a linked substrate row is clearly not the same place as the canonical label."""
    norm_key = normalize_location_alias_key(substrate_normalized_name or substrate_name)
    alias_keys = editorial_alias_keys or frozenset()
    if norm_key and norm_key in alias_keys:
        return False
    if _compare_key(substrate_name) == _compare_key(canonical_label):
        return False

    location_text = str(substrate_name or "").strip()
    if cache_hit_sane_for_substrate(
        substrate_location_type=substrate_location_type,
        location_text=location_text,
        components=components,
        match_label=canonical_label,
        match_formatted_address=formatted_address,
        match_location_type=canonical_location_type,
        match_geometry_type=geometry_type,
    ):
        return False

    if location_names_share_obvious_identity(location_text, canonical_label):
        return False

    return True
