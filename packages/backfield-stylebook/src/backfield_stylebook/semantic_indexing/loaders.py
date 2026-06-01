"""Load persisted substrate rows for semantic document builders."""

from __future__ import annotations

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
from sqlmodel import Session, select

from backfield_stylebook.semantic_indexing.sources import (
    ArticleSource,
    LocationCanonicalSource,
    LocationEntitySource,
    LocationMentionSource,
    LocationOccurrenceSource,
    PersonCanonicalSource,
    PersonEntitySource,
    PersonMentionSource,
    PersonOccurrenceSource,
)


def load_article_source(session: Session, article_id: int) -> ArticleSource | None:
    article = session.get(SubstrateArticle, article_id)
    if article is None:
        return None
    return ArticleSource.from_row(article)


def load_person_sync_bundles(
    session: Session,
    *,
    article_id: int,
) -> list[
    tuple[
        PersonEntitySource,
        PersonMentionSource,
        PersonOccurrenceSource,
        PersonCanonicalSource | None,
    ]
]:
    mentions = session.exec(
        select(SubstratePersonMention).where(SubstratePersonMention.article_id == article_id)
    ).all()
    if not mentions:
        return []

    mention_ids = [int(mention.id) for mention in mentions if mention.id is not None]
    person_ids = {int(mention.person_id) for mention in mentions}
    occurrences = session.exec(
        select(SubstratePersonMentionOccurrence).where(
            SubstratePersonMentionOccurrence.person_mention_id.in_(mention_ids)
        )
    ).all()

    persons: dict[int, SubstratePerson] = {}
    for person_id in person_ids:
        person = session.get(SubstratePerson, person_id)
        if person is not None and person.id is not None:
            persons[int(person.id)] = person

    canonical_ids = {
        str(person.stylebook_person_canonical_id)
        for person in persons.values()
        if person.stylebook_person_canonical_id is not None
    }
    canonicals: dict[str, StylebookPersonCanonical] = {}
    for canonical_id in canonical_ids:
        canonical = session.get(StylebookPersonCanonical, canonical_id)
        if canonical is not None:
            canonicals[canonical_id] = canonical

    mention_by_id = {
        int(mention.id): mention for mention in mentions if mention.id is not None
    }
    bundles: list[
        tuple[
            PersonEntitySource,
            PersonMentionSource,
            PersonOccurrenceSource,
            PersonCanonicalSource | None,
        ]
    ] = []
    for occurrence in occurrences:
        if occurrence.id is None:
            continue
        mention = mention_by_id.get(int(occurrence.person_mention_id))
        if mention is None:
            continue
        person = persons.get(int(mention.person_id))
        if person is None:
            continue
        canonical_source: PersonCanonicalSource | None = None
        cid = person.stylebook_person_canonical_id
        if cid is not None:
            canonical = canonicals.get(str(cid))
            if canonical is not None:
                canonical_source = PersonCanonicalSource.from_row(canonical)
        bundles.append(
            (
                PersonEntitySource.from_row(person),
                PersonMentionSource.from_row(mention),
                PersonOccurrenceSource.from_row(occurrence),
                canonical_source,
            )
        )
    return bundles


def load_location_sync_bundles(
    session: Session,
    *,
    article_id: int,
) -> list[
    tuple[
        LocationEntitySource,
        LocationMentionSource,
        LocationOccurrenceSource,
        LocationCanonicalSource | None,
    ]
]:
    mentions = session.exec(
        select(SubstrateLocationMention).where(SubstrateLocationMention.article_id == article_id)
    ).all()
    if not mentions:
        return []

    mention_ids = [int(mention.id) for mention in mentions if mention.id is not None]
    location_ids = {int(mention.location_id) for mention in mentions}
    occurrences = session.exec(
        select(SubstrateLocationMentionOccurrence).where(
            SubstrateLocationMentionOccurrence.location_mention_id.in_(mention_ids)
        )
    ).all()

    locations: dict[int, SubstrateLocation] = {}
    for location_id in location_ids:
        location = session.get(SubstrateLocation, location_id)
        if location is not None and location.id is not None:
            locations[int(location.id)] = location

    canonical_ids = {
        str(location.stylebook_location_canonical_id)
        for location in locations.values()
        if location.stylebook_location_canonical_id is not None
    }
    canonicals: dict[str, StylebookLocationCanonical] = {}
    for canonical_id in canonical_ids:
        canonical = session.get(StylebookLocationCanonical, canonical_id)
        if canonical is not None:
            canonicals[canonical_id] = canonical

    mention_by_id = {
        int(mention.id): mention for mention in mentions if mention.id is not None
    }
    bundles: list[
        tuple[
            LocationEntitySource,
            LocationMentionSource,
            LocationOccurrenceSource,
            LocationCanonicalSource | None,
        ]
    ] = []
    for occurrence in occurrences:
        if occurrence.id is None:
            continue
        mention = mention_by_id.get(int(occurrence.location_mention_id))
        if mention is None:
            continue
        location = locations.get(int(mention.location_id))
        if location is None:
            continue
        canonical_source: LocationCanonicalSource | None = None
        cid = location.stylebook_location_canonical_id
        if cid is not None:
            canonical = canonicals.get(str(cid))
            if canonical is not None:
                canonical_source = LocationCanonicalSource.from_row(canonical)
        bundles.append(
            (
                LocationEntitySource.from_row(location),
                LocationMentionSource.from_row(mention),
                LocationOccurrenceSource.from_row(occurrence),
                canonical_source,
            )
        )
    return bundles
