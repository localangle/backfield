"""Schema contract tests for shared Backfield content/location models."""

from __future__ import annotations

from backfield_db import (
    BackfieldArticle,
    BackfieldLocation,
    BackfieldLocationCache,
    BackfieldLocationMention,
    BackfieldLocationMentionOccurrence,
)
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def test_backfield_article_unique_constraints_cover_project_external_identity_and_url() -> None:
    assert _unique_constraint_columns(
        BackfieldArticle,
        "uq_backfield_article_project_external",
    ) == ("project_id", "external_source", "external_id")
    assert _unique_constraint_columns(
        BackfieldArticle,
        "uq_backfield_article_project_url",
    ) == ("project_id", "url")


def test_backfield_location_mention_is_unique_per_article_and_location() -> None:
    assert _unique_constraint_columns(
        BackfieldLocationMention,
        "uq_backfield_location_mention_article_location",
    ) == ("article_id", "location_id")


def test_backfield_location_cache_is_project_scoped() -> None:
    assert _unique_constraint_columns(
        BackfieldLocationCache,
        "uq_backfield_location_cache_project_query",
    ) == ("project_id", "query_fingerprint")


def test_location_defaults_keep_workflow_and_provenance_fields_predictable() -> None:
    location = BackfieldLocation(project_id=1, name="Chicago", normalized_name="chicago")
    mention = BackfieldLocationMention(article_id=1, location_id=2)
    occurrence = BackfieldLocationMentionOccurrence(location_mention_id=1, mention_text="Chicago")

    assert location.status == "provisional"
    assert location.source_kind == "unknown"
    assert location.parent_ids_json == []

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
    first_location = BackfieldLocation(project_id=1, name="Chicago", normalized_name="chicago")
    second_location = BackfieldLocation(project_id=1, name="Austin", normalized_name="austin")
    first_mention = BackfieldLocationMention(article_id=1, location_id=2)
    second_occurrence = BackfieldLocationMentionOccurrence(
        location_mention_id=1,
        mention_text="Austin",
    )

    first_location.parent_ids_json.append("parent-1")
    first_mention.nature_secondary_tags_json.append("scene")
    second_occurrence.labels_json.append("quote")

    assert second_location.parent_ids_json == []
    assert BackfieldLocationMention(article_id=2, location_id=3).nature_secondary_tags_json == []
    assert BackfieldLocationMentionOccurrence(
        location_mention_id=2,
        mention_text="Chicago",
    ).labels_json == []
