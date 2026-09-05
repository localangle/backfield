"""Pelias HTTP retry and provider-health recording."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from agate_utils.geocoding.pelias import _pelias_get, _retry_delay_seconds
from agate_utils.geocoding.provider_health import (
    begin_geocoder_health_tracking,
    end_geocoder_health_tracking,
    record_geocoder_http_status,
    snapshot_geocoder_health,
)


def test_retry_delay_honors_retry_after_seconds() -> None:
    response = MagicMock()
    response.headers = {"Retry-After": "2"}
    delay = _retry_delay_seconds(response=response, attempt=1, rate_limited=True)
    assert delay == 2.0


def test_provider_health_records_auth_and_rate_limit() -> None:
    token = begin_geocoder_health_tracking()
    try:
        record_geocoder_http_status("pelias", 401)
        record_geocoder_http_status("pelias", 401)
        record_geocoder_http_status("pelias", 429)
        snap = snapshot_geocoder_health()
        assert snap["pelias"]["auth_error"] == 2
        assert snap["pelias"]["rate_limit"] == 1
    finally:
        end_geocoder_health_tracking(token)


def test_pelias_get_retries_429_then_succeeds() -> None:
    async def _run() -> None:
        token = begin_geocoder_health_tracking()
        try:
            limited = httpx.Response(
                429, request=httpx.Request("GET", "https://example.test/v1/search")
            )
            limited.headers["Retry-After"] = "0"
            ok = httpx.Response(
                200,
                json={"features": []},
                request=httpx.Request("GET", "https://example.test/v1/search"),
            )
            client = AsyncMock()
            client.get = AsyncMock(side_effect=[limited, ok])

            with patch("agate_utils.geocoding.pelias.asyncio.sleep", new_callable=AsyncMock):
                with patch("backfield_observability.external.emit_external_request"):
                    response = await _pelias_get(
                        client, "https://example.test/v1/search", {"text": "x"}
                    )

            assert response.status_code == 200
            assert client.get.await_count == 2
            snap = snapshot_geocoder_health()
            assert snap["pelias"]["rate_limit"] == 1
        finally:
            end_geocoder_health_tracking(token)

    asyncio.run(_run())


def test_pelias_get_does_not_retry_401() -> None:
    async def _run() -> None:
        token = begin_geocoder_health_tracking()
        try:
            unauthorized = httpx.Response(
                401, request=httpx.Request("GET", "https://example.test/v1/search")
            )
            client = AsyncMock()
            client.get = AsyncMock(return_value=unauthorized)

            with patch("backfield_observability.external.emit_external_request"):
                response = await _pelias_get(
                    client, "https://example.test/v1/search", {"text": "x"}
                )

            assert response.status_code == 401
            assert client.get.await_count == 1
            snap = snapshot_geocoder_health()
            assert snap["pelias"]["auth_error"] == 1
        finally:
            end_geocoder_health_tracking(token)

    asyncio.run(_run())
