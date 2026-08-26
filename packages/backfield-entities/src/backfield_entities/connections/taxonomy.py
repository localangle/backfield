"""Connection taxonomy constants and helpers (preferred natures live in ``natures``)."""

from __future__ import annotations

from backfield_entities.connections.natures import (
    AUTO_LINK_ENDPOINT_PAIRS,
    BASED_IN_LOCATION_TYPES,
    BORN_IN_LOCATION_TYPES,
    FOUNDED_IN_LOCATION_TYPES,
    HOLDS_OFFICE_IN_LOCATION_TYPES,
    LIVES_IN_LOCATION_TYPES,
    LOCATED_AT_LOCATION_TYPES,
    OPERATES_OR_SERVES_LOCATION_TYPES,
    OWNS_PROPERTY_IN_LOCATION_TYPES,
    REPRESENTS_PERSON_LOCATION_TYPES,
    allowed_location_types_for_auto_nature,
    auto_link_natures_for_pair,
    is_auto_link_endpoint_pair,
    person_location_forbidden_location_types,
    preferred_natures_for_pair,
)

AUTO_CONNECTION_MIN_CONFIDENCE = 0.9
AUTO_CONNECTION_EVIDENCE_SOURCE = "dboutput_auto_connections"
AUTO_CONNECTION_PROMPT_VERSION = "auto_connections_v1"
AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS = "auto_connections_v6"

__all__ = [
    "AUTO_CONNECTION_EVIDENCE_SOURCE",
    "AUTO_CONNECTION_MIN_CONFIDENCE",
    "AUTO_CONNECTION_PROMPT_VERSION",
    "AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS",
    "AUTO_LINK_ENDPOINT_PAIRS",
    "BASED_IN_LOCATION_TYPES",
    "BORN_IN_LOCATION_TYPES",
    "FOUNDED_IN_LOCATION_TYPES",
    "HOLDS_OFFICE_IN_LOCATION_TYPES",
    "LIVES_IN_LOCATION_TYPES",
    "LOCATED_AT_LOCATION_TYPES",
    "OPERATES_OR_SERVES_LOCATION_TYPES",
    "OWNS_PROPERTY_IN_LOCATION_TYPES",
    "REPRESENTS_PERSON_LOCATION_TYPES",
    "allowed_location_types_for_auto_nature",
    "auto_link_natures_for_pair",
    "is_auto_link_endpoint_pair",
    "person_location_forbidden_location_types",
    "preferred_natures_for_pair",
]
