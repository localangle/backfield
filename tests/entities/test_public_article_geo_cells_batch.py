"""Tests for batch public H3 geo-cell article drill-down."""

from __future__ import annotations

from datetime import date

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticleMeta,
    SubstrateLocation,
    SubstrateLocationMention,
)
from backfield_entities.geo.h3_index import derive_h3_index
from backfield_entities.public.article_geo_cell_detail import (
    PublicArticleGeoCellDetailParams,
    search_public_articles_in_cell,
)
from backfield_entities.public.article_geo_cells_batch import (
    PublicArticleGeoCellsBatchParams,
    PublicArticleGeoCellsBatchValidationError,
    normalize_batch_cells,
    search_public_articles_in_cells,
)
from h3 import get_resolution
from sqlmodel import Session, SQLModel, create_engine

CHICAGO_POINT = {"type": "Point", "coordinates": [-87.6298, 41.8781]}
NEARBY_POINT = {"type": "Point", "coordinates": [-87.63, 41.8785]}


def _apply_h3(location: SubstrateLocation) -> None:
    derived = derive_h3_index(location.geometry_json)
    if derived is None:
        return
    location.h3_cell = derived.h3_cell
    location.h3_resolution = derived.h3_resolution


def _seed_project(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-cell-batch")
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


def _add_location_mention(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    label: str,
    geometry_json: dict,
) -> SubstrateLocation:
    loc = SubstrateLocation(
        project_id=project_id,
        name=label,
        normalized_name=label.lower(),
        location_type="place",
        geometry_type="Point",
        geometry_json=geometry_json,
    )
    _apply_h3(loc)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    session.add(
        SubstrateLocationMention(
            article_id=article_id,
            location_id=int(loc.id),  # type: ignore[arg-type]
            nature="primary",
        )
    )
    session.commit()
    return loc


def test_batch_deduplicates_article_across_cells() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Span",
            text="Body",
            pub_date=date(2024, 3, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)  # type: ignore[arg-type]

        loc_a = _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="A",
            geometry_json=CHICAGO_POINT,
        )
        loc_b = _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="B",
            geometry_json=NEARBY_POINT,
        )
        assert loc_a.h3_cell is not None and loc_b.h3_cell is not None
        assert loc_a.h3_cell != loc_b.h3_cell
        resolution = int(get_resolution(str(loc_a.h3_cell)))

        result = search_public_articles_in_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsBatchParams(
                cells=(str(loc_a.h3_cell), str(loc_b.h3_cell)),
                resolution=resolution,
            ),
        )

    assert result.total == 1
    assert len(result.items) == 1
    assert set(result.items[0].matched_cells) == {str(loc_a.h3_cell), str(loc_b.h3_cell)}
    assert len(result.items[0].matching_locations) == 2
    assert {row.h3_cell for row in result.per_cell_totals} == {
        str(loc_a.h3_cell),
        str(loc_b.h3_cell),
    }
    assert all(row.article_count == 1 for row in result.per_cell_totals)


def test_single_cell_batch_matches_single_cell_route() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Story",
            text="Body",
            pub_date=date(2024, 3, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        loc = _add_location_mention(
            session,
            project_id=project_id,
            article_id=int(article.id),  # type: ignore[arg-type]
            label="Place",
            geometry_json=CHICAGO_POINT,
        )
        assert loc.h3_cell is not None
        cell_id = str(loc.h3_cell)
        resolution = int(get_resolution(cell_id))
        detail_params = PublicArticleGeoCellDetailParams(h3_cell=cell_id)

        single = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=detail_params,
        )
        batch = search_public_articles_in_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsBatchParams(
                cells=(cell_id,),
                resolution=resolution,
            ),
        )

    assert single.total == batch.total == 1
    assert batch.items[0].matched_cells == [cell_id]


def test_external_source_filter_applies() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Trib story",
            text="Body",
            pub_date=date(2024, 3, 1),
            external_source="Chicago Tribune",
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        loc = _add_location_mention(
            session,
            project_id=project_id,
            article_id=int(article.id),  # type: ignore[arg-type]
            label="Place",
            geometry_json=CHICAGO_POINT,
        )
        assert loc.h3_cell is not None
        cell_id = str(loc.h3_cell)
        resolution = int(get_resolution(cell_id))

        included = search_public_articles_in_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsBatchParams(
                cells=(cell_id,),
                resolution=resolution,
                external_source="Chicago Tribune",
            ),
        )
        excluded = search_public_articles_in_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsBatchParams(
                cells=(cell_id,),
                resolution=resolution,
                external_source="Sun-Times",
            ),
        )

    assert included.total == 1
    assert excluded.total == 0


def test_metadata_filter_narrows_batch() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Meta filter",
            text="Body",
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
        session.commit()
        loc = _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="City Hall",
            geometry_json=CHICAGO_POINT,
        )
        assert loc.h3_cell is not None
        cell_id = str(loc.h3_cell)
        resolution = int(get_resolution(cell_id))

        included = search_public_articles_in_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsBatchParams(
                cells=(cell_id,),
                resolution=resolution,
                meta_type="topic",
                meta_category="local_government_politics",
            ),
        )
        excluded = search_public_articles_in_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsBatchParams(
                cells=(cell_id,),
                resolution=resolution,
                meta_type="topic",
                meta_category="sports",
            ),
        )

    assert included.total == 1
    assert excluded.total == 0


def test_normalize_batch_cells_rejects_resolution_mismatch() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(project_id=project_id, headline="Story", text="Body")
        session.add(article)
        session.commit()
        session.refresh(article)
        loc = _add_location_mention(
            session,
            project_id=project_id,
            article_id=int(article.id),  # type: ignore[arg-type]
            label="Place",
            geometry_json=CHICAGO_POINT,
        )
        assert loc.h3_cell is not None
        cell_id = str(loc.h3_cell)
        resolution = int(get_resolution(cell_id))

        with pytest.raises(PublicArticleGeoCellsBatchValidationError):
            normalize_batch_cells([cell_id], resolution=resolution + 1)
