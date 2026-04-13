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
- `make down`: stop the stack and remove orphans.
- `make logs`: inspect compose logs.
- `make migrate`: run Alembic inside `agate-api`.
- `make reset-db`: tear down containers and volumes.
- `make smoke`: run the HTTP golden-path smoke against a live stack.

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

### Flow execution (PlaceExtract, GeocodeAgent)

Graph nodes are executed in the worker using the vendored `agate-runtime` package (ported from agate-ai-platform). The worker reads API keys from the process environment after applying decrypted `agate_project_secret` rows for the graph’s project.

- **Required for LLM PlaceExtract**: `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` (see `agate_utils.llm.call_llm`).
- **GeocodeAgent** may use `OPENAI_API_KEY`, `PELIAS_API_KEY`, `GEOCODIO_API_KEY`, `BRAVE_SEARCH_API_KEY`, and optional Stylebook cache via `STYLEBOOK_API_URL` + `PROJECT_SLUG` + `SERVICE_API_TOKEN`.
- **Who's On First SQLite** (parent lookups in `wof.py`): the database file is not in git (size). Install under `packages/agate-runtime/.../geocoding/data/` or set **`WOF_SQLITE_DB_PATH`** to the `.db` file. See `packages/agate-runtime/src/agate_utils/geocoding/data/README.md`.
- **Celery limits**: `TASK_SOFT_TIME_LIMIT` / `TASK_HARD_TIME_LIMIT` (defaults `3600` / `4200` seconds on the worker service in Compose) mirror agate-ai-platform worker defaults for long-running geocode flows.

For `make smoke`, export at least `OPENAI_API_KEY` if the golden-path graph includes PlaceExtract, or the run will fail when the LLM is invoked.

Docker Compose passes through `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PELIAS_API_KEY`, `GEOCODIO_API_KEY`, `BRAVE_SEARCH_API_KEY`, and `PROJECT_SLUG` from the host environment into the `worker` service.

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