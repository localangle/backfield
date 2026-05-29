"""Schema contract tests for shared substrate content/location models."""

from __future__ import annotations

from backfield_db import (
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationCache,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_db.entity_contracts import model_has_fields
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def test_substrate_article_unique_constraints_cover_project_external_identity_and_url() -> None:
    assert _unique_constraint_columns(
        SubstrateArticle,
        "uq_substrate_article_project_external",
    ) == ("project_id", "external_source", "external_id")
    assert _unique_constraint_columns(
        SubstrateArticle,
        "uq_substrate_article_project_url",
    ) == ("project_id", "url")


def test_substrate_location_mention_is_unique_per_article_and_location() -> None:
    assert _unique_constraint_columns(
        SubstrateLocationMention,
        "uq_substrate_location_mention_article_location",
    ) == ("article_id", "location_id")


def test_substrate_location_cache_is_project_scoped() -> None:
    assert _unique_constraint_columns(
        SubstrateLocationCache,
        "uq_substrate_location_cache_project_query",
    ) == ("project_id", "query_fingerprint")


def test_location_defaults_keep_workflow_and_provenance_fields_predictable() -> None:
    location = SubstrateLocation(project_id=1, name="Chicago", normalized_name="chicago")
    mention = SubstrateLocationMention(article_id=1, location_id=2)
    occurrence = SubstrateLocationMentionOccurrence(location_mention_id=1, mention_text="Chicago")

    assert location.status == "provisional"
    assert location.source_kind == "unknown"

    assert mention.needs_review is False
    assert mention.added is False
    assert mention.edited is False
    assert mention.deleted is False
    assert mention.source_kind == "unknown"
    assert mention.nature_secondary_tags_json == []

    assert occurrence.source_kind == "system_extraction"
    assert occurrence.labels_json == []
    assert occurrence.suppressed is False


def test_location_defaults_use_independent_json_containers() -> None:
    first_mention = SubstrateLocationMention(article_id=1, location_id=2)
    second_mention = SubstrateLocationMention(article_id=1, location_id=3)
    second_occurrence = SubstrateLocationMentionOccurrence(
        location_mention_id=1,
        mention_text="Austin",
    )

    first_mention.nature_secondary_tags_json.append("scene")
    second_occurrence.labels_json.append("quote")

    assert second_mention.nature_secondary_tags_json == []
    assert SubstrateLocationMention(article_id=2, location_id=3).nature_secondary_tags_json == []
    assert SubstrateLocationMentionOccurrence(
        location_mention_id=2,
        mention_text="Chicago",
    ).labels_json == []


def test_location_models_satisfy_shared_entity_contracts() -> None:
    shared_substrate_entity = (
        "project_id",
        "name",
        "normalized_name",
        "status",
        "stylebook_location_canonical_id",
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
    assert model_has_fields(SubstrateLocation, shared_substrate_entity)

    shared_mention = (
        "article_id",
        "location_id",
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
    assert model_has_fields(SubstrateLocationMention, shared_mention)

    shared_occurrence = (
        "location_mention_id",
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
    assert model_has_fields(SubstrateLocationMentionOccurrence, shared_occurrence)

    shared_canonical = (
        "stylebook_id",
        "label",
        "slug",
        "status",
        "created_at",
        "updated_at",
    )
    assert model_has_fields(StylebookLocationCanonical, shared_canonical)

    shared_alias = (
        "location_canonical_id",
        "alias_text",
        "normalized_alias",
        "provenance",
        "suppressed",
        "created_at",
        "updated_at",
    )
    assert model_has_fields(StylebookLocationAlias, shared_alias)

    shared_meta = (
        "project_id",
        "stylebook_location_canonical_id",
        "meta_type",
        "data_json",
        "added",
        "edited",
        "deleted",
        "created_at",
    )
    assert model_has_fields(StylebookLocationMeta, shared_meta)
