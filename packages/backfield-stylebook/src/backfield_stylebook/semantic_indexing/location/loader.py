"""Load location substrate rows for semantic document sync and builders."""

from __future__ import annotations

from backfield_db.models import (
    StylebookLocationCanonical,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from sqlmodel import Session, select

from backfield_stylebook.semantic_indexing.location.sources import (
    LocationCanonicalSource,
    LocationEntitySource,
    LocationMentionSource,
    LocationOccurrenceSource,
)

LocationSyncBundle = tuple[
    LocationEntitySource,
    LocationMentionSource,
    LocationOccurrenceSource,
    LocationCanonicalSource | None,
]


def load_sync_bundles(
    session: Session,
    *,
    article_id: int,
) -> list[LocationSyncBundle]:
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
    bundles: list[LocationSyncBundle] = []
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
