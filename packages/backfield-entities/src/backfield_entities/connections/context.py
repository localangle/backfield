"""Collect linked canonical entities and evidence snippets for one article."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
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


def _collect_people(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> tuple[LinkedEntitySnapshot, ...]:
    mentions = session.exec(
        select(SubstratePersonMention).where(
            SubstratePersonMention.article_id == int(article_id),
            col(SubstratePersonMention.deleted).is_(False),
        )
    ).all()
    if not mentions:
        return ()
    person_ids = sorted({int(m.person_id) for m in mentions if m.person_id is not None})
    people = session.exec(
        select(SubstratePerson).where(
            SubstratePerson.project_id == int(project_id),
            SubstratePerson.id.in_(person_ids),
            SubstratePerson.canonical_link_status == CANONICAL_LINK_LINKED,
            col(SubstratePerson.stylebook_person_canonical_id).is_not(None),
        )
    ).all()
    out: list[LinkedEntitySnapshot] = []
    for person in people[:MAX_LINKED_ENTITIES_PER_TYPE]:
        if person.id is None or person.stylebook_person_canonical_id is None:
            continue
        canon = session.get(StylebookPersonCanonical, str(person.stylebook_person_canonical_id))
        label = (canon.label if canon is not None else person.name) or person.name
        person_mentions = [m for m in mentions if int(m.person_id) == int(person.id)]
        mention_ids = [int(m.id) for m in person_mentions if m.id is not None]
        occurrences: list[SubstratePersonMentionOccurrence] = []
        if mention_ids:
            occurrences = list(
                session.exec(
                    select(SubstratePersonMentionOccurrence).where(
                        SubstratePersonMentionOccurrence.person_mention_id.in_(mention_ids)
                    )
                ).all()
            )
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
                snippets=_snippets_from_occurrences(occurrences),
            )
        )
    return tuple(out)


def _collect_organizations(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> tuple[LinkedEntitySnapshot, ...]:
    mentions = session.exec(
        select(SubstrateOrganizationMention).where(
            SubstrateOrganizationMention.article_id == int(article_id),
            col(SubstrateOrganizationMention.deleted).is_(False),
        )
    ).all()
    if not mentions:
        return ()
    org_ids = sorted({int(m.organization_id) for m in mentions if m.organization_id is not None})
    organizations = session.exec(
        select(SubstrateOrganization).where(
            SubstrateOrganization.project_id == int(project_id),
            SubstrateOrganization.id.in_(org_ids),
            SubstrateOrganization.canonical_link_status == CANONICAL_LINK_LINKED,
            col(SubstrateOrganization.stylebook_organization_canonical_id).is_not(None),
        )
    ).all()
    out: list[LinkedEntitySnapshot] = []
    for organization in organizations[:MAX_LINKED_ENTITIES_PER_TYPE]:
        if organization.id is None or organization.stylebook_organization_canonical_id is None:
            continue
        canon = session.get(
            StylebookOrganizationCanonical,
            str(organization.stylebook_organization_canonical_id),
        )
        label = (canon.label if canon is not None else organization.name) or organization.name
        org_mentions = [m for m in mentions if int(m.organization_id) == int(organization.id)]
        mention_ids = [int(m.id) for m in org_mentions if m.id is not None]
        occurrences: list[SubstrateOrganizationMentionOccurrence] = []
        if mention_ids:
            occurrences = list(
                session.exec(
                    select(SubstrateOrganizationMentionOccurrence).where(
                        SubstrateOrganizationMentionOccurrence.organization_mention_id.in_(
                            mention_ids
                        )
                    )
                ).all()
            )
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
    return tuple(out)


def _collect_locations(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> tuple[LinkedEntitySnapshot, ...]:
    mentions = session.exec(
        select(SubstrateLocationMention).where(
            SubstrateLocationMention.article_id == int(article_id),
            col(SubstrateLocationMention.deleted).is_(False),
        )
    ).all()
    if not mentions:
        return ()
    location_ids = sorted({int(m.location_id) for m in mentions if m.location_id is not None})
    locations = session.exec(
        select(SubstrateLocation).where(
            SubstrateLocation.project_id == int(project_id),
            SubstrateLocation.id.in_(location_ids),
            SubstrateLocation.canonical_link_status == CANONICAL_LINK_LINKED,
            col(SubstrateLocation.stylebook_location_canonical_id).is_not(None),
        )
    ).all()
    out: list[LinkedEntitySnapshot] = []
    for location in locations[:MAX_LINKED_ENTITIES_PER_TYPE]:
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
        occurrences: list[SubstrateLocationMentionOccurrence] = []
        if mention_ids:
            occurrences = list(
                session.exec(
                    select(SubstrateLocationMentionOccurrence).where(
                        SubstrateLocationMentionOccurrence.location_mention_id.in_(mention_ids)
                    )
                ).all()
            )
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
    return tuple(out)


def collect_auto_connection_article_context(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    article_text: str,
) -> AutoConnectionArticleContext:
    return AutoConnectionArticleContext(
        people=_collect_people(session, project_id=project_id, article_id=article_id),
        organizations=_collect_organizations(
            session, project_id=project_id, article_id=article_id
        ),
        locations=_collect_locations(session, project_id=project_id, article_id=article_id),
        article_text=str(article_text or ""),
    )
