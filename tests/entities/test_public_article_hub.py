"""Tests for public article hub counts and embedding helpers."""

from __future__ import annotations

import json
from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookLocationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateArticleEmbedding,
    SubstrateCustomRecord,
    SubstrateImage,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstratePerson,
    SubstratePersonMention,
)
from backfield_entities.public.article_hub import (
    article_hub_counts,
    article_hub_counts_batch,
    article_is_embedded,
    articles_embedded_batch,
)
from sqlmodel import Session, SQLModel, create_engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-article-hub")
    session.add(org)
    session.commit()
    session.refresh(org)
    from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization

    stylebook = ensure_default_stylebook_for_organization(session, int(org.id))  # type: ignore[arg-type]
    proj = BackfieldProject(
        name="News",
        slug="news",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return int(proj.id), int(stylebook.id)  # type: ignore[arg-type]


def test_article_hub_counts_mentions_entities_and_custom_records() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, stylebook_id = _seed_stylebook(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Budget vote",
            text="City Hall debate",
            pub_date=date(2024, 3, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)  # type: ignore[arg-type]

        location_canon = StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            label="City Hall",
            slug="city-hall",
            location_type="place",
        )
        session.add(location_canon)
        session.commit()
        session.refresh(location_canon)

        linked_location = SubstrateLocation(
            project_id=project_id,
            name="City Hall",
            normalized_name="city hall",
            location_type="place",
            stylebook_location_canonical_id=str(location_canon.id),
        )
        unlinked_location = SubstrateLocation(
            project_id=project_id,
            name="Downtown",
            normalized_name="downtown",
            location_type="place",
        )
        unlinked_location_b = SubstrateLocation(
            project_id=project_id,
            name="Uptown",
            normalized_name="uptown",
            location_type="place",
        )
        session.add(linked_location)
        session.add(unlinked_location)
        session.add(unlinked_location_b)
        session.commit()
        session.refresh(linked_location)
        session.refresh(unlinked_location)
        session.refresh(unlinked_location_b)

        session.add(
            SubstrateLocationMention(
                article_id=article_id,
                location_id=int(linked_location.id),  # type: ignore[arg-type]
            )
        )
        session.add(
            SubstrateLocationMention(
                article_id=article_id,
                location_id=int(unlinked_location.id),  # type: ignore[arg-type]
            )
        )
        session.add(
            SubstrateLocationMention(
                article_id=article_id,
                location_id=int(unlinked_location_b.id),  # type: ignore[arg-type]
            )
        )

        person_canon = StylebookPersonCanonical(
            stylebook_id=stylebook_id,
            label="Jane Doe",
            slug="jane-doe",
            person_type="elected_official",
        )
        session.add(person_canon)
        session.commit()
        session.refresh(person_canon)
        person = SubstratePerson(
            project_id=project_id,
            name="Jane Doe",
            normalized_name="jane doe",
            stylebook_person_canonical_id=str(person_canon.id),
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        session.add(
            SubstratePersonMention(
                article_id=article_id,
                person_id=int(person.id),  # type: ignore[arg-type]
            )
        )

        session.add(
            SubstrateImage(
                article_id=article_id,
                image_id="img-1",
                url="https://example.com/photo.jpg",
            )
        )
        session.add(
            SubstrateCustomRecord(
                article_id=article_id,
                record_type="contracts",
                record_index=0,
                fields_json={"vendor": "Acme"},
                mentions_json=[],
                field_schema_json=[],
            )
        )
        session.commit()

        counts = article_hub_counts(session, article_id=article_id)

    assert counts.mentions.locations == 3
    assert counts.mentions.people == 1
    assert counts.mentions.organizations == 0
    assert counts.mentions.total == 4
    assert counts.entities.locations == 1
    assert counts.entities.people == 1
    assert counts.entities.organizations == 0
    assert counts.entities.total == 2
    assert counts.images == 1
    assert counts.custom_records == {"contracts": 1}


def test_article_hub_counts_batch() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _stylebook_id = _seed_stylebook(session)
        first = SubstrateArticle(project_id=project_id, headline="One", text="a")
        second = SubstrateArticle(project_id=project_id, headline="Two", text="b")
        session.add(first)
        session.add(second)
        session.commit()
        session.refresh(first)
        session.refresh(second)
        first_id = int(first.id)  # type: ignore[arg-type]
        second_id = int(second.id)  # type: ignore[arg-type]

        loc = SubstrateLocation(
            project_id=project_id,
            name="Place",
            normalized_name="place",
            location_type="place",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        session.add(
            SubstrateLocationMention(
                article_id=first_id,
                location_id=int(loc.id),  # type: ignore[arg-type]
            )
        )
        session.commit()

        batch = article_hub_counts_batch(session, [first_id, second_id])

    assert batch[first_id].mentions.locations == 1
    assert batch[first_id].mentions.total == 1
    assert batch[second_id].mentions.total == 0


def test_article_is_embedded_helpers() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _stylebook_id = _seed_stylebook(session)
        embedded_article = SubstrateArticle(project_id=project_id, headline="A", text="a")
        plain_article = SubstrateArticle(project_id=project_id, headline="B", text="b")
        session.add(embedded_article)
        session.add(plain_article)
        session.commit()
        session.refresh(embedded_article)
        session.refresh(plain_article)
        embedded_id = int(embedded_article.id)  # type: ignore[arg-type]
        plain_id = int(plain_article.id)  # type: ignore[arg-type]
        session.add(
            SubstrateArticleEmbedding(
                article_id=embedded_id,
                embedded_text="A",
                embedding_model="text-embedding-3-small",
                embedding_dimensions=2,
                embedding=json.dumps([1.0, 0.0]),
            )
        )
        session.commit()

        assert article_is_embedded(session, article_id=embedded_id) is True
        assert article_is_embedded(session, article_id=plain_id) is False
        assert articles_embedded_batch(session, [embedded_id, plain_id]) == {embedded_id}
