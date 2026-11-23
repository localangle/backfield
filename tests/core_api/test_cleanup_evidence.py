"""Evidence, batch evidence and compare reads."""

from __future__ import annotations

from datetime import date

from backfield_db import (
    StylebookActivity,
    StylebookConnection,
    StylebookLocationMeta,
    SubstrateArticle,
)
from sqlmodel import select

from tests.core_api.cleanup_fixtures import (
    CLEANUP_BASE,
    create_cleanup_key,
    seed_article,
    seed_entity,
    seed_mention,
    seed_substrate,
)

ARTICLE_TEXT = "Officials met in Springfield on Monday to discuss the budget for next year."


def _seed_springfield(session, world):
    place = seed_entity(
        session,
        "locations",
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label="Springfield",
        kind="city",
        aliases=("Springfld",),
    )
    first = seed_article(
        session,
        project_id=world.project_id,
        headline="Budget meeting",
        text=ARTICLE_TEXT,
        pub_date=date(2024, 3, 1),
        url="https://example.com/budget",
    )
    start = ARTICLE_TEXT.index("Springfield")
    seed_mention(
        session,
        "locations",
        substrate_id=place.substrate_id,
        article_id=first,
        mention_text="Springfield",
        start_char=start,
        end_char=start + len("Springfield"),
    )
    return place


def test_evidence_assembles_every_section(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    place = _seed_springfield(cleanup_session, cleanup_world)
    other = seed_entity(
        cleanup_session,
        "organizations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="City Council",
    )
    cleanup_session.add(
        StylebookLocationMeta(
            project_id=cleanup_world.project_id,
            stylebook_location_canonical_id=place.canonical_id,
            meta_type="population",
            value_type="number",
            value_number=60000,
        )
    )
    cleanup_session.add(
        StylebookConnection(
            project_id=cleanup_world.project_id,
            stylebook_id=cleanup_world.stylebook_id,
            from_entity_type="organization",
            from_entity_id=other.canonical_id,
            to_entity_type="location",
            to_entity_id=place.canonical_id,
            nature="governs",
        )
    )
    cleanup_session.add(
        StylebookActivity(
            stylebook_id=cleanup_world.stylebook_id,
            source="manual_ui",
            event_type="canonical_updated",
            entity_type="location",
            entity_id=place.canonical_id,
            payload_json={"field": "label"},
        )
    )
    cleanup_session.commit()

    r = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{place.canonical_id}/evidence", headers=headers
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "Springfield"
    assert body["mention_count"] == 1
    assert [a["alias_text"] for a in body["aliases"]] == ["Springfld"]
    assert body["aliases"][0]["provenance"] == "ingest"
    assert body["meta"] == [{"meta_type": "population", "value_type": "number", "value": 60000.0}]
    [connection] = body["connections"]
    assert connection["direction"] == "incoming"
    assert connection["other_label"] == "City Council"
    assert body["activity"][0]["payload"] == {"field": "label"}
    [record] = body["linked_records"]
    assert record["project_slug"] == "general"
    assert record["mention_count"] == 1
    [snippet] = body["snippets"]
    assert snippet["headline"] == "Budget meeting"
    assert snippet["project_slug"] == "general"
    assert "Springfield" in snippet["snippet"]


def test_evidence_is_stylebook_wide_with_project_tags(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    place = _seed_springfield(cleanup_session, cleanup_world)
    from_second = seed_article(
        cleanup_session,
        project_id=cleanup_world.second_project_id,
        headline="Other newsroom",
        text="Springfield again.",
        pub_date=date(2024, 4, 1),
    )
    second_substrate = seed_substrate(
        cleanup_session,
        "locations",
        canonical_id=place.canonical_id,
        project_id=cleanup_world.second_project_id,
        name="Springfield",
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=second_substrate,
        article_id=from_second,
        mention_text="Springfield",
    )

    body = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{place.canonical_id}/evidence", headers=headers
    ).json()

    assert {s["project_slug"] for s in body["snippets"]} == {"general", "second"}


def test_snippet_controls_limit_and_operator_cap(
    cleanup_client, cleanup_world, cleanup_session, monkeypatch
) -> None:
    headers = create_cleanup_key(cleanup_client)
    place = _seed_springfield(cleanup_session, cleanup_world)
    url = f"{CLEANUP_BASE}/locations/{place.canonical_id}/evidence"

    none = cleanup_client.get(url, headers=headers, params={"snippet_limit": 0}).json()
    assert none["snippets"] == []

    monkeypatch.setenv("BACKFIELD_CLEANUP_SNIPPET_MAX_CHARS", "20")
    capped = cleanup_client.get(url, headers=headers, params={"snippet_chars": 300}).json()
    assert len(capped["snippets"][0]["snippet"]) <= 22  # 20 characters plus ellipses

    monkeypatch.setenv("BACKFIELD_CLEANUP_SNIPPET_MAX_CHARS", "0")
    off = cleanup_client.get(url, headers=headers).json()
    assert off["snippets"][0]["snippet"] is None
    assert off["snippets"][0]["mention_text"] == "Springfield"


def test_evidence_404s_outside_the_stylebook(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    foreign = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.foreign_stylebook_id,
        project_id=cleanup_world.project_id,
        label="Elsewhere",
    )

    r = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{foreign.canonical_id}/evidence", headers=headers
    )

    assert r.status_code == 404
    missing = cleanup_client.get(f"{CLEANUP_BASE}/locations/nope/evidence", headers=headers)
    assert missing.status_code == 404


def test_batch_evidence_lists_missing_ids(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    place = _seed_springfield(cleanup_session, cleanup_world)

    r = cleanup_client.post(
        f"{CLEANUP_BASE}/locations/evidence",
        headers=headers,
        json={"ids": [place.canonical_id, "nope", place.canonical_id], "snippet_limit": 1},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert [item["id"] for item in body["items"]] == [place.canonical_id]
    assert body["missing_ids"] == ["nope"]


def test_batch_evidence_enforces_the_size_cap(cleanup_client, cleanup_world) -> None:
    headers = create_cleanup_key(cleanup_client)
    r = cleanup_client.post(
        f"{CLEANUP_BASE}/locations/evidence",
        headers=headers,
        json={"ids": [str(i) for i in range(26)]},
    )
    assert r.status_code == 422


def test_compare_reports_shared_aliases_and_stories(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    left = _seed_springfield(cleanup_session, cleanup_world)
    right = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield, USA",
        kind="city",
        aliases=("Springfld",),
    )
    article_id = cleanup_session.exec(select(SubstrateArticle.id)).one()
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=right.substrate_id,
        article_id=article_id,
        mention_text="Springfield",
    )

    r = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{left.canonical_id}/compare/{right.canonical_id}",
        headers=headers,
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["same_kind"] is True
    assert body["shared_alias_texts"] == ["springfld"]
    assert body["shared_story_count"] == 1
    assert body["connected"] is False
    assert body["left"]["label"] == "Springfield"
    assert body["right"]["label"] == "Springfield, USA"


def test_compare_rejects_identical_and_unknown_ids(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    place = _seed_springfield(cleanup_session, cleanup_world)

    same = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{place.canonical_id}/compare/{place.canonical_id}",
        headers=headers,
    )
    unknown = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{place.canonical_id}/compare/nope", headers=headers
    )

    assert same.status_code == 400
    assert unknown.status_code == 404
