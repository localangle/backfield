"""Tests for public project summary stats."""

from __future__ import annotations

import json
from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticleEmbedding,
    SubstrateArticleMeta,
    SubstrateImage,
    SubstrateImageEmbedding,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateLocationSemanticDocument,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstratePerson,
    SubstratePersonMention,
)
from backfield_db.semantic_indexing import (
    SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
    SEMANTIC_EMBEDDING_STATUS_PENDING,
    SEMANTIC_EMBEDDING_STATUS_READY,
)
from backfield_entities.public.project_stats import get_public_project_summary_stats
from sqlmodel import Session, SQLModel, create_engine


def _seed_project(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-project-stats")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        name="News",
        slug="news",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return int(proj.id)  # type: ignore[arg-type]


def test_get_public_project_summary_stats() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
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

        session.add(
            SubstrateArticleMeta(
                article_id=article_id,
                meta_type="topic",
                category="local_government_politics",
                rationale="test",
                confidence=0.9,
            )
        )
        session.add(
            SubstrateArticleEmbedding(
                article_id=article_id,
                embedded_text="Budget vote",
                embedding_model="text-embedding-3-small",
                embedding_dimensions=2,
                embedding=json.dumps([1.0, 0.0]),
            )
        )
        image = SubstrateImage(
            article_id=article_id,
            image_id="img-1",
            url="https://example.com/photo.jpg",
        )
        session.add(image)
        session.commit()
        session.refresh(image)
        session.add(
            SubstrateImageEmbedding(
                substrate_image_id=int(image.id),  # type: ignore[arg-type]
                generated_text="Council chamber",
                embedding_model="text-embedding-3-small",
                embedding_dimensions=2,
                embedding=json.dumps([1.0, 0.0]),
            )
        )

        location = SubstrateLocation(
            project_id=project_id,
            name="City Hall",
            normalized_name="city hall",
            location_type="place",
        )
        person = SubstratePerson(
            project_id=project_id,
            name="Jane Doe",
            normalized_name="jane doe",
            person_type="elected_official",
        )
        organization = SubstrateOrganization(
            project_id=project_id,
            name="City Council",
            normalized_name="city council",
            organization_type="government",
        )
        session.add(location)
        session.add(person)
        session.add(organization)
        session.commit()
        session.refresh(location)
        session.refresh(person)
        session.refresh(organization)

        location_mention = SubstrateLocationMention(
            article_id=article_id,
            location_id=int(location.id),  # type: ignore[arg-type]
            nature="primary",
        )
        person_mention = SubstratePersonMention(
            article_id=article_id,
            person_id=int(person.id),  # type: ignore[arg-type]
            nature="subject",
        )
        organization_mention = SubstrateOrganizationMention(
            article_id=article_id,
            organization_id=int(organization.id),  # type: ignore[arg-type]
            nature="actor",
        )
        session.add(location_mention)
        session.add(person_mention)
        session.add(organization_mention)
        session.commit()
        session.refresh(location_mention)
        session.refresh(person_mention)

        occurrence = SubstrateLocationMentionOccurrence(
            location_mention_id=int(location_mention.id),  # type: ignore[arg-type]
            mention_text="City Hall",
        )
        session.add(occurrence)
        session.commit()
        session.refresh(occurrence)

        session.add(
            SubstrateLocationSemanticDocument(
                project_id=project_id,
                article_id=article_id,
                location_id=int(location.id),  # type: ignore[arg-type]
                location_mention_id=int(location_mention.id),  # type: ignore[arg-type]
                location_mention_occurrence_id=int(occurrence.id),  # type: ignore[arg-type]
                document_kind=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
                search_text="City Hall pending",
                source_hash="hash-pending",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
            )
        )
        session.commit()

        stats = get_public_project_summary_stats(session, project_id=project_id)

    assert stats.articles.total == 1
    assert stats.articles.embedded == 1
    assert stats.images.total == 1
    assert stats.images.embedded == 1
    assert stats.mentions.total == 3
    assert stats.mentions.embedded == 0


def test_get_public_project_summary_stats_semantically_indexed_mention() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
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

        location = SubstrateLocation(
            project_id=project_id,
            name="City Hall",
            normalized_name="city hall",
            location_type="place",
        )
        session.add(location)
        session.commit()
        session.refresh(location)

        location_mention = SubstrateLocationMention(
            article_id=article_id,
            location_id=int(location.id),  # type: ignore[arg-type]
            nature="primary",
        )
        session.add(location_mention)
        session.commit()
        session.refresh(location_mention)

        occurrence = SubstrateLocationMentionOccurrence(
            location_mention_id=int(location_mention.id),  # type: ignore[arg-type]
            mention_text="City Hall",
        )
        session.add(occurrence)
        session.commit()
        session.refresh(occurrence)

        session.add(
            SubstrateLocationSemanticDocument(
                project_id=project_id,
                article_id=article_id,
                location_id=int(location.id),  # type: ignore[arg-type]
                location_mention_id=int(location_mention.id),  # type: ignore[arg-type]
                location_mention_occurrence_id=int(occurrence.id),  # type: ignore[arg-type]
                document_kind=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
                search_text="City Hall ready",
                source_hash="hash-ready",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_READY,
                embedding=json.dumps([1.0, 0.0]),
            )
        )
        session.commit()

        stats = get_public_project_summary_stats(session, project_id=project_id)

    assert stats.mentions.total == 1
    assert stats.mentions.embedded == 1


def test_get_public_project_summary_stats_excludes_deleted_articles() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        active = SubstrateArticle(
            project_id=project_id,
            headline="Active",
            text="Body",
            pub_date=date(2024, 3, 1),
        )
        deleted = SubstrateArticle(
            project_id=project_id,
            headline="Deleted",
            text="Body",
            pub_date=date(2024, 3, 2),
            deleted=True,
        )
        session.add(active)
        session.add(deleted)
        session.commit()

        stats = get_public_project_summary_stats(session, project_id=project_id)

    assert stats.articles.total == 1
