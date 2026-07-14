# Troubleshooting

Start with:

```bash
backfield doctor
backfield ps
backfield logs --no-follow
```

Filter logs to a service when the failure is isolated:

```bash
backfield logs agate-api worker
```

## The CLI cannot import `backfield_cli`

Run from the repository root:

```bash
make bootstrap
backfield doctor
```

The launcher repairs a failed import probe, but a partial `uv sync` from an app or package directory can leave stale editable installs. Use `uv sync --all-packages` at the root. Do not use `uv run backfield`; `backfield` is a repository launcher, not a Python console-script entry point.

## Initialization or API startup times out

Inspect container state and the failing API:

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs agate-api
```

`backfield init` checks readiness inside each API container. If a container is healthy but the host URL fails or returns unexpected content, another host process may own port 8000, 8003, or 8004. Stop that process or change the port mapping.

Compose orders migrations before database-dependent services. On a cold volume, migration failure can prevent Core API and the worker from starting; inspect the one-off `migrate` service logs.

## A run remains pending

Check:

1. worker logs for startup or task errors
2. Redis connectivity and `REDIS_URL`
3. that producer and worker use the same `CELERY_QUEUE` (`agate` by default)
4. that the worker has the graph's provider credentials

For a batch with many UI items marked Running but few active Celery tasks, old claims may remain after child crashes. The worker reconciles inactive claims using `BATCH_ORPHAN_RUNNING_AFTER_S` and `BATCH_ORPHAN_RECONCILE_INTERVAL_S`. After reconciliation, retry failed items from Agate UI.

## APIs slow down during a large run

Look for long Backfield Output persistence and database timeout errors. API statement/lock timeouts are intended to fail contended reads instead of hanging indefinitely.

Inspect PgBouncer:

```bash
psql postgresql://postgres:postgres@localhost:6432/pgbouncer -c 'SHOW POOLS;'
psql postgresql://postgres:postgres@localhost:6432/pgbouncer -c 'SHOW STATS;'
```

If PostgreSQL reports too many clients, remember that every Celery child has its own SQLAlchemy pool. Reduce worker pool size/overflow, lower `DBOUTPUT_MAX_CONCURRENT_PERSISTS`, reduce `CELERY_WORKER_CONCURRENCY`, tune PgBouncer capacity, or raise PostgreSQL capacity in the deployment. Long-lived processes should use the shared `get_engine()` rather than creating extra engines.

If Backfield Output repeatedly reports deadlocks, workers may be updating the same shared entity row. The worker retries PostgreSQL deadlocks with backoff. Lower `CELERY_WORKER_CONCURRENCY` temporarily if retries remain exhausted.

## Worker children exit with signal 9

Signal 9 without a Celery time-limit message usually indicates an out-of-memory kill. Total memory grows with `CELERY_WORKER_CONCURRENCY` because each prefork child has an import baseline plus the current article's working set.

Lower concurrency or increase the container/Docker VM memory allocation. `CELERY_MAX_MEMORY_PER_CHILD_KB` replaces a child only after a task completes; it cannot prevent a single task from exceeding container memory.

## Worker timeouts

Compare `TASK_SOFT_TIME_LIMIT` and `TASK_HARD_TIME_LIMIT` with node-level LLM timeouts and `AGATE_NODE_TIMEOUT_S`. Local Compose uses 15/18 minutes for processed items, while code fallbacks outside Compose are longer. Do not reduce the soft limit without preserving the node timeout and worker execution buffer.

## Parallel graph execution fails during imports

If LiteLLM/OpenAI reports a Python module-lock deadlock, rebuild and restart the worker so startup import warmup is present. For diagnosis, set this in the root `.env` and restart:

```bash
BACKFIELD_PARALLEL_GRAPH_LEVELS=0
```

This serializes nodes within each item; it does not change concurrency across different batch items.

## Provider or secret errors

- Verify `MASTER_ENCRYPTION_KEY` is the same non-empty value on all APIs and the worker.
- Remove an empty `MASTER_ENCRYPTION_KEY=` line from `.env` or generate a valid Fernet key.
- Verify `SESSION_SECRET` is shared across session-verifying services.
- Verify `SERVICE_API_TOKEN` matches between service callers and APIs.
- For model failures, check the effective project and organization provider credentials on the worker.
- For Stylebook/geocode cache failures, check `STYLEBOOK_API_URL`, project scope, and service auth.

Generate a local Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Stylebook bundle routes return 503

Set `STYLEBOOK_BUNDLE_S3_BUCKET` and matching AWS credentials on both Stylebook API and worker. In Compose, place the values in the root `.env`; an explicitly empty Compose environment override masks `env_file`.

For a non-AWS object store, ensure `AWS_S3_ENDPOINT_URL` or `AWS_ENDPOINT_URL` is reachable by the API, worker, and browser when it follows a presigned export URL.

## Overpass returns 429, 5xx, or HTML

Public interpreters are rate-limited. Lower `OVERPASS_MAX_CONCURRENT`, increase `OVERPASS_QUERY_STAGGER_S`, reduce worker concurrency, or use a dedicated `OVERPASS_API_URL`. Keep a descriptive `OVERPASS_USER_AGENT`. The client retries transient errors and rotates mirrors, but sustained overload still requires less traffic or more capacity.

## UI dependencies are missing

For `vite: not found` or unresolved shared `@backfield/ui` imports, rebuild the affected image without cache:

```bash
docker compose -f infra/docker-compose.yml build agate-ui stylebook-ui --no-cache
make up-detached
```

Compose bind-mounts app and package source while retaining image-built `node_modules` in anonymous volumes. Stale volumes or images can break that alignment.

## Docker reports no space left

Start with cleanup that preserves volumes:

```bash
make docker-trim
```

If more space is required, `make docker-prune-build` removes build cache. `make docker-prune-volumes` and `make docker-trim-full` can delete the database volume after the stack is stopped; use them only when local data loss is acceptable.

## Orphaned Compose resources

Normal cleanup:

```bash
make down
```

If renamed services left orphaned containers:

```bash
docker compose -f infra/docker-compose.yml down --remove-orphans
```

`make down` preserves Compose volumes. Do not add `-v` unless deleting local database data is intentional.
