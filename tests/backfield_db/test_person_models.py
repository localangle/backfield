"""Schema contract tests for person substrate and Stylebook models."""

from __future__ import annotations

from uuid import UUID

from backfield_db import (
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_db.entity_contracts import model_has_fields
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def test_substrate_person_mention_is_unique_per_article_and_person() -> None:
    assert _unique_constraint_columns(
        SubstratePersonMention,
        "uq_substrate_person_mention_article_person",
    ) == ("article_id", "person_id")


def test_substrate_person_fingerprint_is_unique_per_project() -> None:
    assert _unique_constraint_columns(
        SubstratePerson,
        "uq_substrate_person_project_fingerprint",
    ) == ("project_id", "identity_fingerprint")


def test_stylebook_person_canonical_slug_is_unique_per_stylebook() -> None:
    assert _unique_constraint_columns(
        StylebookPersonCanonical,
        "uq_stylebook_person_canonical_stylebook_slug",
    ) == ("stylebook_id", "slug")


def test_person_defaults_keep_workflow_and_provenance_fields_predictable() -> None:
    person = SubstratePerson(project_id=1, name="Jane Doe", normalized_name="jane doe")
    mention = SubstratePersonMention(article_id=1, person_id=2)
    occurrence = SubstratePersonMentionOccurrence(person_mention_id=1, mention_text="Jane Doe")

    assert person.status == "provisional"
    assert person.source_kind == "unknown"
    assert person.public_figure is False

    assert mention.needs_review is False
    assert mention.added is False
    assert mention.edited is False
    assert mention.deleted is False
    assert mention.source_kind == "unknown"
    assert mention.nature_secondary_tags_json == []

    assert occurrence.source_kind == "system_extraction"
    assert occurrence.labels_json == []
    assert occurrence.suppressed is False


def test_person_defaults_use_independent_json_containers() -> None:
    first_mention = SubstratePersonMention(article_id=1, person_id=2)
    second_mention = SubstratePersonMention(article_id=1, person_id=3)
    second_occurrence = SubstratePersonMentionOccurrence(
        person_mention_id=1,
        mention_text="Jane Doe",
    )

    first_mention.nature_secondary_tags_json.append("source")
    second_occurrence.labels_json.append("quote")

    assert second_mention.nature_secondary_tags_json == []
    assert SubstratePersonMention(article_id=2, person_id=3).nature_secondary_tags_json == []
    assert SubstratePersonMentionOccurrence(
        person_mention_id=2,
        mention_text="John Smith",
    ).labels_json == []


def test_person_models_satisfy_shared_entity_contracts() -> None:
    shared_substrate_entity = (
        "project_id",
        "name",
        "normalized_name",
        "status",
        "stylebook_person_canonical_id",
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
    assert model_has_fields(SubstratePerson, shared_substrate_entity)

    shared_mention = (
        "article_id",
        "person_id",
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
    assert model_has_fields(SubstratePersonMention, shared_mention)

    shared_occurrence = (
        "person_mention_id",
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
    assert model_has_fields(SubstratePersonMentionOccurrence, shared_occurrence)

    shared_canonical = (
        "stylebook_id",
        "label",
        "slug",
        "status",
        "created_at",
        "updated_at",
    )
    assert model_has_fields(StylebookPersonCanonical, shared_canonical)

    shared_alias = (
        "person_canonical_id",
        "alias_text",
        "normalized_alias",
        "provenance",
        "suppressed",
        "created_at",
        "updated_at",
    )
    assert model_has_fields(StylebookPersonAlias, shared_alias)

    shared_meta = (
        "project_id",
        "stylebook_person_canonical_id",
        "meta_type",
        "data_json",
        "added",
        "edited",
        "deleted",
        "created_at",
    )
    assert model_has_fields(StylebookPersonMeta, shared_meta)


def test_stylebook_person_canonical_id_is_uuid_string() -> None:
    canonical = StylebookPersonCanonical(stylebook_id=1, label="Jane Doe", slug="jane-doe")
    UUID(canonical.id)
