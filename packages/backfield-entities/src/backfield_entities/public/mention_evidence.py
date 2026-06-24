"""First occurrence evidence helpers for public mention responses."""

from __future__ import annotations

from backfield_db import (
    SubstrateLocationMentionOccurrence,
    SubstrateOrganizationMentionOccurrence,
    SubstratePersonMentionOccurrence,
)
from pydantic import BaseModel
from sqlalchemy import String, and_, cast, exists, func, literal, or_
from sqlmodel import Session, col, select


class PublicMentionEvidenceOut(BaseModel):
    mention_text: str | None = None
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None


class PublicArticleMentionEvidenceOut(BaseModel):
    mention_text: str | None = None
    quote: bool = False
    start_char: int | None = None
    end_char: int | None = None


class PublicMentionOccurrenceOut(BaseModel):
    mention_text: str | None = None
    quote_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    occurrence_order: int | None = None


def _occurrence_is_quote(
    *,
    quote_text: str | None,
    labels_json: list[str] | None,
) -> bool:
    if isinstance(quote_text, str) and quote_text.strip():
        return True
    labels = labels_json or []
    return any(str(label).strip().lower() == "quote" for label in labels)


def _occurrence_is_quote_sql(occurrence_model) -> object:
    quote_text_present = and_(
        occurrence_model.quote_text.isnot(None),
        func.length(func.trim(occurrence_model.quote_text)) > 0,
    )
    labels_has_quote = func.lower(cast(occurrence_model.labels_json, String)).like('%"quote"%')
    return or_(quote_text_present, labels_has_quote)


def mention_has_quoted_first_occurrence(
    mention_id_col,
    *,
    occurrence_model,
    mention_fk_column: str,
) -> object:
    """SQL EXISTS: the mention's first non-suppressed occurrence is quoted."""
    fk_col = getattr(occurrence_model, mention_fk_column)
    first_occ_id = (
        select(occurrence_model.id)
        .where(
            fk_col == mention_id_col,
            occurrence_model.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(occurrence_model.occurrence_order).asc().nulls_last(),
            col(occurrence_model.id),
        )
        .limit(1)
        .correlate_except(occurrence_model)
        .scalar_subquery()
    )
    return exists(
        select(literal(1))
        .select_from(occurrence_model)
        .where(
            occurrence_model.id == first_occ_id,
            _occurrence_is_quote_sql(occurrence_model),
        )
    )


def maybe_quotes_only_mention_filters(
    mention_id_col,
    *,
    occurrence_model,
    mention_fk_column: str,
    quotes_only: bool,
) -> list[object]:
    """Return SQL WHERE fragments limiting to mentions with quoted first occurrence."""
    if not quotes_only:
        return []
    return [
        mention_has_quoted_first_occurrence(
            mention_id_col,
            occurrence_model=occurrence_model,
            mention_fk_column=mention_fk_column,
        )
    ]


def _article_evidence_from_occurrence(
    occ: SubstrateLocationMentionOccurrence
    | SubstratePersonMentionOccurrence
    | SubstrateOrganizationMentionOccurrence,
) -> PublicArticleMentionEvidenceOut:
    raw_mention = (occ.mention_text or "").strip()
    raw_quote = (occ.quote_text or "").strip() if occ.quote_text else ""
    return PublicArticleMentionEvidenceOut(
        mention_text=raw_quote or raw_mention or None,
        quote=_occurrence_is_quote(quote_text=occ.quote_text, labels_json=occ.labels_json),
        start_char=occ.start_char,
        end_char=occ.end_char,
    )


def _first_article_evidence_by_mention_id(
    session: Session,
    *,
    mention_ids: list[int],
    occurrence_model: type[
        SubstrateLocationMentionOccurrence
        | SubstratePersonMentionOccurrence
        | SubstrateOrganizationMentionOccurrence
    ],
    mention_id_column: str,
) -> dict[int, PublicArticleMentionEvidenceOut]:
    if not mention_ids:
        return {}
    mention_col = getattr(occurrence_model, mention_id_column)
    rows = session.exec(
        select(occurrence_model)
        .where(
            col(mention_col).in_(mention_ids),
            occurrence_model.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(mention_col),
            col(occurrence_model.occurrence_order).asc().nulls_last(),
            col(occurrence_model.id),
        )
    ).all()
    out: dict[int, PublicArticleMentionEvidenceOut] = {}
    for occ in rows:
        mid = int(getattr(occ, mention_id_column))
        if mid in out:
            continue
        out[mid] = _article_evidence_from_occurrence(occ)
    return out


def _first_occurrence_by_mention_id(
    session: Session,
    *,
    mention_ids: list[int],
    occurrence_model: type[
        SubstrateLocationMentionOccurrence
        | SubstratePersonMentionOccurrence
        | SubstrateOrganizationMentionOccurrence
    ],
    mention_id_column: str,
) -> dict[int, PublicMentionEvidenceOut]:
    if not mention_ids:
        return {}
    mention_col = getattr(occurrence_model, mention_id_column)
    rows = session.exec(
        select(occurrence_model)
        .where(
            col(mention_col).in_(mention_ids),
            occurrence_model.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(mention_col),
            col(occurrence_model.occurrence_order).asc().nulls_last(),
            col(occurrence_model.id),
        )
    ).all()
    out: dict[int, PublicMentionEvidenceOut] = {}
    for occ in rows:
        mid = int(getattr(occ, mention_id_column))
        if mid in out:
            continue
        mention_text = (occ.mention_text or "").strip() or None
        quote_text = (occ.quote_text or "").strip() if occ.quote_text else None
        out[mid] = PublicMentionEvidenceOut(
            mention_text=mention_text,
            quote_text=quote_text,
            start_char=occ.start_char,
            end_char=occ.end_char,
        )
    return out


def location_evidence_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicMentionEvidenceOut]:
    return _first_occurrence_by_mention_id(
        session,
        mention_ids=mention_ids,
        occurrence_model=SubstrateLocationMentionOccurrence,
        mention_id_column="location_mention_id",
    )


def person_evidence_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicMentionEvidenceOut]:
    return _first_occurrence_by_mention_id(
        session,
        mention_ids=mention_ids,
        occurrence_model=SubstratePersonMentionOccurrence,
        mention_id_column="person_mention_id",
    )


def organization_evidence_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicMentionEvidenceOut]:
    return _first_occurrence_by_mention_id(
        session,
        mention_ids=mention_ids,
        occurrence_model=SubstrateOrganizationMentionOccurrence,
        mention_id_column="organization_mention_id",
    )


def location_article_mention_evidence_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicArticleMentionEvidenceOut]:
    return _first_article_evidence_by_mention_id(
        session,
        mention_ids=mention_ids,
        occurrence_model=SubstrateLocationMentionOccurrence,
        mention_id_column="location_mention_id",
    )


def person_article_mention_evidence_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicArticleMentionEvidenceOut]:
    return _first_article_evidence_by_mention_id(
        session,
        mention_ids=mention_ids,
        occurrence_model=SubstratePersonMentionOccurrence,
        mention_id_column="person_mention_id",
    )


def organization_article_mention_evidence_by_mention_id(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicArticleMentionEvidenceOut]:
    return _first_article_evidence_by_mention_id(
        session,
        mention_ids=mention_ids,
        occurrence_model=SubstrateOrganizationMentionOccurrence,
        mention_id_column="organization_mention_id",
    )


def _occurrence_to_out(
    occ: SubstrateLocationMentionOccurrence
    | SubstratePersonMentionOccurrence
    | SubstrateOrganizationMentionOccurrence,
) -> PublicMentionOccurrenceOut:
    mention_text = (occ.mention_text or "").strip() or None
    quote_text = (occ.quote_text or "").strip() if occ.quote_text else None
    return PublicMentionOccurrenceOut(
        mention_text=mention_text,
        quote_text=quote_text,
        start_char=occ.start_char,
        end_char=occ.end_char,
        occurrence_order=occ.occurrence_order,
    )


def occurrences_by_mention_id(
    session: Session,
    *,
    mention_id: int,
    occurrence_model: type[
        SubstrateLocationMentionOccurrence
        | SubstratePersonMentionOccurrence
        | SubstrateOrganizationMentionOccurrence
    ],
    mention_id_column: str,
) -> list[PublicMentionOccurrenceOut]:
    """Return all non-suppressed occurrences for one mention, in display order."""
    mention_col = getattr(occurrence_model, mention_id_column)
    rows = session.exec(
        select(occurrence_model)
        .where(
            mention_col == mention_id,
            occurrence_model.suppressed == False,  # noqa: E712
        )
        .order_by(
            col(occurrence_model.occurrence_order).asc().nulls_last(),
            col(occurrence_model.id),
        )
    ).all()
    return [_occurrence_to_out(row) for row in rows]
