"""Project-wide mention queries for the public API."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from pydantic import BaseModel
from sqlalchemy import func, literal, or_, union_all
from sqlmodel import Session, col, select

from backfield_entities.public.article_hub import (
    PublicCanonicalSummaryOut,
    PublicEntityMentionType,
    _canonical_summary,
)
from backfield_entities.public.articles import _apply_public_article_list_filters
from backfield_entities.public.mention_evidence import (
    PublicMentionEvidenceOut,
    PublicMentionOccurrenceOut,
    location_evidence_by_mention_id,
    occurrences_by_mention_id,
    organization_evidence_by_mention_id,
    person_evidence_by_mention_id,
)


def _escape_ilike_metacharacters(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PublicMentionArticleOut(BaseModel):
    id: int
    headline: str
    url: str | None = None
    pub_date: date | None = None


class PublicMentionSearchItemOut(BaseModel):
    entity_type: PublicEntityMentionType
    mention_id: int
    substrate_entity_id: int
    label: str
    nature: str | None = None
    role_in_story: str | None = None
    location_type: str | None = None
    person_type: str | None = None
    organization_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    evidence: PublicMentionEvidenceOut | None = None
    article: PublicMentionArticleOut


class PublicMentionDetailOut(BaseModel):
    entity_type: PublicEntityMentionType
    mention_id: int
    substrate_entity_id: int
    label: str
    nature: str | None = None
    role_in_story: str | None = None
    location_type: str | None = None
    person_type: str | None = None
    organization_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    occurrences: list[PublicMentionOccurrenceOut] = []
    article: PublicMentionArticleOut


class PublicMentionFacetsOut(BaseModel):
    entity_types: list[str]
    natures: list[str]
    location_types: list[str]
    person_types: list[str]
    organization_types: list[str]


@dataclass(frozen=True)
class PublicMentionSearchParams:
    entity_type: PublicEntityMentionType | None = None
    q: str | None = None
    nature: str | None = None
    has_canonical: bool | None = None
    author: str | None = None
    external_source: str | None = None
    section: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    location_type: str | None = None
    person_type: str | None = None
    organization_type: str | None = None
    public_figure: bool | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    limit: int = 25
    offset: int = 0


def resolve_public_mention_search_params(
    params: PublicMentionSearchParams,
) -> PublicMentionSearchParams:
    """Apply search sugar such as ``section`` → subject metadata filter."""
    section_value = (params.section or "").strip()
    if not section_value:
        return params
    return replace(
        params,
        section=None,
        meta_type="subject",
        meta_category=section_value,
    )


def _article_article_out(article: SubstrateArticle) -> PublicMentionArticleOut:
    return PublicMentionArticleOut(
        id=int(article.id),  # type: ignore[arg-type]
        headline=str(article.headline),
        url=article.url,
        pub_date=article.pub_date,
    )


def _apply_entity_name_filter(stmt, *, name_col, normalized_col, q: str):
    esc = _escape_ilike_metacharacters(q)
    term = f"%{esc}%"
    return stmt.where(
        or_(
            col(name_col).ilike(term, escape="\\"),
            col(normalized_col).ilike(term, escape="\\"),
        )
    )


def _apply_canonical_filter(stmt, *, canonical_col, has_canonical: bool | None):
    if has_canonical is True:
        return stmt.where(col(canonical_col).is_not(None))
    if has_canonical is False:
        return stmt.where(col(canonical_col).is_(None))
    return stmt


def _apply_article_filters_to_mention_arm(stmt, params: PublicMentionSearchParams):
    return _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        author=params.author,
        external_source=params.external_source,
        has_mentions=None,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )


def _location_mention_arm(
    *,
    project_id: int,
    params: PublicMentionSearchParams,
):
    stmt = (
        select(
            literal("location").label("entity_type"),
            SubstrateLocationMention.id.label("mention_id"),
            SubstrateArticle.pub_date.label("pub_date"),
        )
        .select_from(SubstrateLocationMention)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
    )
    stmt = _apply_article_filters_to_mention_arm(stmt, params)
    nature_value = (params.nature or "").strip()
    if nature_value:
        stmt = stmt.where(SubstrateLocationMention.nature == nature_value)
    location_type = (params.location_type or "").strip()
    if location_type:
        stmt = stmt.where(SubstrateLocation.location_type == location_type)
    q_text = (params.q or "").strip()
    if q_text:
        stmt = _apply_entity_name_filter(
            stmt,
            name_col=SubstrateLocation.name,
            normalized_col=SubstrateLocation.normalized_name,
            q=q_text,
        )
    stmt = _apply_canonical_filter(
        stmt,
        canonical_col=SubstrateLocation.stylebook_location_canonical_id,
        has_canonical=params.has_canonical,
    )
    return stmt


def _person_mention_arm(
    *,
    project_id: int,
    params: PublicMentionSearchParams,
):
    stmt = (
        select(
            literal("person").label("entity_type"),
            SubstratePersonMention.id.label("mention_id"),
            SubstrateArticle.pub_date.label("pub_date"),
        )
        .select_from(SubstratePersonMention)
        .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
    )
    stmt = _apply_article_filters_to_mention_arm(stmt, params)
    nature_value = (params.nature or "").strip()
    if nature_value:
        stmt = stmt.where(SubstratePersonMention.nature == nature_value)
    person_type = (params.person_type or "").strip()
    if person_type:
        stmt = stmt.where(SubstratePerson.person_type == person_type)
    if params.public_figure is not None:
        stmt = stmt.where(SubstratePerson.public_figure == params.public_figure)
    q_text = (params.q or "").strip()
    if q_text:
        stmt = _apply_entity_name_filter(
            stmt,
            name_col=SubstratePerson.name,
            normalized_col=SubstratePerson.normalized_name,
            q=q_text,
        )
    stmt = _apply_canonical_filter(
        stmt,
        canonical_col=SubstratePerson.stylebook_person_canonical_id,
        has_canonical=params.has_canonical,
    )
    return stmt


def _organization_mention_arm(
    *,
    project_id: int,
    params: PublicMentionSearchParams,
):
    stmt = (
        select(
            literal("organization").label("entity_type"),
            SubstrateOrganizationMention.id.label("mention_id"),
            SubstrateArticle.pub_date.label("pub_date"),
        )
        .select_from(SubstrateOrganizationMention)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateOrganizationMention.article_id)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
    )
    stmt = _apply_article_filters_to_mention_arm(stmt, params)
    nature_value = (params.nature or "").strip()
    if nature_value:
        stmt = stmt.where(SubstrateOrganizationMention.nature == nature_value)
    organization_type = (params.organization_type or "").strip()
    if organization_type:
        stmt = stmt.where(SubstrateOrganization.organization_type == organization_type)
    q_text = (params.q or "").strip()
    if q_text:
        stmt = _apply_entity_name_filter(
            stmt,
            name_col=SubstrateOrganization.name,
            normalized_col=SubstrateOrganization.normalized_name,
            q=q_text,
        )
    stmt = _apply_canonical_filter(
        stmt,
        canonical_col=SubstrateOrganization.stylebook_organization_canonical_id,
        has_canonical=params.has_canonical,
    )
    return stmt


def _mention_union_stmt(
    *,
    project_id: int,
    params: PublicMentionSearchParams,
):
    entity_type = params.entity_type
    parts = []
    if entity_type in (None, "location"):
        parts.append(_location_mention_arm(project_id=project_id, params=params))
    if entity_type in (None, "person"):
        parts.append(_person_mention_arm(project_id=project_id, params=params))
    if entity_type in (None, "organization"):
        parts.append(_organization_mention_arm(project_id=project_id, params=params))
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return union_all(*parts)


def _hydrate_location_search_items(
    session: Session,
    mention_ids: list[int],
) -> dict[int, PublicMentionSearchItemOut]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateLocationMention, SubstrateLocation, SubstrateArticle)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .where(col(SubstrateLocationMention.id).in_(mention_ids))
    ).all()
    canonical_ids = [
        str(loc.stylebook_location_canonical_id)
        for _, loc, _ in rows
        if loc.stylebook_location_canonical_id
    ]
    canonicals: dict[str, StylebookLocationCanonical] = {}
    if canonical_ids:
        canon_rows = session.exec(
            select(StylebookLocationCanonical).where(
                col(StylebookLocationCanonical.id).in_(canonical_ids)
            )
        ).all()
        canonicals = {str(row.id): row for row in canon_rows}
    evidence = location_evidence_by_mention_id(session, mention_ids)
    out: dict[int, PublicMentionSearchItemOut] = {}
    for mention, loc, article in rows:
        if mention.id is None or article.id is None:
            continue
        mid = int(mention.id)
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = loc.stylebook_location_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)])
        out[mid] = PublicMentionSearchItemOut(
            entity_type="location",
            mention_id=mid,
            substrate_entity_id=int(loc.id),  # type: ignore[arg-type]
            label=str(loc.name),
            nature=mention.nature,
            role_in_story=mention.role_in_story,
            location_type=loc.location_type,
            canonical=canon,
            evidence=evidence.get(mid),
            article=_article_article_out(article),
        )
    return out


def _hydrate_person_search_items(
    session: Session,
    mention_ids: list[int],
) -> dict[int, PublicMentionSearchItemOut]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstratePersonMention, SubstratePerson, SubstrateArticle)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .join(SubstrateArticle, SubstrateArticle.id == SubstratePersonMention.article_id)
        .where(col(SubstratePersonMention.id).in_(mention_ids))
    ).all()
    canonical_ids = [
        str(person.stylebook_person_canonical_id)
        for _, person, _ in rows
        if person.stylebook_person_canonical_id
    ]
    canonicals: dict[str, StylebookPersonCanonical] = {}
    if canonical_ids:
        canon_rows = session.exec(
            select(StylebookPersonCanonical).where(col(StylebookPersonCanonical.id).in_(canonical_ids))
        ).all()
        canonicals = {str(row.id): row for row in canon_rows}
    evidence = person_evidence_by_mention_id(session, mention_ids)
    out: dict[int, PublicMentionSearchItemOut] = {}
    for mention, person, article in rows:
        if mention.id is None or article.id is None:
            continue
        mid = int(mention.id)
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = person.stylebook_person_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)])
        out[mid] = PublicMentionSearchItemOut(
            entity_type="person",
            mention_id=mid,
            substrate_entity_id=int(person.id),  # type: ignore[arg-type]
            label=str(person.name),
            nature=mention.nature,
            role_in_story=mention.role_in_story,
            person_type=person.person_type,
            title=(person.title or "").strip() or None,
            affiliation=(person.affiliation or "").strip() or None,
            public_figure=bool(person.public_figure),
            canonical=canon,
            evidence=evidence.get(mid),
            article=_article_article_out(article),
        )
    return out


def _hydrate_organization_search_items(
    session: Session,
    mention_ids: list[int],
) -> dict[int, PublicMentionSearchItemOut]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateOrganizationMention, SubstrateOrganization, SubstrateArticle)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateOrganizationMention.article_id)
        .where(col(SubstrateOrganizationMention.id).in_(mention_ids))
    ).all()
    canonical_ids = [
        str(org.stylebook_organization_canonical_id)
        for _, org, _ in rows
        if org.stylebook_organization_canonical_id
    ]
    canonicals: dict[str, StylebookOrganizationCanonical] = {}
    if canonical_ids:
        canon_rows = session.exec(
            select(StylebookOrganizationCanonical).where(
                col(StylebookOrganizationCanonical.id).in_(canonical_ids)
            )
        ).all()
        canonicals = {str(row.id): row for row in canon_rows}
    evidence = organization_evidence_by_mention_id(session, mention_ids)
    out: dict[int, PublicMentionSearchItemOut] = {}
    for mention, org, article in rows:
        if mention.id is None or article.id is None:
            continue
        mid = int(mention.id)
        canon: PublicCanonicalSummaryOut | None = None
        organization_type = org.organization_type
        canon_id = org.stylebook_organization_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon_row = canonicals[str(canon_id)]
            canon = _canonical_summary(canon_row)
            organization_type = organization_type or canon_row.organization_type
        out[mid] = PublicMentionSearchItemOut(
            entity_type="organization",
            mention_id=mid,
            substrate_entity_id=int(org.id),  # type: ignore[arg-type]
            label=str(org.name),
            nature=mention.nature,
            role_in_story=mention.role_in_story,
            organization_type=organization_type,
            canonical=canon,
            evidence=evidence.get(mid),
            article=_article_article_out(article),
        )
    return out


def _hydrate_search_items(
    session: Session,
    page_rows: list[tuple[str, int]],
) -> list[PublicMentionSearchItemOut]:
    by_type: dict[str, list[int]] = {"location": [], "person": [], "organization": []}
    order: list[tuple[str, int]] = []
    for entity_type, mention_id in page_rows:
        by_type[entity_type].append(mention_id)
        order.append((entity_type, mention_id))

    hydrated: dict[tuple[str, int], PublicMentionSearchItemOut] = {}
    for mid, item in _hydrate_location_search_items(session, by_type["location"]).items():
        hydrated[("location", mid)] = item
    for mid, item in _hydrate_person_search_items(session, by_type["person"]).items():
        hydrated[("person", mid)] = item
    for mid, item in _hydrate_organization_search_items(session, by_type["organization"]).items():
        hydrated[("organization", mid)] = item

    return [hydrated[key] for key in order if key in hydrated]


def search_public_mentions(
    session: Session,
    *,
    project_id: int,
    params: PublicMentionSearchParams,
) -> tuple[list[PublicMentionSearchItemOut], int]:
    params = resolve_public_mention_search_params(params)
    union_stmt = _mention_union_stmt(project_id=project_id, params=params)
    if union_stmt is None:
        return [], 0
    subq = union_stmt.subquery()
    total = int(session.exec(select(func.count()).select_from(subq)).one())
    page_rows = session.exec(
        select(subq.c.entity_type, subq.c.mention_id)
        .order_by(col(subq.c.pub_date).desc().nulls_last(), col(subq.c.mention_id).desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    typed_rows = [(str(entity_type), int(mention_id)) for entity_type, mention_id in page_rows]
    return _hydrate_search_items(session, typed_rows), total


def _detail_from_search_item(
    item: PublicMentionSearchItemOut,
    *,
    occurrences: list[PublicMentionOccurrenceOut],
) -> PublicMentionDetailOut:
    return PublicMentionDetailOut(
        entity_type=item.entity_type,
        mention_id=item.mention_id,
        substrate_entity_id=item.substrate_entity_id,
        label=item.label,
        nature=item.nature,
        role_in_story=item.role_in_story,
        location_type=item.location_type,
        person_type=item.person_type,
        organization_type=item.organization_type,
        title=item.title,
        affiliation=item.affiliation,
        public_figure=item.public_figure,
        canonical=item.canonical,
        occurrences=occurrences,
        article=item.article,
    )


def get_public_mention(
    session: Session,
    *,
    project_id: int,
    entity_type: PublicEntityMentionType,
    mention_id: int,
) -> PublicMentionDetailOut | None:
    if entity_type == "location":
        hydrated = _hydrate_location_search_items(session, [mention_id])
        occurrence_model = SubstrateLocationMentionOccurrence
        mention_id_column = "location_mention_id"
    elif entity_type == "person":
        hydrated = _hydrate_person_search_items(session, [mention_id])
        occurrence_model = SubstratePersonMentionOccurrence
        mention_id_column = "person_mention_id"
    else:
        hydrated = _hydrate_organization_search_items(session, [mention_id])
        occurrence_model = SubstrateOrganizationMentionOccurrence
        mention_id_column = "organization_mention_id"

    item = hydrated.get(mention_id)
    if item is None:
        return None
    if item.article.id is None:
        return None
    article = session.exec(
        select(SubstrateArticle).where(
            SubstrateArticle.id == item.article.id,
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
        )
    ).first()
    if article is None:
        return None

    occurrences = occurrences_by_mention_id(
        session,
        mention_id=mention_id,
        occurrence_model=occurrence_model,
        mention_id_column=mention_id_column,
    )
    return _detail_from_search_item(item, occurrences=occurrences)


def _distinct_natures_for_arm(
    session: Session,
    *,
    project_id: int,
    mention_model,
    entity_model,
    entity_fk_col,
) -> list[str]:
    rows = session.exec(
        select(mention_model.nature)
        .select_from(mention_model)
        .join(SubstrateArticle, SubstrateArticle.id == mention_model.article_id)
        .join(entity_model, entity_model.id == entity_fk_col)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            mention_model.deleted == False,  # noqa: E712
            mention_model.nature.isnot(None),
            mention_model.nature != "",
        )
        .distinct()
        .order_by(mention_model.nature)
    ).all()
    return [str(value).strip() for value in rows if str(value).strip()]


def _distinct_entity_field_for_arm(
    session: Session,
    *,
    project_id: int,
    mention_model,
    entity_model,
    entity_fk_col,
    field_col,
) -> list[str]:
    rows = session.exec(
        select(field_col)
        .select_from(mention_model)
        .join(SubstrateArticle, SubstrateArticle.id == mention_model.article_id)
        .join(entity_model, entity_model.id == entity_fk_col)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            mention_model.deleted == False,  # noqa: E712
            field_col.isnot(None),
            field_col != "",
        )
        .distinct()
        .order_by(field_col)
    ).all()
    return [str(value).strip() for value in rows if str(value).strip()]


def _entity_types_with_mentions(session: Session, *, project_id: int) -> list[str]:
    entity_types: list[str] = []
    for entity_type, mention_model in (
        ("location", SubstrateLocationMention),
        ("person", SubstratePersonMention),
        ("organization", SubstrateOrganizationMention),
    ):
        count = session.exec(
            select(func.count())
            .select_from(mention_model)
            .join(SubstrateArticle, SubstrateArticle.id == mention_model.article_id)
            .where(
                SubstrateArticle.project_id == project_id,
                SubstrateArticle.deleted == False,  # noqa: E712
                mention_model.deleted == False,  # noqa: E712
            )
        ).one()
        if int(count) > 0:
            entity_types.append(entity_type)
    return entity_types


def get_public_mention_facets(session: Session, *, project_id: int) -> PublicMentionFacetsOut:
    natures: set[str] = set()
    for mention_model, entity_model, entity_fk in (
        (SubstrateLocationMention, SubstrateLocation, SubstrateLocationMention.location_id),
        (SubstratePersonMention, SubstratePerson, SubstratePersonMention.person_id),
        (
            SubstrateOrganizationMention,
            SubstrateOrganization,
            SubstrateOrganizationMention.organization_id,
        ),
    ):
        natures.update(
            _distinct_natures_for_arm(
                session,
                project_id=project_id,
                mention_model=mention_model,
                entity_model=entity_model,
                entity_fk_col=entity_fk,
            )
        )

    return PublicMentionFacetsOut(
        entity_types=_entity_types_with_mentions(session, project_id=project_id),
        natures=sorted(natures),
        location_types=_distinct_entity_field_for_arm(
            session,
            project_id=project_id,
            mention_model=SubstrateLocationMention,
            entity_model=SubstrateLocation,
            entity_fk_col=SubstrateLocationMention.location_id,
            field_col=SubstrateLocation.location_type,
        ),
        person_types=_distinct_entity_field_for_arm(
            session,
            project_id=project_id,
            mention_model=SubstratePersonMention,
            entity_model=SubstratePerson,
            entity_fk_col=SubstratePersonMention.person_id,
            field_col=SubstratePerson.person_type,
        ),
        organization_types=_distinct_entity_field_for_arm(
            session,
            project_id=project_id,
            mention_model=SubstrateOrganizationMention,
            entity_model=SubstrateOrganization,
            entity_fk_col=SubstrateOrganizationMention.organization_id,
            field_col=SubstrateOrganization.organization_type,
        ),
    )
