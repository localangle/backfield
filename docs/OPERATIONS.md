# Operations

## Local stack

Primary local services are defined in `infra/docker-compose.yml`:

- `postgres` on `localhost:5433`
- `redis` on `localhost:6379`
- `agate-api` on `localhost:8000`
- `stylebook-api` on `localhost:8003`
- `agate-ui` on `localhost:5173`
- `stylebook-ui` on `localhost:5175`
- `worker` as the background Celery consumer

## Canonical commands

- `make up`: bring up the local stack in the foreground.
- `make down`: stop the stack and remove orphans, then run `docker-trim` (build-cache and unused-volume prune).
- `make logs`: inspect compose logs.
- `make migrate`: run Alembic inside `agate-api`.
- `make reset-db`: tear down containers and volumes.
- `make smoke`: run the HTTP golden-path smoke against a live stack.
- `make docker-prune-build`: reclaim disk from Docker build cache (`docker builder prune -f`).
- `make docker-prune-volumes`: remove **unused** anonymous volumes (`docker volume prune -f`); does not remove named volumes while containers still reference them.
- `make docker-trim`: runs both prunes above (handy before `make up` when the daemon is low on disk).

Docker builds use the repo root as context; [.dockerignore](../.dockerignore) excludes large local files such as Who's On First `*.db` under `packages/agate-runtime/.../geocoding/data/` so images do not try to copy multi-gigabyte databases.

## Runtime contracts

- Agate worker queue: `agate`
- Worker task name: `worker.tasks.execute_agate_run`
- Worker app name: `agate_worker`
- Health endpoints:
  - Agate API: `GET /health`
  - Stylebook API: `GET /health`

## Environment variables

- `BACKFIELD_DATABASE_URL` / `DATABASE_URL`: database connection string.
- `REDIS_URL`: Celery broker and backend.
- `STYLEBOOK_API_URL`: worker/node access to Stylebook API.
- `SERVICE_API_TOKEN`: optional shared token between Agate and Stylebook services.
- `MASTER_ENCRYPTION_KEY`: required for encrypted project-secret storage.
- `UI_ORIGIN`: allowed browser origin for local UI access.
- `BACKFIELD_LOCAL_BOOTSTRAP`: when `1`, `agate-api` entrypoint (after Alembic) syncs allowlisted keys from the container environment into **General** (`agate_project_secret`) and creates the **Starter flow** graph if missing. Default in Compose is `1`; set `0` to disable (see repo-root `.env.example`). Allowlisted keys include `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PELIAS_API_KEY`, `GEOCODIO_API_KEY`, `BRAVE_SEARCH_API_KEY`, and `MAPBOX_API_TOKEN`.

### Repo-root `.env` (local only)

`agate-api` and `worker` use Compose `env_file: ../.env` (relative to `infra/docker-compose.yml`, i.e. the repository root). Copy [.env.example](../.env.example) to `.env` and add keys there; the file is gitignored. Variables are injected into the containers (Compose `required: false` so a missing `.env` does not fail the bring-up).

### Flow execution (PlaceExtract, GeocodeAgent)

Graph nodes are executed in the worker using the vendored `agate-runtime` package (ported from agate-ai-platform). The worker reads API keys from the process environment after applying decrypted `agate_project_secret` rows for the graph’s project.

- **Required for LLM PlaceExtract**: `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` (see `agate_utils.llm.call_llm`).
- **GeocodeAgent** may use `OPENAI_API_KEY`, `PELIAS_API_KEY`, `GEOCODIO_API_KEY`, `BRAVE_SEARCH_API_KEY`, and optional Stylebook cache via `STYLEBOOK_API_URL` + `PROJECT_SLUG` + `SERVICE_API_TOKEN`.
- **Who's On First SQLite** (parent lookups in `wof.py`): the database file is not in git (size). Install under `packages/agate-runtime/.../geocoding/data/` or set **`WOF_SQLITE_DB_PATH`** to the `.db` file. See `packages/agate-runtime/src/agate_utils/geocoding/data/README.md`.
- **Celery limits**: `TASK_SOFT_TIME_LIMIT` / `TASK_HARD_TIME_LIMIT` (defaults `3600` / `4200` seconds on the worker service in Compose) mirror agate-ai-platform worker defaults for long-running geocode flows.

For `make smoke`, set at least `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` in repo-root `.env` (or ensure they exist in the worker environment) so PlaceExtract can call the LLM; otherwise the run fails when those nodes execute.

`PROJECT_SLUG` can still be set via Compose interpolation on the worker service for Stylebook cache scoping.

## Database guidance

- Use Alembic for schema changes.
- Agate tables use the `agate_` prefix.
- Existing upgraded databases should point `alembic_version` at `001_agate_baseline`.
- Do not let multiple services race to run migrations for the same revision path.

## Troubleshooting

- If compose networks stay around, use `make down` first because it removes orphans.
- If a run never leaves `pending`, check `worker` logs and Redis connectivity.
- If secrets calls fail, verify `MASTER_ENCRYPTION_KEY`.
- If geocode calls fail, check `stylebook-api`, `STYLEBOOK_API_URL`, and `SERVICE_API_TOKEN`.
- If PlaceExtract or GeocodeAgent fail with auth errors, verify LLM and geocoder keys on the worker (Compose env or project secrets).
- If `make up` / image build fails with **no space left on device**, run `make docker-trim` (and remove any huge local `.db` under `packages/agate-runtime/.../geocoding/data/` if you do not need it). The WOF database must not live in the image; [.dockerignore](../.dockerignore) keeps it out of the build context.