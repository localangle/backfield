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
)


def strict_type_group(location_type: str | None) -> frozenset[str] | None:
    """Return the strict compatibility group for ``location_type``, or ``None`` if flexible."""
    lt = (location_type or "").strip().lower()
    for group in _STRICT_TYPE_GROUPS:
        if lt in group:
            return group
    return None


def link_pair_allowed(_substrate_lt: str | None, _canonical_lt: str | None) -> bool:
    """Return ``True`` when substrate ↔ canonical types may be linked (symmetric).

    Policy is **permissive**: any ``location_type`` pair is allowed for auto-link,
    alias link, and adjudication. Wrong merges are meant to be prevented by scoring,
    recall, head-anchor gates, and human review—not by a fixed type matrix.

    Add explicit ``False`` cases here later if product rules require a deny-list.
    """
    return True


def types_are_comparable(_substrate_lt: str | None, _canonical_lt: str | None) -> bool:
    """Return True when a substrate/canonical pair should be *compared* for matching.

    Recall scoring compares candidates broadly. :func:`link_pair_allowed` is equally
    permissive for automatic linking; both default to allowing the pair.
    """
    return True
