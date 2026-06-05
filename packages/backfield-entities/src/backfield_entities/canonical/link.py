"""Substrate canonical link status values (minimal v1 enum as strings)."""

from __future__ import annotations

CANONICAL_LINK_UNLINKED = "unlinked"
CANONICAL_LINK_PENDING = "pending"
CANONICAL_LINK_LINKED = "linked"
CANONICAL_LINK_WAIVED = "waived"

ALL_STATUSES = frozenset(
    {CANONICAL_LINK_UNLINKED, CANONICAL_LINK_PENDING, CANONICAL_LINK_LINKED, CANONICAL_LINK_WAIVED}
)
