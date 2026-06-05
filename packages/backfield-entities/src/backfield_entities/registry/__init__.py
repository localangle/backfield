"""Entity type registry: slugs, consolidated JSON keys, fingerprint helper."""

from backfield_entities.registry.entity_types import (
    EntityIdKind,
    EntityMeta,
    EntityType,
    all_entity_types,
    compute_identity_fingerprint,
    consolidated_key_for,
    entity_meta,
    entity_type_from_consolidated_key,
    normalize_entity_name,
)

__all__ = [
    "EntityIdKind",
    "EntityMeta",
    "EntityType",
    "all_entity_types",
    "compute_identity_fingerprint",
    "consolidated_key_for",
    "entity_meta",
    "entity_type_from_consolidated_key",
    "normalize_entity_name",
]
