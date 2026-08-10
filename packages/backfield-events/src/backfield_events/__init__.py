"""Typed event contracts, webhook signing, and delivery bookkeeping for Backfield.

This package intentionally contains no HTTP client code and no imports from
apps; delivery transports live in the worker and Core API (see
docs/architecture/overview.md for the dependency direction).
"""

from backfield_events.config import webhooks_enabled
from backfield_events.contracts import (
    EVENT_SCHEMA_VERSION,
    RUN_COMPLETED_EVENT,
    WEBHOOK_TEST_EVENT,
    EventEnvelope,
    RunCompletedCounts,
    RunCompletedData,
    build_run_completed_envelope,
    envelope_from_event,
    normalize_run_outcome,
)
from backfield_events.cursor import CursorExpiredError, decode_event_cursor, encode_event_cursor
from backfield_events.destinations import (
    WebhookDestinationError,
    display_host_for_url,
    validate_webhook_url,
)
from backfield_events.recording import record_run_completed_event
from backfield_events.run_events import (
    RUN_CANCELLED_MESSAGE,
    materialize_run_output_snapshot,
    record_run_output_article,
    record_run_terminal_event,
)
from backfield_events.signing import build_signature_headers, sign_webhook_payload

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "RUN_CANCELLED_MESSAGE",
    "RUN_COMPLETED_EVENT",
    "WEBHOOK_TEST_EVENT",
    "CursorExpiredError",
    "EventEnvelope",
    "RunCompletedCounts",
    "RunCompletedData",
    "WebhookDestinationError",
    "build_run_completed_envelope",
    "build_signature_headers",
    "decode_event_cursor",
    "display_host_for_url",
    "encode_event_cursor",
    "envelope_from_event",
    "materialize_run_output_snapshot",
    "normalize_run_outcome",
    "record_run_completed_event",
    "record_run_output_article",
    "record_run_terminal_event",
    "sign_webhook_payload",
    "validate_webhook_url",
    "webhooks_enabled",
]
