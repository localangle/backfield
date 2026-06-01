"""Persisted substrate field bundles for semantic document builders."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db.models import (
    StylebookLocationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)


@dataclass(frozen=True)
class ArticleSource:
    id: int
    headline: str
    text: str
    deleted: bool

    @classmethod
    def from_row(cls, article: SubstrateArticle) -> ArticleSource:
        assert article.id is not None
        return cls(
            id=int(article.id),
            headline=str(article.headline),
            text=str(article.text),
            deleted=bool(article.deleted),
        )


@dataclass(frozen=True)
class PersonEntitySource:
    id: int
    name: str
    title: str | None
    affiliation: str | None
    person_type: str | None
    public_figure: bool
    stylebook_person_canonical_id: str | None

    @classmethod
    def from_row(cls, person: SubstratePerson) -> PersonEntitySource:
        assert person.id is not None
        cid = person.stylebook_person_canonical_id
        return cls(
            id=int(person.id),
            name=str(person.name),
            title=person.title,
            affiliation=person.affiliation,
            person_type=person.person_type,
            public_figure=bool(person.public_figure),
            stylebook_person_canonical_id=str(cid) if cid is not None else None,
        )


@dataclass(frozen=True)
class PersonCanonicalSource:
    id: str
    label: str
    title: str | None
    affiliation: str | None
    person_type: str | None

    @classmethod
    def from_row(cls, canonical: StylebookPersonCanonical) -> PersonCanonicalSource:
        return cls(
            id=str(canonical.id),
            label=str(canonical.label),
            title=canonical.title,
            affiliation=canonical.affiliation,
            person_type=canonical.person_type,
        )


@dataclass(frozen=True)
class PersonMentionSource:
    id: int
    article_id: int
    person_id: int
    role_in_story: str | None
    nature: str | None
    nature_secondary_tags: tuple[str, ...]
    deleted: bool

    @classmethod
    def from_row(cls, mention: SubstratePersonMention) -> PersonMentionSource:
        assert mention.id is not None
        tags = mention.nature_secondary_tags_json
        secondary = tuple(str(tag) for tag in tags) if isinstance(tags, list) else ()
        return cls(
            id=int(mention.id),
            article_id=int(mention.article_id),
            person_id=int(mention.person_id),
            role_in_story=mention.role_in_story,
            nature=mention.nature,
            nature_secondary_tags=secondary,
            deleted=bool(mention.deleted),
        )


@dataclass(frozen=True)
class PersonOccurrenceSource:
    id: int
    person_mention_id: int
    mention_text: str
    quote_text: str | None
    start_char: int | None
    end_char: int | None
    occurrence_order: int | None
    labels: tuple[str, ...]
    suppressed: bool

    @classmethod
    def from_row(cls, occurrence: SubstratePersonMentionOccurrence) -> PersonOccurrenceSource:
        assert occurrence.id is not None
        labels = occurrence.labels_json
        label_tuple = tuple(str(label) for label in labels) if isinstance(labels, list) else ()
        return cls(
            id=int(occurrence.id),
            person_mention_id=int(occurrence.person_mention_id),
            mention_text=str(occurrence.mention_text),
            quote_text=occurrence.quote_text,
            start_char=occurrence.start_char,
            end_char=occurrence.end_char,
            occurrence_order=occurrence.occurrence_order,
            labels=label_tuple,
            suppressed=bool(occurrence.suppressed),
        )


@dataclass(frozen=True)
class LocationEntitySource:
    id: int
    name: str
    location_type: str | None
    formatted_address: str | None
    stylebook_location_canonical_id: str | None

    @classmethod
    def from_row(cls, location: SubstrateLocation) -> LocationEntitySource:
        assert location.id is not None
        cid = location.stylebook_location_canonical_id
        return cls(
            id=int(location.id),
            name=str(location.name),
            location_type=location.location_type,
            formatted_address=location.formatted_address,
            stylebook_location_canonical_id=str(cid) if cid is not None else None,
        )


@dataclass(frozen=True)
class LocationCanonicalSource:
    id: str
    label: str
    location_type: str | None
    formatted_address: str | None

    @classmethod
    def from_row(cls, canonical: StylebookLocationCanonical) -> LocationCanonicalSource:
        return cls(
            id=str(canonical.id),
            label=str(canonical.label),
            location_type=canonical.location_type,
            formatted_address=canonical.formatted_address,
        )


@dataclass(frozen=True)
class LocationMentionSource:
    id: int
    article_id: int
    location_id: int
    role_in_story: str | None
    nature: str | None
    nature_secondary_tags: tuple[str, ...]
    deleted: bool

    @classmethod
    def from_row(cls, mention: SubstrateLocationMention) -> LocationMentionSource:
        assert mention.id is not None
        tags = mention.nature_secondary_tags_json
        secondary = tuple(str(tag) for tag in tags) if isinstance(tags, list) else ()
        return cls(
            id=int(mention.id),
            article_id=int(mention.article_id),
            location_id=int(mention.location_id),
            role_in_story=mention.role_in_story,
            nature=mention.nature,
            nature_secondary_tags=secondary,
            deleted=bool(mention.deleted),
        )


@dataclass(frozen=True)
class LocationOccurrenceSource:
    id: int
    location_mention_id: int
    mention_text: str
    quote_text: str | None
    start_char: int | None
    end_char: int | None
    occurrence_order: int | None
    labels: tuple[str, ...]
    suppressed: bool

    @classmethod
    def from_row(cls, occurrence: SubstrateLocationMentionOccurrence) -> LocationOccurrenceSource:
        assert occurrence.id is not None
        labels = occurrence.labels_json
        label_tuple = tuple(str(label) for label in labels) if isinstance(labels, list) else ()
        return cls(
            id=int(occurrence.id),
            location_mention_id=int(occurrence.location_mention_id),
            mention_text=str(occurrence.mention_text),
            quote_text=occurrence.quote_text,
            start_char=occurrence.start_char,
            end_char=occurrence.end_char,
            occurrence_order=occurrence.occurrence_order,
            labels=label_tuple,
            suppressed=bool(occurrence.suppressed),
        )
