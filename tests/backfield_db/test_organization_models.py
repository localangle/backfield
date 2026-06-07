"""Schema contract tests for organization substrate and Stylebook models."""

from __future__ import annotations

from uuid import UUID

from backfield_db import (
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from backfield_db.entity_contracts import model_has_fields
from backfield_entities.entities.organization.types import (
    ORGANIZATION_NATURE_VALUES,
    ORGANIZATION_TYPE_VALUES,
    organization_identity_fingerprint,
)
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def test_substrate_organization_mention_is_unique_per_article_and_organization() -> None:
    assert _unique_constraint_columns(
        SubstrateOrganizationMention,
        "uq_substrate_organization_mention_article_organization",
    ) == ("article_id", "organization_id")


def test_substrate_organization_fingerprint_is_unique_per_project() -> None:
    assert _unique_constraint_columns(
        SubstrateOrganization,
        "uq_substrate_organization_project_fingerprint",
    ) == ("project_id", "identity_fingerprint")


def test_stylebook_organization_canonical_slug_is_unique_per_stylebook() -> None:
    assert _unique_constraint_columns(
        StylebookOrganizationCanonical,
        "uq_stylebook_organization_canonical_stylebook_slug",
    ) == ("stylebook_id", "slug")


def test_organization_defaults_keep_workflow_and_provenance_fields_predictable() -> None:
    organization = SubstrateOrganization(
        project_id=1,
        name="Chicago Police Department",
        normalized_name="chicago police department",
        organization_type="law_enforcement",
    )
    mention = SubstrateOrganizationMention(article_id=1, organization_id=2)
    occurrence = SubstrateOrganizationMentionOccurrence(
        organization_mention_id=1,
        mention_text="Chicago Police Department arrested two suspects",
    )

    assert organization.status == "provisional"
    assert organization.source_kind == "unknown"

    assert mention.needs_review is False
    assert mention.added is False
    assert mention.edited is False
    assert mention.deleted is False
    assert mention.source_kind == "unknown"
    assert mention.nature_secondary_tags_json == []

    assert occurrence.source_kind == "system_extraction"
    assert occurrence.labels_json == []
    assert occurrence.suppressed is False


def test_organization_defaults_use_independent_json_containers() -> None:
    first_mention = SubstrateOrganizationMention(article_id=1, organization_id=2)
    second_mention = SubstrateOrganizationMention(article_id=1, organization_id=3)
    second_occurrence = SubstrateOrganizationMentionOccurrence(
        organization_mention_id=1,
        mention_text="Chicago Teachers Union",
    )

    first_mention.nature_secondary_tags_json.append("source")
    second_occurrence.labels_json.append("mention")

    assert second_mention.nature_secondary_tags_json == []
    fresh_mention = SubstrateOrganizationMention(article_id=2, organization_id=3)
    assert fresh_mention.nature_secondary_tags_json == []
    assert SubstrateOrganizationMentionOccurrence(
        organization_mention_id=2,
        mention_text="Chicago City Council",
    ).labels_json == []


def test_organization_models_satisfy_shared_entity_contracts() -> None:
    shared_substrate_entity = (
        "project_id",
        "name",
        "normalized_name",
        "status",
        "stylebook_organization_canonical_id",
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
    assert model_has_fields(SubstrateOrganization, shared_substrate_entity)
    assert hasattr(SubstrateOrganization, "organization_type")

    shared_mention = (
        "article_id",
        "organization_id",
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
    assert model_has_fields(SubstrateOrganizationMention, shared_mention)

    shared_occurrence = (
        "organization_mention_id",
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
    assert model_has_fields(SubstrateOrganizationMentionOccurrence, shared_occurrence)

    shared_canonical = (
        "stylebook_id",
        "label",
        "slug",
        "status",
        "created_at",
        "updated_at",
    )
    assert model_has_fields(StylebookOrganizationCanonical, shared_canonical)
    assert hasattr(StylebookOrganizationCanonical, "organization_type")

    shared_alias = (
        "organization_canonical_id",
        "alias_text",
        "normalized_alias",
        "provenance",
        "suppressed",
        "created_at",
        "updated_at",
    )
    assert model_has_fields(StylebookOrganizationAlias, shared_alias)

    shared_meta = (
        "project_id",
        "stylebook_organization_canonical_id",
        "meta_type",
        "data_json",
        "added",
        "edited",
        "deleted",
        "created_at",
    )
    assert model_has_fields(StylebookOrganizationMeta, shared_meta)


def test_stylebook_organization_canonical_id_is_uuid_string() -> None:
    canonical = StylebookOrganizationCanonical(
        stylebook_id=1,
        label="Chicago Police Department",
        slug="chicago-police-department",
        organization_type="law_enforcement",
    )
    UUID(canonical.id)


def test_organization_type_and_nature_vocabularies_are_non_empty() -> None:
    assert "law_enforcement" in ORGANIZATION_TYPE_VALUES
    assert "other" in ORGANIZATION_TYPE_VALUES
    assert "actor" in ORGANIZATION_NATURE_VALUES
    assert "other" in ORGANIZATION_NATURE_VALUES


def test_organization_identity_fingerprint_includes_name_and_type() -> None:
    fp_a = organization_identity_fingerprint(
        normalized_name="Chicago Police Department",
        organization_type="law_enforcement",
    )
    fp_b = organization_identity_fingerprint(
        normalized_name="Chicago Police Department",
        organization_type="company",
    )
    assert fp_a != fp_b
