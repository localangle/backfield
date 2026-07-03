"""Tests for Stylebook cleanup API routes."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from backfield_db import (
    BackfieldAiModelConfig,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldUser,
    Stylebook,
    StylebookCleanupAiProposal,
    StylebookCleanupAiReview,
    StylebookCleanupCheckRun,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select
from stylebook_api.deps import get_auth as get_auth_dep
from stylebook_api.deps import get_session
from stylebook_api.main import app


def _session_auth_for_user(user: BackfieldUser, *, org_id: int) -> dict[str, Any]:
    return {
        "type": "session",
        "user": user,
        "token_data": {},
        "organization_id": int(org_id),
        "org_role": "org_admin",
        "is_admin": True,
    }


@pytest.fixture
def cleanup_client(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[TestClient, Engine], None, None]:
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    monkeypatch.setattr(
        "stylebook_api.semantic_reindex.celery_app.send_task",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "stylebook_api.routers.stylebook_cleanup_ai_review.celery_app.send_task",
        lambda *_args, **_kwargs: None,
    )

    def _sync_cleanup_check_run_send_task(name, args=None, **_kwargs):
        if name == "worker.tasks.execute_cleanup_check_run" and args:
            from worker.tasks import execute_cleanup_check_run

            monkeypatch.setattr("worker.tasks.get_engine", lambda: engine)
            execute_cleanup_check_run(str(args[0]))

    monkeypatch.setattr(
        "stylebook_api.routers.stylebook_cleanup.celery_app.send_task",
        _sync_cleanup_check_run_send_task,
    )
    import importlib

    import backfield_auth.service_tokens as service_tokens

    importlib.reload(service_tokens)

    database_path = tmp_path / "stylebook-cleanup-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        org = BackfieldOrganization(name="Backfield", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        org_id = int(org.id)
        user = BackfieldUser(email="admin@example.com", password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        sb = Stylebook(
            organization_id=org_id,
            slug="default",
            name="Default Stylebook",
            is_default=True,
        )
        s.add(sb)
        s.commit()
        s.refresh(sb)
        sb_id = int(sb.id)
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="dupe-a",
                label="Ward 36, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="dupe-b",
                label="Ward 36, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="fuzzy-a",
                label="Billy Goat Tavern, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="fuzzy-b",
                label="Billy Goat Tavern, West Loop, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="unique-chicago",
                label="Near West Side, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="missing-geom",
                label="No map pin here",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="has-geom",
                label="Mapped place",
                geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
            )
        )
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="person-dupe-a",
                label="Jane Doe",
            )
        )
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="person-dupe-b",
                label="Jane Doe",
            )
        )
        s.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="org-dupe-a",
                label="City Hall",
            )
        )
        s.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="org-dupe-b",
                label="City Hall",
            )
        )
        s.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="org-crossform-a",
                label="Cook County State's Attorney's Office",
                organization_type="government",
            )
        )
        s.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="org-crossform-b",
                label="Office of the Cook County State's Attorney",
                organization_type="government",
            )
        )
        s.commit()
        user_id = int(user.id)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    def get_test_auth() -> dict[str, Any]:
        with Session(engine) as session:
            u = session.get(BackfieldUser, user_id)
            assert u is not None
            return _session_auth_for_user(u, org_id=org_id)

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_auth_dep] = get_test_auth
    client = TestClient(app)
    try:
        yield client, engine
    finally:
        app.dependency_overrides.clear()


ALL_CLEANUP_CHECK_IDS = (
    "duplicate-locations",
    "missing-geometry-locations",
    "mismatched-locations",
    "duplicate-people",
    "mismatched-people",
    "duplicate-organizations",
    "mismatched-organizations",
)


def _start_cleanup_check(client: TestClient, check_id: str) -> dict[str, Any]:
    response = client.post(f"/v1/stylebooks/default/cleanup/checks/{check_id}/runs")
    assert response.status_code == 200
    return response.json()


def _run_cleanup_check(client: TestClient, check_id: str) -> dict[str, Any]:
    return _start_cleanup_check(client, check_id)


def _run_all_cleanup_checks(client: TestClient) -> None:
    for check_id in ALL_CLEANUP_CHECK_IDS:
        _run_cleanup_check(client, check_id)


def test_list_cleanup_checks(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    r = client.get("/v1/stylebooks/default/cleanup/checks")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body
    ids = {check["id"] for check in body["checks"]}
    assert ids == set(ALL_CLEANUP_CHECK_IDS)
    for check in body["checks"]:
        assert check["status"] == "never_run"
        assert check["count"] == 0
    assert body["total_open"] == 0

    _run_all_cleanup_checks(client)

    r = client.get("/v1/stylebooks/default/cleanup/checks")
    assert r.status_code == 200
    body = r.json()
    by_id = {check["id"]: check for check in body["checks"]}
    assert by_id["duplicate-locations"]["count"] == 2
    assert by_id["duplicate-locations"]["status"] == "succeeded"
    assert by_id["duplicate-people"]["count"] == 1
    assert by_id["duplicate-organizations"]["count"] == 2
    assert by_id["missing-geometry-locations"]["count"] == 6
    assert by_id["mismatched-locations"]["count"] == 0
    assert by_id["mismatched-people"]["count"] == 0
    assert by_id["mismatched-organizations"]["count"] == 0
    assert body["total_open"] == sum(check["count"] for check in body["checks"])


def test_list_cleanup_checks_single_check_id(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    _run_cleanup_check(client, "duplicate-people")
    r = client.get("/v1/stylebooks/default/cleanup/checks?check_id=duplicate-people")
    assert r.status_code == 200
    body = r.json()
    assert len(body["checks"]) == 1
    assert body["checks"][0]["id"] == "duplicate-people"
    assert body["checks"][0]["count"] == 1
    assert body["checks"][0]["status"] == "succeeded"
    assert body["total_open"] == 1


def test_start_cleanup_check_run_is_idempotent_while_active(
    cleanup_client: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine = cleanup_client
    monkeypatch.setattr(
        "stylebook_api.routers.stylebook_cleanup.celery_app.send_task",
        lambda *_args, **_kwargs: None,
    )
    first = _start_cleanup_check(client, "duplicate-locations")
    with Session(engine) as session:
        run = session.get(StylebookCleanupCheckRun, first["id"])
        assert run is not None
        run.status = "running"
        session.add(run)
        session.commit()
    second = _start_cleanup_check(client, "duplicate-locations")
    assert second["id"] == first["id"]
    assert second["status"] == "running"


def test_get_latest_cleanup_check_run(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    missing = client.get("/v1/stylebooks/default/cleanup/checks/duplicate-locations/runs/latest")
    assert missing.status_code == 200
    assert missing.json() is None
    run = _run_cleanup_check(client, "duplicate-locations")
    latest = client.get("/v1/stylebooks/default/cleanup/checks/duplicate-locations/runs/latest")
    assert latest.status_code == 200
    body = latest.json()
    assert body is not None
    assert body["id"] == run["id"]
    assert body["status"] == "succeeded"
    assert body["candidate_count"] == 2


def test_duplicate_location_clusters(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    _run_cleanup_check(client, "duplicate-locations")
    r = client.get("/v1/stylebooks/default/cleanup/checks/duplicate-locations?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    labels = {cluster["label"] for cluster in body["clusters"]}
    assert "Ward 36, Chicago, IL" in labels
    assert "Billy Goat Tavern" in labels


def test_missing_geometry_locations(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    _run_cleanup_check(client, "missing-geometry-locations")
    r = client.get("/v1/stylebooks/default/cleanup/checks/missing-geometry-locations")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 6
    labels = {item["label"] for item in body["canonicals"]}
    assert "No map pin here" in labels
    missing = next(item for item in body["canonicals"] if item["label"] == "No map pin here")
    assert missing["geography_issue"] == "missing_geometry"


def test_delete_empty_cleanup_canonical(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        empty = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.slug == "missing-geom"
            )
        ).one()
        canonical_id = str(empty.id)
    response = client.delete(
        f"/v1/stylebooks/default/cleanup/canonical-locations/{canonical_id}"
    )
    assert response.status_code == 200
    assert response.json()["id"] == canonical_id
    with Session(engine) as session:
        assert session.get(StylebookLocationCanonical, canonical_id) is None


def test_merge_cleanup_canonical_relinks_and_deletes_source(
    cleanup_client: tuple[TestClient, Engine],
) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        session.add(
            BackfieldProject(
                organization_id=int(org.id),
                name="Demo",
                slug="demo-proj",
            )
        )
        session.commit()
        proj = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")
        ).one()
        source = session.exec(
            select(StylebookLocationCanonical).where(StylebookLocationCanonical.slug == "dupe-a")
        ).one()
        target = session.exec(
            select(StylebookLocationCanonical).where(StylebookLocationCanonical.slug == "dupe-b")
        ).one()
        session.add(
            SubstrateLocation(
                project_id=int(proj.id),
                name="Ward spot",
                normalized_name="ward-spot",
                location_type="place",
                identity_fingerprint="fp-cleanup-merge",
                stylebook_location_canonical_id=str(source.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()
        source_id = str(source.id)
        target_id = str(target.id)

    response = client.post(
        f"/v1/stylebooks/default/cleanup/canonical-locations/{source_id}/merge-into",
        json={"target_canonical_id": target_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == source_id
    assert body["target_id"] == target_id
    assert body["relinked_substrate_count"] == 1
    assert body["source_deleted"] is True

    with Session(engine) as session:
        assert session.get(StylebookLocationCanonical, source_id) is None
        loc = session.exec(
            select(SubstrateLocation).where(
                SubstrateLocation.identity_fingerprint == "fp-cleanup-merge"
            )
        ).one()
        assert loc.stylebook_location_canonical_id == target_id


def test_duplicate_person_clusters(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    _run_cleanup_check(client, "duplicate-people")
    response = client.get("/v1/stylebooks/default/cleanup/checks/duplicate-people?limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["clusters"][0]["label"] == "Jane Doe"
    assert len(body["clusters"][0]["canonicals"]) == 2


def test_duplicate_organization_clusters(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    _run_cleanup_check(client, "duplicate-organizations")
    response = client.get(
        "/v1/stylebooks/default/cleanup/checks/duplicate-organizations?limit=10"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    # Exact matches sort first ("City Hall"); the cross-form cluster follows.
    assert body["clusters"][0]["label"] == "City Hall"
    assert len(body["clusters"][0]["canonicals"]) == 2
    cross_form_labels = {
        canonical["label"] for canonical in body["clusters"][1]["canonicals"]
    }
    assert cross_form_labels == {
        "Cook County State's Attorney's Office",
        "Office of the Cook County State's Attorney",
    }


def test_dismiss_duplicate_organization_cluster(
    cleanup_client: tuple[TestClient, Engine],
) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        orgs = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.slug.in_(  # type: ignore[union-attr]
                    ["org-crossform-a", "org-crossform-b"]
                )
            )
        ).all()
        member_ids = sorted(str(row.id) for row in orgs if row.id is not None)
    assert len(member_ids) == 2

    _run_cleanup_check(client, "duplicate-organizations")

    before = client.get(
        "/v1/stylebooks/default/cleanup/checks/duplicate-organizations?limit=10"
    )
    assert before.status_code == 200
    assert before.json()["total"] == 2

    dismiss = client.post(
        "/v1/stylebooks/default/cleanup/dismissals",
        json={
            "check_id": "duplicate-organizations",
            "member_ids": member_ids,
        },
    )
    assert dismiss.status_code == 200
    assert dismiss.json()["dismissed_pair_count"] == 1

    after = client.get(
        "/v1/stylebooks/default/cleanup/checks/duplicate-organizations?limit=10"
    )
    assert after.status_code == 200
    assert after.json()["total"] == 1
    labels = {
        canonical["label"]
        for cluster in after.json()["clusters"]
        for canonical in cluster["canonicals"]
    }
    assert "Cook County State's Attorney's Office" not in labels

    checks = client.get("/v1/stylebooks/default/cleanup/checks")
    assert checks.status_code == 200
    by_id = {check["id"]: check["count"] for check in checks.json()["checks"]}
    assert by_id["duplicate-organizations"] == after.json()["total"]


def test_merge_cleanup_person_relinks_and_deletes_source(
    cleanup_client: tuple[TestClient, Engine],
) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        session.add(
            BackfieldProject(
                organization_id=int(org.id),
                name="Demo",
                slug="demo-proj",
            )
        )
        session.commit()
        proj = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")
        ).one()
        source = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.slug == "person-dupe-a"
            )
        ).one()
        target = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.slug == "person-dupe-b"
            )
        ).one()
        session.add(
            SubstratePerson(
                project_id=int(proj.id),
                name="Jane Doe",
                normalized_name="jane-doe",
                identity_fingerprint="fp-cleanup-person-merge",
                stylebook_person_canonical_id=str(source.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()
        source_id = str(source.id)
        target_id = str(target.id)

    response = client.post(
        f"/v1/stylebooks/default/cleanup/canonical-people/{source_id}/merge-into",
        json={"target_canonical_id": target_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["relinked_substrate_count"] == 1

    with Session(engine) as session:
        assert session.get(StylebookPersonCanonical, source_id) is None
        person = session.exec(
            select(SubstratePerson).where(
                SubstratePerson.identity_fingerprint == "fp-cleanup-person-merge"
            )
        ).one()
        assert person.stylebook_person_canonical_id == target_id


def test_merge_cleanup_organization_relinks_and_deletes_source(
    cleanup_client: tuple[TestClient, Engine],
) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        session.add(
            BackfieldProject(
                organization_id=int(org.id),
                name="Demo",
                slug="demo-proj-org",
            )
        )
        session.commit()
        proj = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "demo-proj-org")
        ).one()
        source = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.slug == "org-dupe-a"
            )
        ).one()
        target = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.slug == "org-dupe-b"
            )
        ).one()
        session.add(
            SubstrateOrganization(
                project_id=int(proj.id),
                name="City Hall",
                normalized_name="city-hall",
                identity_fingerprint="fp-cleanup-org-merge",
                stylebook_organization_canonical_id=str(source.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()
        source_id = str(source.id)
        target_id = str(target.id)

    response = client.post(
        f"/v1/stylebooks/default/cleanup/canonical-organizations/{source_id}/merge-into",
        json={"target_canonical_id": target_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["relinked_substrate_count"] == 1

    with Session(engine) as session:
        assert session.get(StylebookOrganizationCanonical, source_id) is None
        organization = session.exec(
            select(SubstrateOrganization).where(
                SubstrateOrganization.identity_fingerprint == "fp-cleanup-org-merge"
            )
        ).one()
        assert organization.stylebook_organization_canonical_id == target_id


def test_distant_linked_geography_issue(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        session.add(
            BackfieldProject(
                organization_id=int(org.id),
                name="Geo Demo",
                slug="geo-demo",
            )
        )
        session.commit()
        proj = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "geo-demo")
        ).one()
        canon = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.slug == "has-geom"
            )
        ).one()
        session.add(
            SubstrateLocation(
                project_id=int(proj.id),
                name="Far linked place",
                normalized_name="far-linked",
                location_type="place",
                identity_fingerprint="fp-distant-geo",
                stylebook_location_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
                geometry_json={"type": "Point", "coordinates": [-97.45, 31.05]},
            )
        )
        session.commit()

    _run_cleanup_check(client, "missing-geometry-locations")

    response = client.get("/v1/stylebooks/default/cleanup/checks/missing-geometry-locations")
    assert response.status_code == 200
    body = response.json()
    distant = [
        item
        for item in body["canonicals"]
        if item.get("geography_issue") == "distant_linked_places"
    ]
    assert len(distant) >= 1
    mapped = next(item for item in distant if item["label"] == "Mapped place")
    assert mapped["distant_linked_count"] >= 1


def test_dismiss_duplicate_location_cluster(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        locs = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.slug.in_(["dupe-a", "dupe-b"])
            )
        ).all()
        member_ids = sorted(str(row.id) for row in locs if row.id is not None)

    _run_cleanup_check(client, "duplicate-locations")

    before = client.get("/v1/stylebooks/default/cleanup/checks/duplicate-locations?limit=10")
    assert before.status_code == 200
    assert before.json()["total"] >= 1

    dismiss = client.post(
        "/v1/stylebooks/default/cleanup/dismissals",
        json={
            "check_id": "duplicate-locations",
            "member_ids": member_ids,
        },
    )
    assert dismiss.status_code == 200
    assert dismiss.json()["dismissed_pair_count"] == 1

    after = client.get("/v1/stylebooks/default/cleanup/checks/duplicate-locations?limit=10")
    assert after.status_code == 200
    labels = {cluster["label"] for cluster in after.json()["clusters"]}
    assert "Ward 36, Chicago, IL" not in labels

    checks = client.get("/v1/stylebooks/default/cleanup/checks")
    assert checks.status_code == 200
    by_id = {check["id"]: check["count"] for check in checks.json()["checks"]}
    assert by_id["duplicate-locations"] == after.json()["total"]


def test_dismiss_missing_geometry_location(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        missing = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.slug == "missing-geom"
            )
        ).one()
        canonical_id = str(missing.id)

    _run_cleanup_check(client, "missing-geometry-locations")

    before = client.get("/v1/stylebooks/default/cleanup/checks/missing-geometry-locations")
    assert before.status_code == 200
    before_total = before.json()["total"]

    dismiss = client.post(
        "/v1/stylebooks/default/cleanup/dismissals",
        json={
            "check_id": "missing-geometry-locations",
            "canonical_id": canonical_id,
        },
    )
    assert dismiss.status_code == 200
    assert dismiss.json()["dismissed_canonical_id"] == canonical_id

    after = client.get("/v1/stylebooks/default/cleanup/checks/missing-geometry-locations")
    assert after.status_code == 200
    assert after.json()["total"] == before_total - 1
    labels = {item["label"] for item in after.json()["canonicals"]}
    assert "No map pin here" not in labels


def test_mismatched_people_check(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(select(BackfieldOrganization)).one()
        sb = session.exec(select(Stylebook)).one()
        project = BackfieldProject(organization_id=int(org.id), name="Demo", slug="demo")
        session.add(project)
        session.commit()
        session.refresh(project)
        canon = StylebookPersonCanonical(
            stylebook_id=int(sb.id),
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
                identity_fingerprint="fp-mismatch-person",
                stylebook_person_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()

    _run_cleanup_check(client, "mismatched-people")

    checks = client.get("/v1/stylebooks/default/cleanup/checks")
    assert checks.status_code == 200
    by_id = {check["id"]: check["count"] for check in checks.json()["checks"]}
    assert by_id["mismatched-people"] == 1

    response = client.get("/v1/stylebooks/default/cleanup/checks/mismatched-people")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    row = body["canonicals"][0]
    assert row["label"] == "Jane Doe"
    assert row["mismatched_linked_count"] == 1
    assert "John Smith" in row["mismatched_examples"]


def test_dismiss_mismatched_person(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(select(BackfieldOrganization)).one()
        sb = session.exec(select(Stylebook)).one()
        project = BackfieldProject(organization_id=int(org.id), name="Demo", slug="demo")
        session.add(project)
        session.commit()
        session.refresh(project)
        canon = StylebookPersonCanonical(
            stylebook_id=int(sb.id),
            slug="jane-doe-dismiss",
            label="Jane Doe",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        canonical_id = str(canon.id)
        session.add(
            SubstratePerson(
                project_id=int(project.id),
                name="John Smith",
                normalized_name="john-smith",
                person_type="individual",
                identity_fingerprint="fp-mismatch-person-dismiss",
                stylebook_person_canonical_id=canonical_id,
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()

    _run_cleanup_check(client, "mismatched-people")

    before = client.get("/v1/stylebooks/default/cleanup/checks/mismatched-people")
    assert before.status_code == 200
    assert before.json()["total"] >= 1

    dismiss = client.post(
        "/v1/stylebooks/default/cleanup/dismissals",
        json={
            "check_id": "mismatched-people",
            "canonical_id": canonical_id,
        },
    )
    assert dismiss.status_code == 200

    after = client.get("/v1/stylebooks/default/cleanup/checks/mismatched-people")
    assert after.status_code == 200
    assert after.json()["total"] == before.json()["total"] - 1
    labels = {item["label"] for item in after.json()["canonicals"]}
    assert "Jane Doe" not in labels


def test_mismatched_organizations_check(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(select(BackfieldOrganization)).one()
        sb = session.exec(select(Stylebook)).one()
        project = BackfieldProject(organization_id=int(org.id), name="Demo", slug="demo-org")
        session.add(project)
        session.commit()
        session.refresh(project)
        canon = StylebookOrganizationCanonical(
            stylebook_id=int(sb.id),
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
                identity_fingerprint="fp-mismatch-org",
                stylebook_organization_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()

    _run_cleanup_check(client, "mismatched-organizations")

    checks = client.get("/v1/stylebooks/default/cleanup/checks")
    assert checks.status_code == 200
    by_id = {check["id"]: check["count"] for check in checks.json()["checks"]}
    assert by_id["mismatched-organizations"] == 1

    response = client.get("/v1/stylebooks/default/cleanup/checks/mismatched-organizations")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    row = body["canonicals"][0]
    assert row["label"] == "Globex Industries"
    assert row["mismatched_linked_count"] == 1
    assert "Acme Corporation" in row["mismatched_examples"]


def test_cleanup_ai_review_start_and_proposal_accept(
    cleanup_client: tuple[TestClient, Engine],
) -> None:
    client, engine = cleanup_client
    person_b_id = ""
    with Session(engine) as session:
        org = session.exec(select(BackfieldOrganization)).one()
        sb = session.exec(select(Stylebook)).one()
        session.add(
            BackfieldAiModelConfig(
                organization_id=int(org.id),
                name="Test GPT",
                provider="openai",
                provider_model_id="gpt-5-nano",
                model_kind="chat",
                status="active",
                capabilities_json=["text", "json"],
                litellm_model="gpt-5-nano",
            )
        )
        people = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.slug.in_(["person-dupe-a", "person-dupe-b"])
            )
        ).all()
        session.commit()
        person_a = next(row for row in people if row.slug == "person-dupe-a")
        person_b = next(row for row in people if row.slug == "person-dupe-b")
        person_a_id = str(person_a.id)
        person_b_id = str(person_b.id)
        review = StylebookCleanupAiReview(
            id="review-1",
            stylebook_id=int(sb.id),
            check_id="duplicate-people",
            status="succeeded",
            provider_model_id="gpt-5-nano",
            cluster_count=1,
            processed_cluster_count=1,
            proposal_count=1,
        )
        session.add(review)
        session.add(
            StylebookCleanupAiProposal(
                id="proposal-merge-1",
                review_id="review-1",
                stylebook_id=int(sb.id),
                check_id="duplicate-people",
                cluster_id=f"{person_a_id}:2",
                action="merge",
                target_canonical_id=person_a_id,
                member_ids_json=[person_a_id, person_b_id],
                confidence=0.95,
                rationale="Same person",
                status="pending",
            )
        )
        session.commit()

    models = client.get("/v1/stylebooks/default/cleanup/ai-models")
    assert models.status_code == 200
    assert len(models.json()["models"]) == 1

    start = client.post(
        "/v1/stylebooks/default/cleanup/ai-review",
        json={
            "check_id": "duplicate-people",
            "provider_model_id": "gpt-5-nano",
            "ai_model_config_id": models.json()["models"][0]["id"],
        },
    )
    assert start.status_code == 200
    assert start.json()["status"] == "queued"

    latest = client.get(
        "/v1/stylebooks/default/cleanup/ai-review/latest?check_id=duplicate-people"
    )
    assert latest.status_code == 200
    assert latest.json() is not None

    proposals = client.get("/v1/stylebooks/default/cleanup/ai-review/review-1/proposals")
    assert proposals.status_code == 200
    assert len(proposals.json()["proposals"]) == 1

    accept = client.post(
        "/v1/stylebooks/default/cleanup/ai-review/proposals/proposal-merge-1/accept"
    )
    assert accept.status_code == 200
    assert accept.json()["status"] == "applied"

    with Session(engine) as session:
        remaining = session.get(StylebookPersonCanonical, person_b_id)
        assert remaining is None

    reject = client.post(
        "/v1/stylebooks/default/cleanup/ai-review/proposals/proposal-merge-1/reject"
    )
    assert reject.status_code == 409
