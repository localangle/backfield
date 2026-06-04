"""Deterministic person occurrence semantic document builder."""

from __future__ import annotations

from backfield_stylebook.semantic_indexing.common.article import ArticleSource
from backfield_stylebook.semantic_indexing.common.context import extract_article_context_snippet
from backfield_stylebook.semantic_indexing.contracts import (
    DEFAULT_DOCUMENT_KIND,
    SKIP_ARTICLE_DELETED,
    SKIP_MENTION_DELETED,
    SKIP_OCCURRENCE_SUPPRESSED,
    SemanticDocumentBuildSkip,
    SemanticDocumentDraft,
    SemanticDocumentSourceKey,
)
from backfield_stylebook.semantic_indexing.hashing import compute_semantic_source_hash
from backfield_stylebook.semantic_indexing.person.sources import (
    PersonCanonicalSource,
    PersonEntitySource,
    PersonMentionSource,
    PersonOccurrenceSource,
)
from backfield_stylebook.semantic_indexing.search_text import (
    append_joined_line,
    append_labeled_line,
    join_search_text,
)


def occurrence_indexable(
    *,
    article: ArticleSource,
    mention: PersonMentionSource,
    occurrence: PersonOccurrenceSource,
) -> str | None:
    if article.deleted:
        return SKIP_ARTICLE_DELETED
    if mention.deleted:
        return SKIP_MENTION_DELETED
    if occurrence.suppressed:
        return SKIP_OCCURRENCE_SUPPRESSED
    return None


def _hash_payload(
    *,
    article: ArticleSource,
    person: PersonEntitySource,
    canonical: PersonCanonicalSource | None,
    mention: PersonMentionSource,
    occurrence: PersonOccurrenceSource,
    article_context: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "entity_type": "person",
        "document_kind": DEFAULT_DOCUMENT_KIND,
        "occurrence_id": occurrence.id,
        "article": {
            "id": article.id,
            "headline": article.headline,
        },
        "person": {
            "id": person.id,
            "name": person.name,
            "title": person.title,
            "affiliation": person.affiliation,
            "person_type": person.person_type,
            "public_figure": person.public_figure,
            "stylebook_person_canonical_id": person.stylebook_person_canonical_id,
        },
        "mention": {
            "id": mention.id,
            "role_in_story": mention.role_in_story,
            "nature": mention.nature,
            "nature_secondary_tags": list(mention.nature_secondary_tags),
        },
        "occurrence": {
            "id": occurrence.id,
            "mention_text": occurrence.mention_text,
            "quote_text": occurrence.quote_text,
            "start_char": occurrence.start_char,
            "end_char": occurrence.end_char,
            "occurrence_order": occurrence.occurrence_order,
            "labels": list(occurrence.labels),
        },
        "article_context": article_context,
    }
    if canonical is not None:
        payload["canonical"] = {
            "id": canonical.id,
            "label": canonical.label,
            "title": canonical.title,
            "affiliation": canonical.affiliation,
            "person_type": canonical.person_type,
        }
    return payload


def _assemble_search_text(
    *,
    article: ArticleSource,
    person: PersonEntitySource,
    canonical: PersonCanonicalSource | None,
    mention: PersonMentionSource,
    occurrence: PersonOccurrenceSource,
    article_context: str | None,
) -> str:
    lines: list[str] = []
    append_labeled_line(lines, "Article", article.headline)
    append_labeled_line(lines, "Person", person.name)
    if canonical is not None:
        append_labeled_line(lines, "Canonical person", canonical.label)
    append_labeled_line(lines, "Title", person.title or (canonical.title if canonical else None))
    append_labeled_line(
        lines,
        "Affiliation",
        person.affiliation or (canonical.affiliation if canonical else None),
    )
    append_labeled_line(
        lines,
        "Person type",
        person.person_type or (canonical.person_type if canonical else None),
    )
    if person.public_figure:
        lines.append("Public figure: yes")
    append_labeled_line(lines, "Role in story", mention.role_in_story)
    append_labeled_line(lines, "Nature", mention.nature)
    append_joined_line(lines, "Secondary nature tags", mention.nature_secondary_tags)
    append_labeled_line(lines, "Mention", occurrence.mention_text)
    if occurrence.quote_text and occurrence.quote_text.strip():
        append_labeled_line(lines, "Quote", occurrence.quote_text)
    append_joined_line(lines, "Labels", occurrence.labels)
    append_labeled_line(lines, "Context", article_context)
    return join_search_text(lines)


def build_occurrence_document(
    *,
    project_id: int,
    article: ArticleSource,
    person: PersonEntitySource,
    mention: PersonMentionSource,
    occurrence: PersonOccurrenceSource,
    canonical: PersonCanonicalSource | None = None,
) -> SemanticDocumentDraft | SemanticDocumentBuildSkip:
    skip = occurrence_indexable(article=article, mention=mention, occurrence=occurrence)
    if skip is not None:
        return SemanticDocumentBuildSkip(
            entity_type="person",
            occurrence_id=occurrence.id,
            reason=skip,
        )

    article_context = extract_article_context_snippet(
        article.text,
        start_char=occurrence.start_char,
        end_char=occurrence.end_char,
    )
    hash_payload = _hash_payload(
        article=article,
        person=person,
        canonical=canonical,
        mention=mention,
        occurrence=occurrence,
        article_context=article_context,
    )
    search_text = _assemble_search_text(
        article=article,
        person=person,
        canonical=canonical,
        mention=mention,
        occurrence=occurrence,
        article_context=article_context,
    )
    source_key = SemanticDocumentSourceKey(entity_type="person", occurrence_id=occurrence.id)
    return SemanticDocumentDraft(
        source_key=source_key,
        document_kind=DEFAULT_DOCUMENT_KIND,
        search_text=search_text,
        source_hash=compute_semantic_source_hash(hash_payload),
        project_id=project_id,
        article_id=article.id,
        entity_id=person.id,
        mention_id=mention.id,
        occurrence_id=occurrence.id,
    )


def build_occurrence_documents(
    *,
    project_id: int,
    bundles: list[
        tuple[
            ArticleSource,
            PersonEntitySource,
            PersonMentionSource,
            PersonOccurrenceSource,
            PersonCanonicalSource | None,
        ]
    ],
) -> list[SemanticDocumentDraft | SemanticDocumentBuildSkip]:
    """Build documents for many occurrences with deterministic ordering."""
    ordered = sorted(
        bundles,
        key=lambda row: (
            row[3].occurrence_order if row[3].occurrence_order is not None else 10**9,
            row[3].id,
        ),
    )
    results: list[SemanticDocumentDraft | SemanticDocumentBuildSkip] = []
    for article, person, mention, occurrence, canonical in ordered:
        results.append(
            build_occurrence_document(
                project_id=project_id,
                article=article,
                person=person,
                mention=mention,
                occurrence=occurrence,
                canonical=canonical,
            )
        )
    return results
