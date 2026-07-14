# Runtime configuration

Backfield services are configured through environment variables. Keep connection strings and secrets out of images, use the same shared values on every service that participates in a contract, and distinguish pooled runtime database traffic from direct administrative traffic.

## Service identity and routing

- `BACKFIELD_ENV` or `ENVIRONMENT`: deployment label on structured log lines; defaults to `development`. Core API also uses `ENVIRONMENT=production` to apply production cookie behavior.
- `BACKFIELD_HTTP_PATH_PREFIX`: optional prefix stripped before API routing, such as `/api/agate` or `/api/stylebook`.
- `APP_VERSION`, `GIT_SHA`, `BUILD_TIME`: build identity returned by API `/version` and emitted at worker startup.
- `UI_ORIGIN` / `UI_ORIGINS`: allowed browser origins for API access.

All APIs and the worker emit JSON lines to stderr. API request logs exclude health/version paths and carry shared context such as service, environment, request ID, client, run ID, and job ID. Celery tasks emit task start/end events.

Health endpoints are `GET /health` on Agate API, Stylebook API, and Core API.

## Database

- `BACKFIELD_DATABASE_URL` or `DATABASE_URL`: application database connection string.
- `BACKFIELD_DATABASE_URL_DIRECT`: direct PostgreSQL connection for migrations and administrative commands. Migration tooling prefers this value when present.
- `BACKFIELD_ALEMBIC_ROOT`: directory containing `alembic.ini` and `alembic/`; the Agate API production image sets it.
- `BACKFIELD_SQLALCHEMY_POOL_SIZE`, `BACKFIELD_SQLALCHEMY_MAX_OVERFLOW`: per-process SQLAlchemy pool settings. SQLAlchemy defaults are 5 and 10 when unset.
- `BACKFIELD_PG_STATEMENT_TIMEOUT_MS`, `BACKFIELD_PG_LOCK_TIMEOUT_MS`: PostgreSQL statement and lock limits. Apply these to APIs so reads fail promptly during worker write contention; local Compose uses 30000 and 5000.

Local Compose routes runtime traffic through PgBouncer in transaction mode and sends migration traffic directly to PostgreSQL. API pools default to size 3 with overflow 2. The worker maps `WORKER_BACKFIELD_SQLALCHEMY_POOL_SIZE` and `WORKER_BACKFIELD_SQLALCHEMY_MAX_OVERFLOW` to its runtime pool, defaulting to 1 and 0. Each Celery child owns a pool, so worker concurrency multiplies database capacity requirements.

## Authentication and encryption

- `MASTER_ENCRYPTION_KEY`: one Fernet key shared by Agate API, Core API, Stylebook API, and worker. It protects project and organization integration secrets.
- `SESSION_SECRET`: one signing key shared by every service that verifies the session cookie.
- `SESSION_COOKIE_DOMAIN`: optional production cookie domain used by Core API login and logout when sibling hosts share a session.
- `SERVICE_API_TOKEN` or `SERVICE_API_TOKENS`: Bearer token or token set for service-to-service access.

Never use Compose development defaults in production. An empty environment value is not equivalent to an unset value and can mask a safe local default with an unusable secret.

## Redis and Celery

- `REDIS_URL`: Celery broker/backend for Agate enqueueing, worker execution, Core public run triggers, and asynchronous Stylebook jobs.
- `CELERY_QUEUE`: queue name; defaults to `agate`.
- `CELERY_WORKER_CONCURRENCY`: prefork child count; defaults to 16 in the worker image and Compose.
- `CELERY_PREFETCH_MULTIPLIER`: defaults to 1.
- `CELERY_MAX_TASKS_PER_CHILD`: defaults to 1 to release retained Python heap between articles.
- `CELERY_MAX_MEMORY_PER_CHILD_KB`: defaults to 1048576 (1 GiB) and replaces a child after a completed task exceeds the limit.
- `CELERY_LOG_LEVEL`: defaults to `info`.

The worker app name is `agate_worker`. Queue task families include whole-run and per-item execution, S3 batch setup/finalization and reviewed-output synchronization, Stylebook bundle transfer, semantic reindexing, cleanup checks and AI review, and candidate AI review.

## Execution concurrency and time limits

- `BACKFIELD_PARALLEL_GRAPH_LEVELS`: enables predecessor-ready node execution inside one item. Local Compose defaults to `1`; set `0` for sequential topological execution.
- `AGATE_NODE_TIMEOUT_S`: async node wall-clock timeout; code default 600 seconds.
- `TASK_SOFT_TIME_LIMIT`, `TASK_HARD_TIME_LIMIT`: Celery limits for processed items. Local Compose uses 900 and 1080 seconds. Code fallbacks outside Compose are 3600 and 4200.
- `TASK_STALE_RUNNING_GRACE_S`: extra time before an over-limit running item is considered stale; defaults to 300 seconds.
- `BATCH_ORPHAN_RUNNING_AFTER_S`: age at which an inactive running claim can return to pending; defaults to 120 seconds.
- `BATCH_ORPHAN_RECONCILE_INTERVAL_S`: claim reconciliation throttle; defaults to 30 seconds.
- `CANONICAL_ADJUDICATION_MAX_CONCURRENT`: parallel LLM calls per Backfield Output domain pass; defaults to 8.
- `CANDIDATE_AI_REVIEW_MAX_CONCURRENT`: parallel candidate-review LLM work; defaults to the lower of adjudication concurrency and 3.
- `DBOUTPUT_MAX_CONCURRENT_PERSISTS`: Redis-backed cap on concurrent persistence sections across worker children; defaults to 8 and `0` disables the gate.
- `DBOUTPUT_PERSIST_LOCK_TTL_S`: persistence-gate lock lifetime; defaults to 1800 seconds.

Tune database-write concurrency before reducing extraction concurrency when worker writes affect API latency. Do not lower the processed-item soft limit below a node's configured LLM timeout plus its execution buffer.

S3 batch setup dispatches longer text first and fans items out as a Celery chord. The parent run stores a graph-spec snapshot so edits made after dispatch do not change in-flight children. `S3_BATCH_MAX_INFLIGHT` is reserved and does not currently bound dispatch.

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

Project secret values override organization integration values when the same environment name is present. `STYLEBOOK_API_URL`, `PROJECT_SLUG`, and `SERVICE_API_TOKEN` enable worker/node access to Stylebook caching and APIs.

Overpass controls:

- `OVERPASS_API_URL`: primary interpreter
- `OVERPASS_MIRROR_URLS`: comma-separated fallbacks
- `OVERPASS_USER_AGENT`: descriptive request identity
- `OVERPASS_MAX_CONCURRENT`: per-process request cap; code default 1, local Compose default 4
- `OVERPASS_QUERY_STAGGER_S`: delay between related queries; code default 1.0, local Compose default 0.5

Public Overpass instances rate-limit parallel workloads. The client honors `Retry-After`, retries transient overload responses, validates JSON responses, and falls back across mirrors.

## S3 input, output, and Stylebook bundles

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`: S3 credentials.
- `AWS_S3_ENDPOINT_URL` or `AWS_ENDPOINT_URL`: optional S3-compatible endpoint.
- `STYLEBOOK_BUNDLE_S3_BUCKET`: staging bucket for Stylebook import/export. Bundle job routes return 503 when unset.
- `STYLEBOOK_BUNDLE_S3_PREFIX`: object prefix; defaults to `stylebook-bundles`.
- `AGATE_TIMEZONE`: S3 Output date partition timezone; defaults to `America/Chicago`.

Set bundle credentials on both Stylebook API and worker. The browser uploads import bundles through Stylebook API, so the bucket does not need browser upload CORS. Export downloads use presigned GET URLs.

In local Compose, put bundle variables in the root `.env`. Do not add an empty `${STYLEBOOK_BUNDLE_S3_BUCKET}` service override: Compose environment entries take precedence over `env_file` and would mask the configured value.

## Canonical ingest

- `BACKFIELD_STRICT_CANONICAL_GATES`: deterministic autolink safeguards are enabled when unset or set to `1`. Set `0`, `false`, `no`, or `off` only for diagnosis; disabling the gates increases the risk of incorrect canonical merges.

## Local, demo, and CI bootstrap only

- `BACKFIELD_LOCAL_BOOTSTRAP`: Agate API startup ensures the default workspace/project and syncs allowlisted LLM/Azure keys; Compose defaults to `1`.
- `BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV`: Core API startup creates the first administrator only when no users exist.
- `BACKFIELD_BOOTSTRAP_ADMIN_EMAIL`
- `BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD` or `BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD_FILE`
- `BACKFIELD_BOOTSTRAP_ADMIN_DISPLAY_NAME`
- `BACKFIELD_BOOTSTRAP_ADMIN_STRICT`: defaults to `1`; missing required input makes Core API exit.

Do not enable these bootstrap paths for production provisioning. Use one-off migration and seed commands instead.
