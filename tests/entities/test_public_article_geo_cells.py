"""Tests for public H3 geo-cell article coverage aggregation."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticleMeta,
    SubstrateLocation,
    SubstrateLocationMention,
)
from backfield_entities.geo.h3_index import derive_h3_index
from backfield_entities.public.article_geo_cells import (
    PublicArticleGeoCellsParams,
    aggregate_article_geo_cells,
    initial_resolution,
    resolution_for_bbox,
)
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
    org = BackfieldOrganization(name="Org", slug="org-geo-cells")
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
    location_type: str = "place",
    nature: str = "primary",
    h3_cell: str | None = None,
    h3_resolution: int | None = None,
) -> SubstrateLocation:
    loc = SubstrateLocation(
        project_id=project_id,
        name=label,
        normalized_name=label.lower(),
        location_type=location_type,
        geometry_type="Point",
        geometry_json=geometry_json,
    )
    if h3_cell is not None and h3_resolution is not None:
        loc.h3_cell = h3_cell
        loc.h3_resolution = h3_resolution
    else:
        _apply_h3(loc)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    session.add(
        SubstrateLocationMention(
            article_id=article_id,
            location_id=int(loc.id),  # type: ignore[arg-type]
            nature=nature,
        )
    )
    session.commit()
    return loc


def _bbox_around_chicago() -> PublicArticleGeoCellsParams:
    return PublicArticleGeoCellsParams(
        min_lng=-88.0,
        min_lat=41.0,
        max_lng=-87.0,
        max_lat=42.0,
    )


def test_two_places_in_one_cell_count_once_per_article() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Two stops",
            text="Body",
            pub_date=date(2024, 3, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)  # type: ignore[arg-type]

        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="Place A",
            geometry_json=CHICAGO_POINT,
        )
        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="Place B",
            geometry_json=CHICAGO_POINT,
        )

        result = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=_bbox_around_chicago(),
        )

    assert result.resolution == 4
    assert result.derived_resolution == 4
    assert result.requested_resolution is None
    assert result.coarsened is False
    assert result.bbox_extent_km > 0
    assert len(result.cells) == 1
    assert result.cells[0].article_count == 1


def test_two_articles_in_same_cell_count_twice() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        for headline in ("Story one", "Story two"):
            article = SubstrateArticle(
                project_id=project_id,
                headline=headline,
                text="Body",
                pub_date=date(2024, 3, 1),
            )
            session.add(article)
            session.commit()
            session.refresh(article)
            _add_location_mention(
                session,
                project_id=project_id,
                article_id=int(article.id),  # type: ignore[arg-type]
                label=headline,
                geometry_json=CHICAGO_POINT,
            )

        result = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=_bbox_around_chicago(),
        )

    assert result.cells[0].article_count == 2


def test_distinct_article_rollup_across_sibling_cells() -> None:
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
        assert loc_a.h3_cell != loc_b.h3_cell

        params = PublicArticleGeoCellsParams(
            min_lng=-87.63,
            min_lat=41.877,
            max_lng=-87.629,
            max_lat=41.8785,
            resolution=10,
        )
        result = aggregate_article_geo_cells(session, project_id=project_id, params=params)

    assert result.resolution == 10
    assert result.requested_resolution == 10
    assert result.coarsened is False
    assert len(result.cells) == 1
    assert result.cells[0].article_count == 1


def test_coarse_native_location_excluded_at_finer_resolution() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="State story",
            text="Body",
            pub_date=date(2024, 3, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)  # type: ignore[arg-type]

        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="Illinois",
            geometry_json=CHICAGO_POINT,
            location_type="state",
            h3_cell="842664dffffffff",
            h3_resolution=4,
        )

        result = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-87.63,
                min_lat=41.877,
                max_lng=-87.628,
                max_lat=41.879,
                resolution=11,
            ),
        )

    assert result.resolution == 11
    assert result.cells == []


def test_coarse_city_does_not_pollute_fine_point_counts() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="City and block",
            text="Body",
            pub_date=date(2024, 3, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)  # type: ignore[arg-type]

        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="Chicago",
            geometry_json=CHICAGO_POINT,
            location_type="city",
            h3_cell="842664dffffffff",
            h3_resolution=5,
        )
        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="City Hall",
            geometry_json=CHICAGO_POINT,
        )

        fine = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-87.63,
                min_lat=41.877,
                max_lng=-87.628,
                max_lat=41.879,
                resolution=11,
            ),
        )
        coarse = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                resolution=5,
            ),
        )

    assert fine.cells[0].article_count == 1
    assert coarse.cells[0].article_count == 1


def test_resolution_override_honored_without_bbox_clamp() -> None:
    derived = resolution_for_bbox(-88.0, 41.0, -87.0, 42.0)
    assert derived == 4
    assert initial_resolution(derived_resolution=derived, resolution_override=11) == 11
    assert initial_resolution(derived_resolution=derived, resolution_override=3) == 3


def test_auto_coarsen_when_cell_ceiling_exceeded() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        for headline in ("Story one", "Story two"):
            article = SubstrateArticle(
                project_id=project_id,
                headline=headline,
                text="Body",
                pub_date=date(2024, 3, 1),
            )
            session.add(article)
            session.commit()
            session.refresh(article)
            _add_location_mention(
                session,
                project_id=project_id,
                article_id=int(article.id),  # type: ignore[arg-type]
                label=headline,
                geometry_json=CHICAGO_POINT if headline == "Story one" else NEARBY_POINT,
            )

        with patch(
            "backfield_entities.public.article_geo_cells.MAX_CELLS_PER_RESPONSE",
            1,
        ):
            result = aggregate_article_geo_cells(
                session,
                project_id=project_id,
                params=PublicArticleGeoCellsParams(
                    min_lng=-87.63,
                    min_lat=41.877,
                    max_lng=-87.629,
                    max_lat=41.8785,
                    resolution=11,
                ),
            )

    assert result.coarsened is True
    assert result.resolution < 11
    assert len(result.cells) <= 1


def test_nature_filter_narrows_cells() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        article = SubstrateArticle(
            project_id=project_id,
            headline="Nature filter",
            text="Body",
            pub_date=date(2024, 3, 1),
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = int(article.id)  # type: ignore[arg-type]
        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="Primary place",
            geometry_json=CHICAGO_POINT,
            nature="primary",
        )

        primary = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                nature="primary",
            ),
        )
        secondary = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                nature="secondary",
            ),
        )

    assert primary.cells[0].article_count == 1
    assert secondary.cells == []


def test_metadata_filter_narrows_cells() -> None:
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
        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="City Hall",
            geometry_json=CHICAGO_POINT,
        )

        included = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                meta_type="topic",
                meta_category="local_government_politics",
            ),
        )
        excluded = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                meta_type="topic",
                meta_category="sports",
            ),
        )

    assert included.cells[0].article_count == 1
    assert excluded.cells == []


def test_pub_date_filter_narrows_cells() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        in_range = SubstrateArticle(
            project_id=project_id,
            headline="March story",
            text="Body",
            pub_date=date(2024, 3, 15),
        )
        out_of_range = SubstrateArticle(
            project_id=project_id,
            headline="April story",
            text="Body",
            pub_date=date(2024, 4, 1),
        )
        session.add(in_range)
        session.add(out_of_range)
        session.commit()
        session.refresh(in_range)
        session.refresh(out_of_range)
        in_range_id = int(in_range.id)  # type: ignore[arg-type]
        out_of_range_id = int(out_of_range.id)  # type: ignore[arg-type]
        _add_location_mention(
            session,
            project_id=project_id,
            article_id=in_range_id,
            label="City Hall",
            geometry_json=CHICAGO_POINT,
        )
        _add_location_mention(
            session,
            project_id=project_id,
            article_id=out_of_range_id,
            label="City Hall",
            geometry_json=NEARBY_POINT,
        )

        included = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                pub_date_from=date(2024, 3, 1),
                pub_date_to=date(2024, 3, 31),
            ),
        )
        no_match = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                pub_date_from=date(2025, 1, 1),
                pub_date_to=date(2025, 12, 31),
            ),
        )

    assert included.cells[0].article_count == 1
    assert no_match.cells == []
