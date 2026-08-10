# Webhooks and the event feed

Backfield can send a signed HTTP notification to another application when a
flow run finishes, backed by a durable project event feed. This document is the
source of truth for the event contract, delivery semantics, security policy,
and operations.

## Feature gate

Everything below is gated by `BACKFIELD_WEBHOOKS_ENABLED` (off by default in
production until the scheduled recovery pass and delivery alerts are deployed).
The local Compose stack enables it, together with
`BACKFIELD_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS=1` so local receivers work.
When the gate is off, no events or deliveries are recorded; run-attempt article
snapshots are still materialized because the public run-articles endpoint
depends on them.

## Scope of v1

- One event type: **`agate.run.completed`**, recorded for every terminal run
  attempt (succeeded, failed, cancelled, timed out) from every trigger source.
- Endpoints are **project-scoped** and managed by **organization admins** in
  Settings → Webhooks (session API under
  `/v1/organizations/{org_id}/webhook-endpoints`). Up to **10 active endpoints
  per project**; each endpoint subscribes to explicitly selected flows and may
  filter on outcome (`succeeded` / `failed`).
- Payloads are **thin**: receivers pull details through the public API (run
  status, run articles, event feed) using ordinary project API keys. Webhook
  signing secrets and project API keys are separate credentials.
- Post-run editorial changes (article edits, canonical updates) are **not**
  reported; they need a future `article.updated` / canonical event family.
  Arbitrary node or S3 outputs are also out of scope.

## Event model

- `backfield_event` rows are immutable, per-project, and ordered by a bigint
  sequence. `graph_id` / `run_id` are plain text snapshots so feed history
  survives flow and run deletion. Retention is **90 days**; older events are
  purged by the maintenance pass.
- Events are recorded **in the same database transaction** as the run's
  terminal status change (`record_run_terminal_event` in
  `packages/backfield-events`), together with one pending delivery per matching
  active endpoint. A rollback leaves no event or delivery behind.
- Run attempts: `agate_run.execution_attempt` starts at 1 and increments only
  when a terminal run is explicitly rerun; worker claim/recovery keeps the
  current attempt. Every terminal attempt records its own event, and each
  attempt keeps an immutable `agate_run_output_article` snapshot of the
  articles it persisted.

### Envelope

Webhook bodies and feed items share one versioned envelope
(`backfield_events.contracts.EventEnvelope`, `schema_version` 1):

```json
{
  "id": "<event uuid>",
  "sequence": 123,
  "type": "agate.run.completed",
  "schema_version": 1,
  "occurred_at": "2026-08-10T12:00:00Z",
  "project": "general",
  "flow": {"id": "<graph uuid>", "name": "My flow"},
  "run": {"id": "<run uuid>", "attempt": 1, "url": "https://.../runs/<id>"},
  "data": {
    "outcome": "succeeded",
    "completion_reason": "completed",
    "failure_category": null,
    "counts": {"total": 3, "succeeded": 3, "failed": 0},
    "article_count": 2
  },
  "links": {"run": "...", "articles": ".../articles?attempt=1"}
}
```

`outcome` is `succeeded` or `failed`; `completion_reason` is `completed`,
`error`, or `cancelled`. `failure_category` is a normalized label, never raw
provider error text. Raw run results, article bodies, and credentials are never
included.

## Delivery semantics

- **At-least-once.** Consumers must deduplicate on the event `id`
  (`Backfield-Event-Id`); the event ID and body stay stable across retries,
  while manual replays get a new `Backfield-Delivery-Id`.
- Deliveries are claimed with expiring lease tokens
  (`backfield_events.delivery`, following the S3 ingestion ledger pattern): the
  claim transaction commits before any HTTP, and completion updates are fenced
  on the lease token so a stale worker cannot clobber a reclaimed delivery.
- **Retries:** network errors, timeouts, `408`, `429`, and `5xx` retry with
  exponential backoff and jitter (30s base, 1h cap, bounded `Retry-After`
  honored) for up to **24 hours**. Other `4xx` responses terminalize the
  delivery. Redirects are not followed.
- **Auto-pause:** the first delivery that exhausts the retry window pauses the
  endpoint (`pause_reason=delivery_retries_exhausted`); no new deliveries are
  created while paused. The UI shows an in-app warning. Reactivation resumes
  **future events only** — consumers recover the gap from the event feed.
- Dispatch: terminal commits send a best-effort Celery kick
  (`worker.tasks.dispatch_webhook_deliveries` fans out to
  `worker.tasks.deliver_webhook`); the scheduled recovery pass remains
  authoritative.

## Verifying signatures

Each delivery sends:

| Header | Meaning |
| --- | --- |
| `Backfield-Event-Id` | Stable event UUID (dedupe key) |
| `Backfield-Delivery-Id` | Unique per delivery (new on manual replay) |
| `Backfield-Event-Type` | e.g. `agate.run.completed` |
| `Backfield-Timestamp` | Unix seconds when the attempt was signed |
| `Backfield-Signature` | `v1=<hex HMAC-SHA256>` |

Verify by recomputing `HMAC-SHA256(secret, "{timestamp}.{raw_body}")` and
comparing constant-time against the `v1=` value
(`backfield_events.signing.verify_webhook_signature`). Reject stale timestamps
according to your own tolerance. The signing secret is shown exactly once at
creation or rotation; rotation (and any URL change) returns the endpoint to
`pending` and requires a fresh successful test delivery before deliveries
resume.

## Endpoint lifecycle

`pending` → (successful signed test) → `active` → `paused` (auto, on exhausted
retries) or `disabled` (manual) → `active` again via the resume action (which
requires prior verification). New endpoints deliver nothing until a signed
synthetic test (`backfield.webhook.test`, delivery-only, never in the feed)
receives a `2xx`.

## Destination policy (SSRF)

Enforced at save time and re-checked on **every** delivery attempt
(`backfield_events.destinations`):

- HTTPS only outside local development; no embedded credentials or fragments.
- Hostnames are re-resolved per attempt; private, loopback, link-local,
  multicast, reserved, and metadata-service addresses are rejected.
- Redirects are never followed; connection/read/total timeouts and response
  size are bounded (`apps/worker/src/worker/webhooks/sender.py`).
- Logs and stored failure summaries never contain secrets, raw bodies, or
  secret-bearing URLs; endpoints expose only a sanitized display host.

## Recovery and retention operations

`python -m worker.webhook_maintenance` runs one recovery/retention pass:
process due deliveries (anything the post-commit kick missed), purge events
older than 90 days, and emit pending-age gauges. Production should schedule it
about every 60 seconds using the same EventBridge-style scheduled-command
pattern as the metrics collector (see
[`../OBSERVABILITY.md`](../OBSERVABILITY.md)). It exits immediately when the
feature gate is off.

## Consumer recovery contract

1. Store the `cursor` of each processed feed item (or the sequence from
   webhook envelopes).
2. On webhook gaps (pause, outage, missed deliveries), page
   `GET /public/v1/projects/{slug}/events?cursor=...` forward until caught up.
3. A `410 cursor_expired` means the cursor predates the 90-day retention
   window; restart without a cursor.

See [`../api/public.md`](../api/public.md) for the feed and run-articles
endpoint details.

## Metrics

Low-cardinality only (no project, endpoint, URL, or error dimensions):
`webhook_delivery_attempts_total`, `webhook_delivery_failures_total`,
`webhook_delivery_duration_seconds`, `webhook_deliveries_dead_total`,
`webhook_endpoints_paused_total`, `webhook_deliveries_pending`, and
`webhook_deliveries_pending_age_seconds`.

## Code map

- `packages/backfield-events` — contracts, signing, cursors, destination
  validation, transactional recording, claim/terminalize helpers.
- `packages/backfield-db` — models and migration `074_webhooks_and_events`.
- `apps/worker/src/worker/webhooks/` — HTTP sender and delivery orchestration;
  `apps/worker/src/worker/webhook_maintenance.py` — scheduled pass.
- `apps/core-api/src/core_api/webhooks_admin.py`, `webhook_verification.py`,
  `routers/org_webhooks.py` — org-admin management API.
- `apps/core-api/src/core_api/routers/public/events.py` and
  `routers/public/runs/articles.py` — public pull surface.
- `apps/agate-ui/src/pages/WebhooksSettings.tsx` — Settings → Webhooks.
- `tests/smoke/smoke_webhooks.py` — live-stack smoke with a local receiver.
