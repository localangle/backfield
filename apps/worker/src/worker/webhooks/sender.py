"""Signed, bounded, SSRF-guarded HTTP transport for webhook deliveries.

The destination is re-validated (including DNS re-resolution) on every attempt.
Redirects are never followed; response bodies are read up to a small cap and
discarded. Secrets, raw bodies, and full URLs are never logged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from backfield_events.destinations import WebhookDestinationError, validate_webhook_url

CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 10.0
TOTAL_TIMEOUT_S = 15.0
MAX_RESPONSE_BYTES = 64 * 1024
MAX_RETRY_AFTER_S = 3600


@dataclass(frozen=True)
class WebhookSendResult:
    ok: bool
    status_code: int | None
    failure_category: str | None
    failure_summary: str | None
    retryable: bool
    retry_after_seconds: int | None
    duration_ms: int


def send_signed_webhook(*, url: str, body: bytes, headers: dict[str, str]) -> WebhookSendResult:
    started = time.monotonic()

    def _result(
        *,
        ok: bool = False,
        status_code: int | None = None,
        failure_category: str | None = None,
        failure_summary: str | None = None,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> WebhookSendResult:
        return WebhookSendResult(
            ok=ok,
            status_code=status_code,
            failure_category=failure_category,
            failure_summary=failure_summary,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    try:
        validate_webhook_url(url)
    except WebhookDestinationError as e:
        transient = "resolved" in e.reason
        return _result(
            failure_category="dns_error" if transient else "destination_blocked",
            failure_summary=e.reason,
            retryable=transient,
        )

    timeout = httpx.Timeout(TOTAL_TIMEOUT_S, connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            with client.stream("POST", url, content=body, headers=headers) as response:
                read = 0
                for chunk in response.iter_bytes():
                    read += len(chunk)
                    if read > MAX_RESPONSE_BYTES:
                        break
                status_code = response.status_code
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
    except httpx.TimeoutException:
        return _result(
            failure_category="timeout",
            failure_summary="The destination did not respond in time",
            retryable=True,
        )
    except httpx.HTTPError as e:
        return _result(
            failure_category="connection_error",
            failure_summary=type(e).__name__,
            retryable=True,
        )

    if 200 <= status_code < 300:
        return _result(ok=True, status_code=status_code)
    if 300 <= status_code < 400:
        return _result(
            status_code=status_code,
            failure_category="redirect_not_followed",
            failure_summary="Redirects are not followed",
            retryable=False,
        )
    retryable = status_code in (408, 429) or status_code >= 500
    return _result(
        status_code=status_code,
        failure_category="http_4xx" if status_code < 500 else "http_5xx",
        failure_summary=f"HTTP {status_code}",
        retryable=retryable,
        retry_after_seconds=retry_after if retryable else None,
    )


def _parse_retry_after(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        seconds = int(raw.strip())
    except ValueError:
        return None
    if seconds < 0:
        return None
    return min(seconds, MAX_RETRY_AFTER_S)
