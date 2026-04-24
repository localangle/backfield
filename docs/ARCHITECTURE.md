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
  - Wires **optional Postgres geocode cache** (Stylebook canonicals + `substrate_location_cache`, same fingerprint as ingest) into `agate-runtime` when the worker sets `BACKFIELD_PROJECT_ID` and the Geocode node params include `stylebookId`, via `backfield-stylebook` helpers on `AgateEnvContext.metadata` (`cache_resolve`).
  - Should stay free of API routing and frontend app state concerns.
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
  - **S3Input batch runs:** `agate-api` enqueues **`execute_s3_batch_setup`** when the stored graph contains an **S3Input** node. That task lists `*.json` keys under the node’s bucket/prefix (using decrypted project AWS keys), validates each document’s top-level **`text`**, writes **`agate_processed_item`** rows (storing the **full** JSON object), then queues a Celery **`chord`** (a **`group`** of **`execute_processed_item`** tasks plus **`finalize_s3_parent_run`**) so the setup task returns without blocking the worker pool while children execute in parallel (bounded by **`CELERY_WORKER_CONCURRENCY`** / worker `--concurrency`). Each child run uses the same `execute_graph` as a normal run but replaces the **S3Input** runner with a shim fed from the row’s **`input_json`**; the shim outputs the same merged payload as **JSONInput** (all top-level fields such as **`headline`**, **`url`**, **`publication`**, not only **`text`**) plus S3 batch metadata (`total_files`, `source_file`, …). **`BACKFIELD_RUN_ID`** stays the parent **`agate_run.id`** so DBOutput substrate writes stay tied to one batch run.
  - May execute worker-local nodes (e.g. `DBOutput`) that write directly to Postgres using `backfield-db` helpers (see `apps/worker/src/worker/nodes/db_output.py` and `apps/worker/src/worker/substrate_persistence.py`, split across `substrate_common.py`, `substrate_span.py`, `substrate_article.py`, `substrate_location.py`, and `substrate_mentions.py`).
- `packages/backfield-ui`
  - Shared React shell components (`UserAccountMenu`, etc.) for multiple apps.
  - Also publishes **`@backfield/ui/nodeOutputs`**: pure TypeScript helpers that map React Flow graph shape + node types to **`execute_graph` snake_case output keys** (same rules as the Python executor). Agate UI re-exports this from `src/lib/nodeOutputs.ts`; `backfield-core` node sources use the same module via sync-time `@/lib/nodeOutputs` resolution.
- `apps/agate-ui`
  - Owns the flowbuilder UI, API client, and browser-facing interaction patterns.
  - Consumes node metadata and synced node UI generated from `backfield-core`.
- `apps/stylebook-api` (`stylebook_api` Python package to avoid clashing with Agate’s `api` on `PYTHONPATH`)
  - Owns Stylebook HTTP routes: org Stylebook catalog (`/v1/organizations/{org_id}/stylebooks`), starter **`/v1/geocode/resolve`**, substrate-backed **location candidate** list/accept under **`/v1/candidates*`** (project slug + workspace-resolved Stylebook), and health.
  - Manual catalog create: **`POST /v1/canonical-locations`** (and legacy **`POST /v1/locations`**) calls **`create_standalone_canonical`** in **`packages/backfield-stylebook`** and inserts **`stylebook_location_canonical`** + primary alias **without** a **`substrate_location`** row (optional **`location_type`** / **`formatted_address`** on the canonical when provided). Ingest/worker paths still upsert substrate first, then link or **`materialize_new_canonical_and_link`**, which **one-time copies** those geography hints from the originating substrate onto a new canonical; linking an existing canonical does **not** overwrite canonical fields from substrate rows.
  - Uses the same **`resolve_auth`** pattern as Agate (session cookie, service Bearer, `bfk_` project key) via `backfield-auth` + `backfield-db` sessions.
  - Editorial/canonical HTTP stays here; **worker** materializes `stylebook_*` rows during DBOutput using **`packages/backfield-stylebook`** (no `agate-runtime` → DB dependency). Ingest policy in `canonical_policy.decide_canonical_persist_plan` auto-creates a canonical when no alias/fuzzy link matches for most `location_type` values; **address** stays deferred up front, and **intersection** (`intersection_highway`, `intersection_road`), **street_road**, and types whose name contains **`span`** still require resolved geocode **with** geometry before materializing. Non-address fuzzy matching is **string-only** (geometry is not blended into the autolink score for neighborhoods/cities/POIs such as **``place``** / **``point``**, etc.); a **head-token gate** blocks fuzzy autolinks when the first comma-separated segment has multiple distinctive tokens that do not all appear on the candidate canonical label/aliases (reduces false links like a neighborhood or school row attaching to a bare ``Chicago, IL`` canonical). Every ingest outcome persists a structured trace on ``substrate_location.canonical_review_reasons_json`` (exact alias, fuzzy autolink, materialize, defer, or ambiguous), not only deferrals.
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
- `backfield-core` may depend on `agate-runtime` and `backfield-stylebook` (for Geocode DB cache wiring) and must not depend on app code.
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
    Runtime -->|legacy HTTP cache (old graphs)| StylebookAPI[StylebookHTTP]
    Runtime -->|LLM and external geocoders| ExternalAPIs[ExternalAPIs]
    Worker -->|write run results (+ DBOutput substrate writes)| Postgres
    AgateUI -->|poll run| AgateAPI
    AgateAPI -->|read status/result| Postgres
```

### Geocode cache (worker DB path)

When **`BACKFIELD_PROJECT_ID`** is set and the Geocode node enables **Use cache** with a **`stylebookId`**, `backfield-core` supplies a synchronous **`cache_resolve`** closure (Postgres session + `backfield_stylebook.geocode_cache_resolve.try_resolve_geocode_cache`) so **`agate-runtime`** tries tier 1 (active canonicals, label + aliases, single winner) then tier 2 (**`substrate_location_cache`** by `query_fingerprint`) before external geocoders. Runs **without** `BACKFIELD_PROJECT_ID` skip DB tiers (debug log) and use external geocoding only; saved graphs may still use **legacy** HTTP canonical/cache when URL + slug are present and no resolver is registered.

## Important conventions

- `GraphSpec` is the canonical stored graph shape.
- Worker-persisted `execute_graph` results use **stable snake_case keys** per node derived from node types (e.g. `geocode_agent`, `json_output`, `stylebook_output`), not internal React Flow ids. The UI resolves a node’s slice by recomputing that key from the graph spec plus the same ordering rules as the executor (legacy payloads may still include `__outputKeysByNodeId` and older human-readable keys).
- Agate execution tables use the `agate_` prefix. Shared **infrastructure** tables use `backfield_` (e.g. `backfield_project`). The shared **substrate** uses `substrate_*` (e.g. `substrate_location`, `substrate_article`).
- `substrate_location` is the durable shared location entity table (still **`project_id`**-scoped) and may reference a **`stylebook_location_canonical`** row via **`stylebook_location_canonical_id`** when editorially linked. **`stylebook_*`** tables layer canonicalization and alias management; effective Stylebook for a project usually resolves **`project → workspace → workspace.stylebook_id`** (see `packages/backfield-stylebook`). **Stylebook Output (`DBOutput`)** node params may set **`stylebook_id`** to override that default (same-org validation in the worker). The node also carries **`canonicalization_mode`** (`rules` or `ai_assisted`), **`auto_apply_canonicalization`**, and **`adjudication_model`** (`gpt-5-nano` or `gpt-5-mini`). When auto-apply is off, ingest leaves candidates **pending** and stores structured **`canonical_suggestion`** / adjudication entries on **`canonical_review_reasons_json`** for Stylebook UI review; **AI-assisted** mode may call an LLM on ambiguous fuzzy matches before recording suggestions or applying links.
- **LLM canonical adjudication** (`apps/worker/src/worker/canonical_adjudication.py`): upgrades to **`link_existing`** only when the model returns **`confidence` ≥ 0.9** and a candidate id that passes **`link_pair_allowed`**; the prompt requires **same real-world place** (not metro containment, “closest city”, or parent admin substitution). Otherwise the plan stays **materialize** / **defer** with **`canonical_adjudication.outcome = no_high_confidence_link`** (metadata includes **`min_confidence_for_link`**).
- Policy **defer** outcomes also emit **`canonical_suggestion.suggested_action: defer`** in review-only mode so the candidates table can highlight **Defer** like link/create suggestions. For **`private_place_or_residence`** deferrals with **auto-apply** enabled, the worker sets **`canonical_link_status`** to **waived** so the row leaves the open candidate queue without a manual defer.
- Celery queue and worker name use `agate`.
- Node metadata and optional node UI live in `packages/backfield-core/src/backfield_core/nodes`.
- `apps/agate-ui/scripts/sync-nodes.js` copies node UI and generates the frontend registry.

## Design guidance

- Keep business logic near its owning layer.
- Prefer explicit orchestration over hidden coupling between API, worker, and frontend.
- When a change touches multiple layers, keep naming and payload shapes aligned across all of them.

