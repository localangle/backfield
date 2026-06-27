# Operations

## Local stack

Primary local services are defined in `infra/docker-compose.yml`:

- PostGIS-enabled `postgres` on `localhost:5433` (data directory on the **`postgres_data`** named volume)
- `redis` on `localhost:6379`
- `agate-api` on `localhost:8000`
- `stylebook-api` on `localhost:8003`
- `core-api` on `localhost:8004`
- `agate-ui` on `localhost:5173`
- `stylebook-ui` on `localhost:5175`
- `worker` as the background Celery consumer

`agate-ui` is ordered **after** `core-api` and `agate-api` report **healthy** (HTTP `/health` checks) so the Vite dev proxy does not hit `ECONNREFUSED` while Uvicorn is still binding (notably when `agate-api` uses the reload worker).

`core-api` and the **`worker`** wait until the one-off **`migrate`** service has completed successfully and **`agate-api`** is healthy before they touch the database. Otherwise `core-api` can log *Env bootstrap skipped: identity tables missing* on a cold volume because Postgres was ready while migrations had not run yet.

## Canonical commands

Stack orchestration lives in the **`backfield` project launcher** — a repo-aware shell wrapper at **`scripts/backfield`**, not a Python `[project.scripts]` entry point. It finds the repo root, ensures `.venv` can import `backfield_cli`, repairs stale editable installs only when needed, and delegates to `python -m backfield_cli`. The Python package **`backfield-cli`** is an implementation detail.

**Bootstrap** (`make bootstrap`) runs `uv sync`, then copies the launcher to **`.venv/bin/backfield`**. Three equivalent ways to run stack commands:

1. **`make up`** / **`make down`** / **`make logs`** — calls `./scripts/backfield` (no venv activation required)
2. **`source .venv/bin/activate`** then **`backfield up`** — happy path for contributors
3. **`./scripts/backfield up`** — direct launcher invocation

Optional: **`make install-user-cli`** symlinks `~/.local/bin/backfield` → `scripts/backfield` for use without activating the venv (reversible with **`make uninstall-user-cli`**). Bootstrap does not modify shell profiles.

Run **`backfield doctor`** to check repo root, `uv`, Docker, `.venv`, `backfield_cli` import, `.env`, compose file, and launcher installation.

The launcher discovers `infra/docker-compose.yml` from the repo root by default; override with `--compose-file` or `BACKFIELD_COMPOSE_FILE`.

- `make up` / `backfield up` / `./scripts/backfield up`: bring up the local stack in the foreground (`up --build`). Add `--detached`/`-d` for background, `--no-build` to skip the image build. It does **not** run `docker volume prune` or `docker system prune`.
- `make down` / `backfield down`: `docker compose down` (stops and removes app containers, **not** Compose-managed volumes). The `make down` wrapper additionally runs `docker-trim` (`docker system prune -f` only). The Postgres data directory lives on the **`postgres_data`** named volume, so `down` then `up` keeps your local database. Run `make docker-prune-volumes` or `make docker-trim-full` explicitly when you want to reclaim unused volume disk.
- `make logs` / `backfield logs`: follow stack logs (`logs -f`). Pass service names to filter and `--no-follow` to print-and-exit.
- `backfield ps` / `backfield restart [service ...]`: list or restart stack containers.
- `make migrate`: run Alembic via the one-off compose **`migrate`** service. Use `make migrate-host` (`backfield migrate`) when Postgres is reachable on the host (e.g. `:5433`).
- **Production provisioning seed:** after migrations, run `backfield seed --admin-email … --admin-password …` (or `--admin-password-file`). The command ensures the organization (by slug, default `default`) and admin user (by email) exist; re-runs are a no-op and never change an existing admin password or role. Use `BACKFIELD_DATABASE_URL_DIRECT` when set (same as migrations). Local/CI env-flag bootstrap and `POST /v1/bootstrap/first-user` remain for development; prefer `backfield seed` in production.
- **Local first run:** `backfield init` (interactive) or `backfield init --non-interactive --config init.json` ensures repo-root `.env`, generates `MASTER_ENCRYPTION_KEY` / `SESSION_SECRET` when absent, starts Compose, runs migrations, waits for API `/readyz`, seeds admin/org/stylebook display names, and prints Agate UI URLs with numbered next steps (AI models, then Integrations, then [docs.backfield.news](https://docs.backfield.news)). Interactive runs show a banner, step-by-step progress, and **open Settings → AI models in your default browser** when complete. Disable auto-open with `--no-browser` or `BACKFIELD_NO_BROWSER=1`. Re-runs leave existing secrets and admin credentials unchanged.
- `backfield reset-db` (or `make reset-db`): tear down containers and volumes (`down -v`). The CLI prompts for confirmation unless `--yes` is passed (and refuses without `--yes` in a non-interactive shell); the `make` wrapper passes `--yes`.
- `backfield clear-entity-data` (or `make clear-entity-data`): truncate **`substrate_*`**, **`stylebook_*`** entity tables, and Agate **runs** (`agate_run`, `agate_processed_item`, plus run-linked **`backfield_ai_call_record`** rows) while the stack is running (local dev only). The CLI prompts unless `--yes` is passed; the `make` target additionally keeps its **`BACKFIELD_CONFIRM_CLEAR=1`** gate. Preserves Stylebook catalog shells (`stylebook`, `stylebook_membership`, `stylebook_slug_redirect`) and Agate **graphs/templates** (`agate_graph`, `agate_template`); does **not** remove **`backfield_*`** identity rows. Use when you want a clean entity/run slate without wiping Postgres entirely. Implementation: `packages/backfield-db/scripts/clear_entity_data.py` (connects to **`localhost:5433`** by default, same as smoke helpers).

When a migration is **destructive** toward existing Stylebook catalog data (for example revision **`019_stylebook_loc_canon_uuid`**), wipe the Postgres volume with **`make reset-db`** before **`make up`** / **`make migrate`** so Alembic applies cleanly; do not expect in-place upgrades from pre-UUID canonical integer ids.
- `make smoke-fast`: run the fast live-stack smoke bundle (`smoke-auth`, `smoke-agate-basic`, `smoke-stylebook-basic`).
- `make smoke`: run the Agate-to-Stylebook handoff lane against a live stack (`tests/smoke/golden_path_stack.py`). With **`SMOKE_EMAIL`** and **`SMOKE_PASSWORD`** set, it exercises Core login and **`GET /v1/me/workspaces`** before Agate; otherwise it uses the service Bearer path. This lane still needs whichever LLM keys the Starter flow model uses.
- `make smoke-runtime`: run the handoff lane plus `smoke-worker-async`.
- `make smoke-slower`: run `smoke-stylebook-editorial`, `smoke-stylebook-import-export`, and `smoke-s3-batch`.
- Most live smoke lanes delete their temporary graphs, runs, canonicals, and substrate rows when they finish. Set `SMOKE_KEEP_DATA=1` to preserve those artifacts for debugging.
- `make docker-prune-build`: reclaim disk from Docker build cache only (`docker builder prune -f`).
- `make docker-prune-system`: remove stopped containers, dangling images, unused networks, and build cache (`docker system prune -f`).
- `make docker-prune-volumes`: run `docker volume prune -f` (**unused** volumes only — after `make down`, Compose DB volumes are typically unused and **can be deleted**; use only when you intend to reclaim space or reset anonymous volumes).
- `make docker-trim`: runs `docker-prune-system` only (safe default before `make up` when the daemon is low on disk; preserves Postgres and other compose volumes across `down`/`up`).
- `make docker-trim-full`: runs `docker-trim` then `docker-prune-volumes` (aggressive reclaim; can wipe local DB data if nothing references those volumes).

Docker builds use the repo root as context; [.dockerignore](../.dockerignore) excludes optional large local `*.db` files under `packages/backfield-agate/.../geocoding/data/` so image builds do not copy multi-gigabyte artifacts if present on a developer machine.

**Production API images** (`agate-api`, `core-api`, `stylebook-api`) expose a multi-stage Dockerfile with a **`prod`** target (non-editable installs, no `--reload`) and a **`dev`** target (editable installs for local Compose). Build production images from the repo root:

```bash
make docker-build-prod-apis \
  APP_VERSION=v0.1.0 \
  GIT_SHA=$(git rev-parse HEAD) \
  BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

Each production image bakes `APP_VERSION`, `GIT_SHA`, and `BUILD_TIME` into the environment; `GET /version` on a running container reports those values. Local Compose uses `target: dev` explicitly.

**Production worker image** uses the same build-arg pattern. The worker is not an HTTP service; startup logs a JSON line with `event=worker_startup`, version metadata, and the resolved `CELERY_WORKER_CONCURRENCY`. Concurrency, prefetch, and child-process limits are driven from environment variables in `apps/worker/scripts/entrypoint.sh` (Compose default concurrency **16** via `CELERY_WORKER_CONCURRENCY`).

```bash
make docker-build-prod-worker \
  APP_VERSION=v0.1.0 \
  GIT_SHA=$(git rev-parse HEAD) \
  BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

**Production UI bundles** (`agate-ui`, `stylebook-ui`) use relative API paths (`/api/agate`, `/api/stylebook`, empty auth base → `/v1/...` on the same origin). Build from the repo root:

```bash
make ui-build          # both apps → apps/*/dist/
make agate-ui-build    # Agate only
make stylebook-ui-build
```

Each app ships [`.env.production`](../apps/agate-ui/.env.production) defaults loaded by `vite build`. Sync `dist/` to S3 (or any static host); path routing on the origin must forward `/v1`, `/api/agate`, and `/api/stylebook` to the matching APIs. See [`apps/agate-ui/DEPLOY.md`](../apps/agate-ui/DEPLOY.md) and [`docs/FRONTEND.md`](FRONTEND.md) → **Production static builds**.

**`agate-api`**, **`worker`**, and **`core-api` images** copy `packages/backfield-ai` and install editable wheels in dependency order (`backfield-db` → `backfield-ai` → …) because that package name is not published on PyPI (`agate-api` / `worker` continue with `agate-runtime` → `backfield-entities` → … as before).

## Runtime contracts

- Structured logs: all HTTP APIs and the worker emit **JSON lines** to stderr with shared fields (`service`, `environment`, `version`, `git_sha`, `request_id`, `client`, `run_id`, `job_id`, `event`, …). APIs log one `http_request` line per request (health/version paths excluded); Celery tasks log `task_start` / `task_end`. Set `BACKFIELD_ENV` or `ENVIRONMENT` (default `development`). Implementation: `packages/backfield-auth` (`structured_logging`, `request_logging_middleware`, worker `celery_logging` hooks).

- Agate worker queue: `agate`
- Worker task names:
  - `worker.tasks.execute_agate_run` — legacy whole-graph execution when no `agate_processed_item` rows exist (stores output on `agate_run` only).
  - Single **TextInput** / **JSONInput** runs — `POST /runs` creates one `agate_processed_item` and enqueues `execute_processed_item` (same per-item path as S3 batch children).
  - `worker.tasks.execute_s3_batch_setup` — lists/validates S3 JSON under the S3Input prefix, inserts **`agate_processed_item`** rows, then queues a **`chord`** of **`execute_processed_item`** tasks.
  - `worker.tasks.execute_processed_item` — one Celery task per queued item; runs `execute_graph` with an S3Input shim (parent **`agate_run.id`** remains **`BACKFIELD_RUN_ID`** for DBOutput / substrate).
  - `worker.tasks.finalize_s3_parent_run` — chord callback that aggregates parent **`agate_run`** status after all items finish.
  - `worker.tasks.export_stylebook_bundle` — builds a stylebook ZIP (**manifest + canonical JSONL shards only**; no aliases, meta, connections, or candidate-queue data) and uploads it to **`STYLEBOOK_BUNDLE_S3_BUCKET`** for org-admin download links from **stylebook-api**. Schema **3** exports **location** and **person** canonical rows (`canonical_location` / `canonical_person` shards under `canonicals/locations/` and `canonicals/people/`). Older bundles (schema **1** or **2**) contain location canonicals only (`kind: canonical`).
  - `worker.tasks.import_stylebook_bundle` — downloads a staged ZIP from the same bucket and imports **canonical location and person rows** into a **new** stylebook (new canonical UUIDs). Manifest schema **1**, **2**, or **3** is accepted; legacy `kind: canonical` shards are treated as locations.
- Worker app name: `agate_worker`
- Health endpoints:
  - Agate API: `GET /health`
  - Stylebook API: `GET /health`
  - Core API: `GET /health`

## Environment variables

- `BACKFIELD_ENV` / `ENVIRONMENT`: deployment label included on every structured log line (default **`development`** in local Compose).

### Runtime configuration surface (production)

All runtime connectivity and secrets are **environment-driven** — no hardcoded production hosts in application code. Confirm these are set in deployment (not only Compose dev defaults):

| Concern | Primary variables | Notes |
|--------|-------------------|-------|
| Database | `BACKFIELD_DATABASE_URL`, `DATABASE_URL`, `BACKFIELD_DATABASE_URL_DIRECT` | Runtime traffic uses the pooled URL; migrations use `_DIRECT` when set. |
| Redis / Celery | `REDIS_URL`, `CELERY_QUEUE`, `CELERY_WORKER_CONCURRENCY` | Required for async runs and worker execution. |
| Encryption | `MASTER_ENCRYPTION_KEY` | Required on **agate-api**, **worker**, **core-api**, **stylebook-api** for project/org secrets. |
| Session auth | `SESSION_SECRET` | Shared across services that verify the session cookie. |
| Service auth | `SERVICE_API_TOKEN` | Bearer token for service-to-service calls. |
| S3 bundles | `STYLEBOOK_BUNDLE_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_S3_ENDPOINT_URL` | Bundle import/export only; unset bucket disables bundle routes. |
| Stylebook worker access | `STYLEBOOK_API_URL` | Worker → Stylebook API base URL. |
| Build identity | `APP_VERSION`, `GIT_SHA`, `BUILD_TIME` | Baked into prod images; surfaced on `/version` and startup logs. |

**Local-only gaps (do not rely on in production):** Compose dev defaults for `MASTER_ENCRYPTION_KEY` and `SESSION_SECRET`; `BACKFIELD_LOCAL_BOOTSTRAP` project secret sync; `BACKFIELD_BOOTSTRAP_ADMIN_*` first-user creation; `POST /v1/bootstrap/first-user`. Production provisioning uses **`backfield migrate`** + **`backfield seed`** instead.

- `BACKFIELD_DATABASE_URL` / `DATABASE_URL`: runtime database connection string for `agate-api`, **`stylebook-api`**, `worker`, and **`core-api`**. Local Compose routes these through **PgBouncer** (`...@pgbouncer:6432/backfield`) so many client connections multiplex onto a bounded pool of Postgres backends.
- `BACKFIELD_DATABASE_URL_DIRECT`: optional direct Postgres URL for **migrations and admin** (`...@postgres:5432/backfield` in Compose). Alembic, `ensure_database_exists`, and `backfield migrate` prefer this when set so DDL and `CREATE DATABASE` bypass PgBouncer transaction pooling. Set on the **`migrate`** service in local Compose; runtime app code still uses the pooled URL.
- `BACKFIELD_SQLALCHEMY_POOL_SIZE` / `BACKFIELD_SQLALCHEMY_MAX_OVERFLOW`: optional SQLAlchemy pool sizing for `backfield_db.session.get_engine()` (defaults follow SQLAlchemy when unset: **5** / **10**). The local **`worker`** Compose service sets conservative defaults (**2** / **3**) so many Celery child processes plus API Uvicorn processes are less likely to hit Postgres **`max_connections`**. Raise these on the worker if you see pool timeouts under heavy parallel load.
- `BACKFIELD_STRICT_CANONICAL_GATES`: when **`1`** (default) or unset, DBOutput ingest applies deterministic Stylebook autolink gates in `entities.location.policy` (type deny-list, container-vs-POI, jurisdiction vs canonical columns, components vs formatted-address sanity, distance vs cached container city when a **`substrate_location_cache`** hit exists, polygon bbox size). Set to **`0`**, **`false`**, **`no`**, or **`off`** to disable those gates (use only for diagnosis—expect more wrong merges when off). See [docs/ARCHITECTURE.md](ARCHITECTURE.md).
- `REDIS_URL`: Celery broker and backend (required for **agate-api** enqueue, **core-api** public run trigger enqueue, **worker** execution, and **stylebook-api** when using async stylebook bundle export/import jobs).
- `STYLEBOOK_BUNDLE_S3_BUCKET`: S3-compatible bucket used to stage full stylebook ZIPs for the worker and for **stylebook-api** server-side transfers. **Agate UI** sends import ZIPs to **stylebook-api** first (same origin), which streams them to S3, so the bucket does **not** need browser CORS for uploads. Exports still use a presigned GET (typically opened in a new tab). Unset in Compose by default; bundle job routes return **503** until a bucket is configured. Pair with **`AWS_ACCESS_KEY_ID`** / **`AWS_SECRET_ACCESS_KEY`** (and optional **`AWS_SESSION_TOKEN`**) on **stylebook-api** and **worker**.
- `STYLEBOOK_BUNDLE_S3_PREFIX`: optional key prefix inside the bucket (default **`stylebook-bundles`**). Objects are written as `{prefix}/{organization_id}/{job_id}.zip` when the prefix is non-empty.
- **Compose:** set these in the **repository root** `.env` (same file as other dev keys). `stylebook-api` and `worker` load it via `env_file: ../.env`; do not rely on host-only `${STYLEBOOK_BUNDLE_S3_BUCKET}` interpolation in `docker-compose.yml` for that value, or an empty override can mask the file.
- `AWS_S3_ENDPOINT_URL` or `AWS_ENDPOINT_URL`: optional non-AWS endpoint (for example MinIO) for bundle staging and presigned URL signing; must match how the browser and worker reach the same object store.
- `CELERY_WORKER_CONCURRENCY`: optional override for the Agate worker process pool size (Compose passes **`--concurrency`**; default **16** when unset). Higher values improve S3 batch parallelism when many **`execute_processed_item`** tasks are in flight.
- `CELERY_MAX_TASKS_PER_CHILD`: restart each Celery child after this many tasks (Compose default **`1`**). Helps return Python heap to the OS between batch articles; Python often retains freed memory inside a long-lived process even when only one article runs at a time per child.
- `CELERY_MAX_MEMORY_PER_CHILD_KB`: replace a child when its resident set exceeds this many **kilobytes** after a task finishes (Compose default **`1048576`** ≈ 1 GiB). Tune up if heavy articles are killed prematurely; tune down to cap per-slot growth.
- `CANONICAL_ADJUDICATION_MAX_CONCURRENT`: max parallel LLM calls per Backfield Output domain pass during **`ai_assisted`** canonical adjudication (places, people, organizations). Default **8**; set **`1`** for serial LLM behavior. DB upserts, plan application, and mention writes stay serial on one SQLModel session. Tune alongside **`CELERY_WORKER_CONCURRENCY`** if OpenAI rate limits appear.
- `CANDIDATE_AI_REVIEW_MAX_CONCURRENT`: max parallel LLM workers for Stylebook **candidate queue AI review** (worker task). Defaults to **`min(CANONICAL_ADJUDICATION_MAX_CONCURRENT, 3)`** so post-LLM writes and progress updates stay within the worker SQLAlchemy pool (Compose default pool **2** + overflow **3**). Candidate review releases DB connections before each LLM call; raise this if you also raise worker pool size.
- `BACKFIELD_PARALLEL_GRAPH_LEVELS`: when **`1`**, **`true`**, or **`yes`**, the worker uses predecessor-ready parallel scheduling inside each **`execute_processed_item`** / **`execute_agate_run`**: nodes start when their upstream readiness rules are met (direct wires for most nodes; JSON **`Output`** waits for the full graph; **`DBOutput`** waits for direct wires only). Ready nodes run concurrently—e.g. GeocodeAgent can start after PlaceExtract while OrganizationExtract is still running. Local Compose defaults to **`1`** on the **`worker`** service; set **`0`** in repo-root `.env` for sequential topo execution. See [docs/ARCHITECTURE.md](ARCHITECTURE.md). Distinct from **`CELERY_WORKER_CONCURRENCY`**, which parallelizes *different* batch files.
- `STYLEBOOK_API_URL`: worker/node access to Stylebook API.
- `SERVICE_API_TOKEN`: shared Bearer token for service-to-service calls. **Agate API** requires `Authorization: Bearer` (this token or a project `bfk_` key) on protected routes; the service-token versions of `make smoke` and `make smoke-place-geocode-stack` send it automatically (override with `SMOKE_AGATE_BEARER` if needed).
- `SMOKE_KEEP_DATA`: when `1`/`true`/`yes`, skip the normal smoke cleanup so you can inspect the temporary graphs, runs, canonicals, and substrate rows left behind by live smoke lanes.
- `SESSION_SECRET`: signing key for session cookies (`itsdangerous`); shared across services that verify the same `session` cookie (Compose default `dev-session-secret`).
- `MASTER_ENCRYPTION_KEY`: Fernet key (URL-safe base64) for **`backfield_project_secret`** (agate-api, worker) and **organization integration secrets** (core-api). **stylebook-api** needs the same key to decrypt catalog credentials for semantic mention search (and any route that calls `resolve_llm_auth_for_model_config`). Compose injects the same dev default on **agate-api**, **worker**, **core-api**, and **stylebook-api** when the variable is unset; use one shared key across those services in production.
- `UI_ORIGIN`: allowed browser origin for local UI access.
- `BACKFIELD_LOCAL_BOOTSTRAP`: when `1`, `agate-api` entrypoint (after Alembic) ensures a **Default Workspace** (`slug` `default`) under the **Backfield** org (`slug` `default`) and attaches the **General** project to it (idempotent; migration **`003_def_ws_general`** also sets this in Postgres), then syncs allowlisted keys from the container environment into **General** (`backfield_project_secret`). Default in Compose is `1`; set `0` to disable (see repo-root `.env.example`). Bootstrap **does not reset** organization or workspace **display names** after admins rename them in the UI. Allowlisted keys are LLM / Azure only (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `AZURE_API_KEY`, `AZURE_API_BASE`). Geocoding, Brave Search, and S3 credentials are **not** synced into project secrets here—use **Settings → Integrations** (organization) or worker/container env so the Project Integrations tab can distinguish organization defaults from project overrides. **Agate graphs are not created at bootstrap**; create flows in the UI or let smoke harnesses create them via the API.
- **Core API — env bootstrap (local/demo/CI only; not for production):** when `BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV` is `1`/`true`/`yes`, `core-api` creates the first org admin on **process startup** (same rules as `POST /v1/bootstrap/first-user`: only when no users exist; attaches to org `default` and existing projects). Set `BACKFIELD_BOOTSTRAP_ADMIN_EMAIL` and either `BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD` or `BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD_FILE`. Optional: `BACKFIELD_BOOTSTRAP_ADMIN_DISPLAY_NAME`. If the flag is on but email/password are missing, `core-api` exits non-zero by default (`BACKFIELD_BOOTSTRAP_ADMIN_STRICT`, default `1`) so the stack fails fast. After `make up`, with these variables in repo-root `.env`, the admin is created on first start without calling the HTTP bootstrap endpoint.

### Repo-root `.env` (local only)

`agate-api`, **`core-api`**, and `worker` use Compose `env_file: ../.env` (relative to `infra/docker-compose.yml`, i.e. the repository root). Copy [.env.example](../.env.example) to `.env` and add keys there; the file is gitignored. Variables are injected into the containers (Compose `required: false` so a missing `.env` does not fail the bring-up).

### Flow execution (PlaceExtract, GeocodeAgent)

Graph nodes are executed in the worker using the vendored `agate-runtime` package. The worker builds the effective environment with **`merge_project_and_org_llm_api_keys`** (`packages/backfield-ai`): organization **AI provider** integration secrets (`ai.provider.*` on `backfield_organization_integration_secret`), then organization **platform** presets (`platform.geocode.*`, `platform.search.*`, `platform.storage.*` — configured in Agate **Settings → Integrations** via Core API), then decrypted **`backfield_project_secret`** rows for the graph’s project (**project values win** when the same env name appears at multiple layers). S3 **bucket, prefix, and region** stay on S3Input (and related) node parameters, not in the Integrations panels.

- **Required for LLM PlaceExtract**: depends on the catalog model — typically `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and/or `AZURE_API_KEY` plus **`AZURE_API_BASE`** (resource endpoint URL from project secrets / bootstrap `.env`, not an organization integration slot) for Azure OpenAI (see `agate_utils.llm.call_llm`). PlaceExtract writes **`geocode_hints`** when extra story context helps geocoding. **GeocodeAgent** uses them on **`place`** (web search + best-address prompts), passes them into the **`route_strategy`** LLM prompt (with **`geocode_hints_snippet`** on router audit), and into **Region**, **NaturalPlace**, **StreetRoad**, **Intersection**, **Span** (including inner endpoints), and **Address** (Pelias multi-candidate LLM picker after structured miss). Router strategies are **`web_search`** (Brave when configured, then DuckDuckGo fallback for addressable **place** flows) vs **`no_web_search`** (**neither** Brave nor DDG); addressable places without a street line should route to **`web_search`** so hints shape the query rather than skipping retrieval.
- **GeocodeAgent** may use `OPENAI_API_KEY`, `PELIAS_API_KEY`, `GEOCODIO_API_KEY`, `BRAVE_SEARCH_API_KEY`, and optional Stylebook cache via `STYLEBOOK_API_URL` + `PROJECT_SLUG` + `SERVICE_API_TOKEN`.
- **Overpass API** (intersection / street helpers in `agate_utils.geocoding.overpass`): requests send a descriptive `User-Agent` by default; set **`OVERPASS_USER_AGENT`** to override (some public interpreters return **406** for unidentified clients). Public mirrors rate-limit quickly under parallel geocode load — local Compose defaults **`OVERPASS_MAX_CONCURRENT=4`** and **`OVERPASS_QUERY_STAGGER_S=0.5`** on the worker (override in repo-root `.env`); code fallback when unset is **`1`** concurrent / **`1.0`** s stagger. Exponential backoff up to 60s on **429/502/503/504**, honor **`Retry-After`**, validate JSON before parse (HTML overload pages retry instead of failing opaquely), and fall back through **`OVERPASS_MIRROR_URLS`** (built-in lz4 + kumi mirrors when unset). Override the primary interpreter with **`OVERPASS_API_URL`**.
- **Celery limits**: `TASK_SOFT_TIME_LIMIT` / `TASK_HARD_TIME_LIMIT` (Compose defaults **`900`** / **`1080`** seconds — 15 / 18 minutes — on the worker) are enforced on **`worker.tasks.execute_processed_item`** so a hung per-article task fails instead of stalling an S3 batch tail. The default preserves PlaceExtract’s configured **`llmTimeout`** (600s) alongside the nodes’ internal 300s Celery buffer; do not lower the soft limit to 600s without also revisiting that buffer. **`execute_processed_item`** uses **`acks_late`** and **`task_reject_on_worker_lost`** so broker redelivery can resume work after a worker crash; rows left in **`running`** longer than **`TASK_HARD_TIME_LIMIT` + `TASK_STALE_RUNNING_GRACE_S`** (default grace **300** s) are treated as stale — **`finalize_s3_parent_run`** marks them **`failed`** with *Processing interrupted (worker lost or exceeded time limit)* so batch runs can finish. Re-run failed items from the Agate UI when needed.
- **S3 batch dispatch order**: `execute_s3_batch_setup` queues **`execute_processed_item`** tasks longest-article-first (by input `text` length) so heavy items start earlier when worker concurrency is saturated.
- **Async node wall clock**: `AGATE_NODE_TIMEOUT_S` (default **`600`**) wraps async graph nodes in `asyncio.wait_for`; sync nodes rely on Celery limits and API-side Postgres timeouts.
- **API Postgres timeouts**: `BACKFIELD_PG_STATEMENT_TIMEOUT_MS` (default **`30000`**) and `BACKFIELD_PG_LOCK_TIMEOUT_MS` (default **`5000`**) are set on **agate-api**, **core-api**, and **stylebook-api** only (not the worker) so Stylebook/Agate reads fail fast instead of waiting on worker row locks during heavy runs. Under PgBouncer, these apply via **`SET LOCAL`** at transaction start (not libpq startup `options`). API pool defaults: **`BACKFIELD_SQLALCHEMY_POOL_SIZE=3`**, **`MAX_OVERFLOW=2`**.
- **PgBouncer (local Compose)**: the **`pgbouncer`** service listens on **`5432`** inside the Compose network (`...@pgbouncer:5432/...`) and is published to the host as **`localhost:6432`**. **`POOL_MODE=transaction`**, **`MAX_DB_CONNECTIONS=80`**, **`DEFAULT_POOL_SIZE=20`**. Monitor with `psql postgresql://postgres:postgres@localhost:6432/pgbouncer -c 'SHOW POOLS;'`.
- **Worker session release**: Agate worker tasks commit and close DB sessions before long graph execution and LLM work. LLM call records (`backfield_ai_call_record`) persist in short committed transactions; DBOutput auto-connection LLM commits the persist transaction before classification. This avoids **`idle in transaction`** backends pinning Postgres during multi-minute runs.
- **Run performance tooling**: `scripts/perf_report.sql` summarizes LLM cost, failures, geocode call volume, and effective parallelism for a run id (`psql "$BACKFIELD_DATABASE_URL" -v run_id='…' -f scripts/perf_report.sql`). `scripts/verify_geocode_cache_config.py --graph-id …` checks GeocodeAgent **`useCache`** / **`stylebookId`** and Stylebook canonical counts before a heavy batch.
- **S3 batch fan-out**: `execute_s3_batch_setup` lists S3 keys, inserts **`agate_processed_item`** rows, then submits a Celery **`chord`**: a **`group`** of **`execute_processed_item`** tasks plus a **`finalize_s3_parent_run`** callback when every child completes. The setup task returns immediately (no ``group().get()`` in the parent), so workers can run many file tasks in parallel. **`CELERY_WORKER_CONCURRENCY`** (Compose default **16**, override in repo-root `.env`) controls how many child tasks run at once per worker container. Compose also passes **`--prefetch-multiplier 1`**, **`--max-tasks-per-child 1`**, and **`--max-memory-per-child 1048576`** (1 GiB) so each article runs in a fresh child when possible and long batches do not accumulate heap inside the same OS processes. Override via **`CELERY_MAX_TASKS_PER_CHILD`** / **`CELERY_MAX_MEMORY_PER_CHILD_KB`**. At batch setup, the worker snapshots the graph **`spec_json`** on the parent run’s **`result_json`** so every child uses the same Backfield Output settings (including semantic indexing) even if the flow is edited mid-run. Env **`S3_BATCH_MAX_INFLIGHT`** is reserved for a future bounded chunking story. S3 listing and downloads use project secrets merged into the process environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`). The S3Input node param **`max_files`** (default `500`, hard cap `10000`) limits how many valid JSON documents are executed per run; additional valid keys are recorded as **`skipped`** items with reason **`max_files cap`**.

For `make smoke` / `make smoke-runtime`, set whichever LLM credentials match the Starter flow model (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and/or Azure OpenAI `AZURE_API_KEY` + `AZURE_API_BASE`) in repo-root `.env` (or ensure they exist in the worker environment) so PlaceExtract (and any other LLM nodes in the flow) can call the configured model; otherwise the handoff run fails when those nodes execute. `make smoke-fast`, `make smoke-stylebook-editorial`, `make smoke-stylebook-import-export`, and `make smoke-s3-batch` do not depend on external LLM/geocoder calls. For the **session-shaped** smoke lanes, add **`SMOKE_EMAIL`** and **`SMOKE_PASSWORD`** to the same repo-root `.env` (they are loaded automatically; no need to `export`). Run **`core-api`** in Compose. Omit them only when you explicitly want the legacy service-token path on `make smoke`.

`PROJECT_SLUG` can still be set via Compose interpolation on the worker service for Stylebook cache scoping.

## Database guidance

- Use Alembic for schema changes (single chain in `packages/backfield-db`; run via **`backfield migrate`** / **`make migrate`** — do not auto-migrate from API startup).
- The local `postgres` service builds from `infra/postgres/Dockerfile` (PostGIS + **pgvector** + **h3-pg**) because location tables store geometry, semantic document tables store embedding vectors, and H3 spatial indexing supports map aggregation queries.
- Agate execution tables use the `agate_` prefix; tenancy and project tables use `backfield_`.
- Do not let multiple services race to run migrations for the same revision path.

### Core API auth (local)

- `core-api` uses the same DB as Agate (`DATABASE_URL` / `BACKFIELD_DATABASE_URL` in Compose). After migrations, either opt in to **env bootstrap** (see `BACKFIELD_BOOTSTRAP_ADMIN_*` above) so the first admin is created on **`make up`**, or register the first user with **`POST /v1/bootstrap/first-user`** when no users exist, or create users via org-admin routes under **`/v1/organizations/{org_id}/users`** (session + `org_admin` role).

## Troubleshooting

- If **`backfield init`** times out waiting for APIs, run `docker compose -f infra/docker-compose.yml ps` and inspect logs for the failing service (for example `docker compose -f infra/docker-compose.yml logs agate-api`). Init checks `/readyz` **inside each API container**, so another process on host port `8000` does not block init; if browser or curl to `http://localhost:8000` still fails while the container is healthy, another listener is answering on that host port—stop it or change the Compose port mapping.
- If Stylebook or Agate pages **hang or time out during a heavy run**, check worker logs for long DBOutput transactions; API services use **`lock_timeout`** / **`statement_timeout`** (see **API Postgres timeouts** above) so contended reads should fail in seconds with a database error rather than blocking indefinitely.
- If Postgres logs **`FATAL: sorry, too many clients already`**, check PgBouncer **`SHOW POOLS`** / **`SHOW STATS`** first (local Compose). Every service process that imports `backfield_db.session` holds one pooled engine: reduce **`CELERY_WORKER_CONCURRENCY`**, lower **`BACKFIELD_SQLALCHEMY_POOL_SIZE`** / **`BACKFIELD_SQLALCHEMY_MAX_OVERFLOW`** on the worker (Compose defaults are already small), tune PgBouncer **`MAX_DB_CONNECTIONS`**, or raise Postgres **`max_connections`** in your deployment config. Avoid ad-hoc `create_engine` in long-lived workers — use **`get_engine()`** so each process has a single pool.
- If DBOutput fails with **`deadlock detected`** while many batch articles run in parallel, workers are likely updating the same shared **`substrate_location`** row (for example a shared city or county polygon). The worker **retries DBOutput** a few times with backoff and takes row locks on existing location rows during upsert; persist handlers now **commit before parallel adjudication LLM** so locks are not held across multi-second LLM batches. Persistent failures usually clear on retry. If they continue, lower **`CELERY_WORKER_CONCURRENCY`** temporarily.
- If intersection geocoding logs **`Overpass server error … HTTP 429`** or **`Overpass non-JSON body`**, the public Overpass interpreter is rate-limiting or returning an HTML overload page. Defaults use **`OVERPASS_MAX_CONCURRENT=1`**, stagger between the two road queries, mirror fallback, and longer backoff; if it persists under high batch load, lower **`CELERY_WORKER_CONCURRENCY`** or point **`OVERPASS_API_URL`** at a dedicated interpreter.
- If compose networks or stray one-off containers linger, from the repo run `make down`, or `docker compose -f infra/docker-compose.yml down --remove-orphans` if you need to clear orphaned containers from a renamed project.
- If a run never leaves `pending`, check `worker` logs and Redis connectivity.
- If secrets calls fail, verify `MASTER_ENCRYPTION_KEY` is non-empty on **agate-api**, **worker**, **core-api**, and **stylebook-api**. An empty `MASTER_ENCRYPTION_KEY=` line in repo-root `.env` overrides Compose’s dev default with a blank value—remove it or set a key, e.g. `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- If geocode calls fail, check `stylebook-api`, `STYLEBOOK_API_URL`, and `SERVICE_API_TOKEN`.
- If PlaceExtract or GeocodeAgent fail with auth errors, verify LLM and geocoder keys on the worker (Compose env or project secrets).
- If **`agate-ui` fails with `vite: not found`**, the image may be stale or an old anonymous `node_modules` volume may be wrong: rebuild the service (`docker compose build agate-ui --no-cache`) and bring the stack up again. Compose mounts `apps/agate-ui` at `/app/apps/agate-ui` to match the Dockerfile `WORKDIR` so `node_modules` (including Vite) resolves correctly.
- If **`backfield`** fails with **`ModuleNotFoundError: No module named 'backfield_cli'`**, the repo-root `.venv` has a stale editable install (often after a partial `uv sync` from an app package directory). From the repo root run **`make bootstrap`**, then **`backfield doctor`**. The launcher repairs imports only when the probe fails — it does not run `uv sync` on every command. Do not use **`uv run backfield`** (there is no Python console script named `backfield`). Avoid bare `uv sync` from `apps/*` or `packages/*` — use **`uv sync --all-packages`** at the repo root instead.
- **`stylebook-ui`** uses the same pattern: repo-root image build, `WORKDIR` `/app/apps/stylebook-ui`, mounts `apps/stylebook-ui` and `packages/` under `/app/…` so `@backfield/ui` (`file:../../packages/backfield-ui`) resolves. If Vite reports **Failed to resolve import `@backfield/ui`**, rebuild `stylebook-ui` (`docker compose build stylebook-ui --no-cache`) and ensure compose volumes match the Dockerfile paths above.
- If Vite reports **Failed to resolve import** for a dependency used by **`packages/backfield-ui`** (for example `@radix-ui/react-dropdown-menu` from `LayerFilterPopover.tsx`), the shared package’s `node_modules` is missing or stale. UI images run `npm install` in `packages/backfield-ui` at build time; Compose keeps that tree in an anonymous volume at `/app/packages/backfield-ui/node_modules` while bind-mounting `packages/`. Rebuild both UI services (`docker compose -f infra/docker-compose.yml build agate-ui stylebook-ui --no-cache`) and bring the stack up again.
- If `make up` / image build fails with **no space left on device**, run `make docker-trim` first; if space is still tight, run `make docker-trim-full` or `make docker-prune-volumes` knowing it may remove unused volumes (including a stopped stack’s DB volume). Remove any huge optional local `.db` under `packages/backfield-agate/.../geocoding/data/` if you do not need it; [.dockerignore](../.dockerignore) keeps those paths out of the image build context.