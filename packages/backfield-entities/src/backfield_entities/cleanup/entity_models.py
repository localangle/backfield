"""Table lookups for the three canonical entity kinds used by cleanup reads.

Locations, people and organizations each have the same table shape (canonical, alias, meta,
substrate row, mention, occurrence) with different column names. Cleanup reads are identical across
kinds, so this module maps a kind to its tables and the foreign-key column names once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backfield_db import (
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)

# Plural names are the URL segment (`/cleanup/{entity}/...`).
EntityName = Literal["locations", "people", "organizations"]
ENTITY_NAMES: tuple[EntityName, ...] = ("locations", "people", "organizations")


@dataclass(frozen=True)
class CleanupEntityModels:
    """Tables and column names for one entity kind."""

    name: EntityName
    singular: Literal["location", "person", "organization"]
    canonical: type[Any]
    alias: type[Any]
    meta: type[Any]
    substrate: type[Any]
    mention: type[Any]
    occurrence: type[Any]
    kind_column: str
    alias_canonical_column: str
    meta_canonical_column: str
    substrate_canonical_column: str
    mention_substrate_column: str
    occurrence_mention_column: str

    def canonical_kind(self, canonical: Any) -> str | None:
        """Return the canonical's type value (place kind, person type or organization type)."""
        return getattr(canonical, self.kind_column)

    def column(self, model: type[Any], name: str) -> Any:
        """Return an instrumented column by name (keeps getattr in one place)."""
        return getattr(model, name)


_MODELS_BY_NAME: dict[EntityName, CleanupEntityModels] = {
    "locations": CleanupEntityModels(
        name="locations",
        singular="location",
        canonical=StylebookLocationCanonical,
        alias=StylebookLocationAlias,
        meta=StylebookLocationMeta,
        substrate=SubstrateLocation,
        mention=SubstrateLocationMention,
        occurrence=SubstrateLocationMentionOccurrence,
        kind_column="location_type",
        alias_canonical_column="location_canonical_id",
        meta_canonical_column="stylebook_location_canonical_id",
        substrate_canonical_column="stylebook_location_canonical_id",
        mention_substrate_column="location_id",
        occurrence_mention_column="location_mention_id",
    ),
    "people": CleanupEntityModels(
        name="people",
        singular="person",
        canonical=StylebookPersonCanonical,
        alias=StylebookPersonAlias,
        meta=StylebookPersonMeta,
        substrate=SubstratePerson,
        mention=SubstratePersonMention,
        occurrence=SubstratePersonMentionOccurrence,
        kind_column="person_type",
        alias_canonical_column="person_canonical_id",
        meta_canonical_column="stylebook_person_canonical_id",
        substrate_canonical_column="stylebook_person_canonical_id",
        mention_substrate_column="person_id",
        occurrence_mention_column="person_mention_id",
    ),
    "organizations": CleanupEntityModels(
        name="organizations",
        singular="organization",
        canonical=StylebookOrganizationCanonical,
        alias=StylebookOrganizationAlias,
        meta=StylebookOrganizationMeta,
        substrate=SubstrateOrganization,
        mention=SubstrateOrganizationMention,
        occurrence=SubstrateOrganizationMentionOccurrence,
        kind_column="organization_type",
        alias_canonical_column="organization_canonical_id",
        meta_canonical_column="stylebook_organization_canonical_id",
        substrate_canonical_column="stylebook_organization_canonical_id",
        mention_substrate_column="organization_id",
        occurrence_mention_column="organization_mention_id",
    ),
}


def cleanup_entity_models(name: EntityName) -> CleanupEntityModels:
    """Return the table mapping for an entity kind."""
    return _MODELS_BY_NAME[name]


def cleanup_entity_models_for_singular(singular: str) -> CleanupEntityModels:
    """Look up the table mapping by singular name (`location`, `person`, `organization`)."""
    for models in _MODELS_BY_NAME.values():
        if models.singular == singular:
            return models
    raise ValueError(f"Unknown entity type: {singular}")
