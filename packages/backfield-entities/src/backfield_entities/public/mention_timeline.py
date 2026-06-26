"""Mention timelines grouped by article publication date for canonical entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backfield_db import (
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
from sqlmodel import Session, col, func, select

from backfield_entities.public.mention_evidence import maybe_quotes_only_mention_filters
from backfield_entities.public.stylebook_scope import (
    get_public_location_canonical,
    get_public_organization_canonical,
    get_public_person_canonical,
)


@dataclass(frozen=True)
class PublicEntityMentionTimelineParams:
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    quotes_only: bool = False


class PublicEntityMentionTimelineItemOut(BaseModel):
    pub_date: date
    mention_count: int


def _mention_timeline(
    session: Session,
    *,
    project_id: int,
    canonical_id: str,
    params: PublicEntityMentionTimelineParams,
    mention_model,
    entity_model,
    occurrence_model,
    mention_entity_fk,
    entity_canonical_col,
    mention_fk_column: str,
) -> list[PublicEntityMentionTimelineItemOut]:
    filters = [
        entity_canonical_col == canonical_id,
        entity_model.project_id == project_id,
        mention_model.deleted == False,  # noqa: E712
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
        col(SubstrateArticle.pub_date).is_not(None),
    ]
    if params.pub_date_from is not None:
        filters.append(col(SubstrateArticle.pub_date) >= params.pub_date_from)
    if params.pub_date_to is not None:
        filters.append(col(SubstrateArticle.pub_date) <= params.pub_date_to)
    if params.quotes_only:
        filters.extend(
            maybe_quotes_only_mention_filters(
                mention_model.id,
                occurrence_model=occurrence_model,
                mention_fk_column=mention_fk_column,
                quotes_only=True,
            )
        )

    rows = session.exec(
        select(
            SubstrateArticle.pub_date,
            func.count(col(mention_model.id)),
        )
        .select_from(mention_model)
        .join(SubstrateArticle, SubstrateArticle.id == mention_model.article_id)
        .join(entity_model, entity_model.id == mention_entity_fk)
        .where(*filters)
        .group_by(col(SubstrateArticle.pub_date))
        .order_by(col(SubstrateArticle.pub_date).asc())
    ).all()

    items: list[PublicEntityMentionTimelineItemOut] = []
    for pub_date, count in rows:
        if pub_date is None:
            continue
        items.append(
            PublicEntityMentionTimelineItemOut(
                pub_date=pub_date,
                mention_count=int(count or 0),
            )
        )
    return items


def list_public_person_mention_timeline(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    person_id: str,
    params: PublicEntityMentionTimelineParams | None = None,
) -> list[PublicEntityMentionTimelineItemOut] | None:
    timeline_params = params or PublicEntityMentionTimelineParams()
    canon = get_public_person_canonical(session, stylebook_id=stylebook_id, person_id=person_id)
    if canon is None:
        return None
    return _mention_timeline(
        session,
        project_id=project_id,
        canonical_id=str(canon.id),
        params=timeline_params,
        mention_model=SubstratePersonMention,
        entity_model=SubstratePerson,
        occurrence_model=SubstratePersonMentionOccurrence,
        mention_entity_fk=SubstratePersonMention.person_id,
        entity_canonical_col=SubstratePerson.stylebook_person_canonical_id,
        mention_fk_column="person_mention_id",
    )


def list_public_organization_mention_timeline(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    organization_id: str,
    params: PublicEntityMentionTimelineParams | None = None,
) -> list[PublicEntityMentionTimelineItemOut] | None:
    timeline_params = params or PublicEntityMentionTimelineParams()
    canon = get_public_organization_canonical(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
    )
    if canon is None:
        return None
    return _mention_timeline(
        session,
        project_id=project_id,
        canonical_id=str(canon.id),
        params=timeline_params,
        mention_model=SubstrateOrganizationMention,
        entity_model=SubstrateOrganization,
        occurrence_model=SubstrateOrganizationMentionOccurrence,
        mention_entity_fk=SubstrateOrganizationMention.organization_id,
        entity_canonical_col=SubstrateOrganization.stylebook_organization_canonical_id,
        mention_fk_column="organization_mention_id",
    )


def list_public_location_mention_timeline(
    session: Session,
    *,
    stylebook_id: int,
    project_id: int,
    location_id: str,
    params: PublicEntityMentionTimelineParams | None = None,
) -> list[PublicEntityMentionTimelineItemOut] | None:
    timeline_params = params or PublicEntityMentionTimelineParams()
    canon = get_public_location_canonical(
        session,
        stylebook_id=stylebook_id,
        location_id=location_id,
    )
    if canon is None:
        return None
    return _mention_timeline(
        session,
        project_id=project_id,
        canonical_id=str(canon.id),
        params=timeline_params,
        mention_model=SubstrateLocationMention,
        entity_model=SubstrateLocation,
        occurrence_model=SubstrateLocationMentionOccurrence,
        mention_entity_fk=SubstrateLocationMention.location_id,
        entity_canonical_col=SubstrateLocation.stylebook_location_canonical_id,
        mention_fk_column="location_mention_id",
    )
