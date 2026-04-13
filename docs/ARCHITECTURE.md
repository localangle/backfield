# Architecture

Backfield is a small monorepo centered on two product surfaces:

- `Agate`: visual flows, run orchestration, and node execution.
- `Stylebook`: companion APIs and UI for geocode today, broader entities later.

## Reference: agate-ai-platform

This app is **derived from** and is being **refactored from** **agate-ai-platform**. The canonical local checkout used for parity work is:

`/Users/cjdd3b/apps/agate-ai-platform`

When porting features, fixing bugs, or matching UX, **compare against that tree** (same paths under `apps/`, `packages/`, etc., where applicable). Prefer **high-fidelity ports**—copy structure and logic, then adjust imports and Backfield-specific boundaries—rather than reimplementing from memory. Document intentional differences in this repo’s docs or in the change description.

## Package and app boundaries

- `packages/backfield-core`
  - Owns `GraphSpec`, graph execution, thin node runner entrypoints, node metadata, and node UI source files.
  - Delegates heavy node logic to `agate-runtime` for LLM PlaceExtract and LangGraph GeocodeAgent.
  - Should stay free of API routing, database persistence, and frontend app state concerns.
- `packages/agate-runtime`
  - Vendored execution glue (`agate_runtime`), shared helpers (`agate_utils`), and ported nodes under **`agate_nodes/`** (e.g. `geocode_agent`, `place_extract` — no `backfield_` prefix on each node package).
  - Excluded from default Ruff scope in the workspace root config; treat as third-party-style surface when editing.
- `packages/backfield-db`
  - Owns SQLModel models, DB session helpers, encryption helpers, and Alembic migrations.
  - Is the only package that should define DB table names and schema-level conventions.
- `apps/agate-api`
  - Owns HTTP routes for health, projects, graphs, templates, runs, and node metadata.
  - Validates request/response shapes, persists state, and enqueues worker tasks.
- `apps/worker`
  - Owns Celery task execution and runtime concerns for processing runs.
  - Reads from DB, executes `backfield-core`, and writes status/results back to DB.
- `apps/agate-ui`
  - Owns the flowbuilder UI, API client, and browser-facing interaction patterns.
  - Consumes node metadata and synced node UI generated from `backfield-core`.
- `apps/stylebook-api`
  - Owns Stylebook-only HTTP endpoints such as geocode resolution.
- `apps/stylebook-ui`
  - Owns the minimal Stylebook browser shell.

## Dependency direction

- UI apps may depend on their own components, shared client helpers, and published API contracts.
- `agate-api` may depend on `backfield-core` and `backfield-db`.
- `worker` may depend on `backfield-core` and `backfield-db`.
- `backfield-core` may depend on `agate-runtime` and must not depend on app code.
- `agate-runtime` must not depend on app code or `backfield-db`.
- `backfield-db` must not depend on app code.

## Runtime flow

```mermaid
flowchart LR
    AgateUI[AgateUI] -->|create graph / create run| AgateAPI[AgateAPI]
    AgateAPI -->|persist state| Postgres[Postgres]
    AgateAPI -->|enqueue run| Redis[Redis]
    Redis --> Worker[Worker]
    Worker -->|load graph and secrets| Postgres
    Worker -->|execute_graph| Core[backfield_core]
    Core --> Runtime[agate_runtime]
    Runtime -->|optional cache / match| StylebookAPI[StylebookAPI]
    Runtime -->|LLM and external geocoders| ExternalAPIs[ExternalAPIs]
    Worker -->|write result| Postgres
    AgateUI -->|poll run| AgateAPI
    AgateAPI -->|read status/result| Postgres
```



## Important conventions

- `GraphSpec` is the canonical stored graph shape.
- Agate DB tables use the `agate_` prefix.
- Celery queue and worker name use `agate`.
- Node metadata and optional node UI live in `packages/backfield-core/src/backfield_core/nodes`.
- `apps/agate-ui/scripts/sync-nodes.js` copies node UI and generates the frontend registry.

## Design guidance

- Keep business logic near its owning layer.
- Prefer explicit orchestration over hidden coupling between API, worker, and frontend.
- When a change touches multiple layers, keep naming and payload shapes aligned across all of them.

