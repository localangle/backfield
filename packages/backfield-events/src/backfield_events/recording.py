"""Shared recording primitives: status constants, results, and outcome filters.

Event recording itself lives in ``backfield_events.events`` (typed event
classes plus the ``record_event`` entrypoint); this module holds the pieces
shared by recording, delivery bookkeeping, and the admin API without creating
import cycles.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from backfield_db import BackfieldWebhookSubscription

ENDPOINT_STATUS_PENDING = "pending"
ENDPOINT_STATUS_ACTIVE = "active"
ENDPOINT_STATUS_PAUSED = "paused"
ENDPOINT_STATUS_DISABLED = "disabled"

DELIVERY_STATE_PENDING = "pending"
DELIVERY_STATE_DELIVERING = "delivering"
DELIVERY_STATE_DELIVERED = "delivered"
DELIVERY_STATE_FAILED = "failed"


@dataclass(frozen=True)
class RecordedEvent:
    event_id: int
    event_uuid: str
    delivery_ids: tuple[str, ...]


def subscription_matches_outcome(
    subscription: BackfieldWebhookSubscription,
    outcome: str,
) -> bool:
    """NULL outcome filter means all outcomes; otherwise a JSON array of outcomes."""
    if not subscription.outcomes_json:
        return True
    try:
        outcomes = json.loads(subscription.outcomes_json)
    except ValueError:
        return True
    if not isinstance(outcomes, list) or not outcomes:
        return True
    return outcome in {str(item) for item in outcomes}
