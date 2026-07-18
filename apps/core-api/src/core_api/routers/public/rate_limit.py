"""Redis-backed, fail-open rate limits for the public API."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from functools import cache
from typing import Any

import redis
from backfield_auth.structured_logging import log_event
from fastapi import HTTPException, Request, Response, status

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_INCREMENT_SCRIPT = """
local key_count = redis.call("INCR", KEYS[1])
if key_count == 1 then redis.call("EXPIRE", KEYS[1], ARGV[1]) end
local project_count = redis.call("INCR", KEYS[2])
if project_count == 1 then redis.call("EXPIRE", KEYS[2], ARGV[1]) end
return {key_count, project_count}
"""


@dataclass(frozen=True)
class RateLimitDecision:
    limit: int
    remaining: int
    reset_after: int
    retry_after: int
    allowed: bool

    def headers(self) -> dict[str, str]:
        headers = {
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(self.remaining),
            "RateLimit-Reset": str(self.reset_after),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)
        return headers


def _enabled() -> bool:
    return os.getenv("BACKFIELD_PUBLIC_RATE_LIMIT_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _limit_for_request(request: Request) -> tuple[str, int]:
    path = request.url.path
    if request.method == "POST" and path.endswith("/runs"):
        return "runs", int(os.getenv("BACKFIELD_PUBLIC_RATE_LIMIT_RUNS_PER_MINUTE", "5"))
    if any(marker in path for marker in ("semantic-search", "geo-search", "geo-cells")):
        return "search", int(os.getenv("BACKFIELD_PUBLIC_RATE_LIMIT_SEARCH_PER_MINUTE", "60"))
    return "read", int(os.getenv("BACKFIELD_PUBLIC_RATE_LIMIT_READS_PER_MINUTE", "600"))


def _identity(request: Request, auth: dict[str, Any]) -> str:
    if auth["type"] == "api_key":
        credential = auth["credential"]
        return f"key:{int(credential.id)}"
    authorization = request.headers.get("Authorization", "")
    digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:24]
    return f"service:{digest}"


@cache
def _get_redis_client() -> redis.Redis:
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2)


def check_rate_limit(
    request: Request,
    *,
    auth: dict[str, Any],
    project_id: int,
) -> RateLimitDecision | None:
    """Charge key and project fixed-window buckets, failing open on Redis errors."""
    if not _enabled():
        return None

    bucket, key_limit = _limit_for_request(request)
    project_limit = key_limit * 4
    now = int(time.time())
    window = now // _WINDOW_SECONDS
    reset_after = max(1, ((window + 1) * _WINDOW_SECONDS) - now)
    identity = _identity(request, auth)
    prefix = f"backfield:public-rate:{bucket}:{window}"
    key_bucket = f"{prefix}:project:{project_id}:{identity}"
    project_bucket = f"{prefix}:project:{project_id}:aggregate"

    try:
        counts = _get_redis_client().eval(
            _INCREMENT_SCRIPT,
            2,
            key_bucket,
            project_bucket,
            _WINDOW_SECONDS + 1,
        )
        key_count, project_count = int(counts[0]), int(counts[1])
    except Exception as exc:
        log_event(
            logger,
            "public_rate_limit_redis_error",
            level=logging.WARNING,
            error_type=type(exc).__name__,
            project_id=project_id,
            bucket=bucket,
        )
        return None

    key_remaining = max(0, key_limit - key_count)
    project_remaining_scaled = max(0, (project_limit - project_count) // 4)
    allowed = key_count <= key_limit and project_count <= project_limit
    return RateLimitDecision(
        limit=key_limit,
        remaining=min(key_remaining, project_remaining_scaled),
        reset_after=reset_after,
        retry_after=reset_after,
        allowed=allowed,
    )


def enforce_public_rate_limit(
    request: Request,
    response: Response,
    *,
    auth: dict[str, Any],
    project_id: int,
) -> None:
    decision = check_rate_limit(request, auth=auth, project_id=project_id)
    if decision is None:
        return
    headers = decision.headers()
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Public API rate limit exceeded.",
            headers=headers,
        )
    for name, value in headers.items():
        response.headers[name] = value
