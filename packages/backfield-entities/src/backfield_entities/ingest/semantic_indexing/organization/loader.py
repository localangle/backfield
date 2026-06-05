"""Load organization substrate rows for semantic document sync and builders."""

from __future__ import annotations

from backfield_db.models import (
    StylebookOrganizationCanonical,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)
from sqlmodel import Session, select

from backfield_entities.ingest.semantic_indexing.organization.sources import (
    OrganizationCanonicalSource,
    OrganizationEntitySource,
    OrganizationMentionSource,
    OrganizationOccurrenceSource,
)

OrganizationSyncBundle = tuple[
    OrganizationEntitySource,
    OrganizationMentionSource,
    OrganizationOccurrenceSource,
    OrganizationCanonicalSource | None,
]


def load_sync_bundles(
    session: Session,
    *,
    article_id: int,
) -> list[OrganizationSyncBundle]:
    mentions = session.exec(
        select(SubstrateOrganizationMention).where(
            SubstrateOrganizationMention.article_id == article_id
        )
    ).all()
    if not mentions:
        return []

    mention_ids = [int(mention.id) for mention in mentions if mention.id is not None]
    organization_ids = {int(mention.organization_id) for mention in mentions}
    occurrences = session.exec(
        select(SubstrateOrganizationMentionOccurrence).where(
            SubstrateOrganizationMentionOccurrence.organization_mention_id.in_(mention_ids)
        )
    ).all()

    organizations: dict[int, SubstrateOrganization] = {}
    for organization_id in organization_ids:
        organization = session.get(SubstrateOrganization, organization_id)
        if organization is not None and organization.id is not None:
            organizations[int(organization.id)] = organization

    canonical_ids = {
        str(organization.stylebook_organization_canonical_id)
        for organization in organizations.values()
        if organization.stylebook_organization_canonical_id is not None
    }
    canonicals: dict[str, StylebookOrganizationCanonical] = {}
    for canonical_id in canonical_ids:
        canonical = session.get(StylebookOrganizationCanonical, canonical_id)
        if canonical is not None:
            canonicals[canonical_id] = canonical

    mention_by_id = {
        int(mention.id): mention for mention in mentions if mention.id is not None
    }
    bundles: list[OrganizationSyncBundle] = []
    for occurrence in occurrences:
        if occurrence.id is None:
            continue
        mention = mention_by_id.get(int(occurrence.organization_mention_id))
        if mention is None:
            continue
        organization = organizations.get(int(mention.organization_id))
        if organization is None:
            continue
        canonical_source: OrganizationCanonicalSource | None = None
        cid = organization.stylebook_organization_canonical_id
        if cid is not None:
            canonical = canonicals.get(str(cid))
            if canonical is not None:
                canonical_source = OrganizationCanonicalSource.from_row(canonical)
        bundles.append(
            (
                OrganizationEntitySource.from_row(organization),
                OrganizationMentionSource.from_row(mention),
                OrganizationOccurrenceSource.from_row(occurrence),
                canonical_source,
            )
        )
    return bundles
