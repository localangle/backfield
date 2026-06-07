"""Automatic Stylebook connection contracts (taxonomy, evidence, validation)."""

from backfield_entities.connections.evidence import (
    ConnectionCreationEvidence,
    build_connection_creation_evidence,
)
from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_MIN_CONFIDENCE,
    AUTO_LINK_ENDPOINT_PAIRS,
    auto_link_natures_for_pair,
    is_auto_link_endpoint_pair,
)
from backfield_entities.connections.validation import (
    AutoConnectionValidationResult,
    validate_auto_connection_candidate,
)

__all__ = [
    "AUTO_CONNECTION_MIN_CONFIDENCE",
    "AUTO_LINK_ENDPOINT_PAIRS",
    "AutoConnectionValidationResult",
    "ConnectionCreationEvidence",
    "auto_link_natures_for_pair",
    "build_connection_creation_evidence",
    "is_auto_link_endpoint_pair",
    "validate_auto_connection_candidate",
]
