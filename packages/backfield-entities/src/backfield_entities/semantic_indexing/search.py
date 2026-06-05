"""Semantic mention search over occurrence-level semantic documents (Issue 9)."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

from backfield_db import (
    StylebookLocationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateLocationSemanticDocument,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
    SubstratePersonSemanticDocument,
)
from backfield_db.semantic_indexing import SEMANTIC_EMBEDDING_STATUS_READY
from sqlalchemy import and_, func, or_
from sqlmodel import Session, col, select

from backfield_stylebook.semantic_indexing.search_contract import (
    LocationSemanticSearchFilters,
    PersonSemanticSearchFilters,
    QuoteStatusFilter,
    SemanticMentionSearchFilters,
    SemanticMentionSearchHit,
    SemanticMentionSearchResult,
)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _coerce_embedding_vector(raw: object | None) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [float(x) for x in raw]
    # pgvector on Postgres often returns numpy.ndarray via SQLAlchemy.
    tolist = getattr(raw, "tolist", None)
    if callable(tolist):
        try:
            parsed = tolist()
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            return [float(x) for x in parsed]
    if isinstance(raw, tuple):
        return [float(x) for x in raw]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return [float(x) for x in parsed]
    return None


def _occurrence_is_quote(*, quote_text: str | None, labels_json: list[str] | None) -> bool:
    if isinstance(quote_text, str) and quote_text.strip():
        return True
    labels = labels_json or []
    return any(str(label).strip().lower() == "quote" for label in labels)


def _matches_quote_status(
    quote_status: QuoteStatusFilter,
    *,
    quote_text: str | None,
    labels_json: list[str] | None,
) -> bool:
    if quote_status == "any":
        return True
    is_quote = _occurrence_is_quote(quote_text=quote_text, labels_json=labels_json)
    if quote_status == "quote_only":
        return is_quote
    return not is_quote


def _quote_status_clause(
    quote_status: QuoteStatusFilter,
    *,
    quote_text_col: Any,
) -> Any | None:
    if quote_status == "any":
        return None
    quote_present = and_(
        quote_text_col.isnot(None),
        func.length(func.trim(quote_text_col)) > 0,
    )
    if quote_status == "quote_only":
        return quote_present
    return or_(quote_text_col.is_(None), func.length(func.trim(quote_text_col)) == 0)


def _apply_shared_filters(
    stmt: Any,
    *,
    doc_model: type,
    project_id: int,
    filters: SemanticMentionSearchFilters,
    entity_id_col: Any,
    mention_id_col: Any,
    occurrence_id_col: Any,
    canonical_id_col: Any,
    quote_text_col: Any,
) -> Any:
    stmt = stmt.where(
        doc_model.project_id == project_id,
        doc_model.embedding_status == SEMANTIC_EMBEDDING_STATUS_READY,
        doc_model.embedding.isnot(None),
    )
    if filters.active_only:
        stmt = stmt.where(doc_model.active.is_(True), doc_model.stale.is_(False))
    if filters.article_id is not None:
        stmt = stmt.where(doc_model.article_id == filters.article_id)
    if filters.entity_id is not None:
        stmt = stmt.where(entity_id_col == filters.entity_id)
    if filters.mention_id is not None:
        stmt = stmt.where(mention_id_col == filters.mention_id)
    if filters.occurrence_id is not None:
        stmt = stmt.where(occurrence_id_col == filters.occurrence_id)
    if filters.canonical_id is not None:
        stmt = stmt.where(canonical_id_col == filters.canonical_id)
    quote_clause = _quote_status_clause(filters.quote_status, quote_text_col=quote_text_col)
    if quote_clause is not None:
        stmt = stmt.where(quote_clause)
    return stmt


def _article_payload(article: SubstrateArticle) -> dict[str, Any]:
    return {
        "id": int(article.id),  # type: ignore[arg-type]
        "headline": article.headline,
        "url": article.url,
    }


def _person_entity_payload(person: SubstratePerson) -> dict[str, Any]:
    return {
        "id": int(person.id),  # type: ignore[arg-type]
        "name": person.name,
        "title": person.title,
        "affiliation": person.affiliation,
        "person_type": person.person_type,
        "public_figure": bool(person.public_figure),
        "stylebook_person_canonical_id": person.stylebook_person_canonical_id,
    }


def _location_entity_payload(location: SubstrateLocation) -> dict[str, Any]:
    return {
        "id": int(location.id),  # type: ignore[arg-type]
        "name": location.name,
        "location_type": location.location_type,
        "formatted_address": location.formatted_address,
        "stylebook_location_canonical_id": location.stylebook_location_canonical_id,
    }


def _person_canonical_payload(
    session: Session,
    person: SubstratePerson,
) -> dict[str, Any] | None:
    cid = person.stylebook_person_canonical_id
    if not cid:
        return None
    row = session.get(StylebookPersonCanonical, str(cid))
    if row is None:
        return {"id": str(cid)}
    return {
        "id": str(row.id),
        "label": row.label,
        "title": row.title,
        "affiliation": row.affiliation,
        "person_type": row.person_type,
    }


def _location_canonical_payload(
    session: Session,
    location: SubstrateLocation,
) -> dict[str, Any] | None:
    cid = location.stylebook_location_canonical_id
    if not cid:
        return None
    row = session.get(StylebookLocationCanonical, str(cid))
    if row is None:
        return {"id": str(cid)}
    return {
        "id": str(row.id),
        "label": row.label,
        "location_type": row.location_type,
        "formatted_address": row.formatted_address,
    }


def _mention_payload(
    mention: SubstratePersonMention | SubstrateLocationMention,
) -> dict[str, Any]:
    return {
        "id": int(mention.id),  # type: ignore[arg-type]
        "role_in_story": mention.role_in_story,
        "nature": mention.nature,
        "nature_secondary_tags": list(mention.nature_secondary_tags_json or []),
    }


def _occurrence_payload(
    occurrence: SubstratePersonMentionOccurrence | SubstrateLocationMentionOccurrence,
) -> dict[str, Any]:
    labels = list(occurrence.labels_json or [])
    quote_text = occurrence.quote_text
    return {
        "id": int(occurrence.id),  # type: ignore[arg-type]
        "mention_text": occurrence.mention_text,
        "quote_text": quote_text,
        "start_char": occurrence.start_char,
        "end_char": occurrence.end_char,
        "occurrence_order": occurrence.occurrence_order,
        "suppressed": bool(occurrence.suppressed),
        "is_quote": _occurrence_is_quote(quote_text=quote_text, labels_json=labels),
        "labels": labels,
    }


def _rank_and_page(
    rows: list[tuple[Any, ...]],
    *,
    query_vector: list[float],
    doc_index: int,
    occurrence_index: int,
    quote_status: QuoteStatusFilter,
    limit: int,
    offset: int,
) -> tuple[list[tuple[float, tuple[Any, ...]]], int]:
    ranked: list[tuple[float, tuple[Any, ...]]] = []
    for row in rows:
        doc = row[doc_index]
        occurrence = row[occurrence_index]
        if not _matches_quote_status(
            quote_status,
            quote_text=occurrence.quote_text,
            labels_json=list(occurrence.labels_json or []),
        ):
            continue
        vector = _coerce_embedding_vector(getattr(doc, "embedding", None))
        if vector is None:
            continue
        score = cosine_similarity(query_vector, vector)
        ranked.append((score, row))
    ranked.sort(
        key=lambda item: (
            -item[0],
            int(getattr(item[1][doc_index], "id", 0) or 0),
        )
    )
    return ranked[offset : offset + limit], len(ranked)


def search_person_semantic_mentions(
    session: Session,
    *,
    project_id: int,
    query_vector: list[float],
    filters: PersonSemanticSearchFilters,
    limit: int = 20,
    offset: int = 0,
) -> SemanticMentionSearchResult:
    """Search ready person semantic documents with structured filters and vector ranking."""
    stmt = (
        select(
            SubstratePersonSemanticDocument,
            SubstratePerson,
            SubstratePersonMention,
            SubstratePersonMentionOccurrence,
            SubstrateArticle,
        )
        .join(
            SubstratePerson,
            col(SubstratePersonSemanticDocument.person_id) == SubstratePerson.id,
        )
        .join(
            SubstratePersonMention,
            col(SubstratePersonSemanticDocument.person_mention_id) == SubstratePersonMention.id,
        )
        .join(
            SubstratePersonMentionOccurrence,
            col(SubstratePersonSemanticDocument.person_mention_occurrence_id)
            == SubstratePersonMentionOccurrence.id,
        )
        .join(
            SubstrateArticle,
            col(SubstratePersonSemanticDocument.article_id) == SubstrateArticle.id,
        )
    )
    stmt = _apply_shared_filters(
        stmt,
        doc_model=SubstratePersonSemanticDocument,
        project_id=project_id,
        filters=filters,
        entity_id_col=SubstratePersonSemanticDocument.person_id,
        mention_id_col=SubstratePersonSemanticDocument.person_mention_id,
        occurrence_id_col=SubstratePersonSemanticDocument.person_mention_occurrence_id,
        canonical_id_col=SubstratePerson.stylebook_person_canonical_id,
        quote_text_col=SubstratePersonMentionOccurrence.quote_text,
    )
    if filters.person_type is not None:
        stmt = stmt.where(SubstratePerson.person_type == filters.person_type)
    if filters.public_figure is not None:
        stmt = stmt.where(SubstratePerson.public_figure.is_(bool(filters.public_figure)))
    if filters.nature is not None:
        stmt = stmt.where(SubstratePersonMention.nature == filters.nature)
    if filters.title is not None:
        stmt = stmt.where(SubstratePerson.title == filters.title)
    if filters.affiliation is not None:
        stmt = stmt.where(SubstratePerson.affiliation == filters.affiliation)

    rows = list(session.exec(stmt).all())
    page, total = _rank_and_page(
        rows,
        query_vector=query_vector,
        doc_index=0,
        occurrence_index=3,
        quote_status=filters.quote_status,
        limit=limit,
        offset=offset,
    )
    hits = [
        SemanticMentionSearchHit(
            semantic_document_id=int(doc.id),
            entity_type="person",
            score=score,
            article=_article_payload(article),
            entity=_person_entity_payload(person),
            canonical=_person_canonical_payload(session, person),
            mention=_mention_payload(mention),
            occurrence=_occurrence_payload(occurrence),
            search_text=str(doc.search_text),
        )
        for score, (doc, person, mention, occurrence, article) in page
    ]
    return SemanticMentionSearchResult(
        total=total,
        limit=limit,
        offset=offset,
        hits=tuple(hits),
    )


def search_location_semantic_mentions(
    session: Session,
    *,
    project_id: int,
    query_vector: list[float],
    filters: LocationSemanticSearchFilters,
    limit: int = 20,
    offset: int = 0,
) -> SemanticMentionSearchResult:
    """Search ready location semantic documents with structured filters and vector ranking."""
    stmt = (
        select(
            SubstrateLocationSemanticDocument,
            SubstrateLocation,
            SubstrateLocationMention,
            SubstrateLocationMentionOccurrence,
            SubstrateArticle,
        )
        .join(
            SubstrateLocation,
            col(SubstrateLocationSemanticDocument.location_id) == SubstrateLocation.id,
        )
        .join(
            SubstrateLocationMention,
            col(SubstrateLocationSemanticDocument.location_mention_id)
            == SubstrateLocationMention.id,
        )
        .join(
            SubstrateLocationMentionOccurrence,
            col(SubstrateLocationSemanticDocument.location_mention_occurrence_id)
            == SubstrateLocationMentionOccurrence.id,
        )
        .join(
            SubstrateArticle,
            col(SubstrateLocationSemanticDocument.article_id) == SubstrateArticle.id,
        )
    )
    stmt = _apply_shared_filters(
        stmt,
        doc_model=SubstrateLocationSemanticDocument,
        project_id=project_id,
        filters=filters,
        entity_id_col=SubstrateLocationSemanticDocument.location_id,
        mention_id_col=SubstrateLocationSemanticDocument.location_mention_id,
        occurrence_id_col=SubstrateLocationSemanticDocument.location_mention_occurrence_id,
        canonical_id_col=SubstrateLocation.stylebook_location_canonical_id,
        quote_text_col=SubstrateLocationMentionOccurrence.quote_text,
    )
    if filters.location_type is not None:
        stmt = stmt.where(SubstrateLocation.location_type == filters.location_type)

    rows = list(session.exec(stmt).all())
    page, total = _rank_and_page(
        rows,
        query_vector=query_vector,
        doc_index=0,
        occurrence_index=3,
        quote_status=filters.quote_status,
        limit=limit,
        offset=offset,
    )
    hits = [
        SemanticMentionSearchHit(
            semantic_document_id=int(doc.id),
            entity_type="location",
            score=score,
            article=_article_payload(article),
            entity=_location_entity_payload(location),
            canonical=_location_canonical_payload(session, location),
            mention=_mention_payload(mention),
            occurrence=_occurrence_payload(occurrence),
            search_text=str(doc.search_text),
        )
        for score, (doc, location, mention, occurrence, article) in page
    ]
    return SemanticMentionSearchResult(
        total=total,
        limit=limit,
        offset=offset,
        hits=tuple(hits),
    )
