"""Entity type registry: slugs, consolidated JSON keys, fingerprint helper."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

EntityType = Literal["location", "person", "organization", "work"]

EntityIdKind = Literal["uuid"]


@dataclass(frozen=True)
class EntityMeta:
    """Metadata for a Stylebook entity type."""

    slug: EntityType
    consolidated_key: str
    id_kind: EntityIdKind = "uuid"
    display_name_singular: str = ""
    display_name_plural: str = ""


ENTITY_REGISTRY: dict[EntityType, EntityMeta] = {
    "location": EntityMeta(
        slug="location",
        consolidated_key="places",
        display_name_singular="Location",
        display_name_plural="Locations",
    ),
    "person": EntityMeta(
        slug="person",
        consolidated_key="people",
        display_name_singular="Person",
        display_name_plural="People",
    ),
    "organization": EntityMeta(
        slug="organization",
        consolidated_key="organizations",
        display_name_singular="Organization",
        display_name_plural="Organizations",
    ),
    "work": EntityMeta(
        slug="work",
        consolidated_key="works",
        display_name_singular="Work",
        display_name_plural="Works",
    ),
}

CONSOLIDATED_KEY_TO_ENTITY: dict[str, EntityType] = {
    meta.consolidated_key: slug for slug, meta in ENTITY_REGISTRY.items()
}


def all_entity_types() -> tuple[EntityType, ...]:
    return tuple(ENTITY_REGISTRY.keys())


def entity_meta(entity_type: EntityType) -> EntityMeta:
    return ENTITY_REGISTRY[entity_type]


def consolidated_key_for(entity_type: EntityType) -> str:
    return ENTITY_REGISTRY[entity_type].consolidated_key


def entity_type_from_consolidated_key(key: str) -> EntityType | None:
    return CONSOLIDATED_KEY_TO_ENTITY.get(key)


def normalize_entity_name(name: str) -> str:
    return name.strip().lower()


def compute_identity_fingerprint(
    entity_type: EntityType,
    *,
    normalized_name: str,
    **type_fields: object,
) -> str:
    """Stable project-scoped identity hash from normalized name + optional type fields."""

    payload: dict[str, object] = {
        "entity_type": entity_type,
        "normalized_name": normalize_entity_name(normalized_name),
    }
    for key in sorted(type_fields.keys()):
        value = type_fields[key]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        payload[key] = value
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
