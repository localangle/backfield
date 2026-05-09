# Operations

## Local stack

Primary local services are defined in `infra/docker-compose.yml`:

- PostGIS-enabled `postgres` on `localhost:5433` (data directory on the **`postgres_data`** named volume, same persistence pattern as agate-ai-platform)
- `redis` on `localhost:6379`
- `agate-api` on `localhost:8000`
- `stylebook-api` on `localhost:8003`
- `core-api` on `localhost:8004`
- `agate-ui` on `localhost:5173`
- `stylebook-ui` on `localhost:5175`
- `worker` as the background Celery consumer

`agate-ui` is ordered **after** `core-api` and `agate-api` report **healthy** (HTTP `/health` checks) so the Vite dev proxy does not hit `ECONNREFUSED` while Uvicorn is still binding (notably when `agate-api` uses the reload worker).

`core-api` and the **`worker`** likewise wait until **`agate-api` is healthy** so its entrypoint has finished **`alembic upgrade head`** (and optional `BACKFIELD_LOCAL_BOOTSTRAP`) before those services touch the database. Otherwise `core-api` can log *Env bootstrap skipped: identity tables missing* on a cold volume because Postgres was ready while migrations had not run yet.

## Canonical commands

- `make up`: bring up the local stack in the foreground. It does **not** run `docker volume prune` or `docker system prune` (only `docker compose up`).
- `make down`: `docker compose down` (stops and removes app containers, **not** Compose-managed volumes) then `docker-trim` (`docker system prune -f` only). Matches agate-ai-platform local `make down` (no `--remove-orphans`). The Postgres data directory lives on the **`postgres_data`** named volume, so `make down` then `make up` keeps your local database. Run `make docker-prune-volumes` or `make docker-trim-full` explicitly when you want to reclaim unused volume disk.
- `make logs`: inspect compose logs.
- `make migrate`: run Alembic inside `agate-api`.
- `make reset-db`: tear down containers and volumes.

When a migration is **destructive** toward existing Stylebook catalog data (for example revision **`019_stylebook_loc_canon_uuid`**), wipe the Postgres volume with **`make reset-db`** before **`make up`** / **`make migrate`** so Alembic applies cleanly; do not expect in-place upgrades from pre-UUID canonical integer ids.
- `make smoke`: run the HTTP golden-path smoke against a live stack (`tests/smoke/golden_path_stack.py`). With **`SMOKE_EMAIL`** and **`SMOKE_PASSWORD`** set, exercises Core login and **`GET /v1/me/workspaces`** before Agate; otherwise uses the service Bearer on Agate only.
- `make docker-prune-build`: reclaim disk from Docker build cache only (`docker builder prune -f`).
- `make docker-prune-system`: remove stopped containers, dangling images, unused networks, and build cache (`docker system prune -f`).
- `make docker-prune-volumes`: run `docker volume prune -f` (**unused** volumes only — after `make down`, Compose DB volumes are typically unused and **can be deleted**; use only when you intend to reclaim space or reset anonymous volumes).
- `make docker-trim`: runs `docker-prune-system` only (safe default before `make up` when the daemon is low on disk; preserves Postgres and other compose volumes across `down`/`up`).
- `make docker-trim-full`: runs `docker-trim` then `docker-prune-volumes` (aggressive reclaim; can wipe local DB data if nothing references those volumes).

Docker builds use the repo root as context; [.dockerignore](../.dockerignore) excludes optional large local `*.db` files under `packages/backfield-agate/.../geocoding/data/` so image builds do not copy multi-gigabyte artifacts if present on a developer machine.

**`agate-api`**, **`worker`**, and **`core-api` images** copy `packages/backfield-ai` and install editable wheels in dependency order (`backfield-db` → `backfield-ai` → …) because that package name is not published on PyPI (`agate-api` / `worker` continue with `backfield-agate` → `backfield-stylebook` → … as before).

## Runtime contracts

- Agate worker queue: `agate`
- Worker task names:
  - `worker.tasks.execute_agate_run` — default graph execution (single Celery task runs `execute_graph`).
  - `worker.tasks.execute_s3_batch_setup` — lists/validates S3 JSON under the S3Input prefix, inserts **`agate_processed_item`** rows, then queues a **`chord`** of **`execute_processed_item`** tasks.
  - `worker.tasks.execute_processed_item` — one Celery task per queued item; runs `execute_graph` with an S3Input shim (parent **`agate_run.id`** remains **`BACKFIELD_RUN_ID`** for DBOutput / substrate).
  - `worker.tasks.finalize_s3_parent_run` — chord callback that aggregates parent **`agate_run`** status after all items finish.
  - `worker.tasks.export_stylebook_bundle` — builds a full stylebook ZIP (manifest + JSONL shards) and uploads it to **`STYLEBOOK_BUNDLE_S3_BUCKET`** for org-admin download links from **stylebook-api**.
  - `worker.tasks.import_stylebook_bundle` — downloads a staged ZIP from the same bucket and imports it into a **new** stylebook (new canonical ids; optional per-project mapping for notes and connections).
- Worker app name: `agate_worker`
- Health endpoints:
  - Agate API: `GET /health`
  - Stylebook API: `GET /health`
  - Core API: `GET /health`

## Environment variables

- `BACKFIELD_DATABASE_URL` / `DATABASE_URL`: database connection string (required for `agate-api`, **`stylebook-api`**, `worker`, and **`core-api`** — these apps read the same Postgres database; Compose sets the in-network URL `...@postgres:5432/...` so containers do not default to `localhost:5433`, which only works from the host).
- `BACKFIELD_SQLALCHEMY_POOL_SIZE` / `BACKFIELD_SQLALCHEMY_MAX_OVERFLOW`: optional SQLAlchemy pool sizing for `backfield_db.session.get_engine()` (defaults follow SQLAlchemy when unset: **5** / **10**). The local **`worker`** Compose service sets conservative defaults (**2** / **3**) so many Celery child processes plus API Uvicorn processes are less likely to hit Postgres **`max_connections`**. Raise these on the worker if you see pool timeouts under heavy parallel load.
- `BACKFIELD_STRICT_CANONICAL_GATES`: when **`1`** (default) or unset, DBOutput ingest applies deterministic Stylebook autolink gates in `canonical_policy` (type deny-list, container-vs-POI, jurisdiction vs canonical columns, components vs formatted-address sanity, distance vs cached container city when a **`substrate_location_cache`** hit exists, polygon bbox size). Set to **`0`**, **`false`**, **`no`**, or **`off`** to disable those gates (use only for diagnosis—expect more wrong merges when off). See [docs/ARCHITECTURE.md](ARCHITECTURE.md).
- `REDIS_URL`: Celery broker and backend (required for **agate-api** enqueue, **worker** execution, and **stylebook-api** when using async stylebook bundle export/import jobs).
- `STYLEBOOK_BUNDLE_S3_BUCKET`: S3-compatible bucket used to stage full stylebook ZIP files between the browser and the worker (**stylebook-api** presigned URLs + worker upload/download). Unset in Compose by default; export/import job routes return **503** until a bucket is configured. Pair with the same **`AWS_ACCESS_KEY_ID`** / **`AWS_SECRET_ACCESS_KEY`** (and optional **`AWS_SESSION_TOKEN`**) used elsewhere for S3.
- `STYLEBOOK_BUNDLE_S3_PREFIX`: optional key prefix inside the bucket (default **`stylebook-bundles`**). Objects are written as `{prefix}/{organization_id}/{job_id}.zip` when the prefix is non-empty.
- `AWS_S3_ENDPOINT_URL` or `AWS_ENDPOINT_URL`: optional non-AWS endpoint (for example MinIO) for bundle staging and presigned URL signing; must match how the browser and worker reach the same object store.
- `CELERY_WORKER_CONCURRENCY`: optional override for the Agate worker process pool size (Compose passes **`--concurrency`**; default **8** when unset). Higher values improve S3 batch parallelism when many **`execute_processed_item`** tasks are in flight.
- `STYLEBOOK_API_URL`: worker/node access to Stylebook API.
- `SERVICE_API_TOKEN`: shared Bearer token for service-to-service calls. **Agate API** requires `Authorization: Bearer` (this token or a project `bfk_` key) on protected routes; `make smoke` sends it automatically (override with `SMOKE_AGATE_BEARER` if needed).
- `SESSION_SECRET`: signing key for session cookies (`itsdangerous`); shared across services that verify the same `session` cookie (Compose default `dev-session-secret`).
- `MASTER_ENCRYPTION_KEY`: Fernet key (URL-safe base64) for **`backfield_project_secret`** (agate-api, worker) and **organization integration secrets** (core-api). Compose injects the same dev default on **agate-api**, **worker**, and **core-api** when the variable is unset; use one shared key across those services in production.
- `UI_ORIGIN`: allowed browser origin for local UI access.
- `BACKFIELD_LOCAL_BOOTSTRAP`: when `1`, `agate-api` entrypoint (after Alembic) ensures a **Default Workspace** (`slug` `default`) under the **Backfield** org (`slug` `default`) and attaches the **General** project to it (idempotent; migration **`003_def_ws_general`** also sets this in Postgres), then syncs allowlisted keys from the container environment into **General** (`backfield_project_secret`) and creates the **Starter flow** graph if missing. Default in Compose is `1`; set `0` to disable (see repo-root `.env.example`). Allowlisted keys include LLM / Azure (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `AZURE_API_KEY`, `AZURE_API_BASE`) and `MAPBOX_API_TOKEN`. Geocoding, Brave Search, and S3 credentials are **not** synced into project secrets here—use **Settings → Integrations** (organization) or worker/container env so the Project Integrations tab can distinguish organization defaults from project overrides.
- **Core API — env bootstrap (local/demo/CI only; not for production):** when `BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV` is `1`/`true`/`yes`, `core-api` creates the first org admin on **process startup** (same rules as `POST /v1/bootstrap/first-user`: only when no users exist; attaches to org `default` and existing projects). Set `BACKFIELD_BOOTSTRAP_ADMIN_EMAIL` and either `BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD` or `BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD_FILE`. Optional: `BACKFIELD_BOOTSTRAP_ADMIN_DISPLAY_NAME`. If the flag is on but email/password are missing, `core-api` exits non-zero by default (`BACKFIELD_BOOTSTRAP_ADMIN_STRICT`, default `1`) so the stack fails fast. After `make up`, with these variables in repo-root `.env`, the admin is created on first start without calling the HTTP bootstrap endpoint.

### Repo-root `.env` (local only)

`agate-api`, **`core-api`**, and `worker` use Compose `env_file: ../.env` (relative to `infra/docker-compose.yml`, i.e. the repository root). Copy [.env.example](../.env.example) to `.env` and add keys there; the file is gitignored. Variables are injected into the containers (Compose `required: false` so a missing `.env` does not fail the bring-up).

### Flow execution (PlaceExtract, GeocodeAgent)

Graph nodes are executed in the worker using the vendored `backfield-agate` package (ported from agate-ai-platform). The worker builds the effective environment with **`merge_project_and_org_llm_api_keys`** (`packages/backfield-ai`): organization **AI provider** integration secrets (`ai.provider.*` on `backfield_organization_integration_secret`), then organization **platform** presets (`platform.geocode.*`, `platform.search.*`, `platform.storage.*` — configured in Agate **Settings → Integrations** via Core API), then decrypted **`backfield_project_secret`** rows for the graph’s project (**project values win** when the same env name appears at multiple layers). S3 **bucket, prefix, and region** stay on S3Input (and related) node parameters, not in the Integrations panels.

- **Required for LLM PlaceExtract**: depends on the catalog model — typically `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and/or `AZURE_API_KEY` plus **`AZURE_API_BASE`** (resource endpoint URL from project secrets / bootstrap `.env`, not an organization integration slot) for Azure OpenAI (see `agate_utils.llm.call_llm`). PlaceExtract writes **`geocode_hints`** when extra story context helps geocoding. **GeocodeAgent** uses them on **`place`** (web search + best-address prompts), passes them into the **`route_strategy`** LLM prompt (with **`geocode_hints_snippet`** on router audit), and into **Region**, **NaturalPlace**, **StreetRoad**, **Intersection**, **Span** (including inner endpoints), and **Address** (Pelias multi-candidate LLM picker after structured miss). Router strategies are **`web_search`** (Brave when configured, then DuckDuckGo fallback for addressable **place** flows) vs **`no_web_search`** (**neither** Brave nor DDG); addressable places without a street line should route to **`web_search`** so hints shape the query rather than skipping retrieval.
- **GeocodeAgent** may use `OPENAI_API_KEY`, `PELIAS_API_KEY`, `GEOCODIO_API_KEY`, `BRAVE_SEARCH_API_KEY`, and optional Stylebook cache via `STYLEBOOK_API_URL` + `PROJECT_SLUG` + `SERVICE_API_TOKEN`.
- **Overpass API** (intersection / street helpers in `agate_utils.geocoding.overpass`): requests send a descriptive `User-Agent` by default; set **`OVERPASS_USER_AGENT`** to override (some public interpreters return **406** for unidentified clients).
- **Celery limits**: `TASK_SOFT_TIME_LIMIT` / `TASK_HARD_TIME_LIMIT` (defaults `3600` / `4200` seconds on the worker service in Compose) mirror agate-ai-platform worker defaults for long-running geocode flows.
- **S3 batch fan-out**: `execute_s3_batch_setup` lists S3 keys, inserts **`agate_processed_item`** rows, then submits a Celery **`chord`**: a **`group`** of **`execute_processed_item`** tasks plus a **`finalize_s3_parent_run`** callback when every child completes. The setup task returns immediately (no ``group().get()`` in the parent), so workers can run many file tasks in parallel. **`CELERY_WORKER_CONCURRENCY`** (Compose default **8**, override in repo-root `.env`) controls how many child tasks run at once per worker container. Env **`S3_BATCH_MAX_INFLIGHT`** is reserved for a future bounded chunking story. S3 listing and downloads use project secrets merged into the process environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`). The S3Input node param **`max_files`** (default `500`, hard cap `10000`) limits how many valid JSON documents are executed per run; additional valid keys are recorded as **`skipped`** items with reason **`max_files cap`**.

For `make smoke`, set whichever LLM credentials match the Starter flow model (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and/or Azure OpenAI `AZURE_API_KEY` + `AZURE_API_BASE`) in repo-root `.env` (or ensure they exist in the worker environment) so PlaceExtract (and any other LLM nodes in the flow) can call the configured model; otherwise the run fails when those nodes execute. For the **session-shaped** smoke, add **`SMOKE_EMAIL`** and **`SMOKE_PASSWORD`** to the same repo-root `.env` (they are loaded automatically; no need to `export`). Run **`core-api`** in Compose. Omit them to use the legacy service-token path on Agate only.

`PROJECT_SLUG` can still be set via Compose interpolation on the worker service for Stylebook cache scoping.

## Database guidance

- Use Alembic for schema changes (single chain in `packages/backfield-db`; **`make migrate` runs inside `agate-api`** — do not also auto-migrate from `core-api` on startup).
- The local `postgres` service uses a PostGIS-enabled image because shared location tables store geometry columns.
- Agate execution tables use the `agate_` prefix; tenancy and project tables use `backfield_`.
- Do not let multiple services race to run migrations for the same revision path.

### Core API auth (local)

- `core-api` uses the same DB as Agate (`DATABASE_URL` / `BACKFIELD_DATABASE_URL` in Compose). After migrations, either opt in to **env bootstrap** (see `BACKFIELD_BOOTSTRAP_ADMIN_*` above) so the first admin is created on **`make up`**, or register the first user with **`POST /v1/bootstrap/first-user`** when no users exist, or create users via org-admin routes under **`/v1/organizations/{org_id}/users`** (session + `org_admin` role).

## Troubleshooting

- If Postgres logs **`FATAL: sorry, too many clients already`**, every service process that imports `backfield_db.session` holds one pooled engine: reduce **`CELERY_WORKER_CONCURRENCY`**, lower **`BACKFIELD_SQLALCHEMY_POOL_SIZE`** / **`BACKFIELD_SQLALCHEMY_MAX_OVERFLOW`** on the worker (Compose defaults are already small), or raise Postgres **`max_connections`** in your deployment config. Avoid ad-hoc `create_engine` in long-lived workers — use **`get_engine()`** so each process has a single pool.
- If compose networks or stray one-off containers linger, from the repo run `make down`, or `docker compose -f infra/docker-compose.yml down --remove-orphans` if you need to clear orphaned containers from a renamed project.
- If a run never leaves `pending`, check `worker` logs and Redis connectivity.
- If secrets calls fail, verify `MASTER_ENCRYPTION_KEY` is non-empty on **agate-api**, **worker**, and **core-api**. An empty `MASTER_ENCRYPTION_KEY=` line in repo-root `.env` overrides Compose’s dev default with a blank value—remove it or set a key, e.g. `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- If geocode calls fail, check `stylebook-api`, `STYLEBOOK_API_URL`, and `SERVICE_API_TOKEN`.
- If PlaceExtract or GeocodeAgent fail with auth errors, verify LLM and geocoder keys on the worker (Compose env or project secrets).
- If **`agate-ui` fails with `vite: not found`**, the image may be stale or an old anonymous `node_modules` volume may be wrong: rebuild the service (`docker compose build agate-ui --no-cache`) and bring the stack up again. Compose mounts `apps/agate-ui` at `/app/apps/agate-ui` to match the Dockerfile `WORKDIR` so `node_modules` (including Vite) resolves correctly.
- **`stylebook-ui`** uses the same pattern: repo-root image build, `WORKDIR` `/app/apps/stylebook-ui`, mounts `apps/stylebook-ui` and `packages/` under `/app/…` so `@backfield/ui` (`file:../../packages/backfield-ui`) resolves. If Vite reports **Failed to resolve import `@backfield/ui`**, rebuild `stylebook-ui` (`docker compose build stylebook-ui --no-cache`) and ensure compose volumes match the Dockerfile paths above.
- If `make up` / image build fails with **no space left on device**, run `make docker-trim` first; if space is still tight, run `make docker-trim-full` or `make docker-prune-volumes` knowing it may remove unused volumes (including a stopped stack’s DB volume). Remove any huge optional local `.db` under `packages/backfield-agate/.../geocoding/data/` if you do not need it; [.dockerignore](../.dockerignore) keeps those paths out of the image build context.