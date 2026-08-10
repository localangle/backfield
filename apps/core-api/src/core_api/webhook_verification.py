"""Synchronous signed test delivery used to verify webhook endpoints.

The test event is delivery-only (``is_test=True``) and never enters the public
event feed. A 2xx response marks the endpoint verified and active.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

import httpx
from backfield_db import (
    BackfieldEvent,
    BackfieldProject,
    BackfieldWebhookDelivery,
    BackfieldWebhookDeliveryAttempt,
    BackfieldWebhookEndpoint,
)
from backfield_db.crypto import decrypt_secret
from backfield_events.contracts import EVENT_SCHEMA_VERSION, WEBHOOK_TEST_EVENT
from backfield_events.destinations import WebhookDestinationError, validate_webhook_url
from backfield_events.recording import ENDPOINT_STATUS_ACTIVE, ENDPOINT_STATUS_PENDING
from backfield_events.signing import build_signature_headers
from pydantic import BaseModel
from sqlmodel import Session

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_S = 5.0
_READ_TIMEOUT_S = 10.0
_TOTAL_TIMEOUT_S = 15.0
_MAX_RESPONSE_BYTES = 64 * 1024


class WebhookTestResultOut(BaseModel):
    ok: bool
    status_code: int | None
    failure_category: str | None
    failure_summary: str | None


def send_webhook_verification_test(
    session: Session,
    *,
    endpoint: BackfieldWebhookEndpoint,
    project: BackfieldProject,
) -> WebhookTestResultOut:
    """Send one signed synthetic event and record the outcome on the endpoint."""
    now = datetime.now(UTC)
    event = BackfieldEvent(
        event_type=WEBHOOK_TEST_EVENT,
        organization_id=endpoint.organization_id,
        project_id=endpoint.project_id,
        payload_json=json.dumps(
            {
                "message": "Test delivery from Backfield. Your endpoint is reachable.",
                "endpoint_name": endpoint.name,
            }
        ),
        occurred_at=now,
        is_test=True,
    )
    session.add(event)
    session.flush()

    delivery = BackfieldWebhookDelivery(
        event_id=int(event.id or 0),
        endpoint_id=endpoint.id,
        state="delivering",
        attempt_count=1,
        next_attempt_at=now,
        first_attempted_at=now,
        is_test=True,
    )
    session.add(delivery)
    session.flush()

    envelope = {
        "id": event.event_uuid,
        "sequence": 0,
        "type": WEBHOOK_TEST_EVENT,
        "schema_version": EVENT_SCHEMA_VERSION,
        "occurred_at": now.isoformat(),
        "project": project.slug,
        "data": json.loads(event.payload_json),
    }
    body = json.dumps(envelope).encode("utf-8")
    timestamp = str(int(now.timestamp()))
    headers = build_signature_headers(
        secret=decrypt_secret(endpoint.signing_secret_encrypted),
        timestamp=timestamp,
        body=body,
        event_uuid=event.event_uuid,
        delivery_id=delivery.id,
        event_type=WEBHOOK_TEST_EVENT,
    )

    status_code, failure_category, failure_summary, duration_ms = _post_signed(
        url=decrypt_secret(endpoint.url_encrypted),
        body=body,
        headers=headers,
    )

    ok = status_code is not None and 200 <= status_code < 300
    delivery.state = "delivered" if ok else "failed"
    delivery.last_status_code = status_code
    delivery.failure_category = None if ok else failure_category
    delivery.failure_summary = None if ok else failure_summary
    delivery.delivered_at = datetime.now(UTC) if ok else None
    delivery.updated_at = datetime.now(UTC)
    session.add(delivery)
    session.add(
        BackfieldWebhookDeliveryAttempt(
            delivery_id=delivery.id,
            attempt_number=1,
            attempted_at=now,
            status_code=status_code,
            failure_category=None if ok else failure_category,
            failure_summary=None if ok else failure_summary,
            duration_ms=duration_ms,
        )
    )

    if ok:
        endpoint.verified_at = datetime.now(UTC)
        endpoint.last_success_at = endpoint.verified_at
        if endpoint.status == ENDPOINT_STATUS_PENDING:
            endpoint.status = ENDPOINT_STATUS_ACTIVE
    else:
        endpoint.last_failure_at = datetime.now(UTC)
    endpoint.updated_at = datetime.now(UTC)
    session.add(endpoint)
    session.commit()

    return WebhookTestResultOut(
        ok=ok,
        status_code=status_code,
        failure_category=None if ok else failure_category,
        failure_summary=None if ok else failure_summary,
    )


def _post_signed(
    *,
    url: str,
    body: bytes,
    headers: dict[str, str],
) -> tuple[int | None, str | None, str | None, int]:
    """POST with the delivery SSRF policy; returns (status, category, summary, ms)."""
    started = time.monotonic()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        validate_webhook_url(url)
    except WebhookDestinationError as e:
        return None, "destination_blocked", e.reason, _elapsed_ms()

    timeout = httpx.Timeout(
        _TOTAL_TIMEOUT_S,
        connect=_CONNECT_TIMEOUT_S,
        read=_READ_TIMEOUT_S,
    )
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            with client.stream("POST", url, content=body, headers=headers) as response:
                # Bound how much of the response we read; the body is discarded.
                read = 0
                for chunk in response.iter_bytes():
                    read += len(chunk)
                    if read > _MAX_RESPONSE_BYTES:
                        break
                status_code = response.status_code
    except httpx.TimeoutException:
        return None, "timeout", "The destination did not respond in time", _elapsed_ms()
    except httpx.HTTPError as e:
        return None, "connection_error", type(e).__name__, _elapsed_ms()

    if 300 <= status_code < 400:
        return status_code, "redirect_not_followed", "Redirects are not followed", _elapsed_ms()
    if 200 <= status_code < 300:
        return status_code, None, None, _elapsed_ms()
    category = "http_4xx" if status_code < 500 else "http_5xx"
    return status_code, category, f"HTTP {status_code}", _elapsed_ms()
