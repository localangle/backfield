# Webhooks and the event feed

Backfield can send a signed HTTP notification to another application when
things happen in a project — runs finishing, articles being saved, Stylebook
canonicals changing — backed by a durable project event feed. This document is
the source of truth for the event contract, delivery semantics, security
policy, and operations.

## Feature gate

Everything below is gated by `BACKFIELD_WEBHOOKS_ENABLED` (off by default in
production until the scheduled recovery pass and delivery alerts are deployed).
The local Compose stack enables it, together with
`BACKFIELD_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS=1` so local receivers work.
When the gate is off, no events or deliveries are recorded; run-attempt article
snapshots are still materialized because the public run-articles endpoint
depends on them.

## Event types

| Type | Scope | Recorded when |
| --- | --- | --- |
| `agate.run.completed` | flow | A run attempt reaches a terminal state (succeeded, failed, cancelled, timed out), from every trigger source. Supports the outcome filter (`succeeded` / `failed`). |
| `agate.article.created` | flow | DBOutput persists an article for the first time. |
| `agate.article.updated` | flow | An existing article is re-persisted by a run (`change: "reprocessed"`, with `content_changed`) or its review metadata changes through the Agate API (`change: "metadata"`). Coalesced per article per transaction. |
| `stylebook.canonical.created` | project-wide | A canonical entity (location, person, organization) is created — standalone, materialized from a candidate, or accepted in review. |
| `stylebook.canonical.updated` | project-wide | A canonical's fields or geometry are edited in Stylebook. |
| `stylebook.canonical.deleted` | project-wide | A canonical is deleted (manual, cleanup, or orphan pruning). |
| `stylebook.canonical.merged` | project-wide | A canonical is folded into another; the event is scoped to the retired source ID and `data.merged_into` names the target. |
| `stylebook.canonical.evidence.changed` | project-wide | The substrate evidence behind a canonical changes (mention linked or unlinked). Coalesced per canonical per transaction; merges and deletes suppress the per-link noise they would otherwise cascade. |

Flow-scoped types match per-flow subscriptions and "all flows" subscriptions;
project-wide types always apply to the whole project. Canonicals live in a
stylebook shared by multiple projects, so one canonical change **fans out** to
one event per project attached to that stylebook.

Event emission is first-class: every type is a `DomainEvent` subclass
registered in `backfield_events.events`, and call sites emit through one
entrypoint — `record_event(session, event)` (or the typed
`record_*` convenience wrappers) — inside the same open transaction as the
domain mutation. The registry drives admin validation and the UI event picker.

## Scope

- Endpoints are **project-scoped** and managed by **organization admins** in
  Settings → Webhooks (session API under
  `/v1/organizations/{org_id}/webhook-endpoints`). Up to **10 active endpoints
  per project**; each endpoint chooses its event types and either explicit
  flows or all flows.
- Payloads are **thin**: receivers pull details through the public API (run
  status, run articles, articles, canonicals, event feed) using ordinary
  project API keys. Webhook signing secrets and project API keys are separate
  credentials.
- Run starts, connection events, and arbitrary node or S3 outputs are out of
  scope.

## Event model

- `backfield_event` rows are immutable, per-project, and ordered by a bigint
  sequence. `graph_id` / `run_id` / `article_id` / `entity_type` / `entity_id`
  are plain snapshots so feed history survives flow, run, article, and
  canonical deletion. Retention is **90 days**; older events are purged by the
  maintenance pass.
- Events are recorded **in the same database transaction** as the domain
  mutation (`record_event` in `packages/backfield-events`), together with one
  pending delivery per matching active endpoint. A rollback leaves no event or
  delivery behind. Recorded results are stashed on the session and drained
  after commit (`pop_recorded_events`) to kick the delivery dispatcher.
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

`data` payloads per type (all typed in `backfield_events.contracts`):

- `agate.run.completed` — `outcome` (`succeeded` / `failed`),
  `completion_reason` (`completed` / `error` / `cancelled`), normalized
  `failure_category`, item `counts`, `article_count`.
- `agate.article.created` — `headline`.
- `agate.article.updated` — `headline`, `change` (`reprocessed` / `metadata`),
  `content_changed` (for reprocessed articles).
- `stylebook.canonical.created|updated|deleted` — `label`.
- `stylebook.canonical.merged` — `label`, `merged_into` (target canonical ID).
- `stylebook.canonical.evidence.changed` — `label`, `change`
  (`substrate_linked` / `substrate_unlinked`).

`links` carries `run` and `articles` for run-scoped events, `article` for
article events, and `entity` (the public canonical URL) for stylebook events.
Flow and run refs are null for stylebook events. Raw run results, article
bodies, and credentials are never included.

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
   Filter with repeatable `flow_id` and `type` query parameters.
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
  validation, the typed event registry (`events.py`), run/article/canonical
  event classes, transactional recording, claim/terminalize helpers.
- `packages/backfield-entities` — canonical event call sites in the shared
  persist/merge/delete/link mutation helpers.
- `packages/backfield-db` — models and migrations `074_webhooks_and_events`
  and `075_event_scopes_all_flows`.
- `apps/worker/src/worker/webhooks/` — HTTP sender and delivery orchestration;
  `apps/worker/src/worker/webhook_maintenance.py` — scheduled pass. Article
  events are emitted from `nodes/db_output.py`.
- `apps/stylebook-api/src/stylebook_api/webhook_dispatch.py` — post-commit
  dispatcher kick for canonical events recorded during Stylebook requests.
- `apps/core-api/src/core_api/webhooks_admin.py`, `webhook_verification.py`,
  `routers/org_webhooks.py` — org-admin management API.
- `apps/core-api/src/core_api/routers/public/events.py` and
  `routers/public/runs/articles.py` — public pull surface.
- `apps/agate-ui/src/pages/WebhooksSettings.tsx` — Settings → Webhooks.
- `tests/smoke/smoke_webhooks.py` — live-stack smoke with a local receiver.
