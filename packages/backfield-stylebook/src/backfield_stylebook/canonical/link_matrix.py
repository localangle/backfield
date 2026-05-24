"""Symmetric substrate ↔ canonical ``location_type`` rules for linking.

Used by ingest policy, recall filtering, exact-alias checks, Stylebook suggestions,
and manual link validation.  Keeps :mod:`canonical_policy` free of import cycles
with :mod:`canonical_retrieval`.
"""

from __future__ import annotations

# Disjoint strict groups.  Types not in any group are "flexible" for pairing rules.
# Used by :func:`strict_type_group` for **intra-recall ambiguity** (multiple autolink-tier
# candidates in the same group), not for blocking links.
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
    frozenset({"political_district"}),
)


def strict_type_group(location_type: str | None) -> frozenset[str] | None:
    """Return the strict compatibility group for ``location_type``, or ``None`` if flexible."""
    lt = (location_type or "").strip().lower()
    for group in _STRICT_TYPE_GROUPS:
        if lt in group:
            return group
    return None


# Symmetric substrate ↔ canonical pairs denied for autolink / adjudication (manual link may bypass).
# Includes macro-region vs municipality (city/town↔region_city), region vs linear corridors,
# linear vs municipality, POI vs neighborhood/macro-region, neighborhood vs macro-region,
# POI/point vs municipality (city/town/village), and POI/point vs street_road
# (see docs/ARCHITECTURE.md ingest policy).
_DENY_AUTOLINK_TYPE_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"city", "county"}),
        frozenset({"town", "county"}),
        # Municipality must not merge with parent state (e.g. Springfield, IL ↔ Illinois).
        frozenset({"city", "state"}),
        frozenset({"town", "state"}),
        frozenset({"village", "state"}),
        frozenset({"city", "region_state"}),
        frozenset({"town", "region_state"}),
        frozenset({"village", "region_state"}),
        frozenset({"address", "neighborhood"}),
        # Intersections must not collapse onto POI identity.
        frozenset({"intersection_road", "place"}),
        frozenset({"intersection_road", "point"}),
        frozenset({"intersection_highway", "place"}),
        frozenset({"intersection_highway", "point"}),
        # Street-level extracts must not collapse onto municipality or macro admin canonicals.
        frozenset({"address", "city"}),
        frozenset({"address", "town"}),
        frozenset({"address", "village"}),
        frozenset({"address", "county"}),
        frozenset({"address", "state"}),
        frozenset({"city", "neighborhood"}),
        frozenset({"town", "neighborhood"}),
        frozenset({"village", "neighborhood"}),
        frozenset({"street_road", "neighborhood"}),
        frozenset({"intersection_road", "neighborhood"}),
        frozenset({"intersection_highway", "neighborhood"}),
        frozenset({"span", "neighborhood"}),
        # Colloquial macro-regions must not merge with municipalities or linear features.
        frozenset({"city", "region_city"}),
        frozenset({"town", "region_city"}),
        frozenset({"region_city", "street_road"}),
        frozenset({"region_city", "intersection_road"}),
        frozenset({"region_city", "intersection_highway"}),
        frozenset({"region_city", "span"}),
        # Linear features are not their containing city or town.
        frozenset({"city", "street_road"}),
        frozenset({"street_road", "town"}),
        frozenset({"city", "intersection_road"}),
        frozenset({"intersection_road", "town"}),
        frozenset({"city", "intersection_highway"}),
        frozenset({"intersection_highway", "town"}),
        frozenset({"city", "span"}),
        frozenset({"span", "town"}),
        # POI / macro-region / neighborhood identity must not collapse across these pairs.
        frozenset({"neighborhood", "place"}),
        frozenset({"place", "region_city"}),
        frozenset({"neighborhood", "region_city"}),
        # POI / point must not collapse onto a parent municipality canonical.
        frozenset({"city", "place"}),
        frozenset({"place", "town"}),
        frozenset({"place", "village"}),
        frozenset({"city", "point"}),
        frozenset({"point", "town"}),
        frozenset({"point", "village"}),
        # POI / point identity must not collapse onto a street corridor canonical.
        frozenset({"place", "street_road"}),
        frozenset({"point", "street_road"}),
        # Municipality mentions must not collapse onto electoral wards / districts.
        frozenset({"city", "political_district"}),
        frozenset({"town", "political_district"}),
        frozenset({"village", "political_district"}),
    }
)


def link_pair_allowed(substrate_lt: str | None, canonical_lt: str | None) -> bool:
    """Return ``True`` when substrate ↔ canonical types may be linked (symmetric).

    Deny-list (autolink / adjudication / manual type gate): blocks gross type mismatches
    such as linking a **state** substrate row to a **place** canonical.
    """
    s = (substrate_lt or "").strip().lower()
    c = (canonical_lt or "").strip().lower()
    if not s or not c:
        return True
    if frozenset({s, c}) in _DENY_AUTOLINK_TYPE_PAIRS:
        return False
    if s == "state" and c in ("place", "neighborhood", "address"):
        return False
    if s in ("country", "region_national") and c in ("place", "neighborhood", "address"):
        return False
    if s == "county" and c in ("place", "address"):
        return False
    return True


_CONTAINER_SUBSTRATE_TYPES: frozenset[str] = frozenset(
    {"city", "town", "village", "county", "region_city"}
)
_FINE_CANONICAL_TYPES: frozenset[str] = frozenset({"place", "neighborhood", "address"})


def autolink_container_to_fine_denied(substrate_lt: str | None, canonical_lt: str | None) -> bool:
    """True when a coarse substrate geography must not autolink to a fine-grained canonical."""
    s = (substrate_lt or "").strip().lower()
    c = (canonical_lt or "").strip().lower()
    return s in _CONTAINER_SUBSTRATE_TYPES and c in _FINE_CANONICAL_TYPES


def types_are_comparable(substrate_lt: str | None, canonical_lt: str | None) -> bool:
    """Return True when a substrate/canonical pair may enter recall or scoring.

    Uses the same gates as autolink (``link_pair_allowed`` and
    ``autolink_container_to_fine_denied``) so cross-type candidates such as
    **neighborhood ↔ place** are not recalled or ranked for fuzzy linking.
    """
    return link_pair_allowed(substrate_lt, canonical_lt) and not autolink_container_to_fine_denied(
        substrate_lt, canonical_lt
    )
