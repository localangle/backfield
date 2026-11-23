"""Candidate queue list, count, kinds, and per-candidate evidence."""

from __future__ import annotations

from datetime import date

from backfield_entities.canonical.link import CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED

from tests.core_api.cleanup_fixtures import (
    CLEANUP_BASE,
    CleanupWorld,
    create_cleanup_key,
    seed_article,
    seed_entity,
    seed_mention,
    seed_substrate,
)

QUEUE_URL = f"{CLEANUP_BASE}/candidates/locations"


def _candidate(
    session,
    world: CleanupWorld,
    name: str,
    *,
    project_id: int | None = None,
    status: str = CANONICAL_LINK_PENDING,
    kind: str | None = "city",
    reasons: list[dict] | None = None,
    entity: str = "locations",
) -> int:
    return seed_substrate(
        session,
        entity,  # type: ignore[arg-type]
        canonical_id=None,
        project_id=project_id or world.project_id,
        name=name,
        kind=kind,
        link_status=status,
        review_reasons=reasons,
    )


def test_queue_lists_open_candidates_in_name_order(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    _candidate(cleanup_session, cleanup_world, "Zebra Falls")
    _candidate(cleanup_session, cleanup_world, "Alder Creek", kind="river")
    _candidate(cleanup_session, cleanup_world, "Parked", status=CANONICAL_LINK_WAIVED)

    body = cleanup_client.get(QUEUE_URL, headers=headers).json()

    assert body["queue_scope"] == "project"
    assert body["total"] == 2
    assert [i["name"] for i in body["items"]] == ["Alder Creek", "Zebra Falls"]
    assert body["items"][0]["kind"] == "river"
    assert body["items"][0]["project_slug"] == "general"
    assert body["items"][0]["status"] == "open"

    deferred = cleanup_client.get(QUEUE_URL, headers=headers, params={"status": "deferred"}).json()
    assert [i["name"] for i in deferred["items"]] == ["Parked"]
    assert deferred["items"][0]["status"] == "deferred"


def test_queue_filters_and_paging(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    for name in ("Alpha Bay", "Bravo Bay", "Charlie Hill"):
        _candidate(cleanup_session, cleanup_world, name, kind="hill" if "Hill" in name else "bay")

    searched = cleanup_client.get(QUEUE_URL, headers=headers, params={"q": "bay"}).json()
    assert [i["name"] for i in searched["items"]] == ["Alpha Bay", "Bravo Bay"]

    by_kind = cleanup_client.get(QUEUE_URL, headers=headers, params={"kind": "hill"}).json()
    assert [i["name"] for i in by_kind["items"]] == ["Charlie Hill"]

    first = cleanup_client.get(QUEUE_URL, headers=headers, params={"limit": 2}).json()
    assert len(first["items"]) == 2
    second = cleanup_client.get(
        QUEUE_URL, headers=headers, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [i["name"] for i in second["items"]] == ["Charlie Hill"]
    assert second["next_cursor"] is None

    bad = cleanup_client.get(QUEUE_URL, headers=headers, params={"cursor": "zzz"})
    assert bad.status_code == 400


def test_queue_date_filter_and_needs_review(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    old = _candidate(cleanup_session, cleanup_world, "Old Place")
    new = _candidate(cleanup_session, cleanup_world, "New Place")
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=old,
        mention_text="Old Place",
        article_id=seed_article(
            cleanup_session,
            project_id=cleanup_world.project_id,
            headline="o",
            pub_date=date(2023, 1, 1),
        ),
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=new,
        mention_text="New Place",
        article_id=seed_article(
            cleanup_session,
            project_id=cleanup_world.project_id,
            headline="n",
            pub_date=date(2024, 6, 1),
        ),
    )

    ranged = cleanup_client.get(
        QUEUE_URL, headers=headers, params={"mentioned_from": "2024-01-01"}
    ).json()
    assert [i["name"] for i in ranged["items"]] == ["New Place"]

    flagged = cleanup_client.get(QUEUE_URL, headers=headers, params={"needs_review": True}).json()
    assert flagged["items"] == []


def test_queue_exposes_ingest_recommendation(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    target = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield",
    )
    _candidate(
        cleanup_session,
        cleanup_world,
        "Springfld",
        reasons=[
            {"code": "review_note", "note": "check the spelling"},
            {
                "code": "canonical_suggestion",
                "suggested_action": "link_existing",
                "stylebook_location_canonical_id": target.canonical_id,
                "source": "rules",
            },
            {
                "code": "canonical_adjudication",
                "confidence": 0.9,
                "rationale": "same place",
                "model": "m",
                "outcome": "link_existing",
            },
        ],
    )

    [item] = cleanup_client.get(QUEUE_URL, headers=headers).json()["items"]

    assert item["note"] == "check the spelling"
    assert item["recommendation"]["suggested_action"] == "link_existing"
    assert item["recommendation"]["canonical_id"] == target.canonical_id
    assert item["recommendation"]["adjudication_confidence"] == 0.9
    assert len(item["review_reasons"]) == 3


def test_queue_is_project_scoped_unless_service_key_asks_for_the_stylebook(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    user_headers = create_cleanup_key(cleanup_client)
    _candidate(cleanup_session, cleanup_world, "Mine")
    _candidate(cleanup_session, cleanup_world, "Theirs", project_id=cleanup_world.second_project_id)

    own = cleanup_client.get(QUEUE_URL, headers=user_headers).json()
    assert [i["name"] for i in own["items"]] == ["Mine"]
    denied = cleanup_client.get(QUEUE_URL, headers=user_headers, params={"scope": "stylebook"})
    assert denied.status_code == 403

    service_headers = create_cleanup_key(
        cleanup_client, credential_type="service", scopes=["cleanup:read"]
    )
    wide = cleanup_client.get(QUEUE_URL, headers=service_headers, params={"scope": "stylebook"})
    assert wide.status_code == 200, wide.text
    assert [i["name"] for i in wide.json()["items"]] == ["Mine", "Theirs"]
    counts = cleanup_client.get(
        f"{QUEUE_URL}/count", headers=service_headers, params={"scope": "stylebook"}
    ).json()
    assert counts["total"] == 2
    assert {p["project_slug"]: p["count"] for p in counts["projects"]} == {
        "general": 1,
        "second": 1,
    }


def test_count_for_own_project(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    _candidate(cleanup_session, cleanup_world, "One")
    _candidate(cleanup_session, cleanup_world, "Two")

    body = cleanup_client.get(f"{QUEUE_URL}/count", headers=headers).json()

    assert body == {
        "total": 2,
        "projects": [{"project_slug": "general", "project_name": "General", "count": 2}],
    }


def test_types_use_the_place_taxonomy_for_locations_and_the_queue_otherwise(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    _candidate(cleanup_session, cleanup_world, "Ada", kind="elected", entity="people")

    places = cleanup_client.get(f"{QUEUE_URL}/types", headers=headers).json()["types"]
    people = cleanup_client.get(f"{CLEANUP_BASE}/candidates/people/types", headers=headers).json()[
        "types"
    ]

    assert "city" in places
    assert people == ["elected"]


def test_candidate_evidence_has_snippets_and_ranked_matches(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield",
        kind="city",
        aliases=("springfld",),
    )
    candidate = _candidate(cleanup_session, cleanup_world, "Springfld")
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=candidate,
        mention_text="Springfld",
        article_id=seed_article(
            cleanup_session,
            project_id=cleanup_world.project_id,
            headline="Meeting",
            text="They met in Springfld on Monday.",
            pub_date=date(2024, 3, 1),
        ),
    )

    r = cleanup_client.get(f"{QUEUE_URL}/{candidate}/evidence", headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidate"]["name"] == "Springfld"
    assert body["snippets"][0]["headline"] == "Meeting"
    assert "Springfld" in body["snippets"][0]["snippet"]
    assert [m["label"] for m in body["matches"]][:1] == ["Springfield"]


def test_candidate_evidence_404s_for_other_projects_and_linked_records(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    elsewhere = _candidate(
        cleanup_session, cleanup_world, "Elsewhere", project_id=cleanup_world.second_project_id
    )
    linked = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Linked",
    )

    assert (
        cleanup_client.get(f"{QUEUE_URL}/{elsewhere}/evidence", headers=headers).status_code == 404
    )
    assert (
        cleanup_client.get(
            f"{QUEUE_URL}/{linked.substrate_id}/evidence", headers=headers
        ).status_code
        == 404
    )
    assert cleanup_client.get(f"{QUEUE_URL}/999999/evidence", headers=headers).status_code == 404
