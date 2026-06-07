"""Deterministic semantic document builder tests (Issue 3)."""

from __future__ import annotations

import pytest
from backfield_entities.ingest.semantic_indexing import (
    SKIP_OCCURRENCE_SUPPRESSED,
    SemanticDocumentBuildSkip,
    SemanticDocumentDraft,
    build_location_occurrence_document,
    build_location_occurrence_documents,
    build_organization_occurrence_document,
    build_person_occurrence_document,
    build_person_occurrence_documents,
    semantic_builder_supported,
    unsupported_semantic_builder_type,
)
from backfield_entities.ingest.semantic_indexing.common.article import ArticleSource
from backfield_entities.ingest.semantic_indexing.location.sources import (
    LocationCanonicalSource,
    LocationEntitySource,
    LocationMentionSource,
    LocationOccurrenceSource,
)
from backfield_entities.ingest.semantic_indexing.organization.sources import (
    OrganizationCanonicalSource,
    OrganizationEntitySource,
    OrganizationMentionSource,
    OrganizationOccurrenceSource,
)
from backfield_entities.ingest.semantic_indexing.person.sources import (
    PersonCanonicalSource,
    PersonEntitySource,
    PersonMentionSource,
    PersonOccurrenceSource,
)


def _article(*, deleted: bool = False) -> ArticleSource:
    body = (
        "City leaders met downtown on Tuesday. "
        '"We need more officers downtown," Mayor Jane Jones said. '
        "Jones later criticized the response."
    )
    return ArticleSource(
        id=10,
        headline="Mayor speaks on downtown crime",
        text=body,
        deleted=deleted,
    )


def _person(*, name: str = "Jane Jones") -> PersonEntitySource:
    return PersonEntitySource(
        id=20,
        name=name,
        title="Mayor",
        affiliation="Springfield",
        person_type="official",
        public_figure=True,
        stylebook_person_canonical_id="canon-person-1",
    )


def _person_canonical() -> PersonCanonicalSource:
    return PersonCanonicalSource(
        id="canon-person-1",
        label="Mayor Jane Jones",
        title="Mayor",
        affiliation="Springfield",
        person_type="official",
    )


def _person_mention(*, deleted: bool = False, nature: str = "official") -> PersonMentionSource:
    return PersonMentionSource(
        id=30,
        article_id=10,
        person_id=20,
        role_in_story="criticized downtown crime response",
        nature=nature,
        nature_secondary_tags=("crime",),
        deleted=deleted,
    )


def _person_occurrence(
    *,
    occurrence_id: int = 40,
    quote: str | None = "We need more officers downtown.",
    suppressed: bool = False,
    occurrence_order: int | None = 1,
) -> PersonOccurrenceSource:
    quote_start = 44
    quote_end = quote_start + len(quote) if quote else None
    return PersonOccurrenceSource(
        id=occurrence_id,
        person_mention_id=30,
        mention_text="Jones",
        quote_text=quote,
        start_char=quote_start if quote else None,
        end_char=quote_end,
        occurrence_order=occurrence_order,
        labels=("speech",),
        suppressed=suppressed,
    )


def _location() -> LocationEntitySource:
    return LocationEntitySource(
        id=50,
        name="Springfield General Hospital",
        location_type="place",
        formatted_address="100 Main St, Springfield",
        stylebook_location_canonical_id="canon-loc-1",
    )


def _location_canonical() -> LocationCanonicalSource:
    return LocationCanonicalSource(
        id="canon-loc-1",
        label="Springfield General Hospital",
        location_type="place",
        formatted_address="100 Main St, Springfield",
    )


def _location_mention(*, deleted: bool = False) -> LocationMentionSource:
    return LocationMentionSource(
        id=60,
        article_id=10,
        location_id=50,
        role_in_story="transport destination",
        nature="medical",
        nature_secondary_tags=("emergency",),
        deleted=deleted,
    )


def _location_occurrence(
    *,
    occurrence_id: int = 70,
    quote: str | None = None,
    suppressed: bool = False,
    occurrence_order: int | None = 1,
) -> LocationOccurrenceSource:
    return LocationOccurrenceSource(
        id=occurrence_id,
        location_mention_id=60,
        mention_text="the hospital",
        quote_text=quote,
        start_char=10,
        end_char=22,
        occurrence_order=1,
        labels=("setting",),
        suppressed=suppressed,
    )


def test_person_builder_emits_expanded_document_with_quote() -> None:
    result = build_person_occurrence_document(
        project_id=1,
        article=_article(),
        person=_person(),
        mention=_person_mention(),
        occurrence=_person_occurrence(),
        canonical=_person_canonical(),
    )
    assert isinstance(result, SemanticDocumentDraft)
    assert result.source_key.as_string() == "person:occurrence:40"
    assert "Mayor Jane Jones" in result.search_text
    assert "Role in story: criticized downtown crime response" in result.search_text
    assert "Quote: We need more officers downtown." in result.search_text
    assert "Context:" in result.search_text
    assert result.active is True


def test_person_builder_stable_hash_for_unchanged_inputs() -> None:
    kwargs = dict(
        project_id=1,
        article=_article(),
        person=_person(),
        mention=_person_mention(),
        occurrence=_person_occurrence(),
        canonical=_person_canonical(),
    )
    first = build_person_occurrence_document(**kwargs)
    second = build_person_occurrence_document(**kwargs)
    assert isinstance(first, SemanticDocumentDraft)
    assert isinstance(second, SemanticDocumentDraft)
    assert first.source_hash == second.source_hash
    assert first.search_text == second.search_text


def test_person_builder_hash_changes_when_nature_changes() -> None:
    base = dict(
        project_id=1,
        article=_article(),
        person=_person(),
        occurrence=_person_occurrence(),
        canonical=_person_canonical(),
    )
    first = build_person_occurrence_document(**base, mention=_person_mention(nature="official"))
    second = build_person_occurrence_document(**base, mention=_person_mention(nature="witness"))
    assert isinstance(first, SemanticDocumentDraft)
    assert isinstance(second, SemanticDocumentDraft)
    assert first.source_hash != second.source_hash


def test_person_builder_hash_changes_when_canonical_label_changes() -> None:
    base = dict(
        project_id=1,
        article=_article(),
        person=_person(),
        mention=_person_mention(),
        occurrence=_person_occurrence(),
    )
    first = build_person_occurrence_document(**base, canonical=_person_canonical())
    second = build_person_occurrence_document(
        **base,
        canonical=PersonCanonicalSource(
            id="canon-person-1",
            label="Jane Jones",
            title="Mayor",
            affiliation="Springfield",
            person_type="official",
        ),
    )
    assert isinstance(first, SemanticDocumentDraft)
    assert isinstance(second, SemanticDocumentDraft)
    assert first.source_hash != second.source_hash


def test_person_builder_skips_suppressed_and_deleted_evidence() -> None:
    suppressed = build_person_occurrence_document(
        project_id=1,
        article=_article(),
        person=_person(),
        mention=_person_mention(),
        occurrence=_person_occurrence(suppressed=True),
    )
    assert isinstance(suppressed, SemanticDocumentBuildSkip)
    assert suppressed.reason == SKIP_OCCURRENCE_SUPPRESSED

    deleted_mention = build_person_occurrence_document(
        project_id=1,
        article=_article(),
        person=_person(),
        mention=_person_mention(deleted=True),
        occurrence=_person_occurrence(),
    )
    assert isinstance(deleted_mention, SemanticDocumentBuildSkip)


def test_person_builder_orders_occurrences_deterministically() -> None:
    article = _article()
    person = _person()
    mention = _person_mention()
    bundles = [
        (article, person, mention, _person_occurrence(occurrence_id=42, occurrence_order=2), None),
        (article, person, mention, _person_occurrence(occurrence_id=41, occurrence_order=1), None),
    ]
    results = build_person_occurrence_documents(project_id=1, bundles=bundles)
    occurrence_ids = [
        row.occurrence_id for row in results if isinstance(row, SemanticDocumentDraft)
    ]
    assert occurrence_ids == [41, 42]


def test_location_builder_non_quote_occurrence() -> None:
    result = build_location_occurrence_document(
        project_id=1,
        article=_article(),
        location=_location(),
        mention=_location_mention(),
        occurrence=_location_occurrence(quote=None),
        canonical=_location_canonical(),
    )
    assert isinstance(result, SemanticDocumentDraft)
    assert "Location: Springfield General Hospital" in result.search_text
    assert "Mention: the hospital" in result.search_text
    assert "Quote:" not in result.search_text


def test_location_builder_documents_batch_ordering() -> None:
    article = _article()
    location = _location()
    mention = _location_mention()
    bundles = [
        (
            article,
            location,
            mention,
            _location_occurrence(occurrence_id=72, occurrence_order=2),
            None,
        ),
        (
            article,
            location,
            mention,
            _location_occurrence(occurrence_id=71, occurrence_order=1),
            None,
        ),
    ]
    results = build_location_occurrence_documents(project_id=1, bundles=bundles)
    assert [row.occurrence_id for row in results if isinstance(row, SemanticDocumentDraft)] == [
        71,
        72,
    ]


def test_organization_occurrence_document_includes_role_and_type() -> None:
    organization = OrganizationEntitySource(
        id=60,
        name="Chicago City Hall",
        organization_type="government",
        stylebook_organization_canonical_id="canon-org-1",
    )
    canonical = OrganizationCanonicalSource(
        id="canon-org-1",
        label="Chicago City Hall",
        organization_type="government",
    )
    mention = OrganizationMentionSource(
        id=61,
        article_id=10,
        organization_id=60,
        role_in_story="Announced a new policy",
        nature="actor",
        nature_secondary_tags=("source",),
        deleted=False,
    )
    occurrence = OrganizationOccurrenceSource(
        id=62,
        organization_mention_id=61,
        mention_text="Chicago City Hall announced a new policy Monday.",
        quote_text=None,
        start_char=0,
        end_char=48,
        occurrence_order=1,
        labels=(),
        suppressed=False,
    )
    draft = build_organization_occurrence_document(
        project_id=1,
        article=_article(),
        organization=organization,
        mention=mention,
        occurrence=occurrence,
        canonical=canonical,
    )
    assert isinstance(draft, SemanticDocumentDraft)
    assert draft.entity_id == 60
    assert "Chicago City Hall" in draft.search_text
    assert "government" in draft.search_text
    assert "Announced a new policy" in draft.search_text


@pytest.mark.parametrize("entity_type", ["work"])
def test_unsupported_entity_type_result(entity_type: str) -> None:
    assert semantic_builder_supported(entity_type) is False
    unsupported = unsupported_semantic_builder_type(entity_type)
    assert unsupported.entity_type == entity_type


def test_organization_entity_type_is_supported() -> None:
    assert semantic_builder_supported("organization") is True
