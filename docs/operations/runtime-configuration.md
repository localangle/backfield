# Runtime configuration

Backfield services are configured through environment variables. Keep connection strings and secrets
out of images, use the same shared values on every service that participates in a contract, and
distinguish pooled runtime database traffic from direct administrative traffic.

This document describes configuration for local Compose and for systems that consume published
artifacts. **Production self-hosting from this checkout is unsupported**; first administrators are
provisioned with `backfield seed` / `backfield init`, not environment-variable admin bootstrap.

## Service identity and routing

- `BACKFIELD_CLIENT`: trusted deployment slug used as the EMF `Client` dimension. Required when
  application metrics are enabled; see [`../OBSERVABILITY.md`](../OBSERVABILITY.md).
- `BACKFIELD_ENV` or `ENVIRONMENT`: deployment label on structured log lines; defaults to
  `development`. Core API also uses `ENVIRONMENT=production` to apply production cookie behavior.
- `BACKFIELD_HTTP_PATH_PREFIX`: optional prefix stripped before API routing, such as `/api/agate`
  or `/api/stylebook`.
- `APP_VERSION`, `GIT_SHA`, `BUILD_TIME`: build identity returned by API `/version` and emitted at
  worker startup.
- `UI_ORIGIN` / `UI_ORIGINS`: allowed browser origins for API access.
- `PLAYGROUND_ORIGIN`: exact Playground origin allowed by Core and Stylebook API CORS for that
  deployment (for example `https://playground.{organization-slug}.backfield.news`). Local Compose
  already allows `http://localhost:5176` through `UI_ORIGINS` / localhost defaults.
- `PLAYGROUND_ORIGIN_REGEX`: optional CORS origin regex. Defaults to empty; leave unset in
  production and prefer an exact `PLAYGROUND_ORIGIN` per tenant deployment.

All APIs and the worker emit JSON lines to stderr. API request logs exclude health/version paths and
carry shared context such as service, environment, request ID, client, run ID, and job ID. Celery
tasks emit task start/end events.

Health endpoints are `GET /health` on Agate API, Stylebook API, and Core API.

Frontend cross-app destinations are build-time Vite settings. `VITE_AGATE_UI_ORIGIN` and
`VITE_STYLEBOOK_UI_ORIGIN` override tenant sibling-app discovery, `VITE_HELP_URL` overrides the Help
destination (default `https://docs.backfield.news`), and `VITE_PLAYGROUND_URL` overrides the hosted
API Playground destination. Local Agate and Stylebook builds otherwise link to
`http://localhost:5176`; production builds derive
`https://playground.{organization-slug}.backfield.news`. A custom `VITE_PLAYGROUND_URL` may contain
the literal `{organization_slug}` placeholder or identify a fixed tenant deployment.

## Database

- `BACKFIELD_DATABASE_URL` or `DATABASE_URL`: application database connection string.
- `BACKFIELD_DATABASE_URL_DIRECT`: direct PostgreSQL connection for migrations and administrative
  commands. Migration tooling prefers this value when present.
- `BACKFIELD_ALEMBIC_ROOT`: directory containing `alembic.ini` and `alembic/`; the Agate API
  production image sets it.
- `BACKFIELD_SQLALCHEMY_POOL_SIZE`, `BACKFIELD_SQLALCHEMY_MAX_OVERFLOW`: per-process SQLAlchemy
  pool settings. SQLAlchemy defaults are 5 and 10 when unset.
- `BACKFIELD_PG_STATEMENT_TIMEOUT_MS`, `BACKFIELD_PG_LOCK_TIMEOUT_MS`: PostgreSQL statement and lock
  limits. Apply these to APIs so reads fail promptly during worker write contention; local Compose
  uses 30000 and 5000.

Local Compose routes runtime traffic through PgBouncer in transaction mode and sends migration
traffic directly to PostgreSQL. `PGBOUNCER_DEFAULT_POOL_SIZE` (default **32**, capped by
`MAX_DB_CONNECTIONS=80`) sets server connections; at 20, API reads queued behind worker persists
during large batches. API pools default to size 3 with overflow 2. The worker maps
`WORKER_BACKFIELD_SQLALCHEMY_POOL_SIZE` and `WORKER_BACKFIELD_SQLALCHEMY_MAX_OVERFLOW` to its
runtime pool, defaulting to **2** and **1** (headroom for a nested checkout during post-persist
embedding auth; not a substitute for the Redis persist gate). Each Celery child owns a pool, so
worker concurrency multiplies database capacity requirements.

## Authentication and encryption

- `MASTER_ENCRYPTION_KEY`: one Fernet key shared by Agate API, Core API, Stylebook API, and worker.
  It protects project and organization integration secrets.
- `SESSION_SECRET`: **required** signing key shared by every service that verifies the session
  cookie. There is no built-in application default; unset or empty values fail when creating or
  verifying session tokens (not at package import). Local Compose may inject a development default
  when the variable is absent from the host environment; `backfield init` generates a value into
  `.env`. Never reuse Compose development defaults outside local development.
- `SESSION_COOKIE_DOMAIN`: **optional**. When unset or blank, Core API omits the cookie `Domain`
  attribute (host-only cookies). Set it only when sibling hosts must share a session (for example
  a production cookie domain consumed by a separate deployment system). The tenant Playground
  requires a shared parent domain such as `.backfield.news` so its requests to the tenant Core and
  Stylebook APIs include the signed-in session.
- `SERVICE_API_TOKEN` or `SERVICE_API_TOKENS`: Bearer token or token set for service-to-service
  access.

Never use Compose development defaults in a deployed environment. An empty environment value is not
equivalent to an unset value and can mask a safe local default with an unusable secret.

## Redis and Celery

- `REDIS_URL`: Celery broker/backend for Agate enqueueing, worker execution, Core public run
  triggers, public API rate limiting, and asynchronous Stylebook jobs.
- `BACKFIELD_PUBLIC_RATE_LIMIT_ENABLED`: enables Core public API rate limiting; defaults to `1`.
- `BACKFIELD_PUBLIC_RATE_LIMIT_READS_PER_MINUTE`: standard read limit per API key; defaults to 600.
- `BACKFIELD_PUBLIC_RATE_LIMIT_SEARCH_PER_MINUTE`: semantic/geographic search limit per API key;
  defaults to 60.
- `BACKFIELD_PUBLIC_RATE_LIMIT_RUNS_PER_MINUTE`: public run-trigger limit per API key; defaults to 5.
- `BACKFIELD_PUBLIC_RATE_LIMIT_CLEANUP_EXPORT_PER_MINUTE`: limit for the preview cleanup canonical
  export per API key; defaults to 30.
- `BACKFIELD_CLEANUP_SNIPPET_MAX_CHARS`: longest article snippet the preview cleanup evidence
  routes may return, whatever a caller asks for; defaults to 500. `0` turns snippet text off (the
  mention text and article references are still returned).
- `BACKFIELD_CLEANUP_CEILING_MERGE`, `_EDIT`, `_ALIAS`, `_DISMISSAL`, `_RETIREMENT`,
  `_DELETION`: most applied actions of each kind one preview cleanup run may hold. Defaults are
  5000, 5000, 5000, 5000, 500, and 200. Read on every request, so a Core API restart is enough to
  change them. A negative or unreadable value falls back to the default; `0` stops that operation.
- `CELERY_QUEUE`: queue name; defaults to `agate`.
- `CELERY_WORKER_CONCURRENCY`: prefork child count; defaults to 16 in the worker image and Compose.
- `CELERY_PREFETCH_MULTIPLIER`: defaults to 1.
- `CELERY_MAX_TASKS_PER_CHILD`: defaults to 1 to release retained Python heap between articles.
- `CELERY_MAX_MEMORY_PER_CHILD_KB`: defaults to 1048576 (1 GiB) and replaces a child after a
  completed task exceeds the limit.
- `CELERY_LOG_LEVEL`: defaults to `info`.

The worker app name is `agate_worker`. Queue task families include whole-run and per-item execution,
S3 batch setup/finalization and reviewed-output synchronization, Stylebook bundle transfer, semantic
reindexing, cleanup checks and AI review, and candidate AI review.

Public limits also enforce project-aggregate buckets at four times each per-key limit. Internal
service tokens use a hash-derived identity rather than bypassing limits. Redis errors fail open and
emit a structured `public_rate_limit_redis_error` warning.

## Execution concurrency and time limits

- `BACKFIELD_PARALLEL_GRAPH_LEVELS`: enables predecessor-ready node execution inside one item. Local
  Compose defaults to `1`; set `0` for sequential topological execution.
- `AGATE_NODE_TIMEOUT_S`: async node wall-clock timeout; code default 600 seconds. Local Compose
  defaults to **1200**.
- `EXTRACT_LLM_ATTEMPT_TIMEOUT_S`: longest a single model request from an extract node (people,
  organizations, places, custom extract, article metadata) may take before it is retried; defaults
  to **120** seconds and is capped by the node's own `llmTimeout`. The node's `llmTimeout`
  (default 600 s) stays the total budget across retries, so a stalled request no longer uses the
  whole budget and fails the item before a retry can finish. `0` gives each request the whole
  budget.
- `TASK_SOFT_TIME_LIMIT`, `TASK_HARD_TIME_LIMIT`: Celery limits for processed items. Local Compose
  uses **1500** and **1800** seconds (above the node timeout with buffer). Code fallbacks outside
  Compose are 3600 and 4200.
- `TASK_STALE_RUNNING_GRACE_S`: extra time before an over-limit running item is considered stale;
  defaults to 300 seconds.
- `BATCH_ORPHAN_RUNNING_AFTER_S`: age at which an inactive running claim can return to pending;
  defaults to 120 seconds.
- `BATCH_ORPHAN_RECONCILE_INTERVAL_S`: claim reconciliation throttle; defaults to 30 seconds.
- `CANONICAL_ADJUDICATION_MAX_CONCURRENT`: parallel LLM calls per Backfield Output domain pass;
  defaults to **12** (Compose and code).
- `CANDIDATE_AI_REVIEW_MAX_CONCURRENT`: parallel candidate-review LLM work; defaults to the lower
  of adjudication concurrency and 3.
- `DBOUTPUT_MAX_CONCURRENT_PERSISTS`: Redis-backed cap on concurrent **transactional** persistence
  sections across worker children; defaults to **12** and `0` disables the gate. The slot covers
  entity writes, semantic-document sync, and payload upserts—not semantic embedding network I/O.
  Entity-matching model calls (people, organizations, locations) run with the slot handed back:
  the persist commits, frees its slot while the calls run, and waits for a slot again before
  applying the answers, so model latency does not hold database-write capacity.
- `DBOUTPUT_PERSIST_LOCK_TTL_S`: persistence-gate lock lifetime; defaults to 1800 seconds.

Semantic embedding and automatic connection inference both run **after** the persistence slot is
released (best-effort; failures do not roll back the persisted article). Connection-inference
guardrails are eight evidence pairs per request, sixteen requests per article (128 ranked
candidate pairs), forty created edges per pass, and two concurrent model calls per article.
Provider output-budget retries are disabled for these calls so hidden completion retries cannot
exceed the request budget; pairs beyond the request budget are reported as unprocessed.

Fleet-wide geocoder HTTP concurrency (Redis slots; `0` disables that provider's gate):

- `GEOCODE_PELIAS_MAX_CONCURRENT`: Geocode Earth / Pelias in-flight HTTP cap; code default 10,
  local Compose default **20** (helps miss bursts when Stylebook cache absorbs most places).
- `GEOCODE_PELIAS_MAX_RPS`: Pelias requests per second; defaults to **10** (Geocode Earth's hard
  cap). Enforced by a first-come, first-served ticket gate in Redis: each HTTP attempt (including
  retries) reserves the next free time slot, spaced `1 / RPS` apart, and sleeps until it arrives
  before taking a concurrency slot. Calls are smoothed evenly rather than released in
  per-second bursts. `0` disables the gate. Keep this at 10 even when raising concurrent.
- `GEOCODE_NOMINATIM_MAX_CONCURRENT`: Nominatim; defaults to 1. Public Nominatim allows about one
  request per second, so every worker shares this one slot.
- `NOMINATIM_LOOKUP_BUDGET_S`: hard time budget for one Nominatim lookup (waiting for the slot,
  the request, and pauses between rate-limit retries); defaults to 60. When it runs out the lookup
  returns no result, and natural places use the language-model estimate.
- `NOMINATIM_COOLDOWN_S`: after a lookup stays rate-limited until its budget or retries run out,
  every worker skips Nominatim for this many seconds (Redis-backed); defaults to 60, `0` disables.
  Waiting for a busy slot alone does not start a cool-down.
- `NOMINATIM_SEARCH_CACHE_TTL_S`: workers share non-empty Nominatim search answers through Redis
  for this many seconds, so a batch that names the same river or lake in many articles asks the
  public server once; defaults to 21600 (6 hours), `0` disables. Empty answers and failures are
  never cached.
- `GEOCODE_GEOCODIO_MAX_CONCURRENT`: Geocodio; defaults to 8.
- `GEOCODE_OVERPASS_MAX_CONCURRENT`: Overpass across all workers; defaults to 3.
- `GEOCODE_REQUEST_GATE_TTL_S`: lock TTL for a single gated request; defaults to 120 seconds.
- `GEOCODE_MAX_CONCURRENT`: per-article location fan-out inside GeocodeAgent only (code default 5,
  local Compose default **10**: high enough that the last few articles in a batch can keep Pelias busy,
  low enough to keep per-process memory in check across 100 concurrent items);
  does not replace the fleet gates above.
- `GEOCODE_DB_MAX_CONCURRENT`: how many of an article's location lookups against the Stylebook
  cache may hold a database connection at once (defaults to 1). Worker processes have a very small
  connection pool shared with the other nodes, so a high `GEOCODE_MAX_CONCURRENT` without this
  limit starves them (`QueuePool limit ... reached`). Extra lookups wait in line instead of timing
  out and falling back to an external geocode.

Tune database-write concurrency before reducing extraction concurrency when worker writes affect API
latency.

S3 (and JSON Input) batch setup uses a **sliding window** of in-flight processed items.
Dispatch order **interleaves longest and shortest** article bodies so the opening window is
not stacked with only the heaviest geocode/LLM work. `S3_BATCH_MAX_INFLIGHT` caps how many
item tasks run at once (default **100**; `0` = unlimited). When the batch is larger than the
cap, finishing items immediately start the next queued id from Redis (1:1 replace). Parent
finalize **replenishes only when nothing is running** (Redis first, then DB `pending`) so
stranded items cannot sit forever after a lost Celery message—without racing the 1:1 path and
overshooting the cap. Failed Celery enqueues re-push the id onto Redis. The parent run stores a
graph-spec snapshot so edits made after dispatch do not change in-flight children.

**S3 intake streams.** When a prefix holds more objects than `S3_BATCH_INTAKE_CHUNK_SIZE`
(default **50**) and the window cap is on, setup loads it in chunks instead of one pass: each
chunk reads its objects from S3 in parallel (`S3_BATCH_FETCH_WORKERS`, default **16**), skips
already-succeeded objects with one ledger query, commits its items, and queues them up to the
window cap while later chunks are still loading. Items therefore appear in the run and start
within seconds. The run's `s3_batch.intake_complete` flag stays `false` until the last chunk is
committed, and parent finalization waits for it so a fast first chunk cannot finish the run
early. Without Redis, with `S3_BATCH_MAX_INFLIGHT=0`, or for a prefix that fits one chunk, setup
keeps the single-pass behavior (no flag). `S3_BATCH_RAMP_SECONDS` (default **60**) staggers the
first window's starts evenly over that many seconds so items do not hit database persist and
provider calls in lockstep; refills after the first window start immediately. The worker logs
`s3_batch_intake_timing` with listing, S3 read, database, and queueing seconds. A worker crash
during intake leaves `intake_complete` false, so cancel and re-run the run.

## Model, geocoding, and search providers

Project and organization integration resolution can supply:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`
- `AZURE_API_KEY` with `AZURE_API_BASE`
- `PELIAS_API_KEY`
- `GEOCODIO_API_KEY`
- `BRAVE_SEARCH_API_KEY`

Configure AI credentials through **Settings → AI models** and platform credentials through
**Settings → Integrations**. Project overrides take precedence over organization integrations.
The Settings preset dropdown is generated from LiteLLM's model cost map at process start. LiteLLM
fetches that map from GitHub unless `LITELLM_LOCAL_MODEL_COST_MAP=true`, which forces the JSON
bundled in the installed package. Container environment keys remain available for unattended CI and
operator compatibility, but are not the normal credential-management path. `STYLEBOOK_API_URL`,
`PROJECT_SLUG`, and `SERVICE_API_TOKEN` enable worker/node access to Stylebook caching and APIs.

Overpass controls:

- `OVERPASS_API_URL`: primary interpreter
- `OVERPASS_MIRROR_URLS`: comma-separated fallbacks
- `OVERPASS_USER_AGENT`: descriptive request identity
- `OVERPASS_MAX_CONCURRENT`: per-process request cap; code default 1, local Compose default 4
  (the fleet-wide `GEOCODE_OVERPASS_MAX_CONCURRENT` also applies)
- `OVERPASS_LOOKUP_BUDGET_S`: hard time budget for one intersection lookup (slot waits, both
  queries, retries and backoff); defaults to 45. When it runs out the lookup fails and the
  intersection falls back to the language-model estimate.
- `OVERPASS_REQUEST_TIMEOUT_S`: per-request cap, also limited by the remaining budget; defaults to 30.
- `OVERPASS_ATTEMPTS_PER_ENDPOINT`: tries per interpreter for transient errors; defaults to 2.
- `OVERPASS_COOLDOWN_S`: after a lookup fails because the servers look overloaded, every worker
  skips Overpass for this many seconds (Redis-backed); defaults to 60, `0` disables.
- `OVERPASS_QUERY_STAGGER_S`: delay between related queries; code default 1.0, local Compose
  default 0.5

Public Overpass instances rate-limit parallel workloads. The client validates JSON responses and
falls back across mirrors. Capacity errors (HTTP 429, HTML "busy" pages) move straight to the next
mirror instead of retrying the same server, other transient errors retry within the budget, and
`Retry-After` is honored only when it fits the remaining budget.

GeocodeAgent location fan-out (`GEOCODE_MAX_CONCURRENT`) is per article. Geocode Earth
enforces ~10 HTTP req/s, which the Pelias ticket gate holds fleet-wide regardless of fan-out;
keep `GEOCODE_PELIAS_MAX_RPS` at 10 and prefer lowering
`S3_BATCH_MAX_INFLIGHT` (or worker concurrency) over raising Pelias RPS when soft-timeouts
appear. Raise RPS only if the provider quota increases.

## Flow S3 and Stylebook bundles

Configure S3 Input and S3 Output credentials through project or organization integrations. Bucket,
prefix, and region remain flow-node settings. Worker environment credentials are a compatibility
fallback, not the normal product configuration. `AGATE_TIMEZONE` controls S3 Output date partitions
and defaults to `America/Chicago`.

The access key and secret are required. An optional role ARN
(`platform.storage.s3_role_arn`, worker env `BACKFIELD_S3_ROLE_ARN`) tells the worker to call
`sts:AssumeRole` with those keys on each flow S3 client. Temporary credentials stay on that client
and refresh before the default one-hour session ends. Leave the role ARN blank to use the keys
directly, including an optional session token. A project override replaces the organization role;
clearing the override restores it. Stylebook bundle storage does not assume this role.

Stylebook bundle storage is operator infrastructure:

- `STYLEBOOK_BUNDLE_S3_BUCKET`: staging bucket for Stylebook import/export. Bundle job routes return
  503 when unset.
- `STYLEBOOK_BUNDLE_S3_PREFIX`: object prefix; defaults to `stylebook-bundles`.
- `AWS_S3_ENDPOINT_URL` or `AWS_ENDPOINT_URL`: optional S3-compatible endpoint.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`: explicit credentials
  when the standard AWS credential chain or task role is unavailable.

Set bundle configuration on both Stylebook API and worker. The browser uploads import bundles through
Stylebook API, so the bucket does not need browser upload CORS. Export downloads use presigned GET
URLs with a human-readable `Content-Disposition` filename
(`{slug}-stylebook-export-{YYYY-MM-DD}.zip`).

In local Compose, put bundle variables in the root `.env`. Do not add an empty
`${STYLEBOOK_BUNDLE_S3_BUCKET}` service override: Compose environment entries take precedence over
`env_file` and would mask the configured value.

## Canonical ingest

- `BACKFIELD_STRICT_CANONICAL_GATES`: deterministic autolink safeguards are enabled when unset or
  set to `1`. Set `0`, `false`, `no`, or `off` only for diagnosis; disabling the gates increases the
  risk of incorrect canonical merges.

## Local workspace bootstrap (not admin provisioning)

- `BACKFIELD_LOCAL_BOOTSTRAP`: Agate API startup ensures the default workspace/project; explicitly
  injected LLM/Azure keys are also synced for unattended local or CI compatibility. Compose defaults
  to `1`.

This flag does **not** create users or administrators. Provision the first admin with
`backfield init` or `backfield seed` only. See [local setup](../development/local-setup.md).
