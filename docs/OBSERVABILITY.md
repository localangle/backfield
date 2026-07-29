# Application observability (v1)

Cross-repo contract between this application repo and **backfield-cloud**. Cloud owns dashboards, alarms, IAM, ECS scheduling, and `client-status`. This app emits CloudWatch Embedded Metric Format (EMF) lines on stderr and correlated structured logs.

## Status

| Item | Decision | Cloud ack |
|------|----------|-----------|
| Namespace | `Backfield/Application` | **Acked** 2026-07-28 (backfield-cloud `docs/observability.md`, PR branch `chore/cleanup-and-docs`) |
| Completed metric names | Keep `runs_completed_total` / `items_completed_total`; **completed = transition to domain status `succeeded`** | **Acked** — do not rename without both repos |
| Service enum | `agate-api`, `stylebook-api`, `core-api`, `worker` | **Acked** — matches ECS container names |
| Queue / collector `Service` | `worker` | **Acked** |
| Client identity | `BACKFIELD_CLIENT` (deployment slug only) | **Acked** — cloud injects on all tasks |
| Publisher | EMF via JSON stderr (no app `PutMetricData`) | **Acked** — cloud owns log groups / EMF discovery |
| Collector schedule | Every **60s**, EventBridge → ECS RunTask using worker image | **Acked** and live on canary + CPM |
| Queue gauge authority | App collector EMF is authoritative; ECS Exec `LLEN` is diagnostic only | **Acked** |
| Worker entrypoint | Must `exec "$@"` when container command is set so collector is not Celery | **Fixed** in `apps/worker/scripts/entrypoint.sh` (this change); cloud temporary `entryPoint` override can be removed after this image is deployed |
| App implementation | Identity, EMF `log_metric()`, lifecycle/external metrics, collector command, cancel race fix, log scrubbing | Landed; cloud consumer live |

Do not diverge metric names or Service values without updating both repos.

## Dimensions

Required on every metric:

- `Client` — from `BACKFIELD_CLIENT`
- `Environment` — from `BACKFIELD_ENV` or `ENVIRONMENT`
- `Service` — from the locked enum above

Optional:

- `Operation` — only `llm` or `geocoding` (external-request metrics)

Never use as dimensions: `Version`, `RunId`, `JobId`, URLs, emails, raw error strings, provider/model, HTTP status, project/graph ids, or other high-cardinality fields. Those belong in logs (`version` stays on every log line).

## Metric table

| Metric | Type | Dimensions | Emit site | Notes |
|--------|------|------------|-----------|-------|
| `queue_depth` | gauge | Client, Environment, Service=`worker` | Collector (`LLEN`) | Shared Celery queue (`CELERY_QUEUE`, default `agate`) |
| `queue_oldest_age_seconds` | gauge | Client, Environment, Service=`worker` | Collector (`LINDEX` + publish header) | Headerless / undecodable messages → **omit** (unknown ≠ 0) |
| `runs_active` | gauge | Client, Environment, Service=`worker` | Collector (DB count) | `agate_run.status IN ('pending','running')` |
| `runs_completed_total` | counter | Client, Environment, Service | Worker / API terminal hooks | Transition to `succeeded` |
| `runs_failed_total` | counter | Client, Environment, Service | Worker / API terminal hooks | Transition to `failed` |
| `items_completed_total` | counter | Client, Environment, Service | Worker / API terminal hooks | Transition to `succeeded`; exclude `skipped` |
| `items_failed_total` | counter | Client, Environment, Service | Worker / API terminal hooks | Transition to `failed`; exclude claim→pending |
| `item_duration_seconds` | distribution | Client, Environment, Service | Same as item terminal | `terminal_at - started_at` (not `updated_at`) |
| `worker_lost_total` | counter | Client, Environment, Service=`worker` | Best-effort in-app | Incomplete; cloud owns ECS stop/OOM/SIGKILL |
| `external_request_failures_total` | counter | Client, Environment, Service, Operation | Transport wrappers | Transport/timeout/HTTP/malformed only; empty geocode ≠ failure |
| `external_request_duration_seconds` | distribution | Client, Environment, Service, Operation | Transport wrappers | Every physical attempt |

Counters are **approximate** (emit after commit). A transactional outbox is deferred.

## Identity and logs

| Field | Source | Notes |
|-------|--------|-------|
| `client` | `BACKFIELD_CLIENT` | Trusted deployment slug; required when metrics are enabled |
| `request_client` | HTTP `X-Client-ID` / user-agent / peer | Caller label only — never a metric dimension |
| `environment` | `BACKFIELD_ENV` / `ENVIRONMENT` | Default `development` |
| `service` | Hard-coded per process | Must match Service enum |
| `version` / `git_sha` | `APP_VERSION` / `GIT_SHA` | Logs only in v1 |
| `severity` | Mirror of level name | Prefer `severity` in new queries; keep `level` |
| `run_id`, `job_id`, `item_id` | Log context | Correlation; not metric dimensions |
| `operation`, `error_type`, `outcome` | External-call logs | Low-cardinality where possible |

Never log: secrets, auth headers, raw DB/Redis URLs, passwords, or customer content (addresses, article text, geocoder queries/results, provider bodies).

## Collector (cloud handoff)

- **Image:** production worker image.
- **Command:** `python -m worker.metrics_collector` (single shot; exit 0 after one emit pass).
  The worker image `ENTRYPOINT` must honor container command overrides via `exec "$@"`; otherwise
  ECS `command` is ignored and Celery starts instead of the collector.
- **Schedule:** every 60 seconds.
- **Network/secrets:** same Redis (`REDIS_URL`) and DB reachability as the worker; prefer a **read-only** DB role for counting active `agate_run` rows.
- **Environment:** `BACKFIELD_CLIENT` (required), `BACKFIELD_ENV` / `ENVIRONMENT`, `REDIS_URL`, `CELERY_QUEUE` (default `agate`), `BACKFIELD_DATABASE_URL` / `DATABASE_URL`.
- **No writes:** collector must not mutate Redis lists or application tables.
- **Failure mode:** on Redis/DB/decode failure, log a sanitized structured error and **omit** the affected gauge(s). Cloud must treat missing data as **degraded**, not healthy.
- **Not on Celery:** never enqueue the collector through the shared `agate` queue.
- **Idle / busy / stuck:** idle = depth 0 and `runs_active` 0; busy = positive depth/active with completion progress; stuck = positive/increasing `queue_oldest_age_seconds` with no completion progress, combined cloud-side with ECS worker health.

## Idle / busy / stuck

| State | App signals | Cloud also uses |
|-------|-------------|-----------------|
| Idle | `queue_depth=0`, `runs_active=0`, oldest age omitted or 0 | Healthy workers optional |
| Busy | Positive depth and/or `runs_active`, recent completion counters | — |
| Stuck | Positive / increasing `queue_oldest_age_seconds`, no completion progress | **No healthy worker** / ECS desired vs running |

## What this app does not cover

- CloudWatch dashboards, alarms, IAM beyond log ingestion, ECS task scheduling, `client-status` GetMetricData wiring.
- Complete `worker_lost_total` for container OOM / SIGKILL (cloud ECS stop reasons).
- Double-publishing queue depth from hot-path workers.
- Prometheus, StatsD, OpenTelemetry, high-cardinality per-run metrics.

## Acceptance (app side)

1. Synthetic success run moves `runs_completed_total` / `items_completed_total` / `item_duration_seconds` and logs correlate by `run_id`.
2. Deliberate failed job increments failure counters with correlated logs.
3. Collector distinguishes idle vs busy via depth + active; stuck needs oldest age (+ cloud worker health).
