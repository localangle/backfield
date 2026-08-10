"""HMAC signing for webhook deliveries.

Receivers verify by recomputing ``HMAC-SHA256(secret, "{timestamp}.{raw_body}")``
and comparing against the ``v1=`` value in ``Backfield-Signature``.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_VERSION_PREFIX = "v1="

HEADER_EVENT_ID = "Backfield-Event-Id"
HEADER_DELIVERY_ID = "Backfield-Delivery-Id"
HEADER_EVENT_TYPE = "Backfield-Event-Type"
HEADER_TIMESTAMP = "Backfield-Timestamp"
HEADER_SIGNATURE = "Backfield-Signature"


def sign_webhook_payload(*, secret: str, timestamp: str, body: bytes) -> str:
    """Return the ``v1=<hex>`` signature over ``timestamp + "." + raw_body``."""
    message = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_VERSION_PREFIX}{digest}"


def verify_webhook_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> bool:
    expected = sign_webhook_payload(secret=secret, timestamp=timestamp, body=body)
    return hmac.compare_digest(expected, signature)


def build_signature_headers(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
    event_uuid: str,
    delivery_id: str,
    event_type: str,
) -> dict[str, str]:
    """Stable delivery headers; event ID and body are preserved across retries."""
    return {
        "Content-Type": "application/json",
        HEADER_EVENT_ID: event_uuid,
        HEADER_DELIVERY_ID: delivery_id,
        HEADER_EVENT_TYPE: event_type,
        HEADER_TIMESTAMP: timestamp,
        HEADER_SIGNATURE: sign_webhook_payload(secret=secret, timestamp=timestamp, body=body),
    }
