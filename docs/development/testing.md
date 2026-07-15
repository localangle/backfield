# Testing

## Default validation

For Python, API, worker, and package changes:

```bash
make lint
make test
```

`make lint` runs Ruff across `packages`, `apps`, and `tests`.

`make test` runs package unit tests under `packages/*/tests` and the root `tests/` suite.

For UI changes, also run frontend typecheck and unit tests, then build the affected production bundle:

```bash
make ui-typecheck
make ui-test
make agate-ui-build
make stylebook-ui-build
# or both UI production builds:
make ui-build
```

`ui-typecheck` and `ui-test` install locked dependencies in `packages/backfield-ui` and each app,
then run TypeScript checks and the package/app test suites. For `apps/agate-ui`, both targets run
`npm run sync-nodes` first so the gitignored node registry exists before `tsc` or tests.
The UI build targets install locked dependencies before running the production build.

## Test layout

- `packages/*/tests/`: focused package and runtime unit tests
- `tests/agate_api/`: Agate API integration tests
- `tests/core_api/`: Core API integration tests
- `tests/stylebook_api/`: Stylebook API integration tests
- `tests/entities/`: entity-domain tests
- `tests/contracts/`: cross-service schema, index, and runtime contract checks
- `tests/worker/`: worker behavior
- `tests/smoke/`: live-stack and specialized smoke harnesses

Shared root-test fixtures live in `tests/conftest.py`.

## Live-stack smoke tests

Start the stack before running a live lane:

```bash
make up-detached
```

Provision an administrator with `backfield init` or `backfield seed` (not HTTP/env bootstrap):

```bash
backfield seed \
  --admin-email smoke@local.test \
  --admin-password-file /tmp/backfield-admin-password
```

Common Make targets:

- `make smoke-fast`: auth, basic Agate, and basic Stylebook checks (no external LLM required)
- `make smoke`: the primary Agate-to-Stylebook handoff, including Starter flow execution and
  persisted output (needs configured model credentials)

Specialized smoke scripts remain available under `tests/smoke/`. Run them directly when you need a
focused lane:

```bash
uv run python -u tests/smoke/smoke_worker_async.py
uv run python -u tests/smoke/smoke_stylebook_editorial.py
uv run python -u tests/smoke/smoke_stylebook_import_export.py
uv run python -u tests/smoke/smoke_s3_batch.py
uv run python -u tests/smoke/place_geocode_smoke.py
uv run python -u tests/smoke/smoke_people_stack.py --via-agate-api
```

The handoff and extract lanes need credentials for their configured model. For local runs, configure
them through **Settings → AI models**; trusted CI may inject provider keys into a temporary root
`.env` as an unattended fallback. The deterministic fast, editorial, import/export, and S3 batch
lanes do not require external LLM or geocoder calls.

Session-shaped smoke configuration:

- `SMOKE_EMAIL`, `SMOKE_PASSWORD`: Core login; `make smoke` uses service Bearer auth when omitted
- `SMOKE_WORKSPACE_SLUG`, `SMOKE_PROJECT_SLUG`: target scope
- `SMOKE_POLL_TIMEOUT_SECONDS`, `SMOKE_POLL_INTERVAL_SECONDS`: polling behavior
- `SMOKE_AGATE_BEARER`: override the Agate Bearer token
- `SMOKE_KEEP_DATA=1`: retain temporary graphs, runs, canonicals, and entity rows for inspection

Most live DB-writing lanes remove their temporary data by default.

## When to run what

- Documentation-only changes: targeted link or command checks when examples changed
- Python/backend changes: `make lint` and `make test`
- Database changes: default validation plus the relevant migration and live-stack path
- Runtime/integration changes: default validation plus `make smoke-fast` and/or `make smoke`
- UI changes: default validation plus `make ui-typecheck`, `make ui-test`, the affected UI build,
  and a manual browser pass when interaction behavior changed

Use the starter geocode flow—Text Input → Place Extract → Geocode → Backfield Output—as the primary
end-to-end regression path. Add focused tests when changing API names, queue names, statuses, output
schemas, graph handles, or entity reconciliation rules.

## CI contract (fork-safe)

GitHub Actions uses Python 3.11 and Node.js 20 on
[localangle/backfield](https://github.com/localangle/backfield).

On pull requests and pushes that run CI:

1. syncs all Python workspace packages
2. runs `make lint`
3. runs `make ui-typecheck ui-test`, builds both production UIs, and checks same-origin bundles
4. builds the production API and worker images
5. runs `make test`
6. secret-scans the tree
7. starts backend Compose services, waits for API health, seeds a fixed smoke user with
   `backfield seed`, and runs **`make smoke-fast`**

**Provider-dependent golden-path smoke** (`make smoke` / `smoke-handoff`) runs only on **trusted
canonical** workflows: the `localangle/backfield` repository, on pushes or on pull requests whose
head branch is in the same repository. That job requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
as a repository secret. Fork pull requests do not receive those secrets and are expected to rely on
`smoke-fast` plus lint/test/UI/image checks.

Successful pushes to `main` on the canonical repository may additionally publish immutable
production artifacts when artifact publisher configuration is present. See
[deployment](../operations/deployment.md).
