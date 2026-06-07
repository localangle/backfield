"""Integration tests for Stylebook organization API (canonical list, candidates, CSV import)."""

from __future__ import annotations

from typing import Any

import pytest
from backfield_db import (
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    Stylebook,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
)
from backfield_entities.entities.organization.types import organization_identity_fingerprint
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from tests.stylebook_api.test_stylebook_api import _service_headers

pytest_plugins = ["tests.stylebook_api.test_stylebook_api"]


def _add_pending_organization(
    session: Session,
    *,
    project_id: int,
    name: str,
    normalized_name: str,
    organization_type: str | None = "company",
) -> int:
    organization = SubstrateOrganization(
        project_id=project_id,
        name=name,
        normalized_name=normalized_name,
        organization_type=organization_type,
        identity_fingerprint=organization_identity_fingerprint(
            normalized_name=normalized_name,
            organization_type=organization_type,
        ),
        stylebook_organization_canonical_id=None,
        canonical_link_status=CANONICAL_LINK_PENDING,
    )
    session.add(organization)
    session.commit()
    session.refresh(organization)
    return int(organization.id)  # type: ignore[arg-type]


def test_list_canonical_organizations_empty(editor_client: TestClient) -> None:
    r = editor_client.get(
        "/v1/stylebooks/default/canonical-organizations?limit=10&offset=0",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["canonicals"] == []
    assert body["total"] == 0


def test_list_canonical_organizations_token_search(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        s.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                label="City of Portland",
                slug="city-of-portland",
                organization_type="government",
                status="active",
            )
        )
        s.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                label="Unrelated Org",
                slug="unrelated-org",
                status="active",
            )
        )
        s.commit()

    r = editor_client.get(
        "/v1/stylebooks/default/canonical-organizations?q=Portland&limit=10",
    )
    assert r.status_code == 200
    labels = [row["label"] for row in r.json()["canonicals"]]
    assert "City of Portland" in labels


def test_create_canonical_organization(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    r = editor_client.post(
        "/v1/stylebooks/default/canonical-organizations",
        json={"label": "Acme Corp", "organization_type": "company"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Acme Corp"
    assert body["organization_type"] == "company"
    assert body["slug"]

    with Session(stylebook_test_engine) as s:
        rows = s.exec(select(StylebookOrganizationCanonical)).all()
        assert len(rows) == 1
        assert rows[0].label == "Acme Corp"


def test_list_canonical_organizations_stylebook_scoped(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        stylebook = s.get(Stylebook, sb_id)
        assert stylebook is not None
        s.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                label="Metro Transit",
                slug="metro-transit",
                organization_type="public_services",
                status="active",
            )
        )
        s.commit()
        slug = str(stylebook.slug)

    r = editor_client.get(
        f"/v1/stylebooks/{slug}/canonical-organizations?limit=10&offset=0",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["canonicals"][0]["label"] == "Metro Transit"


def test_organization_candidates_lists_unlinked_substrate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        _add_pending_organization(
            s,
            project_id=int(proj.id),
            name="City Hall",
            normalized_name="city hall",
        )

    r = client.get(
        "/v1/organizations/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["candidates"][0]["suggested_name"] == "City Hall"
    assert data["candidates"][0]["suggested_type"] == "company"


def test_borderline_organization_candidate_suggests_defer_not_create(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        oid = _add_pending_organization(
            s,
            project_id=int(proj.id),
            name="The Rube Goldberg Puzzle Book",
            normalized_name="the rube goldberg puzzle book",
            organization_type="media",
        )
        organization = s.get(SubstrateOrganization, oid)
        assert organization is not None
        organization.canonical_review_reasons_json = [
            {"code": "borderline_organization_boundary", "boundary": "work_title"},
            {
                "code": "canonical_suggestion",
                "source": "rules_plan",
                "suggested_action": "materialize_new",
            },
        ]
        s.add(organization)
        s.commit()

    r = client.get(
        "/v1/organizations/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    row = r.json()["candidates"][0]
    assert row["suggested_name"] == "The Rube Goldberg Puzzle Book"
    assert row["canonical_suggestion"]["suggested_action"] == "defer"
    assert row["canonical_suggestion"].get("stylebook_organization_canonical_id") is None


def test_get_substrate_organization_returns_linked_canonical_id(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    oid: int
    canon_id: str
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="City Hall",
            slug="city-hall",
            status="active",
        )
        s.add(canon)
        s.flush()
        canon_id = str(canon.id)
        oid = _add_pending_organization(
            s,
            project_id=int(proj.id),
            name="City Hall",
            normalized_name="city hall",
        )
        organization = s.get(SubstrateOrganization, oid)
        assert organization is not None
        organization.stylebook_organization_canonical_id = canon_id
        organization.canonical_link_status = CANONICAL_LINK_LINKED
        s.add(organization)
        s.commit()

    r = client.get(
        f"/v1/organizations/{oid}?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == oid
    assert body["stylebook_organization_canonical_id"] == canon_id


def test_accept_deferred_organization_candidate_create_new(
    client: TestClient,
    stylebook_test_engine: Engine,
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        sid = _add_pending_organization(
            s,
            project_id=int(proj.id),
            name="Deferred Org",
            normalized_name="deferred org",
        )

    r_def = client.post(
        f"/v1/organizations/candidates/{sid}/defer?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_def.status_code == 200

    r_accept = client.post(
        f"/v1/organizations/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "Deferred Org Canon", "organization_type": "nonprofit"},
    )
    assert r_accept.status_code == 200
    cid = r_accept.json()["stylebook_organization_canonical_id"]

    r_deferred = client.get(
        "/v1/organizations/candidates?project_slug=demo-proj&status=deferred",
        headers=_service_headers(),
    )
    assert r_deferred.status_code == 200
    assert r_deferred.json()["total"] == 0

    with Session(stylebook_test_engine) as s:
        organization = s.get(SubstrateOrganization, sid)
        assert organization is not None
        assert organization.canonical_link_status == CANONICAL_LINK_LINKED
        assert organization.stylebook_organization_canonical_id == cid


def test_accept_organization_candidate_create_new(
    client: TestClient,
    stylebook_test_engine: Engine,
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        sid = _add_pending_organization(
            s,
            project_id=int(proj.id),
            name="New Org",
            normalized_name="new org",
            organization_type="government",
        )

    r_accept = client.post(
        f"/v1/organizations/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "New Org Canon"},
    )
    assert r_accept.status_code == 200
    data = r_accept.json()
    assert data["message"] == "linked"
    cid = data["stylebook_organization_canonical_id"]

    r_open = client.get(
        "/v1/organizations/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r_open.status_code == 200
    assert r_open.json()["total"] == 0

    from stylebook_api.deps import get_auth as get_auth_dep
    from stylebook_api.main import app

    from tests.stylebook_api.test_stylebook_api import _session_auth_for_user

    with Session(stylebook_test_engine) as s:
        user = BackfieldUser(email="org-canon-list-reader@example.com", password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        reader_id = int(user.id)  # type: ignore[arg-type]

    def _reader_auth() -> dict[str, Any]:
        with Session(stylebook_test_engine) as s:
            u = s.get(BackfieldUser, reader_id)
            assert u is not None
            return _session_auth_for_user(u, org_id=1, org_role="org_admin")

    app.dependency_overrides[get_auth_dep] = _reader_auth
    try:
        r_canon = client.get("/v1/stylebooks/default/canonical-organizations")
        assert r_canon.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_dep, None)
    labels = [c["label"] for c in r_canon.json()["canonicals"]]
    assert "New Org Canon" in labels

    with Session(stylebook_test_engine) as s:
        row = s.get(SubstrateOrganization, sid)
        assert row is not None
        assert row.stylebook_organization_canonical_id == cid
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        canon = s.get(StylebookOrganizationCanonical, cid)
        assert canon is not None
        assert canon.label == "New Org Canon"
        assert canon.organization_type == "government"
        aliases = s.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == cid,
            )
        ).all()
        norm_aliases = {a.normalized_alias for a in aliases}
        assert "new org" in norm_aliases


def test_accept_organization_candidate_link_existing_canonical(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Existing Org",
            slug="existing-org",
            organization_type="company",
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)
        sid = _add_pending_organization(
            s,
            project_id=int(proj.id),
            name="Linkme Org",
            normalized_name="linkme org",
        )

    r = client.post(
        f"/v1/organizations/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": False, "stylebook_organization_canonical_id": cid},
    )
    assert r.status_code == 200
    assert r.json()["message"] == "linked"
    assert r.json()["stylebook_organization_canonical_id"] == cid

    with Session(stylebook_test_engine) as s:
        row = s.get(SubstrateOrganization, sid)
        assert row is not None
        assert row.stylebook_organization_canonical_id == cid
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        aliases = s.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == cid,
            )
        ).all()
        norm_aliases = {a.normalized_alias for a in aliases}
        assert "linkme org" in norm_aliases
        assert "existing org" in norm_aliases


def test_stylebook_scoped_csv_organizations_import_requires_editor(
    member_client: TestClient,
) -> None:
    r = member_client.post(
        "/v1/stylebooks/default/import/csv/organizations/analyze",
        json={"csv_data": "label\nCity Hall\n"},
    )
    assert r.status_code == 403


def test_import_csv_organizations_analyze_returns_columns(editor_client: TestClient) -> None:
    csv_data = "label,organization_type\nCity Hall,government\nAcme Corp,company\n"
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/organizations/analyze",
        json={"csv_data": csv_data},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 2
    assert body["available_columns"] == ["label", "organization_type"]
    assert body["sample_row"]["label"] == "City Hall"


def test_import_csv_organizations_analyze_rejects_malformed(editor_client: TestClient) -> None:
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/organizations/analyze",
        json={"csv_data": ""},
    )
    assert r.status_code == 400


def test_import_csv_organizations_creates_canonicals(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    csv_data = (
        "label,organization_type\n"
        "City Hall,government\n"
        "Acme Corp,company\n"
    )
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/organizations",
        json={
            "csv_data": csv_data,
            "field_mappings": {
                "label": "label",
                "organization_type": "organization_type",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 2
    assert body["created_count"] == 2
    assert body["failed_count"] == 0
    labels = {row["label"] for row in body["created"]}
    assert labels == {"City Hall", "Acme Corp"}

    with Session(stylebook_test_engine) as s:
        orgs = s.exec(select(StylebookOrganizationCanonical)).all()
        assert len(orgs) == 2
        city = next(o for o in orgs if o.label == "City Hall")
        assert city.organization_type == "government"
        substrates = s.exec(select(SubstrateOrganization)).all()
        assert substrates == []


def test_import_csv_organizations_partial_failure(
    editor_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stylebook_api.imports.csv_organizations as csv_orgs_mod

    original = csv_orgs_mod.create_standalone_canonical
    calls = {"n": 0}

    def _flaky_create(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("simulated row failure")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(csv_orgs_mod, "create_standalone_canonical", _flaky_create)

    csv_data = "label\nOrg One\nOrg Two\nOrg Three\n"
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/organizations",
        json={"csv_data": csv_data, "field_mappings": {"label": "label"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created_count"] == 2
    assert body["failed_count"] == 1
    assert len(body["failed"]) == 1
    assert body["failed"][0]["row_index"] == 1
