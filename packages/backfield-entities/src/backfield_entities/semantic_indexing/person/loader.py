"""Load person substrate rows for semantic document sync and builders."""

from __future__ import annotations

from backfield_db.models import (
    StylebookPersonCanonical,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from sqlmodel import Session, select

from backfield_stylebook.semantic_indexing.person.sources import (
    PersonCanonicalSource,
    PersonEntitySource,
    PersonMentionSource,
    PersonOccurrenceSource,
)

PersonSyncBundle = tuple[
    PersonEntitySource,
    PersonMentionSource,
    PersonOccurrenceSource,
    PersonCanonicalSource | None,
]


def load_sync_bundles(
    session: Session,
    *,
    article_id: int,
) -> list[PersonSyncBundle]:
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
    bundles: list[PersonSyncBundle] = []
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
