"""Fixed taxonomy for automatic ``stylebook_connections`` edges (v1)."""

from __future__ import annotations

from backfield_entities.entities.location.types import ADDRESS_LIKE_LOCATION_TYPES

AUTO_CONNECTION_MIN_CONFIDENCE = 0.9
AUTO_CONNECTION_EVIDENCE_SOURCE = "dboutput_auto_connections"
AUTO_CONNECTION_PROMPT_VERSION = "auto_connections_v1"
AUTO_CONNECTION_PROMPT_VERSION_WITH_HINTS = "auto_connections_v2"

AUTO_LINK_ENDPOINT_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("person", "organization"),
        ("organization", "location"),
        ("person", "location"),
    }
)

PERSON_ORGANIZATION_NATURES: frozenset[str] = frozenset(
    {
        "works_for",
        "leads",
        "member_of",
        "founded",
        "represents",
    }
)

ORGANIZATION_LOCATION_NATURES: frozenset[str] = frozenset(
    {
        "located_at",
        "based_in",
        "operates_in",
        "serves",
        "founded_in",
    }
)

PERSON_LOCATION_NATURES: frozenset[str] = frozenset(
    {
        "represents",
        "lives_in",
        "born_in",
    }
)

# Concrete address/place targets for organization ``located_at``.
LOCATED_AT_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "place",
        "address",
        "address_intersection",
        "intersection_road",
        "intersection_highway",
        "street_road",
    }
)

# Broader locality targets for organization ``based_in``.
BASED_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "place",
        "neighborhood",
        "city",
        "county",
        "region_city",
    }
)

# Operating/service-area targets for organization ``operates_in`` / ``serves``.
OPERATES_OR_SERVES_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "county",
        "political_district",
        "state",
        "region_state",
        "region_city",
    }
)

FOUNDED_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "county",
        "region_city",
    }
)

LIVES_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "region_city",
    }
)

BORN_IN_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "county",
        "region_city",
    }
)

REPRESENTS_PERSON_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "political_district",
        "city",
        "county",
        "state",
        "region_state",
        "region_city",
    }
)

_NATURES_BY_PAIR: dict[tuple[str, str], frozenset[str]] = {
    ("person", "organization"): PERSON_ORGANIZATION_NATURES,
    ("organization", "location"): ORGANIZATION_LOCATION_NATURES,
    ("person", "location"): PERSON_LOCATION_NATURES,
}

_LOCATION_GRANULARITY_BY_NATURE: dict[str, frozenset[str]] = {
    "located_at": LOCATED_AT_LOCATION_TYPES,
    "based_in": BASED_IN_LOCATION_TYPES,
    "operates_in": OPERATES_OR_SERVES_LOCATION_TYPES,
    "serves": OPERATES_OR_SERVES_LOCATION_TYPES,
    "founded_in": FOUNDED_IN_LOCATION_TYPES,
    "lives_in": LIVES_IN_LOCATION_TYPES,
    "born_in": BORN_IN_LOCATION_TYPES,
    "represents": REPRESENTS_PERSON_LOCATION_TYPES,
}


def is_auto_link_endpoint_pair(from_entity_type: str, to_entity_type: str) -> bool:
    return (from_entity_type.strip().lower(), to_entity_type.strip().lower()) in (
        AUTO_LINK_ENDPOINT_PAIRS
    )


def auto_link_natures_for_pair(from_entity_type: str, to_entity_type: str) -> frozenset[str]:
    key = (from_entity_type.strip().lower(), to_entity_type.strip().lower())
    return _NATURES_BY_PAIR.get(key, frozenset())


def allowed_location_types_for_auto_nature(nature: str) -> frozenset[str] | None:
    """Return allowed ``location_type`` values when ``nature`` targets a location endpoint."""
    return _LOCATION_GRANULARITY_BY_NATURE.get(nature.strip().lower())


def person_location_forbidden_location_types() -> frozenset[str]:
    """Person-location auto-links never target address-like locations."""
    return ADDRESS_LIKE_LOCATION_TYPES
