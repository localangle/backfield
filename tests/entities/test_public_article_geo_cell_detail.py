"""Tests for public H3 geo-cell article drill-down."""

from __future__ import annotations

from datetime import date

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
from backfield_entities.public.article_geo_cells import (
    PublicArticleGeoCellsParams,
    aggregate_article_geo_cells,
)
from h3 import cell_to_parent, latlng_to_cell
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
    org = BackfieldOrganization(name="Org", slug="org-cell-detail")
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


def test_two_mentions_in_one_cell_return_both_matching_locations() -> None:
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

        loc = _add_location_mention(
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
        assert loc.h3_cell is not None

        result = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(h3_cell=str(loc.h3_cell)),
        )

    assert result.total == 1
    assert len(result.items) == 1
    assert len(result.items[0].matching_locations) == 2


def test_two_articles_in_cell_total_two() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        cell_id: str | None = None
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
            loc = _add_location_mention(
                session,
                project_id=project_id,
                article_id=int(article.id),  # type: ignore[arg-type]
                label=headline,
                geometry_json=CHICAGO_POINT,
            )
            cell_id = str(loc.h3_cell)
        assert cell_id is not None

        result = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(h3_cell=cell_id),
        )

    assert result.total == 2
    assert len(result.items) == 2


def test_coarse_location_excluded_for_fine_cell() -> None:
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

        point_loc = _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="City Hall",
            geometry_json=CHICAGO_POINT,
        )
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
        assert point_loc.h3_cell is not None

        result = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(h3_cell=str(point_loc.h3_cell)),
        )

    assert result.total == 1
    assert len(result.items[0].matching_locations) == 1
    assert result.items[0].matching_locations[0].label == "City Hall"


def test_sibling_cell_excludes_other_cell_mentions() -> None:
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
        assert loc_a.h3_cell is not None

        result = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(h3_cell=str(loc_a.h3_cell)),
        )

    assert result.total == 1
    assert len(result.items[0].matching_locations) == 1
    assert result.items[0].matching_locations[0].label == "A"


def test_parent_cell_includes_child_mentions() -> None:
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
        _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="B",
            geometry_json=NEARBY_POINT,
        )
        assert loc_a.h3_cell is not None
        parent_cell = str(cell_to_parent(str(loc_a.h3_cell), 10))

        result = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(h3_cell=parent_cell),
        )

    assert result.total == 1
    assert len(result.items[0].matching_locations) == 2


def test_drilldown_total_matches_geo_cells_article_count() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        for headline in ("Story one", "Story two", "Story three"):
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

        coverage = aggregate_article_geo_cells(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellsParams(
                min_lng=-88.0,
                min_lat=41.0,
                max_lng=-87.0,
                max_lat=42.0,
                resolution=11,
            ),
        )
        assert coverage.cells
        target = coverage.cells[0]

        drilldown = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(h3_cell=target.h3_cell),
        )

    assert drilldown.total == target.article_count


def test_nature_filter_narrows_drilldown() -> None:
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
        loc = _add_location_mention(
            session,
            project_id=project_id,
            article_id=article_id,
            label="Primary place",
            geometry_json=CHICAGO_POINT,
            nature="primary",
        )
        assert loc.h3_cell is not None

        primary = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(
                h3_cell=str(loc.h3_cell),
                nature="primary",
            ),
        )
        secondary = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(
                h3_cell=str(loc.h3_cell),
                nature="secondary",
            ),
        )

    assert primary.total == 1
    assert secondary.total == 0


def test_metadata_filter_narrows_drilldown() -> None:
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
                meta_type="subject",
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

        included = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(
                h3_cell=str(loc.h3_cell),
                meta_type="subject",
                meta_category="local_government_politics",
            ),
        )
        excluded = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(
                h3_cell=str(loc.h3_cell),
                meta_type="subject",
                meta_category="sports",
            ),
        )

    assert included.total == 1
    assert excluded.total == 0


def test_empty_cell_returns_zero_total() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_project(session)
        empty_cell = str(latlng_to_cell(0.0, 0.0, 11))

        result = search_public_articles_in_cell(
            session,
            project_id=project_id,
            params=PublicArticleGeoCellDetailParams(h3_cell=empty_cell),
        )

    assert result.total == 0
    assert result.items == []
