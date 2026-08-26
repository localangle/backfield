"""Collect linked canonical entities and evidence snippets for one article."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

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
from sqlmodel import Session, col, select

from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.connections.candidate_pairs import (
    select_linked_entities_with_pair_priority,
)
from backfield_entities.connections.caps import (
    MAX_LINKED_ENTITIES_PER_TYPE,
    MAX_SNIPPET_CHARS,
    MAX_SNIPPETS_PER_ENTITY,
)
from backfield_entities.connections.types import LinkedEntitySnapshot


@dataclass(frozen=True)
class AutoConnectionArticleContext:
    people: tuple[LinkedEntitySnapshot, ...]
    organizations: tuple[LinkedEntitySnapshot, ...]
    locations: tuple[LinkedEntitySnapshot, ...]
    article_text: str
    reference_at: datetime
    entity_counts: dict[str, int]
    entity_truncated: dict[str, int]


def _trim_snippet(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= MAX_SNIPPET_CHARS:
        return stripped
    return stripped[:MAX_SNIPPET_CHARS] + "..."


def _snippets_from_occurrences(
    occurrences: list[SubstratePersonMentionOccurrence]
    | list[SubstrateOrganizationMentionOccurrence]
    | list[SubstrateLocationMentionOccurrence],
) -> tuple[str, ...]:
    ordered = sorted(occurrences, key=lambda row: int(row.occurrence_order or 0))
    seen: set[str] = set()
    out: list[str] = []
    for occ in ordered:
        if bool(occ.suppressed):
            continue
        text = _trim_snippet(str(occ.mention_text or ""))
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= MAX_SNIPPETS_PER_ENTITY:
            break
    return tuple(out)


def _rank_entities_by_occurrences(
    entities: list[Any],
    mentions: list[Any],
    occurrences: list[Any],
    *,
    mention_entity_field: str,
    occurrence_mention_field: str,
) -> list[Any]:
    mention_to_entity = {
        int(mention.id): int(getattr(mention, mention_entity_field))
        for mention in mentions
        if mention.id is not None and getattr(mention, mention_entity_field) is not None
    }
    counts: dict[int, int] = {}
    for occurrence in occurrences:
        if bool(occurrence.suppressed):
            continue
        entity_id = mention_to_entity.get(
            int(getattr(occurrence, occurrence_mention_field))
        )
        if entity_id is not None:
            counts[entity_id] = counts.get(entity_id, 0) + 1
    return sorted(
        entities,
        key=lambda entity: (
            -counts.get(int(entity.id), 0),
            int(entity.id),
        ),
    )


def _collect_people(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> tuple[tuple[LinkedEntitySnapshot, ...], int]:
    mentions = session.exec(
        select(SubstratePersonMention).where(
            SubstratePersonMention.article_id == int(article_id),
            col(SubstratePersonMention.deleted).is_(False),
        )
    ).all()
    if not mentions:
        return (), 0
    person_ids = sorted({int(m.person_id) for m in mentions if m.person_id is not None})
    people = session.exec(
        select(SubstratePerson).where(
            SubstratePerson.project_id == int(project_id),
            SubstratePerson.id.in_(person_ids),
            SubstratePerson.canonical_link_status == CANONICAL_LINK_LINKED,
            col(SubstratePerson.stylebook_person_canonical_id).is_not(None),
        )
    ).all()
    mention_ids = [int(mention.id) for mention in mentions if mention.id is not None]
    all_occurrences = (
        list(
            session.exec(
                select(SubstratePersonMentionOccurrence).where(
                    SubstratePersonMentionOccurrence.person_mention_id.in_(mention_ids)
                )
            ).all()
        )
        if mention_ids
        else []
    )
    people = _rank_entities_by_occurrences(
        list(people),
        list(mentions),
        all_occurrences,
        mention_entity_field="person_id",
        occurrence_mention_field="person_mention_id",
    )
    occurrences_by_mention: dict[int, list[SubstratePersonMentionOccurrence]] = {}
    for occurrence in all_occurrences:
        occurrences_by_mention.setdefault(int(occurrence.person_mention_id), []).append(
            occurrence
        )
    out: list[LinkedEntitySnapshot] = []
    for person in people:
        if person.id is None or person.stylebook_person_canonical_id is None:
            continue
        canon = session.get(StylebookPersonCanonical, str(person.stylebook_person_canonical_id))
        label = (canon.label if canon is not None else person.name) or person.name
        person_mentions = [m for m in mentions if int(m.person_id) == int(person.id)]
        mention_ids = [int(m.id) for m in person_mentions if m.id is not None]
        occurrences = [
            occurrence
            for mention_id in mention_ids
            for occurrence in occurrences_by_mention.get(mention_id, [])
        ]
        out.append(
            LinkedEntitySnapshot(
                entity_type="person",
                substrate_id=int(person.id),
                canonical_id=str(person.stylebook_person_canonical_id),
                label=str(label).strip(),
                affiliation=(
                    person.affiliation or (canon.affiliation if canon else None) or ""
                ).strip()
                or None,
                person_type=(
                    person.person_type or (canon.person_type if canon else None) or ""
                ).strip()
                or None,
                snippets=_snippets_from_occurrences(occurrences),
            )
        )
    return tuple(out), len(people)


def _collect_organizations(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> tuple[tuple[LinkedEntitySnapshot, ...], int]:
    mentions = session.exec(
        select(SubstrateOrganizationMention).where(
            SubstrateOrganizationMention.article_id == int(article_id),
            col(SubstrateOrganizationMention.deleted).is_(False),
        )
    ).all()
    if not mentions:
        return (), 0
    org_ids = sorted({int(m.organization_id) for m in mentions if m.organization_id is not None})
    organizations = session.exec(
        select(SubstrateOrganization).where(
            SubstrateOrganization.project_id == int(project_id),
            SubstrateOrganization.id.in_(org_ids),
            SubstrateOrganization.canonical_link_status == CANONICAL_LINK_LINKED,
            col(SubstrateOrganization.stylebook_organization_canonical_id).is_not(None),
        )
    ).all()
    mention_ids = [int(mention.id) for mention in mentions if mention.id is not None]
    all_occurrences = (
        list(
            session.exec(
                select(SubstrateOrganizationMentionOccurrence).where(
                    SubstrateOrganizationMentionOccurrence.organization_mention_id.in_(
                        mention_ids
                    )
                )
            ).all()
        )
        if mention_ids
        else []
    )
    organizations = _rank_entities_by_occurrences(
        list(organizations),
        list(mentions),
        all_occurrences,
        mention_entity_field="organization_id",
        occurrence_mention_field="organization_mention_id",
    )
    occurrences_by_mention: dict[
        int, list[SubstrateOrganizationMentionOccurrence]
    ] = {}
    for occurrence in all_occurrences:
        occurrences_by_mention.setdefault(
            int(occurrence.organization_mention_id), []
        ).append(occurrence)
    out: list[LinkedEntitySnapshot] = []
    for organization in organizations:
        if organization.id is None or organization.stylebook_organization_canonical_id is None:
            continue
        canon = session.get(
            StylebookOrganizationCanonical,
            str(organization.stylebook_organization_canonical_id),
        )
        label = (canon.label if canon is not None else organization.name) or organization.name
        org_mentions = [m for m in mentions if int(m.organization_id) == int(organization.id)]
        mention_ids = [int(m.id) for m in org_mentions if m.id is not None]
        occurrences = [
            occurrence
            for mention_id in mention_ids
            for occurrence in occurrences_by_mention.get(mention_id, [])
        ]
        out.append(
            LinkedEntitySnapshot(
                entity_type="organization",
                substrate_id=int(organization.id),
                canonical_id=str(organization.stylebook_organization_canonical_id),
                label=str(label).strip(),
                organization_type=(
                    organization.organization_type
                    or (canon.organization_type if canon else None)
                    or ""
                ).strip()
                or None,
                snippets=_snippets_from_occurrences(occurrences),
            )
        )
    return tuple(out), len(organizations)


def _collect_locations(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> tuple[tuple[LinkedEntitySnapshot, ...], int]:
    mentions = session.exec(
        select(SubstrateLocationMention).where(
            SubstrateLocationMention.article_id == int(article_id),
            col(SubstrateLocationMention.deleted).is_(False),
        )
    ).all()
    if not mentions:
        return (), 0
    location_ids = sorted({int(m.location_id) for m in mentions if m.location_id is not None})
    locations = session.exec(
        select(SubstrateLocation).where(
            SubstrateLocation.project_id == int(project_id),
            SubstrateLocation.id.in_(location_ids),
            SubstrateLocation.canonical_link_status == CANONICAL_LINK_LINKED,
            col(SubstrateLocation.stylebook_location_canonical_id).is_not(None),
        )
    ).all()
    mention_ids = [int(mention.id) for mention in mentions if mention.id is not None]
    all_occurrences = (
        list(
            session.exec(
                select(SubstrateLocationMentionOccurrence).where(
                    SubstrateLocationMentionOccurrence.location_mention_id.in_(mention_ids)
                )
            ).all()
        )
        if mention_ids
        else []
    )
    locations = _rank_entities_by_occurrences(
        list(locations),
        list(mentions),
        all_occurrences,
        mention_entity_field="location_id",
        occurrence_mention_field="location_mention_id",
    )
    occurrences_by_mention: dict[int, list[SubstrateLocationMentionOccurrence]] = {}
    for occurrence in all_occurrences:
        occurrences_by_mention.setdefault(
            int(occurrence.location_mention_id), []
        ).append(occurrence)
    out: list[LinkedEntitySnapshot] = []
    for location in locations:
        if location.id is None or location.stylebook_location_canonical_id is None:
            continue
        canon = session.get(
            StylebookLocationCanonical,
            str(location.stylebook_location_canonical_id),
        )
        label = (canon.label if canon is not None else location.location_name) or (
            location.location_name or location.formatted_address or "Location"
        )
        location_type = (
            (canon.location_type if canon and canon.location_type else None)
            or location.location_type
            or ""
        ).strip() or None
        loc_mentions = [m for m in mentions if int(m.location_id) == int(location.id)]
        mention_ids = [int(m.id) for m in loc_mentions if m.id is not None]
        occurrences = [
            occurrence
            for mention_id in mention_ids
            for occurrence in occurrences_by_mention.get(mention_id, [])
        ]
        out.append(
            LinkedEntitySnapshot(
                entity_type="location",
                substrate_id=int(location.id),
                canonical_id=str(location.stylebook_location_canonical_id),
                label=str(label).strip(),
                location_type=location_type,
                snippets=_snippets_from_occurrences(occurrences),
            )
        )
    return tuple(out), len(locations)


def collect_auto_connection_article_context(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    article_text: str,
) -> AutoConnectionArticleContext:
    article = session.get(SubstrateArticle, int(article_id))
    if article is not None and article.pub_date is not None:
        reference_at = datetime.combine(article.pub_date, time.min, tzinfo=UTC)
    elif article is not None and article.created_at is not None:
        reference_at = article.created_at
    else:
        reference_at = datetime.now(UTC)

    people_all, people_count = _collect_people(
        session,
        project_id=project_id,
        article_id=article_id,
    )
    organizations_all, organization_count = _collect_organizations(
        session,
        project_id=project_id,
        article_id=article_id,
    )
    locations_all, location_count = _collect_locations(
        session,
        project_id=project_id,
        article_id=article_id,
    )
    people, organizations, locations = select_linked_entities_with_pair_priority(
        people=people_all,
        organizations=organizations_all,
        locations=locations_all,
        article_text=str(article_text or ""),
        limit_per_type=MAX_LINKED_ENTITIES_PER_TYPE,
    )
    return AutoConnectionArticleContext(
        people=people,
        organizations=organizations,
        locations=locations,
        article_text=str(article_text or ""),
        reference_at=reference_at,
        entity_counts={
            "person": people_count,
            "organization": organization_count,
            "location": location_count,
        },
        entity_truncated={
            "person": max(0, people_count - len(people)),
            "organization": max(0, organization_count - len(organizations)),
            "location": max(0, location_count - len(locations)),
        },
    )
