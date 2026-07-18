"""Tests for public API Redis rate limiting."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from core_api.routers.public import rate_limit
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response


@pytest.fixture(autouse=True)
def enable_public_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_PUBLIC_RATE_LIMIT_ENABLED", "1")


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def eval(self, _script: str, _num_keys: int, key: str, project: str, _ttl: int) -> list[int]:
        self.counts[key] = self.counts.get(key, 0) + 1
        self.counts[project] = self.counts.get(project, 0) + 1
        return [self.counts[key], self.counts[project]]


def _request(path: str, *, token: str = "bfk_test", method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def _auth(credential_id: int) -> dict[str, object]:
    return {"type": "api_key", "credential": SimpleNamespace(id=credential_id)}


def test_rate_limit_uses_endpoint_buckets_and_returns_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit.time, "time", lambda: 121)
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: fake)

    read = rate_limit.check_rate_limit(
        _request("/public/v1/projects/general/articles"),
        auth=_auth(1),
        project_id=7,
    )
    search = rate_limit.check_rate_limit(
        _request("/public/v1/projects/general/articles/semantic-search"),
        auth=_auth(1),
        project_id=7,
    )
    run = rate_limit.check_rate_limit(
        _request("/public/v1/projects/general/runs", method="POST"),
        auth=_auth(1),
        project_id=7,
    )

    assert read is not None and read.limit == 600
    assert read.headers()["RateLimit-Remaining"] == "599"
    assert read.headers()["RateLimit-Reset"] == "59"
    assert search is not None and search.limit == 60
    assert run is not None and run.limit == 5


def test_rate_limit_rejects_key_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setenv("BACKFIELD_PUBLIC_RATE_LIMIT_READS_PER_MINUTE", "1")
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: fake)
    request = _request("/public/v1/projects/general/articles")

    rate_limit.enforce_public_rate_limit(
        request,
        Response(),
        auth=_auth(1),
        project_id=7,
    )
    with pytest.raises(HTTPException) as exc_info:
        rate_limit.enforce_public_rate_limit(
            request,
            Response(),
            auth=_auth(1),
            project_id=7,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["RateLimit-Remaining"] == "0"
    assert int(exc_info.value.headers["Retry-After"]) >= 1


def test_rate_limit_rejects_project_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setenv("BACKFIELD_PUBLIC_RATE_LIMIT_READS_PER_MINUTE", "1")
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: fake)
    request = _request("/public/v1/projects/general/articles")

    for credential_id in range(1, 5):
        decision = rate_limit.check_rate_limit(
            request,
            auth=_auth(credential_id),
            project_id=7,
        )
        assert decision is not None and decision.allowed
    blocked = rate_limit.check_rate_limit(request, auth=_auth(5), project_id=7)

    assert blocked is not None
    assert not blocked.allowed


def test_rate_limit_service_tokens_have_bounded_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: fake)
    first = rate_limit.check_rate_limit(
        _request("/public/v1/projects/general/articles", token="service-a"),
        auth={"type": "service"},
        project_id=7,
    )
    second = rate_limit.check_rate_limit(
        _request("/public/v1/projects/general/articles", token="service-a"),
        auth={"type": "service"},
        project_id=7,
    )

    assert first is not None and second is not None
    assert second.remaining == first.remaining - 1


def test_rate_limit_fails_open_on_redis_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenRedis:
        def eval(self, *_args: object) -> list[int]:
            raise ConnectionError("down")

    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: BrokenRedis())
    decision = rate_limit.check_rate_limit(
        _request("/public/v1/projects/general/articles"),
        auth=_auth(1),
        project_id=7,
    )

    assert decision is None
    assert "public_rate_limit_redis_error" in caplog.text
