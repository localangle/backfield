"""Documented shared column contracts for substrate and Stylebook entity tables.

Concrete SQLModel tables keep per-entity FK column names (for example
``stylebook_location_canonical_id`` / ``stylebook_person_canonical_id``). These tuples
document the shared shape new types should follow; tests assert location and person
models satisfy the contracts.
"""

from __future__ import annotations

from typing import TypedDict

# --- Substrate entity (substrate_<type>) ---

SUBSTRATE_ENTITY_FIELD_NAMES: tuple[str, ...] = (
    "id",
    "project_id",
    "name",
    "normalized_name",
    "status",
    "stylebook_location_canonical_id",  # per-type FK name; pattern: stylebook_<type>_canonical_id
    "canonical_link_status",
    "canonical_review_reasons_json",
    "external_source",
    "external_id",
    "identity_fingerprint",
    "source_kind",
    "source_details_json",
    "created_at",
    "updated_at",
)

SUBSTRATE_MENTION_FIELD_NAMES: tuple[str, ...] = (
    "id",
    "article_id",
    "location_id",  # per-type FK; pattern: <type>_id
    "role_in_story",
    "nature",
    "nature_secondary_tags_json",
    "needs_review",
    "review_data_json",
    "added",
    "edited",
    "deleted",
    "source_kind",
    "source_details_json",
    "created_at",
    "updated_at",
)

SUBSTRATE_OCCURRENCE_FIELD_NAMES: tuple[str, ...] = (
    "id",
    "location_mention_id",  # per-type FK; pattern: <type>_mention_id
    "source_kind",
    "source_details_json",
    "mention_text",
    "quote_text",
    "start_char",
    "end_char",
    "occurrence_order",
    "labels_json",
    "suppressed",
    "created_at",
    "updated_at",
)

# --- Stylebook canonical trio ---

STYLEBOOK_CANONICAL_FIELD_NAMES: tuple[str, ...] = (
    "id",
    "stylebook_id",
    "label",
    "slug",
    "status",
    "primary_substrate_location_id",  # per-type optional FK; pattern: primary_substrate_<type>_id
    "created_at",
    "updated_at",
)

STYLEBOOK_ALIAS_FIELD_NAMES: tuple[str, ...] = (
    "id",
    "location_canonical_id",  # per-type FK; pattern: <type>_canonical_id
    "alias_text",
    "normalized_alias",
    "provenance",
    "suppressed",
    "created_at",
    "updated_at",
)

STYLEBOOK_META_FIELD_NAMES: tuple[str, ...] = (
    "id",
    "project_id",
    "stylebook_location_canonical_id",  # per-type FK
    "meta_type",
    "data_json",
    "added",
    "edited",
    "deleted",
    "created_at",
)


class SubstrateEntityFields(TypedDict, total=False):
    """Shared substrate entity columns (documentation only)."""

    project_id: int
    name: str
    normalized_name: str
    status: str
    canonical_link_status: str
    identity_fingerprint: str | None
    source_kind: str


class StylebookCanonicalFields(TypedDict, total=False):
    """Shared Stylebook canonical columns (documentation only)."""

    stylebook_id: int
    label: str
    slug: str
    status: str


def model_has_fields(model: type[object], field_names: tuple[str, ...]) -> bool:
    return all(hasattr(model, name) for name in field_names)
