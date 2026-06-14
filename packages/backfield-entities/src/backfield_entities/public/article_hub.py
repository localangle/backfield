"""Article hub queries: counts, mentions, locations, images."""

from __future__ import annotations

from typing import Literal

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
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
    PublicMentionEvidenceOut,
    location_evidence_by_mention_id,
    organization_evidence_by_mention_id,
    person_evidence_by_mention_id,
)

PublicEntityMentionType = Literal["location", "person", "organization"]


class PublicCanonicalSummaryOut(BaseModel):
    id: str
    slug: str | None = None
    label: str


class PublicArticleEntityCountsOut(BaseModel):
    locations: int = 0
    people: int = 0
    organizations: int = 0


class PublicArticleCountsOut(BaseModel):
    entity_counts: PublicArticleEntityCountsOut
    custom_record_counts: dict[str, int] = Field(default_factory=dict)
    image_count: int = 0


class PublicArticleMentionOut(BaseModel):
    entity_type: PublicEntityMentionType
    mention_id: int
    substrate_entity_id: int
    label: str
    nature: str | None = None
    role_in_story: str | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    evidence: PublicMentionEvidenceOut | None = None


class PublicArticleLocationOut(BaseModel):
    mention_id: int
    substrate_location_id: int
    label: str
    location_type: str | None = None
    formatted_address: str | None = None
    geometry_type: str | None = None
    geometry_json: dict | None = None
    canonical: PublicCanonicalSummaryOut | None = None
    nature: str | None = None
    role_in_story: str | None = None
    evidence: PublicMentionEvidenceOut | None = None


class PublicArticleImageOut(BaseModel):
    id: int
    image_id: str
    url: str
    caption: str | None = None


def _canonical_summary(
    row: StylebookLocationCanonical | StylebookPersonCanonical | StylebookOrganizationCanonical,
) -> PublicCanonicalSummaryOut:
    return PublicCanonicalSummaryOut(
        id=str(row.id),
        slug=str(row.slug),
        label=str(row.label),
    )


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

    return PublicArticleCountsOut(
        entity_counts=PublicArticleEntityCountsOut(
            locations=int(location_count),
            people=int(person_count),
            organizations=int(organization_count),
        ),
        custom_record_counts=custom_record_counts,
        image_count=int(image_count),
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
    images_by_article = {int(aid): int(count) for aid, count in image_rows}
    records_by_article: dict[int, dict[str, int]] = {}
    for article_id, record_type, count in record_rows:
        aid = int(article_id)
        records_by_article.setdefault(aid, {})[str(record_type)] = int(count)

    out: dict[int, PublicArticleCountsOut] = {}
    for article_id in article_ids:
        out[article_id] = PublicArticleCountsOut(
            entity_counts=PublicArticleEntityCountsOut(
                locations=locations_by_article.get(article_id, 0),
                people=people_by_article.get(article_id, 0),
                organizations=organizations_by_article.get(article_id, 0),
            ),
            custom_record_counts=records_by_article.get(article_id, {}),
            image_count=images_by_article.get(article_id, 0),
        )
    return out


def _mention_union_stmt(
    article_id: int,
    entity_type: PublicEntityMentionType | None,
):
    parts = []
    if entity_type in (None, "location"):
        parts.append(
            select(
                literal("location").label("entity_type"),
                SubstrateLocationMention.id.label("mention_id"),
                SubstrateLocationMention.created_at.label("created_at"),
            ).where(
                SubstrateLocationMention.article_id == article_id,
                SubstrateLocationMention.deleted == False,  # noqa: E712
            )
        )
    if entity_type in (None, "person"):
        parts.append(
            select(
                literal("person").label("entity_type"),
                SubstratePersonMention.id.label("mention_id"),
                SubstratePersonMention.created_at.label("created_at"),
            ).where(
                SubstratePersonMention.article_id == article_id,
                SubstratePersonMention.deleted == False,  # noqa: E712
            )
        )
    if entity_type in (None, "organization"):
        parts.append(
            select(
                literal("organization").label("entity_type"),
                SubstrateOrganizationMention.id.label("mention_id"),
                SubstrateOrganizationMention.created_at.label("created_at"),
            ).where(
                SubstrateOrganizationMention.article_id == article_id,
                SubstrateOrganizationMention.deleted == False,  # noqa: E712
            )
        )
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
    evidence = location_evidence_by_mention_id(session, mention_ids)
    out: list[PublicArticleMentionOut] = []
    for mid in mention_ids:
        pair = by_id.get(mid)
        if pair is None:
            continue
        mention, loc = pair
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = loc.stylebook_location_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)])
        out.append(
            PublicArticleMentionOut(
                entity_type="location",
                mention_id=mid,
                substrate_entity_id=int(loc.id),  # type: ignore[arg-type]
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
    evidence = person_evidence_by_mention_id(session, mention_ids)
    out: list[PublicArticleMentionOut] = []
    for mid in mention_ids:
        pair = by_id.get(mid)
        if pair is None:
            continue
        mention, person = pair
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = person.stylebook_person_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)])
        out.append(
            PublicArticleMentionOut(
                entity_type="person",
                mention_id=mid,
                substrate_entity_id=int(person.id),  # type: ignore[arg-type]
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
    evidence = organization_evidence_by_mention_id(session, mention_ids)
    out: list[PublicArticleMentionOut] = []
    for mid in mention_ids:
        pair = by_id.get(mid)
        if pair is None:
            continue
        mention, org = pair
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = org.stylebook_organization_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)])
        out.append(
            PublicArticleMentionOut(
                entity_type="organization",
                mention_id=mid,
                substrate_entity_id=int(org.id),  # type: ignore[arg-type]
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
    for row in _hydrate_location_mentions(session, by_type["location"]):
        hydrated[("location", row.mention_id)] = row
    for row in _hydrate_person_mentions(session, by_type["person"]):
        hydrated[("person", row.mention_id)] = row
    for row in _hydrate_organization_mentions(session, by_type["organization"]):
        hydrated[("organization", row.mention_id)] = row

    return [hydrated[key] for key in order if key in hydrated]


def list_article_mentions(
    session: Session,
    *,
    article_id: int,
    entity_type: PublicEntityMentionType | None,
    limit: int,
    offset: int,
) -> tuple[list[PublicArticleMentionOut], int]:
    union_stmt = _mention_union_stmt(article_id, entity_type)
    if union_stmt is None:
        return [], 0
    subq = union_stmt.subquery()
    total = int(session.exec(select(func.count()).select_from(subq)).one())
    page_rows = session.exec(
        select(subq.c.entity_type, subq.c.mention_id)
        .order_by(col(subq.c.created_at).desc())
        .limit(limit)
        .offset(offset)
    ).all()
    typed_rows = [(str(entity_type), int(mention_id)) for entity_type, mention_id in page_rows]
    return _hydrate_mentions(session, typed_rows), total


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
    evidence = location_evidence_by_mention_id(session, mention_ids)
    out: dict[int, PublicArticleLocationOut] = {}
    for mention, loc in rows:
        if mention.id is None:
            continue
        mid = int(mention.id)
        canon: PublicCanonicalSummaryOut | None = None
        canon_id = loc.stylebook_location_canonical_id
        if canon_id and str(canon_id) in canonicals:
            canon = _canonical_summary(canonicals[str(canon_id)])
        out[mid] = PublicArticleLocationOut(
            mention_id=mid,
            substrate_location_id=int(loc.id),  # type: ignore[arg-type]
            label=str(loc.name),
            location_type=loc.location_type,
            formatted_address=loc.formatted_address,
            geometry_type=loc.geometry_type,
            geometry_json=loc.geometry_json,
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
