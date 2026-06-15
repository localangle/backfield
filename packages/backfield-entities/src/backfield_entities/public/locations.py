"""Canonical location queries for the public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from backfield_db import (
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
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
    location_evidence_by_mention_id,
)
from backfield_entities.public.stylebook_scope import (
    get_public_location_canonical,
    stylebook_slugs_by_id,
)


def _escape_ilike_metacharacters(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PublicLocationSort(StrEnum):
    label = "label"
    recent = "recent"


class PublicLocationOut(BaseModel):
    id: str
    slug: str
    label: str
    stylebook_slug: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_type: str | None = None
    geometry_json: dict[str, Any] | None = None
    h3_cell: str | None = None
    h3_resolution: int | None = None
    mention_count: int = 0


class PublicLocationMentionArticleOut(BaseModel):
    id: int
    headline: str
    url: str | None = None
    pub_date: date | None = None


class PublicLocationMentionOut(BaseModel):
    mention_id: int
    article: PublicLocationMentionArticleOut
    label: str
    location_type: str | None = None
    formatted_address: str | None = None
    nature: str | None = None
    role_in_story: str | None = None
    evidence: PublicMentionEvidenceOut | None = None


@dataclass(frozen=True)
class PublicLocationSearchParams:
    q: str | None = None
    location_type: str | None = None
    nature: str | None = None
    min_mentions: int = 0
    sort: PublicLocationSort = PublicLocationSort.label
    limit: int = 25
    offset: int = 0


def _location_to_public_out(
    canon: StylebookLocationCanonical,
    *,
    mention_count: int = 0,
    stylebook_slug: str | None = None,
) -> PublicLocationOut:
    return PublicLocationOut(
        id=str(canon.id),
        slug=str(canon.slug),
        label=str(canon.label),
        stylebook_slug=stylebook_slug,
        location_type=canon.location_type,
        formatted_address=canon.formatted_address,
        geometry_type=canon.geometry_type,
        geometry_json=canon.geometry_json,
        h3_cell=canon.h3_cell,
        h3_resolution=canon.h3_resolution,
        mention_count=mention_count,
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
            SubstrateLocation.stylebook_location_canonical_id,
            func.count(col(SubstrateLocationMention.id)),
        )
        .select_from(SubstrateLocationMention)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            SubstrateLocation.project_id == project_id,
            col(SubstrateLocation.stylebook_location_canonical_id).in_(canonical_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateLocation.stylebook_location_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def location_filters(
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicLocationSearchParams,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        StylebookLocationCanonical.stylebook_id == stylebook_id,
        StylebookLocationCanonical.status == "active",
    ]
    q_text = (params.q or "").strip()
    if q_text:
        esc = _escape_ilike_metacharacters(q_text)
        term = f"%{esc}%"
        filters.append(
            or_(
                col(StylebookLocationCanonical.label).ilike(term, escape="\\"),
                col(StylebookLocationCanonical.formatted_address).ilike(term, escape="\\"),
            )
        )
    location_type = (params.location_type or "").strip()
    if location_type:
        filters.append(col(StylebookLocationCanonical.location_type) == location_type)
    nature = (params.nature or "").strip()
    if nature:
        filters.append(
            exists().where(
                SubstrateLocation.stylebook_location_canonical_id == StylebookLocationCanonical.id,
                SubstrateLocation.project_id == project_id,
                SubstrateLocationMention.location_id == SubstrateLocation.id,
                SubstrateLocationMention.deleted == False,  # noqa: E712
                SubstrateLocationMention.nature == nature,
            )
        )
    if params.min_mentions > 0:
        min_stmt = (
            select(SubstrateLocation.stylebook_location_canonical_id)
            .select_from(SubstrateLocationMention)
            .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
            .where(
                SubstrateLocation.project_id == project_id,
                col(SubstrateLocation.stylebook_location_canonical_id).is_not(None),
                SubstrateLocationMention.deleted == False,  # noqa: E712
            )
            .group_by(SubstrateLocation.stylebook_location_canonical_id)
            .having(func.count(col(SubstrateLocationMention.id)) >= params.min_mentions)
        )
        filters.append(col(StylebookLocationCanonical.id).in_(min_stmt))
    return filters


def _activity_order_columns(*, project_id: int) -> tuple:
    max_sub_updated = (
        select(func.max(col(SubstrateLocation.updated_at)))
        .where(
            col(SubstrateLocation.stylebook_location_canonical_id)
            == col(StylebookLocationCanonical.id),
            SubstrateLocation.project_id == project_id,
        )
        .scalar_subquery()
    )
    canon_updated = col(StylebookLocationCanonical.updated_at)
    coalesced = func.coalesce(max_sub_updated, canon_updated)
    activity = case(
        (coalesced > canon_updated, coalesced),
        else_=canon_updated,
    )
    label_lower = func.lower(col(StylebookLocationCanonical.label))
    return (activity.desc(), label_lower.asc(), col(StylebookLocationCanonical.id).asc())


def _keyword_order_by(*, params: PublicLocationSearchParams, project_id: int) -> tuple:
    label_lower = func.lower(col(StylebookLocationCanonical.label))
    label_col = col(StylebookLocationCanonical.label)
    q_text = (params.q or "").strip()
    if params.sort == PublicLocationSort.recent:
        return _activity_order_columns(project_id=project_id)
    if q_text:
        q_lower = q_text.lower()
        esc = _escape_ilike_metacharacters(q_text)
        prefix_pat = f"{esc}%"
        rank = case(
            (label_lower == literal(q_lower), 0),
            (label_col.ilike(prefix_pat, escape="\\"), 1),
            else_=2,
        )
        return (
            rank.asc(),
            func.length(label_col).asc(),
            label_lower.asc(),
            col(StylebookLocationCanonical.id).asc(),
        )
    return (label_lower.asc(), col(StylebookLocationCanonical.id).asc())


def search_public_locations(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicLocationSearchParams,
) -> tuple[list[PublicLocationOut], int]:
    filters = location_filters(
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=params,
    )
    total = int(
        session.scalar(
            select(func.count()).select_from(StylebookLocationCanonical).where(*filters)
        )
        or 0
    )
    order_by = _keyword_order_by(params=params, project_id=project_id)
    rows = list(
        session.exec(
            select(StylebookLocationCanonical)
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
        _location_to_public_out(
            row,
            mention_count=mention_counts.get(str(row.id), 0),
            stylebook_slug=stylebook_slug,
        )
        for row in rows
    ]
    return items, total


def get_public_location(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    location_id: str,
) -> PublicLocationOut | None:
    canon = get_public_location_canonical(
        session,
        stylebook_id=stylebook_id,
        location_id=location_id,
    )
    if canon is None:
        return None
    mention_counts = _mention_counts_by_canonical(
        session,
        project_id=project_id,
        canonical_ids=[str(canon.id)],
    )
    stylebook_slug = stylebook_slugs_by_id(session, {stylebook_id}).get(stylebook_id)
    return _location_to_public_out(
        canon,
        mention_count=mention_counts.get(str(canon.id), 0),
        stylebook_slug=stylebook_slug,
    )


def list_public_location_mentions(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    location_id: str,
    limit: int = 50,
    offset: int = 0,
    sort: Literal["article", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
) -> tuple[list[PublicLocationMentionOut], int] | None:
    canon = get_public_location_canonical(
        session,
        stylebook_id=stylebook_id,
        location_id=location_id,
    )
    if canon is None:
        return None

    base_where: list[ColumnElement[bool]] = [
        SubstrateLocation.stylebook_location_canonical_id == str(canon.id),
        SubstrateLocation.project_id == project_id,
        SubstrateLocationMention.deleted == False,  # noqa: E712
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    total = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateLocationMention)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
            .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
            .where(*base_where)
        )
        or 0
    )

    descending = sort_direction != "asc"
    if sort == "article":
        headline_sort = col(SubstrateArticle.headline)
        order_by = headline_sort.desc() if descending else headline_sort.asc()
    else:
        ts = col(SubstrateLocationMention.updated_at)
        order_by = ts.desc() if descending else ts.asc()

    triples = list(
        session.exec(
            select(SubstrateLocationMention, SubstrateArticle, SubstrateLocation)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
            .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
            .where(*base_where)
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    mention_ids = [int(m.id) for m, _, _ in triples if m.id is not None]  # type: ignore[union-attr]
    evidence_by_id = location_evidence_by_mention_id(session, mention_ids)

    items: list[PublicLocationMentionOut] = []
    for mention, article, location in triples:
        if mention.id is None or article.id is None:
            continue
        mid = int(mention.id)
        items.append(
            PublicLocationMentionOut(
                mention_id=mid,
                article=PublicLocationMentionArticleOut(
                    id=int(article.id),
                    headline=str(article.headline),
                    url=article.url,
                    pub_date=article.pub_date,
                ),
                label=str(location.name),
                location_type=location.location_type,
                formatted_address=location.formatted_address,
                nature=mention.nature,
                role_in_story=mention.role_in_story,
                evidence=evidence_by_id.get(mid),
            )
        )
    return items, total


def list_public_location_articles(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    location_id: str,
    limit: int = 25,
    offset: int = 0,
    nature: str | None = None,
    include_preview: bool = False,
) -> tuple[list[PublicArticleOut], int] | None:
    canon = get_public_location_canonical(
        session,
        stylebook_id=stylebook_id,
        location_id=location_id,
    )
    if canon is None:
        return None

    pairs = collect_mention_article_pairs(
        session,
        mention_model=SubstrateLocationMention,
        entity_model=SubstrateLocation,
        mention_entity_fk=SubstrateLocationMention.location_id,
        entity_canonical_col=SubstrateLocation.stylebook_location_canonical_id,
        canonical_id=str(canon.id),
        project_id=project_id,
        nature=nature,
    )
    items, total = paginate_public_articles_from_mention_pairs(
        session,
        pairs=pairs,
        limit=limit,
        offset=offset,
        include_preview=include_preview,
    )
    return items, total
