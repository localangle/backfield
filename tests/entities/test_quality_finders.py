"""Unit tests for cleanup quality finders."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.quality.finders.duplicate_locations import (
    duplicate_location_cluster_ids,
    duplicate_location_pair_edges,
)
from backfield_entities.quality.finders.duplicate_organizations import (
    duplicate_organization_cluster_ids,
)
from backfield_entities.quality.finders.duplicate_people import duplicate_person_cluster_ids
from backfield_entities.quality.finders.location_geography_issues import (
    count_location_geography_issues,
    list_location_geography_issues,
    substrate_is_distant_from_canonical,
)
from sqlmodel import Session, SQLModel, create_engine


def _make_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Test Org", slug="test-org")
    session.add(org)
    session.commit()
    session.refresh(org)
    sb = Stylebook(
        organization_id=int(org.id),
        slug="test-sb",
        name="Test",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    assert sb.id is not None
    assert org.id is not None
    return int(sb.id), int(org.id)


def _add_canonical(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
    label: str,
    geometry_json: dict | None = None,
) -> StylebookLocationCanonical:
    row = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        slug=slug,
        label=label,
        geometry_json=geometry_json,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_exact_duplicate_location_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        shared_label = "Ward 36, Chicago, IL"
        _add_canonical(session, stylebook_id=stylebook_id, slug="ward-36-a", label=shared_label)
        _add_canonical(session, stylebook_id=stylebook_id, slug="ward-36-b", label=shared_label)
        session.commit()

        clusters = duplicate_location_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_fuzzy_duplicate_location_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="billy-goat-chicago",
            label="Billy Goat Tavern, Chicago, IL",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="billy-goat-west-loop",
            label="Billy Goat Tavern, West Loop, Chicago, IL",
        )
        session.commit()

        clusters = duplicate_location_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_suffix_only_labels_not_clustered_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="ward-36",
            label="Ward 36, Chicago, IL",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="near-west-side",
            label="Near West Side, Chicago, IL",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="washington-park",
            label="Washington Park, South Side, Chicago, IL",
        )
        session.commit()

        pairs = duplicate_location_pair_edges(session, stylebook_id=stylebook_id)
        assert pairs == []


def test_location_geography_issues_missing_geometry_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, org_id = _make_stylebook(session)
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="no-geom",
            label="Place without map",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="with-geom",
            label="Place with map",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
        )
        session.commit()

        assert (
            count_location_geography_issues(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
            )
            == 1
        )
        rows, total = list_location_geography_issues(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert len(rows) == 1
        assert rows[0].label == "Place without map"
        assert rows[0].issue == "missing_geometry"


def test_substrate_is_distant_from_canonical() -> None:
    illinois = {"type": "Point", "coordinates": [-88.28, 42.04]}
    texas = {"type": "Point", "coordinates": [-97.45, 31.05]}
    assert substrate_is_distant_from_canonical(
        substrate_geometry_json=texas,
        canonical_geometry_json=illinois,
    )
    assert not substrate_is_distant_from_canonical(
        substrate_geometry_json=illinois,
        canonical_geometry_json=illinois,
    )


def test_location_geography_issues_distant_linked_places_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, org_id = _make_stylebook(session)
        org = session.get(BackfieldOrganization, org_id)
        assert org is not None
        project = BackfieldProject(organization_id=org_id, name="Demo", slug="demo")
        session.add(project)
        session.commit()
        session.refresh(project)

        canon = _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="elgin-il",
            label="Community Center Christian Ministries, Elgin, IL",
            geometry_json={"type": "Point", "coordinates": [-88.28, 42.04]},
        )
        session.add(
            SubstrateLocation(
                project_id=int(project.id),
                name="Community Center Christian Ministries, Elgin, IL",
                normalized_name="community-center-elgin",
                location_type="place",
                identity_fingerprint="fp-distant-tx",
                stylebook_location_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
                geometry_json={"type": "Point", "coordinates": [-97.45, 31.05]},
            )
        )
        session.commit()

        rows, total = list_location_geography_issues(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert rows[0].issue == "distant_linked_places"
        assert rows[0].distant_linked_count == 1


def test_exact_duplicate_person_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        from backfield_db import StylebookPersonCanonical

        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-a",
                label="Jane Doe",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-b",
                label="Jane Doe",
            )
        )
        session.commit()

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_fuzzy_duplicate_person_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        from backfield_db import StylebookPersonCanonical

        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-doe",
                label="Jane Doe",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-m-doe",
                label="Jane M. Doe",
            )
        )
        session.commit()

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def _add_person(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
    label: str,
    person_type: str | None = None,
) -> str:
    from backfield_db import StylebookPersonCanonical

    row = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        slug=slug,
        label=label,
        person_type=person_type,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return str(row.id)


def test_aaron_ampudia_diacritic_variants_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        a = _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="aaron-ampudia",
            label="Aaron Ampudia",
        )
        b = _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="aaron-ampudia-accent",
            label="Aarón Ampudia",
        )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert set(clusters[0]) == {a, b}


def test_mr_t_title_variants_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        a = _add_person(session, stylebook_id=stylebook_id, slug="mr-t-a", label="Mr T")
        b = _add_person(session, stylebook_id=stylebook_id, slug="mr-t-b", label="Mr. T")

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert set(clusters[0]) == {a, b}


def test_sasha_ann_hyphen_variants_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        a = _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="sasha-ann-a",
            label="Sasha-Ann Simons",
        )
        b = _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="sasha-ann-b",
            label="Sasha Ann Simons",
        )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert set(clusters[0]) == {a, b}


def test_donald_trump_suffix_mismatch_does_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="donald-trump",
            label="Donald Trump",
        )
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="donald-trump-jr",
            label="Donald Trump Jr",
        )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_weak_first_suffix_bridge_does_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="mike-conley-jr",
            label="Mike Conley Jr",
        )
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="mike-oliver-jr",
            label="Mike Oliver Jr",
        )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_numbered_detective_groups_do_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="area-3-detectives",
            label="Area 3 detectives",
        )
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="area-5-detectives",
            label="Area 5 detectives",
        )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_numbered_courts_do_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="court-1-judge",
            label="Court 1 Judge",
        )
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="court-2-judge",
            label="Court 2 Judge",
        )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_same_person_type_alone_does_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="john-adams",
            label="John Adams",
            person_type="public_official",
        )
        _add_person(
            session,
            stylebook_id=stylebook_id,
            slug="john-quincy",
            label="John Quincy Adams",
            person_type="public_official",
        )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_duplicate_person_bounded_no_false_positives_sqlite() -> None:
    """Many unrelated people must not produce spurious clusters."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        for index in range(300):
            _add_person(
                session,
                stylebook_id=stylebook_id,
                slug=f"unique-person-{index}",
                label=f"Unique Person Number {index}",
            )

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def _add_organization(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
    label: str,
    organization_type: str | None = None,
) -> str:
    from backfield_db import StylebookOrganizationCanonical

    row = StylebookOrganizationCanonical(
        stylebook_id=stylebook_id,
        slug=slug,
        label=label,
        organization_type=organization_type,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return str(row.id)


def test_exact_duplicate_organization_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_organization(session, stylebook_id=stylebook_id, slug="city-hall-a", label="City Hall")
        _add_organization(session, stylebook_id=stylebook_id, slug="city-hall-b", label="City Hall")

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_fuzzy_duplicate_organization_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="city-finance-a",
            label="City of Chicago Finance Department",
        )
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="city-finance-b",
            label="City of Chicago Department of Finance",
        )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_trump_administration_variants_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        a = _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="trump-admin",
            label="Trump Administration",
        )
        b = _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="donald-trump-admin",
            label="Donald Trump Administration",
        )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert set(clusters[0]) == {a, b}


def test_cook_county_states_attorney_office_variants_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        a = _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="cook-sao",
            label="Cook County State's Attorney's Office",
            organization_type="government",
        )
        b = _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="office-of-cook-sao",
            label="Office of the Cook County State's Attorney",
            organization_type="government",
        )
        c = _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="cook-sao-burke",
            label="Cook County State's Attorney Eileen O'Neill Burke's office",
            organization_type="government",
        )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert set(clusters[0]) == {a, b, c}


def test_named_official_office_alone_does_not_bridge_to_generic_office_sqlite() -> None:
    """Removed narrow named-official bridge must stay removed.

    ``State's Attorney Eileen O'Neill Burke's office`` (no county) should not
    cluster with the county state's attorney office when the only shared
    signal would be the named-official bridge.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="cook-sao",
            label="Cook County State's Attorney's Office",
            organization_type="government",
        )
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="sao-burke",
            label="State's Attorney Eileen O'Neill Burke's office",
            organization_type="government",
        )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_county_mismatch_states_attorney_offices_do_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="cook-sao",
            label="Cook County State's Attorney's Office",
            organization_type="government",
        )
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="dekalb-sao",
            label="DeKalb County State's Attorney's Office",
            organization_type="government",
        )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_sports_team_sport_mismatch_does_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="marian-football",
            label="Marian Catholic High School boys football team",
            organization_type="sports_team",
        )
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="marian-basketball",
            label="Marian Catholic High School boys basketball team",
            organization_type="sports_team",
        )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_same_organization_type_alone_does_not_cluster_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="st-andrews",
            label="St. Andrew's Greek Orthodox Church",
            organization_type="religious_org",
        )
        _add_organization(
            session,
            stylebook_id=stylebook_id,
            slug="st-george",
            label="St. George Greek Orthodox Church",
            organization_type="religious_org",
        )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_duplicate_organization_bounded_no_false_positives_sqlite() -> None:
    """Many unrelated orgs must not produce spurious clusters or explode pair generation."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        for index in range(300):
            _add_organization(
                session,
                stylebook_id=stylebook_id,
                slug=f"unique-org-{index}",
                label=f"Unique Organization Number {index}",
                organization_type=None,
            )

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert clusters == []


def test_duplicate_organization_clusters_sort_exact_matches_first_sqlite() -> None:
    from backfield_db import StylebookOrganizationCanonical
    from backfield_entities.quality.finders.duplicate_organizations import (
        paginate_duplicate_organization_clusters,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="advocate-center-a",
                label="Advocate Center",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="advocate-center-b",
                label="Advocate Center",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="city-finance-a",
                label="City of Chicago Finance Department",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="city-finance-b",
                label="City of Chicago Department of Finance",
            )
        )
        session.commit()

        page, total = paginate_duplicate_organization_clusters(
            session,
            stylebook_id=stylebook_id,
            limit=10,
            offset=0,
        )
        assert total == 2
        assert len(page[0]) == 2
        labels = {
            session.get(StylebookOrganizationCanonical, member_id).label  # type: ignore[union-attr]
            for member_id in page[0]
        }
        assert labels == {"Advocate Center"}


def test_duplicate_organization_clusters_filter_by_query_sqlite() -> None:
    from backfield_db import StylebookOrganizationCanonical
    from backfield_entities.quality.finders.duplicate_organizations import (
        paginate_duplicate_organization_clusters,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="advocate-center-a",
                label="Advocate Center",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="advocate-center-b",
                label="Advocate Center",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="city-hall-a",
                label="City Hall",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="city-hall-b",
                label="City Hall",
            )
        )
        session.commit()

        page, total = paginate_duplicate_organization_clusters(
            session,
            stylebook_id=stylebook_id,
            limit=10,
            offset=0,
            query="advocate",
        )
        assert total == 1
        assert len(page) == 1
        assert len(page[0]) == 2


def test_person_name_mismatch_finder_sqlite() -> None:
    from backfield_db import (
        BackfieldProject,
        StylebookPersonCanonical,
        SubstratePerson,
    )
    from backfield_entities.quality.dismissals import dismiss_canonical_issue
    from backfield_entities.quality.finders.person_name_mismatch import (
        count_person_name_mismatches,
        list_person_name_mismatches,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, org_id = _make_stylebook(session)
        project = BackfieldProject(organization_id=org_id, name="Demo", slug="demo")
        session.add(project)
        session.commit()
        session.refresh(project)

        canon = StylebookPersonCanonical(
            stylebook_id=stylebook_id,
            slug="jane-doe",
            label="Jane Doe",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)

        session.add(
            SubstratePerson(
                project_id=int(project.id),
                name="John Smith",
                normalized_name="john-smith",
                person_type="individual",
                identity_fingerprint="fp-person-mismatch",
                stylebook_person_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()

        assert (
            count_person_name_mismatches(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
            )
            == 1
        )
        rows, total = list_person_name_mismatches(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert rows[0].label == "Jane Doe"
        assert rows[0].mismatched_linked_count == 1
        assert "John Smith" in rows[0].mismatched_examples

        dismiss_canonical_issue(
            session,
            stylebook_id=stylebook_id,
            check_id="mismatched-people",
            canonical_id=str(canon.id),
            created_by_user_id=None,
        )
        session.commit()
        assert (
            count_person_name_mismatches(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
            )
            == 0
        )


def test_organization_name_mismatch_finder_sqlite() -> None:
    from backfield_db import (
        BackfieldProject,
        StylebookOrganizationCanonical,
        SubstrateOrganization,
    )
    from backfield_entities.quality.finders.organization_name_mismatch import (
        count_organization_name_mismatches,
        list_organization_name_mismatches,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, org_id = _make_stylebook(session)
        project = BackfieldProject(organization_id=org_id, name="Demo", slug="demo")
        session.add(project)
        session.commit()
        session.refresh(project)

        canon = StylebookOrganizationCanonical(
            stylebook_id=stylebook_id,
            slug="globex",
            label="Globex Industries",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)

        session.add(
            SubstrateOrganization(
                project_id=int(project.id),
                name="Acme Corporation",
                normalized_name="acme-corporation",
                organization_type="company",
                identity_fingerprint="fp-org-mismatch",
                stylebook_organization_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()

        assert (
            count_organization_name_mismatches(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
            )
            == 1
        )
        rows, total = list_organization_name_mismatches(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert rows[0].label == "Globex Industries"
        assert rows[0].mismatched_linked_count == 1
        assert "Acme Corporation" in rows[0].mismatched_examples


def test_location_name_mismatch_finder_sqlite() -> None:
    from backfield_entities.quality.dismissals import dismiss_canonical_issue
    from backfield_entities.quality.finders.location_name_mismatch import (
        count_location_name_mismatches,
        list_location_name_mismatches,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, org_id = _make_stylebook(session)
        project = BackfieldProject(organization_id=org_id, name="Demo", slug="demo")
        session.add(project)
        session.commit()
        session.refresh(project)

        canon = StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            slug="chicago-avenue",
            label="Chicago Avenue, Near North Side, Chicago, IL",
            location_type="street_road",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)

        session.add(
            SubstrateLocation(
                project_id=int(project.id),
                name="62nd Street, Chicago, IL",
                normalized_name="62nd street, chicago, il",
                location_type="street_road",
                identity_fingerprint="fp-location-mismatch",
                stylebook_location_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()

        assert (
            count_location_name_mismatches(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
            )
            == 1
        )
        rows, total = list_location_name_mismatches(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert rows[0].label == "Chicago Avenue, Near North Side, Chicago, IL"
        assert rows[0].mismatched_linked_count == 1
        assert "62nd Street, Chicago, IL" in rows[0].mismatched_examples

        dismiss_canonical_issue(
            session,
            stylebook_id=stylebook_id,
            check_id="mismatched-locations",
            canonical_id=str(canon.id),
            created_by_user_id=None,
        )
        session.commit()
        assert (
            count_location_name_mismatches(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
            )
            == 0
        )


def test_exact_duplicate_organization_apostrophe_normalization_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        from backfield_db import StylebookOrganizationCanonical

        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="wendys-a",
                label="Wendy\u2019s",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="wendys-b",
                label="Wendy's",
            )
        )
        session.commit()

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2
