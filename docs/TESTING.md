# Testing regime

## Layers

1. **Unit (backfield-core, backfield-auth)**
  Graph execution, node behavior, and wiring; session/service token helpers. Run: `make test-unit` or `uv run pytest packages/backfield-core/tests packages/backfield-auth/tests`.
2. **Integration / API smoke**
  FastAPI apps mounted via `TestClient` where no Docker is required. Run: `make test-integration`.
3. **End-to-end (manual or CI)**
  `make up`, then run `make smoke` or open Agate UI and **Run pipeline**. Validates Postgres, Redis, Celery, and the starter pipeline nodes together (including **DBOutput** persistence). `make smoke` runs the **General** project’s **Starter flow** graph (created by local bootstrap on first API start). Put `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (and optional geocoder keys) in repo-root `.env` so the worker and encrypted project secrets receive them, or the run will fail when those nodes call external APIs.

## Validation ladder

1. **Fast local gate**
  - `make lint`
  - `make test`
  - When changing **`apps/stylebook-ui`** or **`packages/backfield-ui`**, also run **`make stylebook-ui-build`** (`npm ci` in **`packages/backfield-ui`** then **`apps/stylebook-ui`**, then `tsc` + `vite build`).
2. **Structural checks**
  Runtime contract and schema-prefix assertions live in the test suite and run as part of `make test`.
3. **Golden-path smoke**
  `make smoke` against a live stack (implementation: [`tests/smoke/golden_path_stack.py`](../tests/smoke/golden_path_stack.py)). It checks Agate and Stylebook health, then:

  - **If `SMOKE_EMAIL` and `SMOKE_PASSWORD` are set** (including via repo-root **`.env`**, loaded automatically): logs in to Core API (`CORE_API_BASE`, default `http://localhost:8004`), calls **`GET /v1/me/workspaces`** (same data the home page uses), picks workspace slug `SMOKE_WORKSPACE_SLUG` (default `default`) and project `SMOKE_PROJECT_SLUG` (default `general`), then calls Agate with the **`session` cookie** to list graphs and **`POST /runs`** — matching **log in → workspace → project → run**.
  - **Otherwise:** uses **`Authorization: Bearer`** on Agate (defaults to `SERVICE_API_TOKEN` or `SMOKE_AGATE_BEARER` / a project API key), finds the **General** project and **Starter flow** graph, enqueues a run, and polls for completion.

  In both paths it asserts the **Starter flow** `spec` matches bootstrap (`starter_geocode_flow_graph_spec`, ending in **DBOutput**) and the finished run **`result`** includes **`stylebook_output`** with **`success: true`** (and omits **`json_output`** / **`__outputKeysByNodeId`**).

  Poll tuning: `SMOKE_POLL_TIMEOUT_SECONDS` (default 180s). Optional: `SMOKE_BOOTSTRAP=1` with Core credentials to call **`POST /v1/bootstrap/first-user`** first (empty DB only). The smoke does not delete General or the starter graph.
4. **Manual UI pass**
  Use the Agate UI when the task changes browser-facing behavior or flowbuilder interactions.

## Conventions

- Keep the **starter geocode pipeline** (TextInput → PlaceExtract → GeocodeAgent → Stylebook Output / `DBOutput`, no JSON Output node) as the canonical regression story; add tests when changing execution or handles.
- Prefer a few high-signal tests over broad shallow coverage.
- When adding nodes, add a focused unit test under `packages/backfield-core/tests/`.
- When changing API or worker contracts, add or update a test that guards the naming, queue, status, or schema assumption.

### Root `tests/` layout

- **Packages:** unit and tight library tests live under `packages/*/tests/` (for example `packages/backfield-core/tests/`).
- **Repo root `tests/`:** integration and contract tests, grouped by surface so the tree stays navigable:
  - `tests/core_api/` — `core-api` HTTP tests and core-api-only bootstrap/env behavior.
  - `tests/agate_api/` — Agate API `TestClient` tests.
  - `tests/stylebook_api/` — Stylebook API tests (`stylebook_api` app). **`POST /v1/geocode/resolve`** requires auth (service Bearer, session, or `bfk_`), matching production `resolve_auth` behavior. Substrate ↔ canonical editorial routes (**`GET /v1/candidates/{id}/suggested-canonicals`**, **`POST /v1/locations/{id}/link-canonical`**, **`POST /v1/locations/{id}/unlink-canonical`**, **`GET /v1/canonical-locations/{id}/linked-substrates`**) are covered here as well.
  - `tests/stylebook/` — Stylebook-domain pure tests (for example canonical fuzzy-match scoring without Postgres). **Trigram retrieval** against a live Postgres DB is covered by running **`make migrate`** on Compose and exercising ingest/worker paths locally; CI SQLite runs use the dialect fallback only.
  - `tests/contracts/` — cross-cutting structural checks (schema prefixes, indexes, shared runtime contracts) that are not tied to a single HTTP app.
  - `tests/smoke/` — **live-stack** golden-path script (`golden_path_stack.py`), invoked by `make smoke` (not part of `make test` / pytest collection). Optional **PlaceExtract + GeocodeAgent** harness: [`place_geocode_smoke.py`](../tests/smoke/place_geocode_smoke.py) + corpus under [`fixtures/`](../tests/smoke/fixtures/); **`make smoke-place-geocode`** (in-process, JSONL under `tests/smoke/artifacts/`) and **`make smoke-place-geocode-stack`** (`--via-agate-api`; optional **`SMOKE_PLACE_GEOCODE_STACK_GRAPH_ID`**, else Starter flow). See script docstring for env vars.
- Shared pytest defaults for these tests live in `tests/conftest.py` at the repo `tests/` root.
- Add new FastAPI integration tests under the folder that matches the app; add new structural or schema-wide assertions under `tests/contracts/`.

## CI suggestion

```bash
uv sync
make lint
make test
```

The GitHub Actions **smoke** job brings up Compose (including **`core-api`**), waits for Core + Agate + Stylebook health, bootstraps a fixed CI user when the DB is empty, sets **`SMOKE_EMAIL` / `SMOKE_PASSWORD`**, and runs the **session-shaped** golden path. Configure at least one of **`OPENAI_API_KEY`** or **`ANTHROPIC_API_KEY`** as a [repository secret](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions); optionally add **`MAPBOX_API_TOKEN`**. The workflow writes a short-lived repo-root `.env` so `agate-api` / `worker` receive keys (same mechanism as local dev). Fork PRs from outside contributors typically cannot read those secrets, so smoke may be skipped or failed by policy.

**Note:** `make smoke` runs the same module; GNU Make reports **exit code 2** when the recipe fails even if Python exited 1, which can obscure logs in some UIs—prefer invoking `uv run python -u tests/smoke/golden_path_stack.py` in automation when you need a clear process exit code.