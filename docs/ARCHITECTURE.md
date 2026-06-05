# Architecture

Backfield is a small monorepo centered on two product surfaces:

- `Agate`: visual flows, run orchestration, and node execution.
- `Stylebook`: companion APIs and UI for geocode today, broader entities later.

## Reference: agate-ai-platform

This app is **derived from** and is being **refactored from** **agate-ai-platform**. The canonical local checkout used for parity work is:

`/Users/cjdd3b/apps/agate-ai-platform`

When porting features, fixing bugs, or matching UX, **compare against that tree** (same paths under `apps/`, `packages/`, etc., where applicable). Prefer **high-fidelity ports**—copy structure and logic, then adjust imports and Backfield-specific boundaries—rather than reimplementing from memory. Document intentional differences in this repo’s docs or in the change description.

## Package and app boundaries

- `packages/backfield-agate`
  - Owns `GraphSpec`, graph execution, starter flow helpers, thin node runner entrypoints, node metadata, and node UI source files.
  - Owns shared Agate runtime code under `agate_runtime`, shared helpers under `agate_utils`, and ported nodes under **`agate_nodes/`** (for example `geocode_agent`, `place_extract`, `text_input`, `json_input`, `s3_input`, `output`, `db_output`).
  - Wires the optional Postgres geocode cache (Stylebook canonicals + `substrate_location_cache`, same fingerprint as ingest) into `AgateEnvContext.metadata` when the worker sets `BACKFIELD_PROJECT_ID` and the Geocode node params include **`stylebook_id`** (legacy **`stylebookId`** graphs still load).
  - Must stay free of API routing and frontend app state concerns.
- `packages/backfield-db`
  - Owns SQLModel models, DB session helpers, encryption helpers, and Alembic migrations.
  - Owns the shared **`substrate_*`** content/location substrate (`substrate_article`, `substrate_location`, location mentions/occurrences, cache) in addition to **`backfield_*`** tenancy and Agate execution tables.
  - Is the only package that should define DB table names and schema-level conventions.
- `apps/agate-api`
  - Owns HTTP routes for health, projects, graphs, templates, runs, and node metadata.
  - Processed-item review logic lives in `api/processed_item/` (`content/`, `entities/location/`, `overlay/`, shared `mention_occurrences.py`), consumed by the runs router. See [`ENTITY_TYPES.md`](ENTITY_TYPES.md) for layout when adding entity types.
  - Validates request/response shapes, persists state, and enqueues worker tasks.
- `apps/worker`
  - Owns Celery task execution and runtime concerns for processing runs.
  - Reads from DB, executes `agate-runtime`, and writes status/results back to DB.
  - **Processed items:** Every run that processes article-shaped input uses **`agate_processed_item`** rows. **S3Input batch runs:** `agate-api` enqueues **`execute_s3_batch_setup`** when the stored graph contains an **S3Input** node. That task lists `*.json` keys under the node’s bucket/prefix (using decrypted project AWS keys), validates each document has a non-empty article body (see **`resolve_document_body_text`** in **`agate_runtime.nodes.json_input`**: longest non-empty among **`article_text`**, **`body`**, **`content`**, **`text`**, and related keys), writes **`agate_processed_item`** rows (storing the **full** JSON object), then queues a Celery **`chord`** (a **`group`** of **`execute_processed_item`** tasks plus **`finalize_s3_parent_run`**) so the setup task returns without blocking the worker pool while children execute in parallel (bounded by **`CELERY_WORKER_CONCURRENCY`** / worker `--concurrency`). **Single TextInput / JSONInput runs:** `POST /runs` inserts one row (ingress params snapshotted in **`input_json`**) and enqueues **`execute_processed_item`** immediately. Each **`execute_processed_item`** run uses the same `execute_graph` as other item runs but replaces ingress node runners (**S3Input**, **TextInput**, or **JSONInput**) with shims fed from the row’s **`input_json`**; S3 shims also emit batch metadata (`total_files`, `source_file`, …). **`finalize_s3_parent_run`** (also invoked after each single-item child) aggregates parent **`agate_run`** status when all items are terminal. **`BACKFIELD_RUN_ID`** stays the parent **`agate_run.id`** so DBOutput substrate writes stay tied to one run. Legacy runs without item rows may still use **`execute_agate_run`** (whole-graph result on **`agate_run.result_json`** only); the UI exposes those as synthetic **`items/1`**.
  - May execute worker-local nodes (e.g. `DBOutput`) that write directly to Postgres using `backfield-db` helpers (see `apps/worker/src/worker/nodes/db_output.py`). Substrate ingest lives under `apps/worker/src/worker/substrate/` (`content/` for article, `entities/location/` for places, `canonical/` for adjudication, `orchestration.py` for `persist_from_consolidated`). Adding canonical types: see [`ENTITY_TYPES.md`](ENTITY_TYPES.md) and `.cursor/skills/add-entity-type/SKILL.md`.
- `packages/backfield-ui`
  - Shared React shell components (`UserAccountMenu`, etc.) for multiple apps.
  - Also publishes **`@backfield/ui/nodeOutputs`**: pure TypeScript helpers that map React Flow graph shape + node types to **`execute_graph` snake_case output keys** (same rules as the Python executor). Agate UI re-exports this from `src/lib/nodeOutputs.ts`; synced `agate-runtime` node sources use the same module via sync-time `@/lib/nodeOutputs` resolution.
- `apps/agate-ui`
  - Owns the flowbuilder UI, API client, and browser-facing interaction patterns.
  - Consumes node metadata and synced node UI generated from `agate-runtime`.
- `apps/stylebook-api` (`stylebook_api` Python package to avoid clashing with Agate’s `api` on `PYTHONPATH`)
  - Owns Stylebook HTTP routes: org Stylebook catalog (`/v1/organizations/{org_id}/stylebooks`), starter **`/v1/geocode/resolve`**, substrate-backed **location candidate** list/accept under **`/v1/candidates*`** (project slug + workspace-resolved Stylebook), and health.
  - Manual catalog create: **`POST /v1/canonical-locations`** (and legacy **`POST /v1/locations`**) calls **`create_standalone_canonical`** in **`packages/backfield-entities`** and inserts **`stylebook_location_canonical`** + primary alias **without** a **`substrate_location`** row (optional **`location_type`** / **`formatted_address`** on the canonical when provided). Ingest/worker paths still upsert substrate first, then link or **`materialize_new_canonical_and_link`**, which **one-time copies** those geography hints from the originating substrate onto a new canonical; linking an existing canonical does **not** overwrite canonical fields from substrate rows.
  - Uses the same **`resolve_auth`** pattern as Agate (session cookie, service Bearer, `bfk_` project key) via `backfield-auth` + `backfield-db` sessions.
  - Editorial/canonical HTTP stays here; **worker** materializes `stylebook_*` rows during DBOutput using **`packages/backfield-entities`** (no `agate-runtime` → DB dependency). **Location** ingest policy in `entities.location.policy.decide_location_canonical_persist_plan` auto-creates a canonical when no alias/fuzzy link matches for most `location_type` values; **address** stays deferred up front; **`span`** (roadway between endpoints) is **always deferred**—not auto-linked or auto-materialized as a canonical. **intersection** (`intersection_highway`, `intersection_road`) and **street_road** still require resolved geocode **with** geometry before materializing. Non-address fuzzy matching is **string-only** (geometry is not blended into the autolink score for neighborhoods/cities/POIs such as **``place``** / **``point``**, etc.); a **head-token gate** blocks fuzzy autolinks when the first comma-separated segment has multiple distinctive tokens that do not all appear on the candidate canonical label/aliases (reduces false links like a neighborhood or school row attaching to a bare ``Chicago, IL`` canonical). **Strict canonical gates** (default **on**; disable with **`BACKFIELD_STRICT_CANONICAL_GATES=0`**) add deterministic checks before autolink: **`link_pair_allowed`** deny-list for gross type mismatches (e.g. state ↔ POI) plus **city/county**, **city or town/village ↔ neighborhood**, **city/town ↔ `region_city`**, **`region_city` ↔** linear corridors (`street_road`, intersections, **`span`**), **`place`/`point` ↔ `street_road`**, and **linear types** (`street_road`, intersections, **`span`**) ↔ **neighborhood**; **container-vs-fine** blocking (city/town/county/**`region_city`** … ↔ place/neighborhood/address); **jurisdiction** consistency using PlaceExtract components vs **`stylebook_location_canonical`** `country_code` / `subdivision_code`; **components vs formatted-address** country/state sanity; **distance vs cached container city** geometry (tier-2 **`substrate_location_cache`** hit only—no live geocode on miss); **polygon bbox diagonal** caps for fine-grained types; **address → neighborhood** autolink requires the address point inside the neighborhood bbox and within **50 km** of the neighborhood centroid (skip when geometry is missing); **PlaceExtract `political_district`** rows with a full structured **district key** **defer** when fuzzy recall returns no canonical with that same **`district_key`** (stored on canonicals materialized from PlaceExtract); recall scoring **demotes** political-district candidates whose **`district_key`** disagrees with the substrate. **GeocodeAgent consolidate** may route **`city`** rows with a PlaceExtract **city** to **`needs_review`** when the resolved hit looks **state-only** (`geocode_qa_code` **`geocode_admin_level_mismatch`**, e.g. Portland ME → Maine). Every ingest outcome persists a structured trace on ``substrate_location.canonical_review_reasons_json`` (exact alias, fuzzy autolink, materialize, defer, or ambiguous), not only deferrals. **Person** ingest uses `entities.person.policy.decide_person_canonical_persist_plan` (tier-1 exact name + affiliation link; alias/label recall capped at 24; `ambiguous_person_canonical_match` → pending or `ai_assisted` LLM in `worker/substrate/entities/person/adjudication.py` at confidence ≥ 0.9; when the model declines all recall matches and `person_may_materialize_canonical_after_recall`, auto-materialize a new canonical—blocked by PersonExtract `flag_review` / `auto_defer`).
- `apps/stylebook-ui`
  - Owns the minimal Stylebook browser shell.
- `packages/backfield-auth`
  - Owns signed session tokens, service Bearer validation, FastAPI dependencies, and **`gate.py`** (DB-backed session + project API key resolution against `backfield-db`) shared by Core API and Agate API.
- `apps/core-api`
  - Owns Core domain HTTP routes (auth, org admin, project API credentials, future article import); uses `backfield-db` for users and credentials and `backfield-auth` for session and service authentication.

## Dependency direction

- UI apps may depend on their own components, shared client helpers, and published API contracts.
- `agate-api` may depend on `agate-runtime`, `backfield-db`, and `backfield-auth` (when wiring shared auth).
- `worker` may depend on `agate-runtime`, `backfield-db`, and `backfield-entities` (canonical sync next to substrate persistence).
- `core-api` may depend on `backfield-auth`, `backfield-db`, and `backfield-entities` (default Stylebook + workspace creation defaults).
- `agate-runtime` may depend on `backfield-db` and `backfield-entities` for shared executor/runtime wiring (for example the Geocode cache bundle), but must not depend on app code.
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
    Worker -->|execute_graph| Agate[agate_runtime]
    Agate --> Runtime[agate_nodes + agate_utils]
    Runtime -->|legacy HTTP cache (old graphs)| StylebookAPI[StylebookHTTP]
    Runtime -->|LLM and external geocoders| ExternalAPIs[ExternalAPIs]
    Worker -->|write run results (+ DBOutput substrate writes)| Postgres
    AgateUI -->|poll run| AgateAPI
    AgateAPI -->|read status/result| Postgres
```

### Geocode cache (worker DB path)

When **`BACKFIELD_PROJECT_ID`** is set and the Geocode node enables **Use cache** with a persisted **`stylebook_id`** on the node, `agate-runtime` attaches a **`geocode_cache_bundle`** on `AgateEnvContext.metadata` with three sync DB closures (opened per call via `sqlmodel.Session`): **strict resolve with outcome**, **permissive adjudication candidate listing**, and **canonical materialization**. **`agate-runtime`** runs **strict deterministic tiers first**: tier 1 is **exact only** (normalized query equals canonical **label** or a non-suppressed **alias**, same `normalize_substrate_cache_query` as ingest); a **singleton** auto-hit also requires **`link_pair_allowed`** / container-vs-fine Stylebook policy between extractor type and canonical **`location_type`** (**city**/**town**/**village** ↔ **`political_district`** is denied). Ward/precinct-shaped labels (or tier-2 **`formatted_address`** / **`location_name`**) are rejected for municipality mentions even when normalized aliases collide. **ambiguous tier 1** (multiple equal-string winners) does **not** fall through to tier 2. Tier 2 is **`substrate_location_cache`** by `query_fingerprint`; optional **PlaceExtract component sanity** (e.g. state abbreviation present in row strings) can reject a fingerprint hit. **Content sanity** (`geocode_cache_sanity`) additionally blocks cache auto-hits when a street-address or POI extract would resolve to a city-or-coarser canonical/row without the street or venue name in the cached label (poisoned tier-1 aliases or tier-2 rows); failures set **`tier2_sanity_failed`** so optional LLM adjudication or external geocode can run. Address/place rows that still receive a coarse Stylebook geometry are flagged in consolidate **`geocode_city_level_fallback`** QA. After strict tiers, an optional **LLM adjudication** step (evaluation model; toggles **`useCacheLlmAdjudication`** / **`useCacheLlmAdjudicationOnMissRecall`**) may choose among **closed-list** canonicals from trigram alias recall (`retrieve_candidate_canonical_ids`, permissive recall **excluding** ward-like rows when the mention is a municipality) plus ambiguous tier-1 ids; it never invents geometry. Runs **without** `BACKFIELD_PROJECT_ID` skip DB tiers (debug log) and use external geocoding only; saved graphs may still use **legacy** HTTP canonical/cache when URL + slug are present and **`geocode_cache_bundle`** is absent (legacy **`cache_resolve`** callable remains supported).

### Catalog resolution order (workspace bridge)

Across APIs and the worker, **which catalog** applies follows one precedence chain wherever **`resolve_effective_stylebook_id_for_project`** is used:

1. **Explicit catalog row id** — caller-supplied integer (validated against the project’s organization).
2. **Catalog slug** — e.g. optional **`stylebook_slug`** query on Stylebook HTTP routes (resolved in the project’s organization, including redirects).
3. **Workspace default** — **`workspace.stylebook_id`** for the project’s workspace (**`resolve_stylebook_id_for_project_id`**).

**Worker DBOutput** uses **`resolve_effective_stylebook_id`** (same precedence via delegation): optional node **`stylebook_id`** wins; omitted/null falls through to the workspace catalog.

**Worker GeocodeAgent** (database cache tier) does **not** use this fallback chain for cache lookups; when cache is on, the catalog id on the node is authoritative — see **`packages/backfield-entities/src/backfield_entities/resolve.py`** module docstring for rationale.

Legacy workspaces without a resolvable **`workspace.stylebook_id`** still surface **`LookupError`** from step **3**; DBOutput persistence catches **`LookupError`** and skips catalog-backed canonicalization rather than failing the whole ingest row batch — upgrade paths remain documented here.

## Important conventions

- `GraphSpec` is the canonical stored graph shape.
- Worker-persisted `execute_graph` results use **stable snake_case keys** per node derived from node types (e.g. `geocode_agent`, `json_output`, `stylebook_output`), not internal React Flow ids. The UI resolves a node’s slice by recomputing that key from the graph spec plus the same ordering rules as the executor (legacy payloads may still include `__outputKeysByNodeId` and older human-readable keys).
- Agate execution tables use the `agate_` prefix. Shared **infrastructure** tables use `backfield_` (e.g. `backfield_project`). The shared **substrate** uses `substrate_*` (e.g. `substrate_location`, `substrate_article`).
- `substrate_location` is the durable shared location entity table (still **`project_id`**-scoped) and may reference a **`stylebook_location_canonical`** row via **`stylebook_location_canonical_id`** when editorially linked. When the same article URL is ingested again (batch re-run or a later batch pass), **`retire_stale_article_mentions_for_rerun`** soft-deletes mentions whose geocode identity no longer appears in the new extract; **`dispose_orphan_substrates_after_retired_mentions`** then unlinks and deletes any linked substrate that has **no active mentions anywhere** (so superseded ingest does not leave empty canonical links). **`stylebook_*`** tables layer canonicalization and alias management; the shared resolver (**explicit catalog id → slug → workspace default**) is documented above and implemented in **`backfield_entities.resolve`**. **Backfield Output (`DBOutput`)** node params may set **`stylebook_id`** to override the workspace catalog for persistence (same-org validation). The node also carries **`canonicalization_mode`** (`rules` or `ai_assisted`), **`auto_apply_canonicalization`**, **`adjudication_model`** (provider model id from the project’s effective AI catalog, same as other graph model pickers), optional **`adjudication_ai_model_config_id`** for catalog credentials, and optional **`semantic_indexing_enabled`** (default off). When **`semantic_indexing_enabled`** is on, the worker synchronizes **`substrate_*_semantic_document`** rows after substrate persistence for persisted **`people`** / **`places`** domains, then batch-embeds pending documents using the project or organization default **`semantic.embedding`** model, and returns a compact **`semantic_indexing`** summary (including **`embedding`** counts) on the node output; generic JSON Output does not run this step. When auto-apply is off, ingest leaves candidates **pending** and stores structured **`canonical_suggestion`** / adjudication entries on **`canonical_review_reasons_json`** for Stylebook UI review; **AI-assisted** mode may call an LLM on ambiguous fuzzy matches before recording suggestions or applying links.
- **LLM canonical adjudication** (`apps/worker/src/worker/canonical_adjudication.py`): upgrades to **`link_existing`** only when the model returns **`confidence` ≥ 0.9** and a candidate id that passes **`link_pair_allowed`** and is not blocked by **`autolink_container_to_fine_denied`** (same container-vs-POI rule as rules-based autolink). **`link_pair_allowed`** applies a small **deny-list** for gross type mismatches (e.g. **state** ↔ **place**) plus **city/county**, **city/town/village ↔ state / `region_state`** (municipality vs parent subdivision), **address ↔ neighborhood**, **intersection ↔ `place`/`point`**, **city–neighborhood**, **city/town ↔ `region_city`**, **`region_city` ↔ linear**, **linear ↔ city/town** (street/intersection/span vs municipality), **`place`/`point` ↔ `street_road`**, **linear ↔ neighborhood**, **`place` ↔ `neighborhood`**, **`place` ↔ `region_city`**, **`neighborhood` ↔ `region_city`**, and **`place`/`point` ↔ `city`/`town`/`village`** (manual relink may still bypass the type gate). **Address** and **intersection** rows additionally use **`geocode_cache_sanity`** content checks (street fragment / venue name on the canonical label) on cache hits, fuzzy recall, and exact-alias ingest so token overlap on a city or neighborhood name cannot substitute for street or POI identity. The prompt requires **same real-world place** (not metro containment, “closest city”, or parent admin substitution). For **`political_district`**, **AI-assisted** mode also runs adjudication on **rules-based fuzzy autolink** plans (not only **`ambiguous_canonical_match`**): the prompt includes structured **district identity**, and a post-check **rejects** a high-confidence pick when the substrate’s **`district_key`** disagrees with the chosen canonical (**`district_key_mismatch_coerced`** → **materialize** or **defer**). Otherwise the plan stays **materialize** / **defer** with **`canonical_adjudication.outcome = no_high_confidence_link`** (metadata includes **`min_confidence_for_link`**).
- Policy **defer** outcomes also emit **`canonical_suggestion.suggested_action: defer`** in review-only mode so the candidates table can highlight **Defer** like link/create suggestions. For **`private_place_or_residence`** deferrals with **auto-apply** enabled, the worker sets **`canonical_link_status`** to **waived** so the row leaves the open candidate queue without a manual defer.
- Celery queue and worker name use `agate`.
- Node metadata and optional node UI live in `packages/backfield-agate/src/agate_nodes`.
- `apps/agate-ui/scripts/sync-nodes.js` copies node UI from `packages/backfield-agate/src/agate_nodes/*/ui/` into `apps/agate-ui/src/nodes/` and generates the frontend registry. Edit node panels in the package tree, not the synced app copies.

## Design guidance

- Keep business logic near its owning layer.
- Prefer explicit orchestration over hidden coupling between API, worker, and frontend.
- When a change touches multiple layers, keep naming and payload shapes aligned across all of them.

