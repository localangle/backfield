"""Overpass HTTP client resilience (rate limits, mirrors, JSON validation)."""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from agate_utils.geocoding import overpass as overpass_module


@pytest.fixture(autouse=True)
def _no_redis_cooldown(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Keep tests off Redis; record cool-down starts."""
    started: list[str] = []
    monkeypatch.setattr(overpass_module, "provider_cooldown_active", lambda _provider: False)
    monkeypatch.setattr(
        overpass_module, "start_provider_cooldown", lambda _provider, reason: started.append(reason)
    )
    return started


def _no_slot(deadline: float | None = None) -> contextlib.AbstractContextManager[None]:
    return contextlib.nullcontext()


def _patch_endpoints(monkeypatch: pytest.MonkeyPatch, count: int) -> None:
    urls = [f"https://endpoint-{index}.test/api/interpreter" for index in range(count)]
    monkeypatch.setattr(overpass_module, "_overpass_endpoint_urls", lambda: urls)
    monkeypatch.setattr(overpass_module, "_overpass_request_slot", _no_slot)
    monkeypatch.setattr(overpass_module.time, "sleep", MagicMock())


def _mock_client(responses: list[httpx.Response | Exception]) -> MagicMock:
    client = MagicMock()
    client.post.side_effect = responses
    client.__enter__.return_value = client
    return client


@pytest.fixture(autouse=True)
def _reset_overpass_semaphore() -> None:
    overpass_module._overpass_semaphore_instance = None
    yield
    overpass_module._overpass_semaphore_instance = None


def test_overpass_request_slot_acquires_and_releases_semaphore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OVERPASS_MAX_CONCURRENT", "1")
    semaphore = overpass_module._overpass_semaphore()
    with overpass_module._overpass_request_slot():
        assert not semaphore.acquire(blocking=False)
    assert semaphore.acquire(blocking=False)
    semaphore.release()


def test_overpass_endpoint_urls_dedupes_primary_and_mirrors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OVERPASS_API_URL", "https://primary.example/api/interpreter")
    monkeypatch.setenv(
        "OVERPASS_MIRROR_URLS",
        "https://mirror-a.example/api/interpreter,https://primary.example/api/interpreter",
    )
    assert overpass_module._overpass_endpoint_urls() == [
        "https://primary.example/api/interpreter",
        "https://mirror-a.example/api/interpreter",
    ]


def test_looks_like_overpass_json() -> None:
    assert overpass_module._looks_like_overpass_json(b'{"elements": []}')
    assert overpass_module._looks_like_overpass_json(b"  [{")
    assert not overpass_module._looks_like_overpass_json(b"<!DOCTYPE html>")


def test_run_query_retries_transient_error_then_parses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        overpass_module,
        "_overpass_endpoint_urls",
        lambda: ["https://overpass.test/api/interpreter"],
    )
    monkeypatch.setattr(
        overpass_module,
        "_overpass_request_slot",
        _no_slot,
    )
    sleep_mock = MagicMock()
    monkeypatch.setattr(overpass_module.time, "sleep", sleep_mock)

    ok_body = b'{"version": 0.6, "generator": "test", "elements": []}'
    responses = [
        httpx.Response(503, text="<!DOCTYPE html><html>unavailable</html>"),
        httpx.Response(200, content=ok_body),
    ]

    mock_client = MagicMock()
    mock_client.post.side_effect = responses
    mock_client.__enter__.return_value = mock_client

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy("[out:json]; node(1); out;", max_retries=3)

    assert result is not None
    assert isinstance(result, overpass_module.overpy.Result)
    assert mock_client.post.call_count == 2
    sleep_mock.assert_called_once()


def test_run_query_moves_to_mirror_after_non_json_200_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_endpoints(monkeypatch, 2)
    ok_body = b'{"version": 0.6, "generator": "test", "elements": []}'
    mock_client = _mock_client(
        [
            httpx.Response(200, content=b"<!DOCTYPE html><html>busy</html>"),
            httpx.Response(200, content=ok_body),
        ]
    )

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy("[out:json]; node(1); out;", max_retries=3)

    assert result is not None
    urls_called = [call.args[0] for call in mock_client.post.call_args_list]
    assert urls_called == [
        "https://endpoint-0.test/api/interpreter",
        "https://endpoint-1.test/api/interpreter",
    ]


def test_run_query_falls_back_to_mirror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        overpass_module,
        "_overpass_endpoint_urls",
        lambda: [
            "https://primary.test/api/interpreter",
            "https://mirror.test/api/interpreter",
        ],
    )
    monkeypatch.setattr(
        overpass_module,
        "_overpass_request_slot",
        _no_slot,
    )
    monkeypatch.setattr(overpass_module.time, "sleep", MagicMock())

    ok_body = b'{"version": 0.6, "generator": "test", "elements": []}'
    responses = [
        httpx.Response(429, text="rate limited"),
        httpx.Response(200, content=ok_body),
    ]

    mock_client = MagicMock()
    mock_client.post.side_effect = responses
    mock_client.__enter__.return_value = mock_client

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy("[out:json]; node(1); out;", max_retries=2)

    assert result is not None
    urls_called = [call.args[0] for call in mock_client.post.call_args_list]
    assert "https://mirror.test/api/interpreter" in urls_called


def test_run_query_does_not_retry_capacity_errors_on_the_same_endpoint(
    monkeypatch: pytest.MonkeyPatch, _no_redis_cooldown: list[str]
) -> None:
    _patch_endpoints(monkeypatch, 1)
    mock_client = _mock_client([httpx.Response(429, text="at capacity")])

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy("[out:json]; node(1); out;")

    assert result is None
    assert mock_client.post.call_count == 1
    assert len(_no_redis_cooldown) == 1


def test_run_query_makes_no_request_after_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch, _no_redis_cooldown: list[str]
) -> None:
    _patch_endpoints(monkeypatch, 2)
    mock_client = _mock_client([])

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy(
            "[out:json]; node(1); out;", deadline=time.monotonic() - 1.0
        )

    assert result is None
    mock_client.post.assert_not_called()
    assert len(_no_redis_cooldown) == 1


def test_run_query_gives_up_instead_of_sleeping_past_the_budget(
    monkeypatch: pytest.MonkeyPatch, _no_redis_cooldown: list[str]
) -> None:
    _patch_endpoints(monkeypatch, 1)
    mock_client = _mock_client([httpx.Response(503, text="unavailable")])

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy(
            "[out:json]; node(1); out;", max_retries=3, deadline=time.monotonic() + 1.0
        )

    assert result is None
    assert mock_client.post.call_count == 1
    overpass_module.time.sleep.assert_not_called()
    assert len(_no_redis_cooldown) == 1


def test_run_query_caps_each_request_by_remaining_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_endpoints(monkeypatch, 1)
    monkeypatch.setenv("OVERPASS_REQUEST_TIMEOUT_S", "30")
    ok_body = b'{"version": 0.6, "generator": "test", "elements": []}'
    mock_client = _mock_client([httpx.Response(200, content=ok_body)])

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        overpass_module.run_query_with_overpy(
            "[out:json]; node(1); out;", deadline=time.monotonic() + 5.0
        )

    request_timeout = mock_client.post.call_args.kwargs["timeout"]
    assert request_timeout.read <= 5.0


def test_run_query_bad_request_does_not_start_cooldown(
    monkeypatch: pytest.MonkeyPatch, _no_redis_cooldown: list[str]
) -> None:
    _patch_endpoints(monkeypatch, 2)
    mock_client = _mock_client([httpx.Response(400, text="syntax error")])

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy("bad query")

    assert result is None
    assert mock_client.post.call_count == 1
    assert _no_redis_cooldown == []


def test_run_query_skips_http_while_fleet_cooldown_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_endpoints(monkeypatch, 1)
    monkeypatch.setattr(overpass_module, "provider_cooldown_active", lambda _provider: True)
    mock_client = _mock_client([])

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client) as client_cls:
        result = overpass_module.run_query_with_overpy("[out:json]; node(1); out;")

    assert result is None
    client_cls.assert_not_called()


def test_run_query_slot_wait_timeout_does_not_start_cooldown(
    monkeypatch: pytest.MonkeyPatch, _no_redis_cooldown: list[str]
) -> None:
    _patch_endpoints(monkeypatch, 1)

    @contextlib.contextmanager
    def busy_slot(deadline: float | None = None):  # type: ignore[no-untyped-def]
        raise overpass_module.GateWaitTimeout("busy")
        yield  # pragma: no cover

    monkeypatch.setattr(overpass_module, "_overpass_request_slot", busy_slot)

    assert overpass_module.run_query_with_overpy("[out:json]; node(1); out;") is None
    assert _no_redis_cooldown == []


def test_find_intersection_stops_after_first_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        overpass_module, "generate_single_road_query_with_llm", lambda *_a, **_k: "query"
    )
    calls: list[str] = []

    def failing_query(query: str, **_: object) -> None:
        calls.append(query)

    monkeypatch.setattr(overpass_module, "run_query_with_overpy", failing_query)
    monkeypatch.setenv("OVERPASS_QUERY_STAGGER_S", "0")

    results, queries = asyncio.run(
        overpass_module.find_intersection_coordinates(
            "Wells St", "Lake St", 41.8, -87.6, "key", radius=1000
        )
    )

    assert (results, queries) == ([], [])
    assert calls == ["query"]


def test_estimate_overpass_parameters_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def slow_llm(**_: object) -> str:
        time.sleep(0.3)
        return '{"latitude": 41.8, "longitude": -87.6, "radius": 1000}'

    monkeypatch.setattr(overpass_module, "call_llm", slow_llm)
    async def run() -> tuple[tuple[float, float, int] | None, int]:
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        ticker_task = asyncio.create_task(ticker())
        try:
            params = await overpass_module.estimate_overpass_parameters("Wells St, Chicago", "key")
        finally:
            ticker_task.cancel()
        return params, ticks

    params, ticks = asyncio.run(run())
    assert params == (41.8, -87.6, 1000)
    # A blocked loop would have let the ticker run at most once while the LLM call slept.
    assert ticks >= 5
