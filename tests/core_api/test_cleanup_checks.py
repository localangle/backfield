"""Check list, cached results, run start, and latest run."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from backfield_db import (
    StylebookCleanupCheckResult,
    StylebookCleanupCheckRun,
    StylebookCleanupDismissal,
)
from backfield_entities.cleanup.check_reads import QueueScope, build_run_scope
from backfield_entities.quality.check_runs import cleanup_algorithm_version, cleanup_scope_hash
from backfield_entities.quality.dismissals import pair_key_for_ids

from tests.core_api.cleanup_fixtures import (
    CLEANUP_BASE,
    CleanupWorld,
    create_cleanup_key,
    seed_article,
    seed_entity,
    seed_mention,
)

CHECK_ID = "duplicate-locations"


def _seed_run(
    session,
    world: CleanupWorld,
    *,
    queue_scope: QueueScope = "project",
    status: str = "succeeded",
    check_id: str = CHECK_ID,
) -> StylebookCleanupCheckRun:
    scope = build_run_scope(
        check_id=check_id,
        stylebook_id=world.stylebook_id,
        organization_id=world.organization_id,
        queue_scope=queue_scope,
        project_id=world.project_id,
        project_slug="general",
    )
    run = StylebookCleanupCheckRun(
        stylebook_id=world.stylebook_id,
        check_id=check_id,
        status=status,
        scope_hash=cleanup_scope_hash(scope),
        algorithm_version=cleanup_algorithm_version(check_id),
        completed_at=datetime(2026, 11, 1, tzinfo=UTC) if status == "succeeded" else None,
    )
    session.add(run)
    session.commit()
    return run


def _seed_cluster(session, run, *, ordinal: int, label: str, members: list[str]) -> None:
    session.add(
        StylebookCleanupCheckResult(
            run_id=run.id,
            stylebook_id=run.stylebook_id,
            check_id=run.check_id,
            ordinal=ordinal,
            item_kind="cluster",
            item_key=f"cluster-{ordinal}",
            label=label,
            canonical_ids_json=members,
            pair_keys_json=[pair_key_for_ids(members[0], members[1])],
            payload_json={"reason": "similar names", "score": 0.9},
            searchable_text=label.lower(),
        )
    )
    session.commit()


def _two_places(session, world: CleanupWorld, *, name: str):
    left = seed_entity(
        session,
        "locations",
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label=name,
    )
    right = seed_entity(
        session,
        "locations",
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label=f"{name} City",
    )
    return left, right


def test_check_list_reports_never_run_and_open_counts(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)

    fresh = cleanup_client.get(f"{CLEANUP_BASE}/checks", headers=headers).json()
    assert fresh["queue_scope"] == "project"
    assert len(fresh["checks"]) == 9
    assert {c["status"] for c in fresh["checks"]} == {"never_run"}

    left, right = _two_places(cleanup_session, cleanup_world, name="Springfield")
    run = _seed_run(cleanup_session, cleanup_world)
    _seed_cluster(
        cleanup_session,
        run,
        ordinal=0,
        label="Springfield",
        members=[left.canonical_id, right.canonical_id],
    )

    listed = cleanup_client.get(f"{CLEANUP_BASE}/checks", headers=headers).json()
    check = next(c for c in listed["checks"] if c["id"] == CHECK_ID)
    assert check["status"] == "succeeded"
    assert check["open_count"] == 1
    assert check["entity"] == "locations"
    assert check["algorithm_version"] == "duplicate-locations:v2"


def test_results_page_filter_and_hide_dismissed(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    run = _seed_run(cleanup_session, cleanup_world)
    pairs = [
        _two_places(cleanup_session, cleanup_world, name=n) for n in ("Alpha", "Bravo", "Charlie")
    ]
    for ordinal, (left, right) in enumerate(pairs):
        _seed_cluster(
            cleanup_session,
            run,
            ordinal=ordinal,
            label=f"Cluster {ordinal}",
            members=[left.canonical_id, right.canonical_id],
        )
    url = f"{CLEANUP_BASE}/checks/{CHECK_ID}/results"

    first = cleanup_client.get(url, headers=headers, params={"limit": 2}).json()
    assert [i["label"] for i in first["items"]] == ["Cluster 0", "Cluster 1"]
    assert first["total"] == 3
    assert first["as_of"] is not None
    assert first["items"][0]["payload"] == {"reason": "similar names", "score": 0.9}
    second = cleanup_client.get(
        url, headers=headers, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [i["label"] for i in second["items"]] == ["Cluster 2"]
    assert second["next_cursor"] is None

    searched = cleanup_client.get(url, headers=headers, params={"q": "cluster 1"}).json()
    assert [i["label"] for i in searched["items"]] == ["Cluster 1"]

    left, right = pairs[0]
    cleanup_session.add(
        StylebookCleanupDismissal(
            stylebook_id=cleanup_world.stylebook_id,
            check_id=CHECK_ID,
            pair_key=pair_key_for_ids(left.canonical_id, right.canonical_id),
        )
    )
    cleanup_session.commit()
    after = cleanup_client.get(url, headers=headers).json()
    assert [i["label"] for i in after["items"]] == ["Cluster 1", "Cluster 2"]


def test_results_paging_does_not_skip_results_dismissed_between_pages(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    run = _seed_run(cleanup_session, cleanup_world)
    pairs = [
        _two_places(cleanup_session, cleanup_world, name=n) for n in ("Alpha", "Bravo", "Charlie")
    ]
    for ordinal, (left, right) in enumerate(pairs):
        _seed_cluster(
            cleanup_session,
            run,
            ordinal=ordinal,
            label=f"Cluster {ordinal}",
            members=[left.canonical_id, right.canonical_id],
        )
    url = f"{CLEANUP_BASE}/checks/{CHECK_ID}/results"

    first = cleanup_client.get(url, headers=headers, params={"limit": 1}).json()
    assert [i["label"] for i in first["items"]] == ["Cluster 0"]
    left, right = pairs[0]
    cleanup_session.add(
        StylebookCleanupDismissal(
            stylebook_id=cleanup_world.stylebook_id,
            check_id=CHECK_ID,
            pair_key=pair_key_for_ids(left.canonical_id, right.canonical_id),
        )
    )
    cleanup_session.commit()

    second = cleanup_client.get(
        url, headers=headers, params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert [i["label"] for i in second["items"]] == ["Cluster 1"]


def test_results_before_any_run_are_empty(cleanup_client, cleanup_world) -> None:
    headers = create_cleanup_key(cleanup_client)
    body = cleanup_client.get(f"{CLEANUP_BASE}/checks/{CHECK_ID}/results", headers=headers).json()
    assert body["items"] == []
    assert body["run_id"] is None


def test_results_date_filter_keeps_clusters_with_mentions_in_range(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    run = _seed_run(cleanup_session, cleanup_world)
    old_pair = _two_places(cleanup_session, cleanup_world, name="Old")
    new_pair = _two_places(cleanup_session, cleanup_world, name="New")
    for ordinal, (name, pair) in enumerate((("Old", old_pair), ("New", new_pair))):
        _seed_cluster(
            cleanup_session,
            run,
            ordinal=ordinal,
            label=name,
            members=[pair[0].canonical_id, pair[1].canonical_id],
        )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=old_pair[0].substrate_id,
        article_id=seed_article(
            cleanup_session,
            project_id=cleanup_world.project_id,
            headline="o",
            pub_date=date(2023, 1, 1),
        ),
        mention_text="Old",
    )
    seed_mention(
        cleanup_session,
        "locations",
        substrate_id=new_pair[1].substrate_id,
        article_id=seed_article(
            cleanup_session,
            project_id=cleanup_world.project_id,
            headline="n",
            pub_date=date(2024, 6, 1),
        ),
        mention_text="New City",
    )

    body = cleanup_client.get(
        f"{CLEANUP_BASE}/checks/{CHECK_ID}/results",
        headers=headers,
        params={"mentioned_from": "2024-01-01", "mentioned_to": "2024-12-31"},
    ).json()

    assert [i["label"] for i in body["items"]] == ["New"]


def test_stylebook_scope_needs_a_service_key(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    user_headers = create_cleanup_key(cleanup_client, scopes=["cleanup:read"])
    denied = cleanup_client.get(
        f"{CLEANUP_BASE}/checks", headers=user_headers, params={"scope": "stylebook"}
    )
    assert denied.status_code == 403

    service_headers = create_cleanup_key(
        cleanup_client, credential_type="service", scopes=["cleanup:read"]
    )
    run = _seed_run(cleanup_session, cleanup_world, queue_scope="stylebook")
    left, right = _two_places(cleanup_session, cleanup_world, name="Everywhere")
    _seed_cluster(
        cleanup_session,
        run,
        ordinal=0,
        label="Everywhere",
        members=[left.canonical_id, right.canonical_id],
    )
    body = cleanup_client.get(
        f"{CLEANUP_BASE}/checks/{CHECK_ID}/results",
        headers=service_headers,
        params={"scope": "stylebook"},
    ).json()
    assert body["queue_scope"] == "stylebook"
    assert [i["label"] for i in body["items"]] == ["Everywhere"]


def test_unknown_check_and_bad_cursor(cleanup_client, cleanup_world) -> None:
    headers = create_cleanup_key(cleanup_client)
    unknown = cleanup_client.get(f"{CLEANUP_BASE}/checks/nope/results", headers=headers)
    assert unknown.status_code == 404
    bad = cleanup_client.get(
        f"{CLEANUP_BASE}/checks/{CHECK_ID}/results", headers=headers, params={"cursor": "zzz"}
    )
    # No finished run yet, but a bad cursor is still rejected up front.
    assert bad.status_code == 400


def test_start_run_queues_once_and_reports_latest(
    cleanup_client, cleanup_world, monkeypatch
) -> None:
    queued: list[tuple[str, list]] = []
    monkeypatch.setattr(
        "core_api.routers.public.cleanup.checks.enqueue_worker_task",
        lambda task, args: queued.append((task, args)),
    )
    headers = create_cleanup_key(cleanup_client)
    runs_url = f"{CLEANUP_BASE}/checks/{CHECK_ID}/runs"

    assert cleanup_client.get(f"{runs_url}/latest", headers=headers).status_code == 404

    first = cleanup_client.post(runs_url, headers=headers)
    again = cleanup_client.post(runs_url, headers=headers)

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "queued"
    assert again.json()["id"] == first.json()["id"]
    assert len(queued) == 1
    assert queued[0][0] == "worker.tasks.execute_cleanup_check_run"
    assert queued[0][1] == [first.json()["id"]]
    latest = cleanup_client.get(f"{runs_url}/latest", headers=headers).json()
    assert latest["id"] == first.json()["id"]


def test_start_run_marks_the_run_failed_when_queueing_fails(
    cleanup_client, cleanup_world, monkeypatch
) -> None:
    def broken(task: str, args: list) -> None:
        raise ConnectionError("broker down")

    monkeypatch.setattr("core_api.routers.public.cleanup.checks.enqueue_worker_task", broken)
    headers = create_cleanup_key(cleanup_client)
    runs_url = f"{CLEANUP_BASE}/checks/{CHECK_ID}/runs"

    failed = cleanup_client.post(runs_url, headers=headers)

    assert failed.status_code == 503
    assert cleanup_client.get(f"{runs_url}/latest", headers=headers).json()["status"] == "failed"


@pytest.mark.parametrize("path", ["/checks", "/checks/duplicate-locations/results"])
def test_check_reads_need_cleanup_read(cleanup_client, cleanup_world, path: str) -> None:
    headers = create_cleanup_key(cleanup_client, scopes=["read"])
    assert cleanup_client.get(f"{CLEANUP_BASE}{path}", headers=headers).status_code == 403
