"""Integration tests for Stylebook person API (canonical list, candidates, connections)."""

from __future__ import annotations

from typing import Any

import pytest
from backfield_db import (
    BackfieldAiModelConfig,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldUser,
    BackfieldWorkspace,
    Stylebook,
    StylebookCandidateAiReview,
    StylebookConnection,
    StylebookLocationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.canonical.link import (
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


def test_list_canonical_people_empty(
    editor_client: TestClient) -> None:
    r = editor_client.get(
        "/v1/stylebooks/default/canonical-people?limit=10&offset=0",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["canonicals"] == []
    assert body["total"] == 0


def test_list_canonical_people_orders_by_sort_key_then_label(
    editor_client: TestClient,
) -> None:
    for label in ("Bob Smith", "Alice Smith", "Carol Adams"):
        r = editor_client.post(
            "/v1/stylebooks/default/canonical-people",
            json={"label": label},
        )
        assert r.status_code == 200

    r = editor_client.get(
        "/v1/stylebooks/default/canonical-people?limit=50",
    )
    assert r.status_code == 200
    labels = [row["label"] for row in r.json()["canonicals"]]
    assert labels == ["Carol Adams", "Alice Smith", "Bob Smith"]


def test_list_canonical_people_token_search_ronald_finds_ron_wyden(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Ron Wyden",
                slug="ron-wyden",
                status="active",
            )
        )
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Unrelated Person",
                slug="unrelated-person",
                status="active",
            )
        )
        s.commit()

    r = editor_client.get(
        "/v1/stylebooks/default/canonical-people?q=Wyden&limit=10",
    )
    assert r.status_code == 200
    labels = [row["label"] for row in r.json()["canonicals"]]
    assert "Ron Wyden" in labels


def test_stylebook_canonical_people_min_mentions(editor_client: TestClient) -> None:
    r = editor_client.get("/v1/stylebooks/default/canonical-people?min_mentions=1")
    assert r.status_code == 200
    assert r.json().get("canonicals") == []


def test_list_canonical_people_stylebook_scoped(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        stylebook = s.get(Stylebook, sb_id)
        assert stylebook is not None
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Governor Example",
                slug="governor-example",
                status="active",
            )
        )
        s.commit()
        slug = str(stylebook.slug)

    r = editor_client.get(
        f"/v1/stylebooks/{slug}/canonical-people?limit=10&offset=0",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["canonicals"][0]["label"] == "Governor Example"


def test_stylebook_canonical_people_title_filter(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        stylebook = s.get(Stylebook, sb_id)
        assert stylebook is not None
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Jane Doe",
                slug="jane-doe",
                title="Mayor",
                status="active",
            )
        )
        s.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="John Smith",
                slug="john-smith",
                title="CEO",
                status="active",
            )
        )
        s.commit()
        slug = str(stylebook.slug)

    r = editor_client.get(
        f"/v1/stylebooks/{slug}/canonical-people?title_filter=Mayor",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [row["label"] for row in body["canonicals"]] == ["Jane Doe"]


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


def test_get_substrate_person_returns_linked_canonical_id(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    pid: int
    canon_id: str
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="jane-doe",
            status="active",
        )
        s.add(canon)
        s.flush()
        canon_id = str(canon.id)
        pid = _add_pending_person(
            s,
            project_id=int(proj.id),
            name="Jane Doe",
            normalized_name="jane doe",
            fingerprint="fp-jane-get-1",
        )
        person = s.get(SubstratePerson, pid)
        assert person is not None
        person.stylebook_person_canonical_id = canon_id
        person.canonical_link_status = CANONICAL_LINK_LINKED
        s.add(person)
        s.commit()

    r = client.get(
        f"/v1/people/{pid}?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pid
    assert body["stylebook_person_canonical_id"] == canon_id


def test_canonical_people_filters_public_figure(
    editor_client: TestClient, stylebook_test_engine: Engine
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

    r = editor_client.get(
        "/v1/stylebooks/default/canonical-people?public_figure=true",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["canonicals"][0]["label"] == "Public Figure"
    assert body["canonicals"][0]["public_figure"] is True


def test_accept_deferred_person_candidate_create_new(
    client: TestClient,
    stylebook_test_engine: Engine,
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        sid = _add_pending_person(
            s,
            project_id=int(proj.id),
            name="Deferred Person",
            normalized_name="deferred person",
            fingerprint="fp-deferred-person-1",
        )

    r_def = client.post(
        f"/v1/people/candidates/{sid}/defer?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_def.status_code == 200

    r_suggest = client.get(
        f"/v1/people/candidates/{sid}/suggested-canonicals?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_suggest.status_code == 200

    r_accept = client.post(
        f"/v1/people/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "Deferred Person Canon"},
    )
    assert r_accept.status_code == 200
    cid = r_accept.json()["stylebook_person_canonical_id"]

    r_deferred = client.get(
        "/v1/people/candidates?project_slug=demo-proj&status=deferred",
        headers=_service_headers(),
    )
    assert r_deferred.status_code == 200
    assert r_deferred.json()["total"] == 0

    with Session(stylebook_test_engine) as s:
        person = s.get(SubstratePerson, sid)
        assert person is not None
        assert person.canonical_link_status == CANONICAL_LINK_LINKED
        assert person.stylebook_person_canonical_id == cid


def test_accept_person_candidate_create_new(
    client: TestClient,
    stylebook_test_engine: Engine,
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

    from stylebook_api.deps import get_auth as get_auth_dep
    from stylebook_api.main import app

    from tests.stylebook_api.test_stylebook_api import _session_auth_for_user

    with Session(stylebook_test_engine) as s:
        user = BackfieldUser(email="canon-list-reader@example.com", password_hash="x")
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
        r_canon = client.get("/v1/stylebooks/default/canonical-people")
        assert r_canon.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_dep, None)
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
    editor_client: TestClient, stylebook_test_engine: Engine
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

    r0 = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations/{loc_id}/connections",
    )
    assert r0.status_code == 200
    assert r0.json()["connections"] == []

    r1 = editor_client.post(
        f"/v1/stylebooks/default/canonical-locations/{loc_id}/connections",
        json={"to_entity_type": "person", "to_entity_id": person_id, "nature": "lives_in"},
    )
    assert r1.status_code == 200
    body = r1.json()
    assert body["to_entity_type"] == "person"
    assert body["to_entity_id"] == person_id
    assert body["to_display_name"] == "Conn Person"
    conn_id = int(body["id"])

    r2 = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations/{loc_id}/connections",
    )
    assert len(r2.json()["connections"]) == 1
    assert r2.json()["connections"][0]["to_display_name"] == "Conn Person"

    r3 = editor_client.patch(
        f"/v1/stylebooks/default/canonical-locations/{loc_id}/connections/{conn_id}",
        json={"nature": "works_in"},
    )
    assert r3.status_code == 200
    assert r3.json()["nature"] == "works_in"

    r4 = editor_client.delete(
        f"/v1/stylebooks/default/canonical-locations/{loc_id}/connections/{conn_id}",
    )
    assert r4.status_code == 200

    with Session(stylebook_test_engine) as s:
        row = s.get(StylebookConnection, conn_id)
        assert row is None


def test_canonical_person_mentions_and_stylebook_meta(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        stylebook = s.get(Stylebook, sb_id)
        assert stylebook is not None
        slug = str(stylebook.slug)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Mentioned Person",
            slug="mentioned-person",
            status="active",
        )
        s.add(canon)
        art = SubstrateArticle(
            project_id=int(proj.id),
            headline="City council vote",
            text="Mayor Jane Doe spoke at the meeting.",
            url="https://example.com/council",
            deleted=False,
        )
        s.add(art)
        s.commit()
        s.refresh(canon)
        s.refresh(art)
        cid = str(canon.id)
        aid = int(art.id)  # type: ignore[arg-type]
        person = SubstratePerson(
            project_id=int(proj.id),
            name="Jane Doe",
            normalized_name="jane doe",
            identity_fingerprint="fp-mention-person-1",
            stylebook_person_canonical_id=cid,
            canonical_link_status=CANONICAL_LINK_LINKED,
            status="active",
        )
        s.add(person)
        s.commit()
        s.refresh(person)
        pid = int(person.id)  # type: ignore[arg-type]
        mention = SubstratePersonMention(
            article_id=aid,
            person_id=pid,
            nature="official",
            role_in_story="Spoke at meeting",
            deleted=False,
        )
        s.add(mention)
        s.commit()
        s.refresh(mention)
        mid = int(mention.id)  # type: ignore[arg-type]
        s.add(
            SubstratePersonMentionOccurrence(
                person_mention_id=mid,
                mention_text="Mayor Jane Doe",
                quote_text="Mayor Jane Doe spoke",
                start_char=0,
                end_char=15,
            )
        )
        s.add(
            StylebookPersonMeta(
                project_id=int(proj.id),
                stylebook_person_canonical_id=cid,
                meta_type="note",
                data_json={"source": "test"},
            )
        )
        s.commit()

        editor = s.exec(
            select(BackfieldUser).where(BackfieldUser.email == "editor@example.com")
        ).one()
        s.add(
            BackfieldProjectMembership(
                project_id=int(proj.id),
                user_id=int(editor.id),  # type: ignore[arg-type]
                role="editor",
            )
        )
        s.commit()

    r_mentions = editor_client.get(
        f"/v1/stylebooks/{slug}/canonical-people/{cid}/mentions?project=demo-proj",
    )
    assert r_mentions.status_code == 200
    body = r_mentions.json()
    assert body["canonical_person_id"] == cid
    assert body["total"] == 1
    assert len(body["mentions"]) == 1
    row = body["mentions"][0]
    assert row["substrate_person_id"] == pid
    assert row["mention_nature"] == "official"
    assert row["description"] == "Spoke at meeting"
    assert row["original_text"] == "Mayor Jane Doe"

    r_meta = editor_client.get(
        f"/v1/stylebooks/{slug}/canonical-people/{cid}/meta",
    )
    assert r_meta.status_code == 200
    assert r_meta.json()["count"] == 1
    assert r_meta.json()["meta"][0]["meta_type"] == "note"


def test_stylebook_scoped_csv_people_import_requires_editor(member_client: TestClient) -> None:
    r = member_client.post(
        "/v1/stylebooks/default/import/csv/people/analyze",
        json={"csv_data": "label\nJane Doe\n"},
    )
    assert r.status_code == 403


def test_import_csv_people_analyze_returns_columns(editor_client: TestClient) -> None:
    csv_data = "full_name,title,affiliation\nJane Doe,Mayor,City Hall\nJohn Smith,CEO,Acme\n"
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/people/analyze",
        json={"csv_data": csv_data},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 2
    assert body["available_columns"] == ["affiliation", "full_name", "title"]
    assert body["sample_row"]["full_name"] == "Jane Doe"


def test_import_csv_people_analyze_rejects_malformed(editor_client: TestClient) -> None:
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/people/analyze",
        json={"csv_data": ""},
    )
    assert r.status_code == 400


def test_import_csv_people_creates_canonicals(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    csv_data = (
        "full_name,title,affiliation,public_figure,person_type,sort_key\n"
        "Jane Doe,Mayor,City Hall,true,official,doe\n"
        "John Smith,CEO,Acme Corp,false,individual,smith\n"
    )
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/people",
        json={
            "csv_data": csv_data,
            "field_mappings": {
                "full_name": "full_name",
                "title": "title",
                "affiliation": "affiliation",
                "public_figure": "public_figure",
                "person_type": "person_type",
                "sort_key": "sort_key",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 2
    assert body["created_count"] == 2
    assert body["failed_count"] == 0
    labels = {row["label"] for row in body["created"]}
    assert labels == {"Jane Doe", "John Smith"}

    with Session(stylebook_test_engine) as s:
        people = s.exec(select(StylebookPersonCanonical)).all()
        assert len(people) == 2
        jane = next(p for p in people if p.label == "Jane Doe")
        assert jane.title == "Mayor"
        assert jane.affiliation == "City Hall"
        assert jane.public_figure is True
        assert jane.person_type == "official"
        assert jane.sort_key == "doe"
        substrates = s.exec(select(SubstratePerson)).all()
        assert substrates == []


def test_import_csv_people_partial_failure(
    editor_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stylebook_api.imports.csv_people as csv_people_mod

    original = csv_people_mod.create_standalone_canonical
    calls = {"n": 0}

    def _flaky_create(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("simulated row failure")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(csv_people_mod, "create_standalone_canonical", _flaky_create)

    csv_data = "full_name\nAlice One\nBob Two\nCarol Three\n"
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/people",
        json={"csv_data": csv_data, "field_mappings": {"full_name": "full_name"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created_count"] == 2
    assert body["failed_count"] == 1
    assert len(body["failed"]) == 1
    assert body["failed"][0]["row_index"] == 1


def test_import_csv_people_duplicate_labels_create_two(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    csv_data = "full_name\nJane Doe\nJane Doe\n"
    r = editor_client.post(
        "/v1/stylebooks/default/import/csv/people",
        json={"csv_data": csv_data, "field_mappings": {"full_name": "full_name"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created_count"] == 2
    ids = {row["canonical_id"] for row in body["created"]}
    assert len(ids) == 2

    with Session(stylebook_test_engine) as s:
        people = s.exec(
            select(StylebookPersonCanonical).where(StylebookPersonCanonical.label == "Jane Doe")
        ).all()
        assert len(people) == 2
        slugs = {p.slug for p in people}
        assert len(slugs) == 2


def test_candidate_ai_review_start(
    editor_client: TestClient,
    stylebook_test_engine: Engine,
) -> None:
    with Session(stylebook_test_engine) as s:
        org = s.exec(select(BackfieldOrganization)).one()
        s.add(
            BackfieldAiModelConfig(
                organization_id=int(org.id),
                name="Candidate review model",
                provider="openai",
                provider_model_id="gpt-5-nano",
                model_kind="chat",
                status="active",
                capabilities_json=["text", "json"],
                litellm_model="gpt-5-nano",
            )
        )
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        editor = s.exec(
            select(BackfieldUser).where(BackfieldUser.email == "editor@example.com")
        ).one()
        s.add(
            BackfieldProjectMembership(
                project_id=int(proj.id),
                user_id=int(editor.id),  # type: ignore[arg-type]
                role="editor",
            )
        )
        s.commit()

    models = editor_client.get("/v1/stylebooks/default/candidates/ai-models")
    assert models.status_code == 200
    assert len(models.json()["models"]) == 1

    with pytest.MonkeyPatch.context() as mp:
        sent: list[str] = []
        mp.setattr(
            "stylebook_api.routers.stylebook_candidate_ai_review.celery_app.send_task",
            lambda name, args, queue: sent.append(str(args[0])),
        )
        start = editor_client.post(
            "/v1/stylebooks/default/candidates/ai-review",
            json={
                "entity_type": "person",
                "project_slug": "demo-proj",
                "provider_model_id": "gpt-5-nano",
                "ai_model_config_id": models.json()["models"][0]["id"],
            },
        )
    assert start.status_code == 200
    body = start.json()
    assert body["status"] == "queued"
    assert body["entity_type"] == "person"
    assert sent == [body["id"]]

    latest = editor_client.get(
        "/v1/stylebooks/default/candidates/ai-review/latest"
        "?entity_type=person&project_slug=demo-proj"
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    with Session(stylebook_test_engine) as s:
        review = s.get(StylebookCandidateAiReview, body["id"])
        assert review is not None
        review.status = "running"
        s.add(review)
        s.commit()

    cancel = editor_client.post(
        f"/v1/stylebooks/default/candidates/ai-review/{body['id']}/cancel",
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    cancel_again = editor_client.post(
        f"/v1/stylebooks/default/candidates/ai-review/{body['id']}/cancel",
    )
    assert cancel_again.status_code == 400
