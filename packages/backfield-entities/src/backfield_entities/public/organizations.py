"""Canonical organization queries for the public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from backfield_db import (
    StylebookOrganizationCanonical,
    SubstrateArticle,
    SubstrateOrganization,
    SubstrateOrganizationMention,
)
from pydantic import BaseModel
from sqlalchemy import case, exists, literal
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from backfield_entities.public.articles import PublicArticleOut
from backfield_entities.public.entity_articles import (
    collect_mention_article_pairs,
    paginate_public_articles_from_mention_pairs,
)
from backfield_entities.public.mention_evidence import (
    PublicMentionEvidenceOut,
    organization_evidence_by_mention_id,
)
from backfield_entities.public.stylebook_scope import (
    get_public_organization_canonical,
    stylebook_slugs_by_id,
)


def _escape_ilike_metacharacters(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _canonical_list_sort_key():
    return func.lower(col(StylebookOrganizationCanonical.label))


class PublicOrganizationSort(StrEnum):
    label = "label"
    recent = "recent"


class PublicOrganizationOut(BaseModel):
    id: str
    slug: str
    label: str
    stylebook_slug: str | None = None
    organization_type: str | None = None
    mention_count: int = 0


class PublicOrganizationMentionArticleOut(BaseModel):
    id: int
    headline: str
    url: str | None = None
    pub_date: date | None = None


class PublicOrganizationMentionOut(BaseModel):
    mention_id: int
    article: PublicOrganizationMentionArticleOut
    label: str
    organization_type: str | None = None
    nature: str | None = None
    role_in_story: str | None = None
    evidence: PublicMentionEvidenceOut | None = None


@dataclass(frozen=True)
class PublicOrganizationSearchParams:
    q: str | None = None
    organization_type: str | None = None
    nature: str | None = None
    min_mentions: int = 0
    sort: PublicOrganizationSort = PublicOrganizationSort.label
    limit: int = 25
    offset: int = 0


def _organization_to_public_out(
    canon: StylebookOrganizationCanonical,
    *,
    mention_count: int = 0,
    stylebook_slug: str | None = None,
) -> PublicOrganizationOut:
    return PublicOrganizationOut(
        id=str(canon.id),
        slug=str(canon.slug),
        label=str(canon.label),
        stylebook_slug=stylebook_slug,
        organization_type=canon.organization_type,
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
            SubstrateOrganization.stylebook_organization_canonical_id,
            func.count(col(SubstrateOrganizationMention.id)),
        )
        .select_from(SubstrateOrganizationMention)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            SubstrateOrganization.project_id == project_id,
            col(SubstrateOrganization.stylebook_organization_canonical_id).in_(canonical_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
    ).all()
    return {str(cid): int(cnt) for cid, cnt in rows if cid is not None}


def _organization_filters(
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicOrganizationSearchParams,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        StylebookOrganizationCanonical.stylebook_id == stylebook_id,
        StylebookOrganizationCanonical.status == "active",
    ]
    q_text = (params.q or "").strip()
    if q_text:
        esc = _escape_ilike_metacharacters(q_text)
        term = f"%{esc}%"
        filters.append(col(StylebookOrganizationCanonical.label).ilike(term, escape="\\"))
    org_type = (params.organization_type or "").strip()
    if org_type:
        filters.append(col(StylebookOrganizationCanonical.organization_type) == org_type)
    nature = (params.nature or "").strip()
    if nature:
        filters.append(
            exists().where(
                SubstrateOrganization.stylebook_organization_canonical_id
                == StylebookOrganizationCanonical.id,
                SubstrateOrganization.project_id == project_id,
                SubstrateOrganizationMention.organization_id == SubstrateOrganization.id,
                SubstrateOrganizationMention.deleted == False,  # noqa: E712
                SubstrateOrganizationMention.nature == nature,
            )
        )
    if params.min_mentions > 0:
        min_stmt = (
            select(SubstrateOrganization.stylebook_organization_canonical_id)
            .select_from(SubstrateOrganizationMention)
            .join(
                SubstrateOrganization,
                SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
            )
            .where(
                SubstrateOrganization.project_id == project_id,
                col(SubstrateOrganization.stylebook_organization_canonical_id).is_not(None),
                SubstrateOrganizationMention.deleted == False,  # noqa: E712
            )
            .group_by(SubstrateOrganization.stylebook_organization_canonical_id)
            .having(func.count(col(SubstrateOrganizationMention.id)) >= params.min_mentions)
        )
        filters.append(col(StylebookOrganizationCanonical.id).in_(min_stmt))
    return filters


def _activity_order_columns(*, project_id: int) -> tuple:
    max_sub_updated = (
        select(func.max(col(SubstrateOrganization.updated_at)))
        .where(
            col(SubstrateOrganization.stylebook_organization_canonical_id)
            == col(StylebookOrganizationCanonical.id),
            SubstrateOrganization.project_id == project_id,
        )
        .scalar_subquery()
    )
    canon_updated = col(StylebookOrganizationCanonical.updated_at)
    coalesced = func.coalesce(max_sub_updated, canon_updated)
    activity = case(
        (coalesced > canon_updated, coalesced),
        else_=canon_updated,
    )
    sort_key_col = _canonical_list_sort_key()
    return (activity.desc(), sort_key_col.asc(), col(StylebookOrganizationCanonical.id).asc())


def search_public_organizations(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    params: PublicOrganizationSearchParams,
) -> tuple[list[PublicOrganizationOut], int]:
    filters = _organization_filters(
        stylebook_id=stylebook_id,
        project_id=project_id,
        params=params,
    )
    total = int(
        session.scalar(
            select(func.count()).select_from(StylebookOrganizationCanonical).where(*filters)
        )
        or 0
    )

    label_lower = func.lower(col(StylebookOrganizationCanonical.label))
    label_col = col(StylebookOrganizationCanonical.label)
    sort_key_col = _canonical_list_sort_key()
    q_text = (params.q or "").strip()
    if params.sort == PublicOrganizationSort.recent:
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
            sort_key_col.asc(),
            col(StylebookOrganizationCanonical.id).asc(),
        )
    else:
        order_by = (sort_key_col.asc(), col(StylebookOrganizationCanonical.id).asc())

    rows = list(
        session.exec(
            select(StylebookOrganizationCanonical)
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
        _organization_to_public_out(
            row,
            mention_count=mention_counts.get(str(row.id), 0),
            stylebook_slug=stylebook_slug,
        )
        for row in rows
    ]
    return items, total


def get_public_organization(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    organization_id: str,
) -> PublicOrganizationOut | None:
    canon = get_public_organization_canonical(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    if canon is None:
        return None
    mention_counts = _mention_counts_by_canonical(
        session,
        project_id=project_id,
        canonical_ids=[str(canon.id)],
    )
    stylebook_slug = stylebook_slugs_by_id(session, {stylebook_id}).get(stylebook_id)
    return _organization_to_public_out(
        canon,
        mention_count=mention_counts.get(str(canon.id), 0),
        stylebook_slug=stylebook_slug,
    )


def list_public_organization_mentions(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    organization_id: str,
    limit: int = 50,
    offset: int = 0,
    sort: Literal["article", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
) -> tuple[list[PublicOrganizationMentionOut], int] | None:
    canon = get_public_organization_canonical(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    if canon is None:
        return None

    base_where: list[ColumnElement[bool]] = [
        SubstrateOrganization.stylebook_organization_canonical_id == str(canon.id),
        SubstrateOrganization.project_id == project_id,
        SubstrateOrganizationMention.deleted == False,  # noqa: E712
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    ]

    total = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateOrganizationMention)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateOrganizationMention.article_id)
            .join(
                SubstrateOrganization,
                SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
            )
            .where(*base_where)
        )
        or 0
    )

    descending = sort_direction != "asc"
    if sort == "article":
        headline_sort = col(SubstrateArticle.headline)
        order_by = headline_sort.desc() if descending else headline_sort.asc()
    else:
        ts = col(SubstrateOrganizationMention.updated_at)
        order_by = ts.desc() if descending else ts.asc()

    triples = list(
        session.exec(
            select(SubstrateOrganizationMention, SubstrateArticle, SubstrateOrganization)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateOrganizationMention.article_id)
            .join(
                SubstrateOrganization,
                SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
            )
            .where(*base_where)
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    mention_ids = [int(m.id) for m, _, _ in triples if m.id is not None]  # type: ignore[union-attr]
    evidence_by_id = organization_evidence_by_mention_id(session, mention_ids)

    items: list[PublicOrganizationMentionOut] = []
    for mention, article, organization in triples:
        if mention.id is None or article.id is None:
            continue
        mid = int(mention.id)
        items.append(
            PublicOrganizationMentionOut(
                mention_id=mid,
                article=PublicOrganizationMentionArticleOut(
                    id=int(article.id),
                    headline=str(article.headline),
                    url=article.url,
                    pub_date=article.pub_date,
                ),
                label=str(organization.name),
                organization_type=organization.organization_type,
                nature=mention.nature,
                role_in_story=mention.role_in_story,
                evidence=evidence_by_id.get(mid),
            )
        )
    return items, total


def list_public_organization_articles(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    organization_id: str,
    limit: int = 25,
    offset: int = 0,
    nature: str | None = None,
    include_preview: bool = False,
) -> tuple[list[PublicArticleOut], int] | None:
    canon = get_public_organization_canonical(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    if canon is None:
        return None

    pairs = collect_mention_article_pairs(
        session,
        mention_model=SubstrateOrganizationMention,
        entity_model=SubstrateOrganization,
        mention_entity_fk=SubstrateOrganizationMention.organization_id,
        entity_canonical_col=SubstrateOrganization.stylebook_organization_canonical_id,
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
