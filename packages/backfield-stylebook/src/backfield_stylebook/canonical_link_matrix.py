"""Symmetric substrate ↔ canonical ``location_type`` rules for linking.

Used by ingest policy, recall filtering, exact-alias checks, Stylebook suggestions,
and manual link validation.  Keeps :mod:`canonical_policy` free of import cycles
with :mod:`canonical_retrieval`.
"""

from __future__ import annotations

from backfield_stylebook.place_extract_location_types import is_address_like_location_type

# Disjoint strict groups.  Types not in any group are "flexible" for pairing rules.
_STRICT_TYPE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"country", "region_national"}),
    frozenset({"state", "region_state"}),
    frozenset({"county"}),
    frozenset({"city", "town"}),
    frozenset(
        {
            "neighborhood",
            "community_area",
            "district",
            "borough",
            "suburb",
            "village",
        }
    ),
    frozenset({"region_city"}),
)


def strict_type_group(location_type: str | None) -> frozenset[str] | None:
    """Return the strict compatibility group for ``location_type``, or ``None`` if flexible."""
    lt = (location_type or "").strip().lower()
    for group in _STRICT_TYPE_GROUPS:
        if lt in group:
            return group
    return None


def _cross_type_place_address_pair(substrate_lt: str, canonical_lt: str) -> bool:
    """Intentional exception: address-like types may link with ``place`` (both directions)."""
    s = substrate_lt.strip().lower()
    c = canonical_lt.strip().lower()
    return (is_address_like_location_type(s) and c == "place") or (
        is_address_like_location_type(c) and s == "place"
    )


def link_pair_allowed(substrate_lt: str | None, canonical_lt: str | None) -> bool:
    """Return ``True`` when a substrate type may link to a canonical type (symmetric).

    Rules:
    - Missing **substrate** type: allow (cannot infer incompatibility).
    - Explicit **address-like ↔ place** cross (see :func:`is_address_like_location_type`).
    - If both sides are outside strict groups (fully flexible): allow.
    - If **either** side is in a strict group and the other is not: deny (no strict↔flexible
      except the place/address exception above).
    - If **both** are strict: allow only when they share the same strict group.
    """
    if not (substrate_lt or "").strip():
        return True

    s = (substrate_lt or "").strip().lower()
    c_raw = (canonical_lt or "").strip().lower() if (canonical_lt or "").strip() else ""

    if c_raw and _cross_type_place_address_pair(s, c_raw):
        return True

    sg = strict_type_group(s)
    cg = strict_type_group(c_raw) if c_raw else None

    if sg is None and cg is None:
        return True
    if sg is None or cg is None:
        return False
    return sg is cg


def types_are_comparable(substrate_lt: str | None, canonical_lt: str | None) -> bool:
    """Return True when a substrate/canonical pair should be *compared* for matching.

    This is intentionally **more permissive** than :func:`link_pair_allowed`, because:
    - Canonical `location_type` may be user-defined (uploaded geometries), not from PlaceExtract.
    - Substrate `location_type` may reflect a geocoder/LLM label that we do not control.

    The strict safety decision (whether we may automatically link) remains with
    :func:`link_pair_allowed`.
    """
    # Missing types: allow comparison; we can't infer incompatibility.
    if not (substrate_lt or "").strip():
        return True
    if not (canonical_lt or "").strip():
        return True
    # Default posture: compare broadly; link narrowly.
    return True
