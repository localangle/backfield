"""Nominatim lookup budget, fleet cool-down, and shared search cache."""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import MagicMock

import pytest
from agate_utils.geocoding import nominatim as nominatim_module
from agate_utils.geocoding import nominatim_cache, request_gate
from agate_utils.geocoding.request_gate import GateWaitTimeout

_RESULTS = [{"osm_type": "relation", "osm_id": 1, "display_name": "Chicago River"}]


class _FakeRedis:
    """Just the string commands the cache and cool-down use."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expiries[key] = ex

    def exists(self, key: str) -> int:
        return int(key in self.values)


@pytest.fixture
def redis_client(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    client = _FakeRedis()
    monkeypatch.setattr(request_gate, "_connect_gate_redis", lambda: client)
    return client


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the gate and the HTTP call; ``http.get.side_effect`` supplies responses."""
    get = MagicMock()
    monkeypatch.setattr(nominatim_module.requests, "get", get)
    monkeypatch.setattr(
        nominatim_module,
        "acquire_geocode_request_slot",
        lambda provider, max_wait_s=None: contextlib.nullcontext(),
    )
    monkeypatch.setattr(nominatim_module.time, "sleep", MagicMock())
    return get


def _response(status: int, body: Any = None, headers: dict[str, str] | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = body if body is not None else []
    response.raise_for_status.return_value = None
    return response


def _search() -> list[dict[str, Any]]:
    return nominatim_module.NominatimGeocoder().search_raw("Chicago River, IL")


def test_search_stores_answers_and_reuses_them(redis_client, http) -> None:
    http.get.side_effect = None
    http.side_effect = [_response(200, _RESULTS)]

    assert _search() == _RESULTS
    assert _search() == _RESULTS
    assert http.call_count == 1


def test_search_does_not_remember_empty_answers(redis_client, http) -> None:
    http.side_effect = [_response(200, []), _response(200, _RESULTS)]

    assert _search() == []
    assert _search() == _RESULTS
    assert http.call_count == 2


def test_search_cache_key_depends_on_every_option() -> None:
    base = {"q": "Chicago River", "limit": "10"}
    assert nominatim_cache.search_cache_key(base) == nominatim_cache.search_cache_key(dict(base))
    assert nominatim_cache.search_cache_key(base) != nominatim_cache.search_cache_key(
        {**base, "layer": "natural"}
    )


def test_search_cache_can_be_disabled(redis_client, http, monkeypatch) -> None:
    monkeypatch.setenv("NOMINATIM_SEARCH_CACHE_TTL_S", "0")
    http.side_effect = [_response(200, _RESULTS), _response(200, _RESULTS)]

    _search()
    _search()
    assert http.call_count == 2
    assert redis_client.values == {}


def test_search_uses_answer_cached_while_waiting_for_the_slot(
    redis_client, http, monkeypatch
) -> None:
    @contextlib.contextmanager
    def _slot_after_a_peer_fetched(provider: str, max_wait_s: float | None = None):
        nominatim_cache.store_cached_search(
            nominatim_cache.search_cache_key(_params()), _RESULTS
        )
        yield

    def _params() -> dict[str, str]:
        return {
            "q": "Chicago River, IL",
            "format": "jsonv2",
            "limit": "10",
            "addressdetails": "1",
            "extratags": "1",
            "namedetails": "1",
            "accept-language": "en",
        }

    monkeypatch.setattr(
        nominatim_module, "acquire_geocode_request_slot", _slot_after_a_peer_fetched
    )

    assert _search() == _RESULTS
    http.assert_not_called()


def test_search_gives_up_when_no_slot_frees_up_without_starting_cooldown(
    redis_client, http, monkeypatch
) -> None:
    @contextlib.contextmanager
    def _never_free(provider: str, max_wait_s: float | None = None):
        raise GateWaitTimeout("busy")
        yield

    monkeypatch.setattr(nominatim_module, "acquire_geocode_request_slot", _never_free)

    assert _search() == []
    http.assert_not_called()
    assert not request_gate.provider_cooldown_active("nominatim")


def test_search_is_skipped_during_fleet_cooldown(redis_client, http) -> None:
    request_gate.start_provider_cooldown("nominatim", "test")

    assert _search() == []
    http.assert_not_called()


def test_rate_limit_that_outlasts_the_budget_starts_cooldown(
    redis_client, http, monkeypatch
) -> None:
    monkeypatch.setenv("NOMINATIM_LOOKUP_BUDGET_S", "5")
    http.side_effect = [_response(429, headers={"Retry-After": "30"})]

    assert _search() == []
    assert http.call_count == 1
    assert request_gate.provider_cooldown_active("nominatim")


def test_rate_limit_within_budget_is_retried(redis_client, http) -> None:
    http.side_effect = [
        _response(429, headers={"Retry-After": "2"}),
        _response(200, _RESULTS),
    ]

    assert _search() == _RESULTS
    assert http.call_count == 2
    assert not request_gate.provider_cooldown_active("nominatim")


def test_geocode_is_skipped_during_fleet_cooldown(redis_client, monkeypatch) -> None:
    request_gate.start_provider_cooldown("nominatim", "test")
    geocoder = nominatim_module.NominatimGeocoder()
    monkeypatch.setattr(geocoder, "_get_geocoder", lambda: pytest.fail("must not call Nominatim"))

    assert geocoder.geocode("Chicago") is None


def test_geocode_gives_up_when_no_slot_frees_up(redis_client, monkeypatch) -> None:
    @contextlib.contextmanager
    def _never_free(provider: str, max_wait_s: float | None = None):
        raise GateWaitTimeout("busy")
        yield

    monkeypatch.setattr(nominatim_module, "acquire_geocode_request_slot", _never_free)
    geocoder = nominatim_module.NominatimGeocoder()
    monkeypatch.setattr(geocoder, "_get_geocoder", MagicMock)

    assert geocoder.geocode("Chicago") is None
    assert not request_gate.provider_cooldown_active("nominatim")


def test_provider_cooldowns_are_separate_and_expire(redis_client, monkeypatch) -> None:
    monkeypatch.setenv("NOMINATIM_COOLDOWN_S", "45")
    request_gate.start_provider_cooldown("nominatim", "slow")

    assert request_gate.provider_cooldown_active("nominatim")
    assert not request_gate.provider_cooldown_active("overpass")
    assert redis_client.expiries["backfield:geocode:nominatim:cooldown"] == 45


def test_cooldown_can_be_disabled(redis_client, monkeypatch) -> None:
    monkeypatch.setenv("NOMINATIM_COOLDOWN_S", "0")
    request_gate.start_provider_cooldown("nominatim", "slow")

    assert redis_client.values == {}
    assert not request_gate.provider_cooldown_active("nominatim")


def test_overpass_cooldown_keeps_its_key(redis_client) -> None:
    request_gate.start_provider_cooldown("overpass", "busy")

    assert "backfield:geocode:overpass:cooldown" in redis_client.values
    assert request_gate.provider_cooldown_active("overpass")
