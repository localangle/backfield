"""Organization substrate field bundles for semantic document builders."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db.models import (
    StylebookOrganizationCanonical,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
)


@dataclass(frozen=True)
class OrganizationEntitySource:
    id: int
    name: str
    organization_type: str | None
    stylebook_organization_canonical_id: str | None

    @classmethod
    def from_row(cls, organization: SubstrateOrganization) -> OrganizationEntitySource:
        assert organization.id is not None
        cid = organization.stylebook_organization_canonical_id
        return cls(
            id=int(organization.id),
            name=str(organization.name),
            organization_type=organization.organization_type,
            stylebook_organization_canonical_id=str(cid) if cid is not None else None,
        )


@dataclass(frozen=True)
class OrganizationCanonicalSource:
    id: str
    label: str
    organization_type: str | None

    @classmethod
    def from_row(cls, canonical: StylebookOrganizationCanonical) -> OrganizationCanonicalSource:
        return cls(
            id=str(canonical.id),
            label=str(canonical.label),
            organization_type=canonical.organization_type,
        )


@dataclass(frozen=True)
class OrganizationMentionSource:
    id: int
    article_id: int
    organization_id: int
    role_in_story: str | None
    nature: str | None
    nature_secondary_tags: tuple[str, ...]
    deleted: bool

    @classmethod
    def from_row(cls, mention: SubstrateOrganizationMention) -> OrganizationMentionSource:
        assert mention.id is not None
        tags = mention.nature_secondary_tags_json
        secondary = tuple(str(tag) for tag in tags) if isinstance(tags, list) else ()
        return cls(
            id=int(mention.id),
            article_id=int(mention.article_id),
            organization_id=int(mention.organization_id),
            role_in_story=mention.role_in_story,
            nature=mention.nature,
            nature_secondary_tags=secondary,
            deleted=bool(mention.deleted),
        )


@dataclass(frozen=True)
class OrganizationOccurrenceSource:
    id: int
    organization_mention_id: int
    mention_text: str
    quote_text: str | None
    start_char: int | None
    end_char: int | None
    occurrence_order: int | None
    labels: tuple[str, ...]
    suppressed: bool

    @classmethod
    def from_row(
        cls,
        occurrence: SubstrateOrganizationMentionOccurrence,
    ) -> OrganizationOccurrenceSource:
        assert occurrence.id is not None
        labels = occurrence.labels_json
        label_tuple = tuple(str(label) for label in labels) if isinstance(labels, list) else ()
        return cls(
            id=int(occurrence.id),
            organization_mention_id=int(occurrence.organization_mention_id),
            mention_text=str(occurrence.mention_text),
            quote_text=occurrence.quote_text,
            start_char=occurrence.start_char,
            end_char=occurrence.end_char,
            occurrence_order=occurrence.occurrence_order,
            labels=label_tuple,
            suppressed=bool(occurrence.suppressed),
        )
