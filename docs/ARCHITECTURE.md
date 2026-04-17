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
  - Owns the shared **`substrate_*`** content/location substrate (`substrate_article`, `substrate_location`, location mentions/occurrences, cache) in addition to **`backfield_*`** tenancy and Agate execution tables.
  - Is the only package that should define DB table names and schema-level conventions.
- `apps/agate-api`
  - Owns HTTP routes for health, projects, graphs, templates, runs, and node metadata.
  - Validates request/response shapes, persists state, and enqueues worker tasks.
- `apps/worker`
  - Owns Celery task execution and runtime concerns for processing runs.
  - Reads from DB, executes `backfield-core`, and writes status/results back to DB.
  - May execute worker-local nodes (e.g. `DBOutput`) that write directly to Postgres using `backfield-db` helpers (see `apps/worker/src/worker/nodes/db_output.py` and `apps/worker/src/worker/substrate_persistence.py`, split across `substrate_common.py`, `substrate_span.py`, `substrate_article.py`, `substrate_location.py`, and `substrate_mentions.py`).
- `packages/backfield-ui`
  - Shared React shell components (`UserAccountMenu`, etc.) for multiple apps.
  - Also publishes **`@backfield/ui/nodeOutputs`**: pure TypeScript helpers that map React Flow graph shape + node types to **`execute_graph` snake_case output keys** (same rules as the Python executor). Agate UI re-exports this from `src/lib/nodeOutputs.ts`; `backfield-core` node sources use the same module via sync-time `@/lib/nodeOutputs` resolution.
- `apps/agate-ui`
  - Owns the flowbuilder UI, API client, and browser-facing interaction patterns.
  - Consumes node metadata and synced node UI generated from `backfield-core`.
- `apps/stylebook-api` (`stylebook_api` Python package to avoid clashing with Agate’s `api` on `PYTHONPATH`)
  - Owns Stylebook HTTP routes: org Stylebook catalog (`/v1/organizations/{org_id}/stylebooks`), starter **`/v1/geocode/resolve`**, and health.
  - Uses the same **`resolve_auth`** pattern as Agate (session cookie, service Bearer, `bfk_` project key) via `backfield-auth` + `backfield-db` sessions.
  - Editorial/canonical HTTP stays here; **worker** materializes `stylebook_*` rows during DBOutput using **`packages/backfield-stylebook`** (no `agate-runtime` → DB dependency).
- `apps/stylebook-ui`
  - Owns the minimal Stylebook browser shell.
- `packages/backfield-auth`
  - Owns signed session tokens, service Bearer validation, FastAPI dependencies, and **`gate.py`** (DB-backed session + project API key resolution against `backfield-db`) shared by Core API and Agate API.
- `apps/core-api`
  - Owns Core domain HTTP routes (auth, org admin, project API credentials, future article import); uses `backfield-db` for users and credentials and `backfield-auth` for session and service authentication.

## Dependency direction

- UI apps may depend on their own components, shared client helpers, and published API contracts.
- `agate-api` may depend on `backfield-core`, `backfield-db`, and `backfield-auth` (when wiring shared auth).
- `worker` may depend on `backfield-core`, `backfield-db`, and `backfield-stylebook` (canonical sync next to substrate persistence).
- `core-api` may depend on `backfield-auth`, `backfield-db`, and `backfield-stylebook` (default Stylebook + workspace creation defaults).
- `backfield-core` may depend on `agate-runtime` and must not depend on app code.
- `agate-runtime` must not depend on app code or `backfield-db`.
  - **TypeScript in `agate-runtime`:** vendored node UI under `src/agate_nodes/*/ui` mirrors agate-ai-platform and uses the same `@/…` aliases as Agate UI for shadcn-style imports. For executor output keys it imports **`@backfield/ui/nodeOutputs`**, matching the **`exports`** entry in `packages/backfield-ui/package.json` (not a Python dependency on `backfield-ui`).
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
    Worker -->|write run results (+ DBOutput substrate writes)| Postgres
    AgateUI -->|poll run| AgateAPI
    AgateAPI -->|read status/result| Postgres
```



## Important conventions

- `GraphSpec` is the canonical stored graph shape.
- Worker-persisted `execute_graph` results use **stable snake_case keys** per node derived from node types (e.g. `geocode_agent`, `json_output`, `stylebook_output`), not internal React Flow ids. The UI resolves a node’s slice by recomputing that key from the graph spec plus the same ordering rules as the executor (legacy payloads may still include `__outputKeysByNodeId` and older human-readable keys).
- Agate execution tables use the `agate_` prefix. Shared **infrastructure** tables use `backfield_` (e.g. `backfield_project`). The shared **substrate** uses `substrate_*` (e.g. `substrate_location`, `substrate_article`).
- `substrate_location` is the durable shared location entity table (still **`project_id`**-scoped). **`stylebook_*`** tables layer editorial canonicalization and alias management; effective Stylebook for a run resolves **`project → workspace → workspace.stylebook_id`**.
- Celery queue and worker name use `agate`.
- Node metadata and optional node UI live in `packages/backfield-core/src/backfield_core/nodes`.
- `apps/agate-ui/scripts/sync-nodes.js` copies node UI and generates the frontend registry.

## Design guidance

- Keep business logic near its owning layer.
- Prefer explicit orchestration over hidden coupling between API, worker, and frontend.
- When a change touches multiple layers, keep naming and payload shapes aligned across all of them.

