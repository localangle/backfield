"""Integration tests for Stylebook person API (canonical list, candidates, connections)."""

from __future__ import annotations

from backfield_db import (
    BackfieldProject,
    BackfieldWorkspace,
    StylebookConnection,
    StylebookLocationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    SubstratePerson,
)
from backfield_stylebook.canonical_link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
)
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from tests.stylebook_api.test_stylebook_api import _service_headers

pytest_plugins = ["tests.stylebook_api.test_stylebook_api"]


def _add_pending_person(
    session: Session,
    *,
    project_id: int,
    name: str,
    normalized_name: str,
    fingerprint: str,
    person_type: str | None = "individual",
    public_figure: bool = False,
    title: str | None = None,
    affiliation: str | None = None,
) -> int:
    person = SubstratePerson(
        project_id=project_id,
        name=name,
        normalized_name=normalized_name,
        person_type=person_type,
        public_figure=public_figure,
        title=title,
        affiliation=affiliation,
        identity_fingerprint=fingerprint,
        stylebook_person_canonical_id=None,
        canonical_link_status=CANONICAL_LINK_PENDING,
    )
    session.add(person)
    session.commit()
    session.refresh(person)
    return int(person.id)  # type: ignore[arg-type]


def test_list_canonical_people_empty(client: TestClient) -> None:
    r = client.get(
        "/v1/canonical-people?project_slug=demo-proj&limit=10&offset=0",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["canonicals"] == []
    assert body["total"] == 0


def test_person_candidates_lists_unlinked_substrate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        _add_pending_person(
            s,
            project_id=int(proj.id),
            name="Jane Doe",
            normalized_name="jane doe",
            fingerprint="fp-jane-open-1",
        )

    r = client.get(
        "/v1/people/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["candidates"][0]["suggested_name"] == "Jane Doe"


def test_canonical_people_filters_public_figure(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Public Figure",
                slug="public-figure",
                public_figure=True,
                status="active",
            )
        )
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Private Person",
                slug="private-person",
                public_figure=False,
                status="active",
            )
        )
        s.commit()

    r = client.get(
        "/v1/canonical-people?project_slug=demo-proj&public_figure=true",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["canonicals"][0]["label"] == "Public Figure"
    assert body["canonicals"][0]["public_figure"] is True


def test_accept_person_candidate_create_new(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        sid = _add_pending_person(
            s,
            project_id=int(proj.id),
            name="New Person",
            normalized_name="new person",
            fingerprint="fp-new-person-1",
            title="Mayor",
            affiliation="City Hall",
        )

    r_accept = client.post(
        f"/v1/people/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "New Person Canon"},
    )
    assert r_accept.status_code == 200
    data = r_accept.json()
    assert data["message"] == "linked"
    cid = data["stylebook_person_canonical_id"]

    r_open = client.get(
        "/v1/people/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r_open.status_code == 200
    assert r_open.json()["total"] == 0

    r_canon = client.get(
        "/v1/canonical-people?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_canon.status_code == 200
    labels = [c["label"] for c in r_canon.json()["canonicals"]]
    assert "New Person Canon" in labels

    with Session(stylebook_test_engine) as s:
        row = s.get(SubstratePerson, sid)
        assert row is not None
        assert row.stylebook_person_canonical_id == cid
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        canon = s.get(StylebookPersonCanonical, cid)
        assert canon is not None
        assert canon.label == "New Person Canon"
        assert canon.title == "Mayor"
        assert canon.affiliation == "City Hall"
        aliases = s.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == cid,
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "new person"


def test_accept_person_candidate_link_existing_canonical(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Existing Person",
            slug="existing-person",
            title="Senator",
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)
        sid = _add_pending_person(
            s,
            project_id=int(proj.id),
            name="Linkme Person",
            normalized_name="linkme person",
            fingerprint="fp-link-person-1",
        )

    r = client.post(
        f"/v1/people/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": False, "stylebook_person_canonical_id": cid},
    )
    assert r.status_code == 200
    assert r.json()["message"] == "linked"
    assert r.json()["stylebook_person_canonical_id"] == cid

    with Session(stylebook_test_engine) as s:
        row = s.get(SubstratePerson, sid)
        assert row is not None
        assert row.stylebook_person_canonical_id == cid
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        aliases = s.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == cid,
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "linkme person"


def test_location_person_connection_roundtrip(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        loc = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Conn City",
            slug="conn-city",
            location_type="city",
            status="active",
        )
        person = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Conn Person",
            slug="conn-person",
            status="active",
        )
        s.add(loc)
        s.add(person)
        s.commit()
        s.refresh(loc)
        s.refresh(person)
        loc_id = str(loc.id)
        person_id = str(person.id)

    r0 = client.get(
        f"/v1/canonical-locations/{loc_id}/connections?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r0.status_code == 200
    assert r0.json()["connections"] == []

    r1 = client.post(
        f"/v1/canonical-locations/{loc_id}/connections?project_slug=demo-proj",
        headers=_service_headers(),
        json={"to_entity_type": "person", "to_entity_id": person_id, "nature": "lives_in"},
    )
    assert r1.status_code == 200
    body = r1.json()
    assert body["to_entity_type"] == "person"
    assert body["to_entity_id"] == person_id
    assert body["to_display_name"] == "Conn Person"
    conn_id = int(body["id"])

    r2 = client.get(
        f"/v1/canonical-locations/{loc_id}/connections?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert len(r2.json()["connections"]) == 1
    assert r2.json()["connections"][0]["to_display_name"] == "Conn Person"

    r3 = client.patch(
        f"/v1/canonical-locations/{loc_id}/connections/{conn_id}?project_slug=demo-proj",
        headers=_service_headers(),
        json={"nature": "works_in"},
    )
    assert r3.status_code == 200
    assert r3.json()["nature"] == "works_in"

    r4 = client.delete(
        f"/v1/canonical-locations/{loc_id}/connections/{conn_id}?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r4.status_code == 200

    with Session(stylebook_test_engine) as s:
        row = s.get(StylebookConnection, conn_id)
        assert row is None
