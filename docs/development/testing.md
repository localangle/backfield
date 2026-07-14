# Testing

## Default validation

For Python, API, worker, and package changes:

```bash
make lint
make test
```

`make lint` runs Ruff across `packages`, `apps`, and `tests`.

`make test` combines:

- `make test-unit`: package tests for `backfield-agate`, `backfield-auth`, `backfield-db`, and `backfield-cli`
- `make test-integration`: the root `tests/` pytest suite

For UI changes, also build the affected production bundle:

```bash
make agate-ui-build
make stylebook-ui-build
# or both:
make ui-build
```

The UI build targets install locked dependencies in `packages/backfield-ui` and the selected app before running the production build.

## Test layout

- `packages/*/tests/`: focused package and runtime unit tests
- `tests/agate_api/`: Agate API integration tests
- `tests/core_api/`: Core API integration and bootstrap tests
- `tests/stylebook_api/`: Stylebook API integration tests
- `tests/entities/`: entity-domain tests
- `tests/contracts/`: cross-service schema, index, and runtime contract checks
- `tests/worker/`: worker behavior
- `tests/smoke/`: live-stack and in-process smoke harnesses invoked through Make

Shared root-test fixtures live in `tests/conftest.py`.

## Live-stack smoke tests

Start the stack before running a live lane:

```bash
make up-detached
```

Use the narrowest lane that covers the changed behavior:

- `make smoke-auth`: session login and user scope across Core, Agate, and Stylebook
- `make smoke-agate-basic`: deterministic Text Input to JSON Output run through Agate and the worker
- `make smoke-stylebook-basic`: canonical create/read behavior
- `make smoke`: the primary Agate-to-Stylebook handoff, including Starter flow execution and persisted output
- `make smoke-worker-async`: asynchronous run lifecycle and item detail
- `make smoke-stylebook-editorial`: candidate review and canonical linking
- `make smoke-stylebook-import-export`: GeoJSON analysis and import
- `make smoke-s3-batch`: deterministic S3 batch setup and parent/item summaries

Bundles:

- `make smoke-fast`: auth, Agate basic, and Stylebook basic
- `make smoke-runtime`: handoff and worker lifecycle
- `make smoke-slower`: editorial, import/export, and S3 batch

Optional extract and performance harnesses are also exposed by `make help`: place/geocode, people, organizations, article metadata, custom extract, and parallel graph variants. Their `-stack` targets execute through Agate API; the in-process variants use controlled dependencies where implemented.

The handoff and stack extract lanes need the credentials used by their configured model in the root `.env`. The deterministic fast, editorial, import/export, and S3 batch lanes do not require external LLM or geocoder calls.

Session-shaped smoke configuration:

- `SMOKE_EMAIL`, `SMOKE_PASSWORD`: Core login; `make smoke` uses service Bearer auth when omitted
- `SMOKE_WORKSPACE_SLUG`, `SMOKE_PROJECT_SLUG`: target scope
- `SMOKE_POLL_TIMEOUT_SECONDS`, `SMOKE_POLL_INTERVAL_SECONDS`: polling behavior
- `SMOKE_AGATE_BEARER`: override the Agate Bearer token
- `SMOKE_BOOTSTRAP=1`: create the first Core user on an empty local database
- `SMOKE_KEEP_DATA=1`: retain temporary graphs, runs, canonicals, and entity rows for inspection

Most live DB-writing lanes remove their temporary data by default.

## When to run what

- Documentation-only changes: targeted link or command checks when examples changed
- Python/backend changes: `make lint` and `make test`
- Database changes: default validation plus the relevant migration and live-stack path
- Runtime/integration changes: default validation plus the matching smoke lane
- UI changes: default validation plus the affected UI build and a manual browser pass when interaction behavior changed

Use the starter geocode flow—Text Input → Place Extract → Geocode → Backfield Output—as the primary end-to-end regression path. Add focused tests when changing API names, queue names, statuses, output schemas, graph handles, or entity reconciliation rules.

## CI contract

GitHub Actions uses Python 3.11 and Node.js 20.

On pull requests and pushes to `main`, CI:

1. syncs all Python workspace packages
2. runs `make lint`
3. builds both production UIs and checks their same-origin bundles
4. builds the production API and worker images
5. runs `make test`
6. starts the backend Compose services, waits for all API health endpoints, creates a fixed smoke user, runs the three fast lanes, and runs `make smoke`

The smoke job requires either `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` as a repository secret and writes the available keys to a temporary root `.env`. Fork pull requests cannot normally access repository secrets.

Successful pushes to `main` additionally publish immutable production artifacts. See [deployment](../operations/deployment.md).
