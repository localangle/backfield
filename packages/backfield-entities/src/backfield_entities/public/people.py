"""Canonical person queries for the public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from backfield_db import (
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from pydantic import BaseModel
from sqlalchemy import case, exists, literal, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from backfield_entities.public.articles import PublicArticleOut
from backfield_entities.public.entity_articles import (
    collect_mention_article_pairs,
    paginate_public_articles_from_mention_pairs,
)
from backfield_entities.public.mention_evidence import (
    PublicMentionEvidenceOut,
    person_evidence_by_mention_id,
)
from backfield_entities.public.mention_filters import (
    PublicEntityMentionListParams,
    apply_entity_mention_list_filters,
)
from backfield_entities.public.stylebook_scope import (
    get_public_person_canonical,
    stylebook_slugs_by_id,
)


def _escape_ilike_metacharacters(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _canonical_list_sort_key():
    return func.coalesce(
        func.lower(col(StylebookPersonCanonical.sort_key)),
        func.lower(col(StylebookPersonCanonical.label)),
    )


def _person_list_sort_tiebreakers() -> tuple:
    """Last-name order, then full label (first name) for shared sort keys."""
    return (
        _canonical_list_sort_key().asc(),
        func.lower(col(StylebookPersonCanonical.label)).asc(),
        col(StylebookPersonCanonical.id).asc(),
    )


class PublicPersonSort(StrEnum):
    sort_key = "sort_key"
    recent = "recent"
    label = "label"


class PublicPersonOut(BaseModel):
    id: str
    slug: str
    label: str
    stylebook_slug: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    person_type: str | None = None
    mention_count: int = 0
    story_count: int = 0


class PublicPersonMentionArticleOut(BaseModel):
    id: int
    headline: str
    url: str | None = None
    pub_date: date | None = None


class PublicPersonMentionOut(BaseModel):
    mention_id: int
    article: PublicPersonMentionArticleOut
    label: str
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    nature: str | None = None
    role_in_story: str | None = None
    evidence: PublicMentionEvidenceOut | None = None


@dataclass(frozen=True)
class PublicPersonSearchParams:
    q: str | None = None
    person_type: str | None = None
    public_figure: bool | None = None
    title: str | None = None
    affiliation: str | None = None
    nature: str | None = None
    min_mentions: int = 0
    sort: PublicPersonSort = PublicPersonSort.sort_key
    limit: int = 25
    offset: int = 0


def _person_to_public_out(
    canon: StylebookPersonCanonical,
    *,
    mention_count: int = 0,
    story_count: int = 0,
    stylebook_slug: str | None = None,
) -> PublicPersonOut:
    return PublicPersonOut(
        id=str(canon.id),
        slug=str(canon.slug),
        label=str(canon.label),
        stylebook_slug=stylebook_slug,
        title=canon.title,
        affiliation=canon.affiliation,
        public_figure=bool(canon.public_figure),
        person_type=canon.person_type,
        mention_count=mention_count,
        story_count=story_count,
    )


def _mention_counts_by_canonical(
    session: Session,
    *,
    project_id: int,
    canonical_ids: list[str],
) -> dict[str, int]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(col(SubstratePersonMention.id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            SubstratePerson.project_id == project_id,
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _story_counts_by_canonical(
    session: Session,
    *,
    project_id: int,
    canonical_ids: list[str],
) -> dict[str, int]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            SubstratePerson.stylebook_person_canonical_id,
            func.count(func.distinct(SubstratePersonMention.article_id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            SubstratePerson.project_id == project_id,
            col(SubstratePerson.stylebook_person_canonical_id).in_(canonical_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePerson.stylebook_person_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _person_filters(
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicPersonSearchParams,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        StylebookPersonCanonical.stylebook_id == stylebook_id,
        StylebookPersonCanonical.status == "active",
    ]
    q_text = (params.q or "").strip()
    if q_text:
        esc = _escape_ilike_metacharacters(q_text)
        term = f"%{esc}%"
        filters.append(
            or_(
                col(StylebookPersonCanonical.label).ilike(term, escape="\\"),
                col(StylebookPersonCanonical.title).ilike(term, escape="\\"),
                col(StylebookPersonCanonical.affiliation).ilike(term, escape="\\"),
            )
        )
    person_type = (params.person_type or "").strip()
    if person_type:
        filters.append(col(StylebookPersonCanonical.person_type) == person_type)
    if params.public_figure is not None:
        filters.append(StylebookPersonCanonical.public_figure == params.public_figure)
    title_text = (params.title or "").strip()
    if title_text:
        esc = _escape_ilike_metacharacters(title_text)
        filters.append(col(StylebookPersonCanonical.title).ilike(f"%{esc}%", escape="\\"))
    affiliation_text = (params.affiliation or "").strip()
    if affiliation_text:
        esc = _escape_ilike_metacharacters(affiliation_text)
        filters.append(
            col(StylebookPersonCanonical.affiliation).ilike(f"%{esc}%", escape="\\")
        )
    nature = (params.nature or "").strip()
    if nature:
        filters.append(
            exists().where(
                SubstratePerson.stylebook_person_canonical_id == StylebookPersonCanonical.id,
                SubstratePerson.project_id == project_id,
                SubstratePersonMention.person_id == SubstratePerson.id,
                SubstratePersonMention.deleted == False,  # noqa: E712
                SubstratePersonMention.nature == nature,
            )
        )
    if params.min_mentions > 0:
        min_stmt = (
            select(SubstratePerson.stylebook_person_canonical_id)
            .select_from(SubstratePersonMention)
            .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
            .where(
                SubstratePerson.project_id == project_id,
                col(SubstratePerson.stylebook_person_canonical_id).is_not(None),
                SubstratePersonMention.deleted == False,  # noqa: E712
            )
            .group_by(SubstratePerson.stylebook_person_canonical_id)
            .having(func.count(col(SubstratePersonMention.id)) >= params.min_mentions)
        )
        filters.append(col(StylebookPersonCanonical.id).in_(min_stmt))
    return filters


def _activity_order_columns(*, project_id: int) -> tuple:
    max_sub_updated = (
        select(func.max(col(SubstratePerson.updated_at)))
        .where(
            col(SubstratePerson.stylebook_person_canonical_id) == col(StylebookPersonCanonical.id),
            SubstratePerson.project_id == project_id,
        )
        .scalar_subquery()
    )
    canon_updated = col(StylebookPersonCanonical.updated_at)
    coalesced = func.coalesce(max_sub_updated, canon_updated)
    activity = case(
        (coalesced > canon_updated, coalesced),
        else_=canon_updated,
    )
    return (activity.desc(), *_person_list_sort_tiebreakers())


def search_public_people(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicPersonSearchParams,
) -> tuple[list[PublicPersonOut], int]:
    filters = _person_filters(
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=params,
    )
    total = int(
        session.scalar(select(func.count()).select_from(StylebookPersonCanonical).where(*filters))
        or 0
    )

    label_lower = func.lower(col(StylebookPersonCanonical.label))
    label_col = col(StylebookPersonCanonical.label)
    q_text = (params.q or "").strip()
    if params.sort == PublicPersonSort.recent:
        order_by = _activity_order_columns(project_id=project_id)
    elif q_text:
        q_lower = q_text.lower()
        esc = _escape_ilike_metacharacters(q_text)
        prefix_pat = f"{esc}%"
        rank = case(
            (label_lower == literal(q_lower), 0),
            (label_col.ilike(prefix_pat, escape="\\"), 1),
            else_=2,
        )
        order_by = (
            rank.asc(),
            func.length(label_col).asc(),
            *_person_list_sort_tiebreakers(),
        )
    else:
        order_by = _person_list_sort_tiebreakers()

    rows = list(
        session.exec(
            select(StylebookPersonCanonical)
            .where(*filters)
            .order_by(*order_by)
            .offset(params.offset)
            .limit(params.limit)
        ).all()
    )
    canonical_ids = [str(row.id) for row in rows if row.id is not None]
    mention_counts = _mention_counts_by_canonical(
        session,
        project_id=project_id,
        canonical_ids=canonical_ids,
    )
    stylebook_slug = stylebook_slugs_by_id(session, {stylebook_id}).get(stylebook_id)
    items = [
        _person_to_public_out(
            row,
            mention_count=mention_counts.get(str(row.id), 0),
            stylebook_slug=stylebook_slug,
        )
        for row in rows
    ]
    return items, total


def get_public_person(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    person_id: str,
) -> PublicPersonOut | None:
    canon = get_public_person_canonical(session, stylebook_id=stylebook_id, person_id=person_id)
    if canon is None:
        return None
    mention_counts = _mention_counts_by_canonical(
        session,
        project_id=project_id,
        canonical_ids=[str(canon.id)],
    )
    story_counts = _story_counts_by_canonical(
        session,
        project_id=project_id,
        canonical_ids=[str(canon.id)],
    )
    stylebook_slug = stylebook_slugs_by_id(session, {stylebook_id}).get(stylebook_id)
    return _person_to_public_out(
        canon,
        mention_count=mention_counts.get(str(canon.id), 0),
        story_count=story_counts.get(str(canon.id), 0),
        stylebook_slug=stylebook_slug,
    )


def list_public_person_mentions(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    person_id: str,
    params: PublicEntityMentionListParams | None = None,
) -> tuple[list[PublicPersonMentionOut], int] | None:
    list_params = params or PublicEntityMentionListParams()
    canon = get_public_person_canonical(session, stylebook_id=stylebook_id, person_id=person_id)
    if canon is None:
        return None

    base_where: list[ColumnElement[bool]] = [
        SubstratePerson.stylebook_person_canonical_id == str(canon.id),
        SubstratePerson.project_id == project_id,
        SubstratePersonMention.deleted == False,  # noqa: E712
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    count_stmt = (
        select(func.count())
        .select_from(SubstratePersonMention)
        .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(*base_where)
    )
    count_stmt = apply_entity_mention_list_filters(
        count_stmt,
        params=list_params,
        mention_nature_col=SubstratePersonMention.nature,
        mention_id_col=SubstratePersonMention.id,
        occurrence_model=SubstratePersonMentionOccurrence,
        mention_fk_column="person_mention_id",
    )
    total = int(session.scalar(count_stmt) or 0)

    descending = list_params.sort_direction != "asc"
    if list_params.sort == "article":
        headline_sort = col(SubstrateArticle.headline)
        order_by = headline_sort.desc() if descending else headline_sort.asc()
    else:
        ts = col(SubstratePersonMention.updated_at)
        order_by = ts.desc() if descending else ts.asc()

    select_stmt = (
        select(SubstratePersonMention, SubstrateArticle, SubstratePerson)
        .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(*base_where)
    )
    select_stmt = apply_entity_mention_list_filters(
        select_stmt,
        params=list_params,
        mention_nature_col=SubstratePersonMention.nature,
        mention_id_col=SubstratePersonMention.id,
        occurrence_model=SubstratePersonMentionOccurrence,
        mention_fk_column="person_mention_id",
    )
    triples = list(
        session.exec(
            select_stmt.order_by(order_by)
            .offset(list_params.offset)
            .limit(list_params.limit)
        ).all()
    )
    mention_ids = [int(m.id) for m, _, _ in triples if m.id is not None]  # type: ignore[union-attr]
    evidence_by_id = person_evidence_by_mention_id(session, mention_ids)

    items: list[PublicPersonMentionOut] = []
    for mention, article, person in triples:
        if mention.id is None or article.id is None:
            continue
        mid = int(mention.id)
        items.append(
            PublicPersonMentionOut(
                mention_id=mid,
                article=PublicPersonMentionArticleOut(
                    id=int(article.id),
                    headline=str(article.headline),
                    url=article.url,
                    pub_date=article.pub_date,
                ),
                label=str(person.name),
                person_type=person.person_type,
                title=(person.title or "").strip() or None,
                affiliation=(person.affiliation or "").strip() or None,
                nature=mention.nature,
                role_in_story=mention.role_in_story,
                evidence=evidence_by_id.get(mid),
            )
        )
    return items, total


def list_public_person_articles(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    person_id: str,
    limit: int = 25,
    offset: int = 0,
    nature: str | None = None,
) -> tuple[list[PublicArticleOut], int] | None:
    canon = get_public_person_canonical(session, stylebook_id=stylebook_id, person_id=person_id)
    if canon is None:
        return None

    pairs = collect_mention_article_pairs(
        session,
        mention_model=SubstratePersonMention,
        entity_model=SubstratePerson,
        mention_entity_fk=SubstratePersonMention.person_id,
        entity_canonical_col=SubstratePerson.stylebook_person_canonical_id,
        canonical_id=str(canon.id),
        project_id=project_id,
        nature=nature,
    )
    items, total = paginate_public_articles_from_mention_pairs(
        session,
        pairs=pairs,
        limit=limit,
        offset=offset,
    )
    return items, total
