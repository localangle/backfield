"""GET .../cleanup/{entity}/export: paging, filters, counts, scoping."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from tests.core_api.cleanup_fixtures import (
    CLEANUP_BASE,
    CleanupWorld,
    create_cleanup_key,
    seed_article,
    seed_entity,
    seed_mention,
)


def _export(client: TestClient, headers: dict[str, str], entity: str = "locations", **params):
    return client.get(f"{CLEANUP_BASE}/{entity}/export", headers=headers, params=params)


def test_export_requires_cleanup_read(cleanup_client, cleanup_world) -> None:
    headers = create_cleanup_key(cleanup_client, scopes=["read"])
    assert _export(cleanup_client, headers).status_code == 403


def test_export_returns_counts_and_details(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    place = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield",
        kind="city",
        aliases=("Springfld",),
    )
    first = seed_article(
        cleanup_session,
        project_id=cleanup_world.project_id,
        headline="A",
        pub_date=date(2024, 3, 1),
    )
    second = seed_article(
        cleanup_session,
        project_id=cleanup_world.second_project_id,
        headline="B",
        pub_date=date(2024, 6, 1),
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=place.substrate_id,
        article_id=first,
        mention_text="Springfield",
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=place.substrate_id,
        article_id=second,
        mention_text="Springfield",
    )

    body = _export(cleanup_client, headers).json()

    assert body["entity"] == "locations"
    assert body["next_cursor"] is None
    [item] = body["items"]
    assert item["id"] == place.canonical_id
    assert item["kind"] == "city"
    assert item["mention_count"] == 2
    assert item["story_count"] == 2
    assert item["alias_count"] == 1
    assert item["details"]["point"] is None


def test_export_pages_with_cursor(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    for label in ("Alpha", "Bravo", "Charlie"):
        seed_entity(
            cleanup_session,
            "locations",
            stylebook_id=cleanup_world.stylebook_id,
            project_id=cleanup_world.project_id,
            label=label,
        )

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        body = _export(cleanup_client, headers, **params).json()
        seen.extend(item["label"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert sorted(seen) == ["Alpha", "Bravo", "Charlie"]
    assert len(seen) == len(set(seen))


def test_export_rejects_bad_cursor(cleanup_client, cleanup_world) -> None:
    headers = create_cleanup_key(cleanup_client)
    r = _export(cleanup_client, headers, cursor="not-a-cursor")
    assert r.status_code == 400


def test_export_filters_by_mention_date_and_counts_in_range(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    old = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Old Town",
    )
    recent = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Recent Town",
    )
    deleted_only = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Ghost Town",
    )
    article_2023 = seed_article(
        cleanup_session,
        project_id=cleanup_world.project_id,
        headline="2023",
        pub_date=date(2023, 5, 1),
    )
    article_2024 = seed_article(
        cleanup_session,
        project_id=cleanup_world.project_id,
        headline="2024",
        pub_date=date(2024, 5, 1),
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=old.substrate_id,
        article_id=article_2023,
        mention_text="Old Town",
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=recent.substrate_id,
        article_id=article_2023,
        mention_text="Recent Town",
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=recent.substrate_id,
        article_id=article_2024,
        mention_text="Recent Town",
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=deleted_only.substrate_id,
        article_id=article_2024,
        mention_text="Ghost Town",
        deleted=True,
    )

    body = _export(
        cleanup_client, headers, mentioned_from="2024-01-01", mentioned_to="2024-12-31"
    ).json()

    assert [item["label"] for item in body["items"]] == ["Recent Town"]
    assert body["items"][0]["mention_count"] == 1


def test_export_updated_since_and_kind(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield",
        kind="city",
    )
    seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Main Street",
        kind="street",
    )

    by_kind = _export(cleanup_client, headers, kind="STREET").json()
    assert [item["label"] for item in by_kind["items"]] == ["Main Street"]

    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert _export(cleanup_client, headers, updated_since=future).json()["items"] == []


def test_export_covers_people_and_organizations(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    seed_entity(
        cleanup_session,
        "people",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Ada Lovelace",
    )
    seed_entity(
        cleanup_session,
        "organizations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="City Council",
    )

    people = _export(cleanup_client, headers, entity="people").json()
    orgs = _export(cleanup_client, headers, entity="organizations").json()

    assert [i["label"] for i in people["items"]] == ["Ada Lovelace"]
    assert people["items"][0]["details"]["public_figure"] is False
    assert [i["label"] for i in orgs["items"]] == ["City Council"]


def test_export_is_scoped_to_the_stylebook(
    cleanup_client, cleanup_world: CleanupWorld, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.foreign_stylebook_id,
        project_id=cleanup_world.project_id,
        label="Elsewhere",
    )

    assert _export(cleanup_client, headers).json()["items"] == []


def test_export_rejects_unknown_entity(cleanup_client, cleanup_world) -> None:
    headers = create_cleanup_key(cleanup_client)
    assert _export(cleanup_client, headers, entity="widgets").status_code == 422


def test_canonical_updated_at_advances_on_orm_updates(cleanup_world, cleanup_session) -> None:
    """`updated_since` relies on canonicals bumping `updated_at` whenever a row changes."""
    from backfield_db import StylebookLocationCanonical

    seeded = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield",
    )
    canonical = cleanup_session.get(StylebookLocationCanonical, seeded.canonical_id)
    canonical.updated_at = datetime(2020, 1, 1, tzinfo=UTC)
    cleanup_session.commit()

    canonical.label = "Springfield, USA"
    cleanup_session.commit()
    cleanup_session.refresh(canonical)

    assert canonical.updated_at.replace(tzinfo=UTC) > datetime(2021, 1, 1, tzinfo=UTC)
