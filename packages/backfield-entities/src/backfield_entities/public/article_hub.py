"""Article hub queries: counts, mentions, locations, images."""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticleEmbedding,
    SubstrateCustomRecord,
    SubstrateImage,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstratePerson,
    SubstratePersonMention,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, literal, union_all
from sqlmodel import Session, col, select

from backfield_entities.public.mention_evidence import (
    PublicArticleMentionEvidenceOut,
    PublicMentionEvidenceOut,
    location_article_mention_evidence_by_mention_id,
    location_evidence_by_mention_id,
    organization_article_mention_evidence_by_mention_id,
    organization_evidence_by_mention_id,
    person_article_mention_evidence_by_mention_id,
    person_evidence_by_mention_id,
)
from backfield_entities.public.stylebook_scope import stylebook_slugs_by_id

PublicEntityMentionType = Literal["location", "person", "organization"]


class PublicCanonicalSummaryOut(BaseModel):
    id: str
    slug: str | None = None
    label: str
    stylebook_slug: str | None = None


class PublicArticleTypeCountsOut(BaseModel):
    locations: int = 0
    people: int = 0
    organizations: int = 0
    total: int = 0


class PublicArticleCountsOut(BaseModel):
    mentions: PublicArticleTypeCountsOut
    entities: PublicArticleTypeCountsOut
    images: int = 0
    custom_records: dict[str, int] = Field(default_factory=dict)


PUBLIC_ARTICLE_INLINE_IMAGES_CAP = 10


class PublicArticleMentionOut(BaseModel):
    entity_type: PublicEntityMentionType
    label: str
    nature: str | None = None
    role_in_story: str | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    evidence: PublicArticleMentionEvidenceOut | None = None


class PublicArticleLocationOut(BaseModel):
    mention_id: int
    label: str
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_type: str | None = None
    geometry_json: dict | None = None
    h3_cell: str | None = None
    h3_resolution: int | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    nature: str | None = None
    role_in_story: str | None = None
    evidence: PublicMentionEvidenceOut | None = None


class PublicArticleImageOut(BaseModel):
    id: int
    image_id: str
    url: str
    caption: str | None = None


class PublicArticlePersonOut(BaseModel):
    mention_id: int
    label: str
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False
    person_type: str | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    nature: str | None = None
    role_in_story: str | None = None
    evidence: PublicMentionEvidenceOut | None = None


class PublicArticleOrganizationOut(BaseModel):
    mention_id: int
    label: str
    organization_type: str | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    nature: str | None = None
    role_in_story: str | None = None
    evidence: PublicMentionEvidenceOut | None = None


class PublicArticleCustomRecordOut(BaseModel):
    id: int
    record_type: str
    record_index: int
    fields: dict[str, Any]
    mentions: list[dict[str, Any]]
    field_schema: list[dict[str, Any]]
    confidence: float | None = None


StylebookCanonicalRow = (
    StylebookLocationCanonical | StylebookPersonCanonical | StylebookOrganizationCanonical
)


def _canonical_stylebook_slugs(
    session: Session,
    canonicals: dict[str, StylebookCanonicalRow],
) -> dict[int, str]:
    stylebook_ids = {
        int(row.stylebook_id) for row in canonicals.values() if row.stylebook_id is not None
    }
    return stylebook_slugs_by_id(session, stylebook_ids)


def _canonical_summary(
    row: StylebookCanonicalRow,
    *,
    stylebook_slugs: dict[int, str],
) -> PublicCanonicalSummaryOut:
    stylebook_slug = (
        stylebook_slugs.get(int(row.stylebook_id)) if row.stylebook_id is not None else None
    )
    return PublicCanonicalSummaryOut(
        id=str(row.id),
        slug=str(row.slug),
        label=str(row.label),
        stylebook_slug=stylebook_slug,
    )


def _type_counts(*, locations: int, people: int, organizations: int) -> PublicArticleTypeCountsOut:
    return PublicArticleTypeCountsOut(
        locations=locations,
        people=people,
        organizations=organizations,
        total=locations + people + organizations,
    )


def _distinct_canonical_location_count(session: Session, *, article_id: int) -> int:
    value = session.exec(
        select(func.count(func.distinct(SubstrateLocation.stylebook_location_canonical_id)))
        .select_from(SubstrateLocationMention)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            SubstrateLocationMention.article_id == article_id,
            SubstrateLocationMention.deleted == False,  # noqa: E712
            col(SubstrateLocation.stylebook_location_canonical_id).isnot(None),
        )
    ).one()
    return int(value or 0)


def _distinct_canonical_person_count(session: Session, *, article_id: int) -> int:
    value = session.exec(
        select(func.count(func.distinct(SubstratePerson.stylebook_person_canonical_id)))
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            SubstratePersonMention.article_id == article_id,
            SubstratePersonMention.deleted == False,  # noqa: E712
            col(SubstratePerson.stylebook_person_canonical_id).isnot(None),
        )
    ).one()
    return int(value or 0)


def _distinct_canonical_organization_count(session: Session, *, article_id: int) -> int:
    value = session.exec(
        select(
            func.count(func.distinct(SubstrateOrganization.stylebook_organization_canonical_id))
        )
        .select_from(SubstrateOrganizationMention)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            SubstrateOrganizationMention.article_id == article_id,
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
            col(SubstrateOrganization.stylebook_organization_canonical_id).isnot(None),
        )
    ).one()
    return int(value or 0)


def article_hub_counts(session: Session, *, article_id: int) -> PublicArticleCountsOut:
    location_count = session.exec(
        select(func.count())
        .select_from(SubstrateLocationMention)
        .where(
            SubstrateLocationMention.article_id == article_id,
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
    ).one()
    person_count = session.exec(
        select(func.count())
        .select_from(SubstratePersonMention)
        .where(
            SubstratePersonMention.article_id == article_id,
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
    ).one()
    organization_count = session.exec(
        select(func.count())
        .select_from(SubstrateOrganizationMention)
        .where(
            SubstrateOrganizationMention.article_id == article_id,
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
    ).one()
    image_count = session.exec(
        select(func.count())
        .select_from(SubstrateImage)
        .where(SubstrateImage.article_id == article_id)
    ).one()

    record_rows = session.exec(
        select(SubstrateCustomRecord.record_type, func.count())
        .where(SubstrateCustomRecord.article_id == article_id)
        .group_by(SubstrateCustomRecord.record_type)
    ).all()
    custom_record_counts = {str(record_type): int(count) for record_type, count in record_rows}

    location_entities = _distinct_canonical_location_count(session, article_id=article_id)
    person_entities = _distinct_canonical_person_count(session, article_id=article_id)
    organization_entities = _distinct_canonical_organization_count(
        session, article_id=article_id
    )

    return PublicArticleCountsOut(
        mentions=_type_counts(
            locations=int(location_count),
            people=int(person_count),
            organizations=int(organization_count),
        ),
        entities=_type_counts(
            locations=location_entities,
            people=person_entities,
            organizations=organization_entities,
        ),
        images=int(image_count),
        custom_records=custom_record_counts,
    )


def article_hub_counts_batch(
    session: Session, article_ids: list[int]
) -> dict[int, PublicArticleCountsOut]:
    """Load hub counts for many articles without per-row round trips."""
    if not article_ids:
        return {}

    location_rows = session.exec(
        select(SubstrateLocationMention.article_id, func.count())
        .where(
            col(SubstrateLocationMention.article_id).in_(article_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateLocationMention.article_id)
    ).all()
    person_rows = session.exec(
        select(SubstratePersonMention.article_id, func.count())
        .where(
            col(SubstratePersonMention.article_id).in_(article_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstratePersonMention.article_id)
    ).all()
    organization_rows = session.exec(
        select(SubstrateOrganizationMention.article_id, func.count())
        .where(
            col(SubstrateOrganizationMention.article_id).in_(article_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
        .group_by(SubstrateOrganizationMention.article_id)
    ).all()
    location_entity_rows = session.exec(
        select(
            SubstrateLocationMention.article_id,
            func.count(func.distinct(SubstrateLocation.stylebook_location_canonical_id)),
        )
        .select_from(SubstrateLocationMention)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            col(SubstrateLocationMention.article_id).in_(article_ids),
            SubstrateLocationMention.deleted == False,  # noqa: E712
            col(SubstrateLocation.stylebook_location_canonical_id).isnot(None),
        )
        .group_by(SubstrateLocationMention.article_id)
    ).all()
    person_entity_rows = session.exec(
        select(
            SubstratePersonMention.article_id,
            func.count(func.distinct(SubstratePerson.stylebook_person_canonical_id)),
        )
        .select_from(SubstratePersonMention)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(
            col(SubstratePersonMention.article_id).in_(article_ids),
            SubstratePersonMention.deleted == False,  # noqa: E712
            col(SubstratePerson.stylebook_person_canonical_id).isnot(None),
        )
        .group_by(SubstratePersonMention.article_id)
    ).all()
    organization_entity_rows = session.exec(
        select(
            SubstrateOrganizationMention.article_id,
            func.count(
                func.distinct(SubstrateOrganization.stylebook_organization_canonical_id)
            ),
        )
        .select_from(SubstrateOrganizationMention)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(
            col(SubstrateOrganizationMention.article_id).in_(article_ids),
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
            col(SubstrateOrganization.stylebook_organization_canonical_id).isnot(None),
        )
        .group_by(SubstrateOrganizationMention.article_id)
    ).all()
    image_rows = session.exec(
        select(SubstrateImage.article_id, func.count())
        .where(col(SubstrateImage.article_id).in_(article_ids))
        .group_by(SubstrateImage.article_id)
    ).all()
    record_rows = session.exec(
        select(
            SubstrateCustomRecord.article_id,
            SubstrateCustomRecord.record_type,
            func.count(),
        )
        .where(col(SubstrateCustomRecord.article_id).in_(article_ids))
        .group_by(SubstrateCustomRecord.article_id, SubstrateCustomRecord.record_type)
    ).all()

    locations_by_article = {int(aid): int(count) for aid, count in location_rows}
    people_by_article = {int(aid): int(count) for aid, count in person_rows}
    organizations_by_article = {int(aid): int(count) for aid, count in organization_rows}
    location_entities_by_article = {int(aid): int(count) for aid, count in location_entity_rows}
    person_entities_by_article = {int(aid): int(count) for aid, count in person_entity_rows}
    organization_entities_by_article = {
        int(aid): int(count) for aid, count in organization_entity_rows
    }
    images_by_article = {int(aid): int(count) for aid, count in image_rows}
    records_by_article: dict[int, dict[str, int]] = {}
    for article_id, record_type, count in record_rows:
        aid = int(article_id)
        records_by_article.setdefault(aid, {})[str(record_type)] = int(count)

    out: dict[int, PublicArticleCountsOut] = {}
    for article_id in article_ids:
        out[article_id] = PublicArticleCountsOut(
            mentions=_type_counts(
                locations=locations_by_article.get(article_id, 0),
                people=people_by_article.get(article_id, 0),
                organizations=organizations_by_article.get(article_id, 0),
            ),
            entities=_type_counts(
                locations=location_entities_by_article.get(article_id, 0),
                people=person_entities_by_article.get(article_id, 0),
                organizations=organization_entities_by_article.get(article_id, 0),
            ),
            images=images_by_article.get(article_id, 0),
            custom_records=records_by_article.get(article_id, {}),
        )
    return out


def article_is_embedded(session: Session, *, article_id: int) -> bool:
    row = session.exec(
        select(SubstrateArticleEmbedding.article_id)
        .where(
            SubstrateArticleEmbedding.article_id == article_id,
            col(SubstrateArticleEmbedding.embedding).isnot(None),
        )
        .limit(1)
    ).first()
    return row is not None


def articles_embedded_batch(session: Session, article_ids: list[int]) -> set[int]:
    if not article_ids:
        return set()
    rows = session.exec(
        select(SubstrateArticleEmbedding.article_id).where(
            col(SubstrateArticleEmbedding.article_id).in_(article_ids),
            col(SubstrateArticleEmbedding.embedding).isnot(None),
        )
    ).all()
    return {int(article_id) for article_id in rows}


def enrich_articles_with_counts(session: Session, articles: list) -> None:
    """Attach ``counts`` and ``embedded`` to article output rows (in place)."""
    if not articles:
        return
    from backfield_entities.public.articles import PublicArticleOut

    article_ids = [int(article.id) for article in articles]
    counts_by_id = article_hub_counts_batch(session, article_ids)
    embedded_ids = articles_embedded_batch(session, article_ids)
    for article in articles:
        if not isinstance(article, PublicArticleOut):
            continue
        aid = int(article.id)
        article.counts = counts_by_id.get(aid)
        article.embedded = aid in embedded_ids


def _mention_union_stmt(
    article_id: int,
    entity_type: PublicEntityMentionType | None,
    nature: str | None = None,
):
    nature_value = (nature or "").strip()
    parts = []
    if entity_type in (None, "location"):
        stmt = select(
            literal("location").label("entity_type"),
            SubstrateLocationMention.id.label("mention_id"),
            SubstrateLocationMention.created_at.label("created_at"),
        ).where(
            SubstrateLocationMention.article_id == article_id,
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        if nature_value:
            stmt = stmt.where(SubstrateLocationMention.nature == nature_value)
        parts.append(stmt)
    if entity_type in (None, "person"):
        stmt = select(
            literal("person").label("entity_type"),
            SubstratePersonMention.id.label("mention_id"),
            SubstratePersonMention.created_at.label("created_at"),
        ).where(
            SubstratePersonMention.article_id == article_id,
            SubstratePersonMention.deleted == False,  # noqa: E712
        )
        if nature_value:
            stmt = stmt.where(SubstratePersonMention.nature == nature_value)
        parts.append(stmt)
    if entity_type in (None, "organization"):
        stmt = select(
            literal("organization").label("entity_type"),
            SubstrateOrganizationMention.id.label("mention_id"),
            SubstrateOrganizationMention.created_at.label("created_at"),
        ).where(
            SubstrateOrganizationMention.article_id == article_id,
            SubstrateOrganizationMention.deleted == False,  # noqa: E712
        )
        if nature_value:
            stmt = stmt.where(SubstrateOrganizationMention.nature == nature_value)
        parts.append(stmt)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return union_all(*parts)


def _hydrate_location_mentions(
    session: Session, mention_ids: list[int]
) -> list[PublicArticleMentionOut]:
    if not mention_ids:
        return []
    rows = session.exec(
        select(SubstrateLocationMention, SubstrateLocation)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(col(SubstrateLocationMention.id).in_(mention_ids))
    ).all()
    by_id = {int(m.id): (m, loc) for m, loc in rows if m.id is not None}  # type: ignore[arg-type]
    canonical_ids = [
        str(loc.stylebook_location_canonical_id)
        for _, loc in by_id.values()
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
    stylebook_slugs = _canonical_stylebook_slugs(session, canonicals)
    evidence = location_article_mention_evidence_by_mention_id(session, mention_ids)
    out: list[PublicArticleMentionOut] = []
    for mid in mention_ids:
        pair = by_id.get(mid)
        if pair is None:
            continue
        mention, loc = pair
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = loc.stylebook_location_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)], stylebook_slugs=stylebook_slugs)
        out.append(
            PublicArticleMentionOut(
                entity_type="location",
                label=str(loc.name),
                nature=mention.nature,
                role_in_story=mention.role_in_story,
                canonical=canon,
                evidence=evidence.get(mid),
            )
        )
    return out


def _hydrate_person_mentions(
    session: Session, mention_ids: list[int]
) -> list[PublicArticleMentionOut]:
    if not mention_ids:
        return []
    rows = session.exec(
        select(SubstratePersonMention, SubstratePerson)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(col(SubstratePersonMention.id).in_(mention_ids))
    ).all()
    by_id = {int(m.id): (m, person) for m, person in rows if m.id is not None}  # type: ignore[arg-type]
    canonical_ids = [
        str(person.stylebook_person_canonical_id)
        for _, person in by_id.values()
        if person.stylebook_person_canonical_id
    ]
    canonicals: dict[str, StylebookPersonCanonical] = {}
    if canonical_ids:
        canon_rows = session.exec(
            select(StylebookPersonCanonical).where(col(StylebookPersonCanonical.id).in_(canonical_ids))
        ).all()
        canonicals = {str(row.id): row for row in canon_rows}
    stylebook_slugs = _canonical_stylebook_slugs(session, canonicals)
    evidence = person_article_mention_evidence_by_mention_id(session, mention_ids)
    out: list[PublicArticleMentionOut] = []
    for mid in mention_ids:
        pair = by_id.get(mid)
        if pair is None:
            continue
        mention, person = pair
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = person.stylebook_person_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)], stylebook_slugs=stylebook_slugs)
        out.append(
            PublicArticleMentionOut(
                entity_type="person",
                label=str(person.name),
                nature=mention.nature,
                role_in_story=mention.role_in_story,
                canonical=canon,
                evidence=evidence.get(mid),
            )
        )
    return out


def _hydrate_organization_mentions(
    session: Session, mention_ids: list[int]
) -> list[PublicArticleMentionOut]:
    if not mention_ids:
        return []
    rows = session.exec(
        select(SubstrateOrganizationMention, SubstrateOrganization)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(col(SubstrateOrganizationMention.id).in_(mention_ids))
    ).all()
    by_id = {int(m.id): (m, org) for m, org in rows if m.id is not None}  # type: ignore[arg-type]
    canonical_ids = [
        str(org.stylebook_organization_canonical_id)
        for _, org in by_id.values()
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
    stylebook_slugs = _canonical_stylebook_slugs(session, canonicals)
    evidence = organization_article_mention_evidence_by_mention_id(session, mention_ids)
    out: list[PublicArticleMentionOut] = []
    for mid in mention_ids:
        pair = by_id.get(mid)
        if pair is None:
            continue
        mention, org = pair
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = org.stylebook_organization_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)], stylebook_slugs=stylebook_slugs)
        out.append(
            PublicArticleMentionOut(
                entity_type="organization",
                label=str(org.name),
                nature=mention.nature,
                role_in_story=mention.role_in_story,
                canonical=canon,
                evidence=evidence.get(mid),
            )
        )
    return out


def _hydrate_mentions(
    session: Session,
    page_rows: list[tuple[str, int]],
) -> list[PublicArticleMentionOut]:
    by_type: dict[str, list[int]] = {"location": [], "person": [], "organization": []}
    order: list[tuple[str, int]] = []
    for entity_type, mention_id in page_rows:
        by_type[entity_type].append(mention_id)
        order.append((entity_type, mention_id))

    hydrated: dict[tuple[str, int], PublicArticleMentionOut] = {}
    for mid, row in zip(
        by_type["location"],
        _hydrate_location_mentions(session, by_type["location"]),
        strict=True,
    ):
        hydrated[("location", mid)] = row
    for mid, row in zip(
        by_type["person"],
        _hydrate_person_mentions(session, by_type["person"]),
        strict=True,
    ):
        hydrated[("person", mid)] = row
    for mid, row in zip(
        by_type["organization"],
        _hydrate_organization_mentions(session, by_type["organization"]),
        strict=True,
    ):
        hydrated[("organization", mid)] = row

    return [hydrated[key] for key in order if key in hydrated]


def list_article_mentions(
    session: Session,
    *,
    article_id: int,
    entity_type: PublicEntityMentionType | None,
    nature: str | None = None,
    quotes_only: bool = False,
) -> list[PublicArticleMentionOut]:
    union_stmt = _mention_union_stmt(article_id, entity_type, nature=nature)
    if union_stmt is None:
        return []
    subq = union_stmt.subquery()
    page_rows = session.exec(
        select(subq.c.entity_type, subq.c.mention_id).order_by(col(subq.c.created_at).desc())
    ).all()
    typed_rows = [(str(entity_type), int(mention_id)) for entity_type, mention_id in page_rows]
    items = _hydrate_mentions(session, typed_rows)
    if quotes_only:
        items = [item for item in items if item.evidence is not None and item.evidence.quote]
    return items


def location_mentions_out_by_ids(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicArticleLocationOut]:
    """Hydrate location mention rows keyed by mention id."""
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateLocationMention, SubstrateLocation)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(col(SubstrateLocationMention.id).in_(mention_ids))
    ).all()
    canonical_ids = [
        str(loc.stylebook_location_canonical_id)
        for _, loc in rows
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
    stylebook_slugs = _canonical_stylebook_slugs(session, canonicals)
    evidence = location_evidence_by_mention_id(session, mention_ids)
    out: dict[int, PublicArticleLocationOut] = {}
    for mention, loc in rows:
        if mention.id is None:
            continue
        mid = int(mention.id)
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = loc.stylebook_location_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)], stylebook_slugs=stylebook_slugs)
        out[mid] = PublicArticleLocationOut(
            mention_id=mid,
            label=str(loc.name),
            location_type=loc.location_type,
            formatted_address=loc.formatted_address,
            geometry_type=loc.geometry_type,
            geometry_json=loc.geometry_json,
            h3_cell=loc.h3_cell,
            h3_resolution=loc.h3_resolution,
            canonical=canon,
            nature=mention.nature,
            role_in_story=mention.role_in_story,
            evidence=evidence.get(mid),
        )
    return out


def list_article_locations(
    session: Session,
    *,
    article_id: int,
    limit: int,
    offset: int,
) -> tuple[list[PublicArticleLocationOut], int]:
    base = (
        select(SubstrateLocationMention, SubstrateLocation)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .where(
            SubstrateLocationMention.article_id == article_id,
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
    )
    count_stmt = select(func.count()).select_from(
        select(SubstrateLocationMention.id)
        .where(
            SubstrateLocationMention.article_id == article_id,
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
        .subquery()
    )
    total = int(session.exec(count_stmt).one())
    rows = session.exec(
        base.order_by(col(SubstrateLocationMention.created_at).desc())
        .limit(limit)
        .offset(offset)
    ).all()
    mention_ids = [int(m.id) for m, _ in rows if m.id is not None]  # type: ignore[arg-type]
    by_id = location_mentions_out_by_ids(session, mention_ids)
    items = [by_id[mid] for mid in mention_ids if mid in by_id]
    return items, total


def person_mentions_out_by_ids(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicArticlePersonOut]:
    """Hydrate person mention rows keyed by mention id."""
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstratePersonMention, SubstratePerson)
        .join(SubstratePerson, SubstratePerson.id == SubstratePersonMention.person_id)
        .where(col(SubstratePersonMention.id).in_(mention_ids))
    ).all()
    canonical_ids = [
        str(person.stylebook_person_canonical_id)
        for _, person in rows
        if person.stylebook_person_canonical_id
    ]
    canonicals: dict[str, StylebookPersonCanonical] = {}
    if canonical_ids:
        canon_rows = session.exec(
            select(StylebookPersonCanonical).where(col(StylebookPersonCanonical.id).in_(canonical_ids))
        ).all()
        canonicals = {str(row.id): row for row in canon_rows}
    stylebook_slugs = _canonical_stylebook_slugs(session, canonicals)
    evidence = person_evidence_by_mention_id(session, mention_ids)
    out: dict[int, PublicArticlePersonOut] = {}
    for mention, person in rows:
        if mention.id is None:
            continue
        mid = int(mention.id)
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = person.stylebook_person_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)], stylebook_slugs=stylebook_slugs)
        out[mid] = PublicArticlePersonOut(
            mention_id=mid,
            label=str(person.name),
            title=person.title,
            affiliation=person.affiliation,
            public_figure=bool(person.public_figure),
            person_type=person.person_type,
            canonical=canon,
            nature=mention.nature,
            role_in_story=mention.role_in_story,
            evidence=evidence.get(mid),
        )
    return out


def list_article_people(
    session: Session,
    *,
    article_id: int,
    nature: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[PublicArticlePersonOut], int]:
    filters = [
        SubstratePersonMention.article_id == article_id,
        SubstratePersonMention.deleted == False,  # noqa: E712
    ]
    nature_value = (nature or "").strip()
    if nature_value:
        filters.append(SubstratePersonMention.nature == nature_value)
    count_stmt = select(func.count()).select_from(
        select(SubstratePersonMention.id).where(*filters).subquery()
    )
    total = int(session.exec(count_stmt).one())
    rows = session.exec(
        select(SubstratePersonMention.id)
        .where(*filters)
        .order_by(col(SubstratePersonMention.created_at).desc())
        .limit(limit)
        .offset(offset)
    ).all()
    mention_ids = [int(row) for row in rows]
    by_id = person_mentions_out_by_ids(session, mention_ids)
    items = [by_id[mid] for mid in mention_ids if mid in by_id]
    return items, total


def organization_mentions_out_by_ids(
    session: Session, mention_ids: list[int]
) -> dict[int, PublicArticleOrganizationOut]:
    """Hydrate organization mention rows keyed by mention id."""
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstrateOrganizationMention, SubstrateOrganization)
        .join(
            SubstrateOrganization,
            SubstrateOrganization.id == SubstrateOrganizationMention.organization_id,
        )
        .where(col(SubstrateOrganizationMention.id).in_(mention_ids))
    ).all()
    canonical_ids = [
        str(org.stylebook_organization_canonical_id)
        for _, org in rows
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
    stylebook_slugs = _canonical_stylebook_slugs(session, canonicals)
    evidence = organization_evidence_by_mention_id(session, mention_ids)
    out: dict[int, PublicArticleOrganizationOut] = {}
    for mention, org in rows:
        if mention.id is None:
            continue
        mid = int(mention.id)
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = org.stylebook_organization_canonical_id
        organization_type = org.organization_type
        if canon_id and str(canon_id) in canonicals:
            canon_row = canonicals[str(canon_id)]
            canon = _canonical_summary(canon_row, stylebook_slugs=stylebook_slugs)
            organization_type = organization_type or canon_row.organization_type
        out[mid] = PublicArticleOrganizationOut(
            mention_id=mid,
            label=str(org.name),
            organization_type=organization_type,
            canonical=canon,
            nature=mention.nature,
            role_in_story=mention.role_in_story,
            evidence=evidence.get(mid),
        )
    return out


def list_article_organizations(
    session: Session,
    *,
    article_id: int,
    nature: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[PublicArticleOrganizationOut], int]:
    filters = [
        SubstrateOrganizationMention.article_id == article_id,
        SubstrateOrganizationMention.deleted == False,  # noqa: E712
    ]
    nature_value = (nature or "").strip()
    if nature_value:
        filters.append(SubstrateOrganizationMention.nature == nature_value)
    count_stmt = select(func.count()).select_from(
        select(SubstrateOrganizationMention.id).where(*filters).subquery()
    )
    total = int(session.exec(count_stmt).one())
    rows = session.exec(
        select(SubstrateOrganizationMention.id)
        .where(*filters)
        .order_by(col(SubstrateOrganizationMention.created_at).desc())
        .limit(limit)
        .offset(offset)
    ).all()
    mention_ids = [int(row) for row in rows]
    by_id = organization_mentions_out_by_ids(session, mention_ids)
    items = [by_id[mid] for mid in mention_ids if mid in by_id]
    return items, total


def list_article_custom_records(
    session: Session,
    *,
    article_id: int,
    record_type: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[PublicArticleCustomRecordOut], int]:
    filters = [SubstrateCustomRecord.article_id == article_id]
    record_type_value = (record_type or "").strip()
    if record_type_value:
        filters.append(SubstrateCustomRecord.record_type == record_type_value)
    count_stmt = select(func.count()).select_from(
        select(SubstrateCustomRecord.id).where(*filters).subquery()
    )
    total = int(session.exec(count_stmt).one())
    rows = session.exec(
        select(SubstrateCustomRecord)
        .where(*filters)
        .order_by(
            col(SubstrateCustomRecord.record_type).asc(),
            col(SubstrateCustomRecord.record_index).asc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        PublicArticleCustomRecordOut(
            id=int(row.id),  # type: ignore[arg-type]
            record_type=str(row.record_type),
            record_index=int(row.record_index),
            fields=dict(row.fields_json or {}),
            mentions=list(row.mentions_json or []),
            field_schema=list(row.field_schema_json or []),
            confidence=row.confidence,
        )
        for row in rows
    ]
    return items, total


def list_article_images(
    session: Session,
    *,
    article_id: int,
    limit: int,
    offset: int,
) -> tuple[list[PublicArticleImageOut], int]:
    base = select(SubstrateImage).where(SubstrateImage.article_id == article_id)
    total = int(session.exec(select(func.count()).select_from(base.subquery())).one())
    rows = session.exec(
        base.order_by(col(SubstrateImage.id).asc()).limit(limit).offset(offset)
    ).all()
    items = [
        PublicArticleImageOut(
            id=int(row.id),  # type: ignore[arg-type]
            image_id=str(row.image_id),
            url=str(row.url),
            caption=row.caption,
        )
        for row in rows
    ]
    return items, total


def inline_article_images(
    session: Session,
    *,
    article_id: int,
    cap: int = PUBLIC_ARTICLE_INLINE_IMAGES_CAP,
) -> list[PublicArticleImageOut]:
    """Return up to ``cap`` images for inline detail responses."""
    items, _ = list_article_images(session, article_id=article_id, limit=cap, offset=0)
    return items
