"""Overpass HTTP client resilience (rate limits, mirrors, JSON validation)."""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import httpx
import pytest
from agate_utils.geocoding import overpass as overpass_module


@pytest.fixture(autouse=True)
def _reset_overpass_semaphore() -> None:
    overpass_module._overpass_semaphore = None
    yield
    overpass_module._overpass_semaphore = None


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


def test_retry_delay_honors_retry_after_header() -> None:
    response = httpx.Response(429, headers={"Retry-After": "12"})
    delay = overpass_module._retry_delay_seconds(
        response=response,
        attempt=1,
        base_delay_s=4.0,
        rate_limited=True,
    )
    assert delay == 12.0


def test_run_query_retries_after_429_then_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        overpass_module,
        "_overpass_endpoint_urls",
        lambda: ["https://overpass.test/api/interpreter"],
    )
    monkeypatch.setattr(
        overpass_module,
        "_overpass_request_slot",
        lambda: contextlib.nullcontext(),
    )
    sleep_mock = MagicMock()
    monkeypatch.setattr(overpass_module.time, "sleep", sleep_mock)

    ok_body = b'{"version": 0.6, "generator": "test", "elements": []}'
    responses = [
        httpx.Response(429, text="<!DOCTYPE html><html>rate limit</html>"),
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


def test_run_query_retries_non_json_200_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        overpass_module,
        "_overpass_endpoint_urls",
        lambda: ["https://overpass.test/api/interpreter"],
    )
    monkeypatch.setattr(
        overpass_module,
        "_overpass_request_slot",
        lambda: contextlib.nullcontext(),
    )
    monkeypatch.setattr(overpass_module.time, "sleep", MagicMock())

    ok_body = b'{"version": 0.6, "generator": "test", "elements": []}'
    responses = [
        httpx.Response(200, content=b"<!DOCTYPE html><html>busy</html>"),
        httpx.Response(200, content=ok_body),
    ]

    mock_client = MagicMock()
    mock_client.post.side_effect = responses
    mock_client.__enter__.return_value = mock_client

    with patch.object(overpass_module.httpx, "Client", return_value=mock_client):
        result = overpass_module.run_query_with_overpy("[out:json]; node(1); out;", max_retries=3)

    assert result is not None
    assert mock_client.post.call_count == 2


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
        lambda: contextlib.nullcontext(),
    )
    monkeypatch.setattr(overpass_module.time, "sleep", MagicMock())

    ok_body = b'{"version": 0.6, "generator": "test", "elements": []}'
    responses = [
        httpx.Response(429, text="rate limited"),
        httpx.Response(429, text="rate limited"),
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
