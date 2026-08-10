"""Typed event contracts, webhook signing, and delivery bookkeeping for Backfield.

This package intentionally contains no HTTP client code and no imports from
apps; delivery transports live in the worker and Core API (see
docs/architecture/overview.md for the dependency direction).

Importing this package registers every domain event class with the event
registry (``registered_event_types``).
"""

from backfield_events.article_events import (
    ArticleCreated,
    ArticleUpdated,
    record_article_created,
    record_article_updated,
)
from backfield_events.canonical_events import (
    CanonicalCreated,
    CanonicalDeleted,
    CanonicalEvidenceChanged,
    CanonicalMerged,
    CanonicalUpdated,
    record_canonical_created,
    record_canonical_deleted,
    record_canonical_evidence_changed,
    record_canonical_merged,
    record_canonical_updated,
    suppress_canonical_evidence_events,
)
from backfield_events.config import webhooks_enabled
from backfield_events.contracts import (
    ARTICLE_CREATED_EVENT,
    ARTICLE_UPDATED_EVENT,
    CANONICAL_CREATED_EVENT,
    CANONICAL_DELETED_EVENT,
    CANONICAL_EVIDENCE_CHANGED_EVENT,
    CANONICAL_MERGED_EVENT,
    CANONICAL_UPDATED_EVENT,
    EVENT_SCHEMA_VERSION,
    RUN_COMPLETED_EVENT,
    WEBHOOK_TEST_EVENT,
    EventEnvelope,
    RunCompletedCounts,
    RunCompletedData,
    envelope_from_event,
    normalize_run_outcome,
)
from backfield_events.cursor import CursorExpiredError, decode_event_cursor, encode_event_cursor
from backfield_events.destinations import (
    WebhookDestinationError,
    display_host_for_url,
    validate_webhook_url,
)
from backfield_events.events import (
    DomainEvent,
    EventScope,
    event_type_is_flow_scoped,
    event_type_is_registered,
    pop_recorded_events,
    record_event,
    registered_event_types,
    suppress_events,
)
from backfield_events.recording import RecordedEvent
from backfield_events.run_events import (
    RUN_CANCELLED_MESSAGE,
    RunCompleted,
    materialize_run_output_snapshot,
    record_run_output_article,
    record_run_terminal_event,
)
from backfield_events.signing import build_signature_headers, sign_webhook_payload

__all__ = [
    "ARTICLE_CREATED_EVENT",
    "ARTICLE_UPDATED_EVENT",
    "CANONICAL_CREATED_EVENT",
    "CANONICAL_DELETED_EVENT",
    "CANONICAL_EVIDENCE_CHANGED_EVENT",
    "CANONICAL_MERGED_EVENT",
    "CANONICAL_UPDATED_EVENT",
    "EVENT_SCHEMA_VERSION",
    "RUN_CANCELLED_MESSAGE",
    "RUN_COMPLETED_EVENT",
    "WEBHOOK_TEST_EVENT",
    "ArticleCreated",
    "ArticleUpdated",
    "CanonicalCreated",
    "CanonicalDeleted",
    "CanonicalEvidenceChanged",
    "CanonicalMerged",
    "CanonicalUpdated",
    "CursorExpiredError",
    "DomainEvent",
    "EventEnvelope",
    "EventScope",
    "RecordedEvent",
    "RunCompleted",
    "RunCompletedCounts",
    "RunCompletedData",
    "WebhookDestinationError",
    "build_signature_headers",
    "decode_event_cursor",
    "display_host_for_url",
    "encode_event_cursor",
    "envelope_from_event",
    "event_type_is_flow_scoped",
    "event_type_is_registered",
    "materialize_run_output_snapshot",
    "normalize_run_outcome",
    "pop_recorded_events",
    "record_article_created",
    "record_article_updated",
    "record_canonical_created",
    "record_canonical_deleted",
    "record_canonical_evidence_changed",
    "record_canonical_merged",
    "record_canonical_updated",
    "record_event",
    "record_run_output_article",
    "record_run_terminal_event",
    "registered_event_types",
    "sign_webhook_payload",
    "suppress_canonical_evidence_events",
    "suppress_events",
    "validate_webhook_url",
    "webhooks_enabled",
]
