# API

This document covers the Agate API in `apps/agate-api` and summarizes **Core API** routes used by the Agate UI for auth and org administration (`apps/core-api`).

## Core API (session and org admin)

- **Auth:** `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout`, `POST /v1/auth/change-password` (body: `current_password`, `new_password`; session cookie required). `GET /v1/auth/me` includes `organization_name` (from `backfield_organization.name`) when authenticated.
- **Session home (any signed-in user):** `GET /v1/me/workspaces` — workspaces with nested `projects` (`id`, `name`, `slug`) the user may access (filtered like Agate’s project list; **org admins** also see **empty** org workspaces with `projects: []`; members see empty workspaces they are assigned to via `backfield_workspace_membership`). Each real workspace includes `stylebook_id` and `stylebook_name`; the synthetic **Other projects** workspace (`slug` `_ungrouped`) omits those when the user has projects without a `workspace_id`. **Session cookie only** (returns 403 for service token or project API key).
- **Org admin** (session `org_role` = `org_admin` for the same `organization_id` as the path):
  - `PATCH /v1/organizations/{org_id}` — body `{ "name": "<publication display name>" }`; updates `backfield_organization.name` (slug unchanged). Service token may also call this route.
  - `GET /v1/organizations/{org_id}/projects` — projects in the org (`id`, `name`, `slug`).
  - `GET /v1/organizations/{org_id}/stylebooks` — Stylebooks in the org (`id`, `name`, `slug`, `is_default`), default first then by name. Org admins only (workspace Stylebook picker, etc.).
  - `GET /v1/organizations/{org_id}/workspaces` — workspaces in the org, each with nested `projects` (`id`, `name`, `slug`) for admin UI context, plus `stylebook_id` and `stylebook_name` for the workspace’s assigned Stylebook.
  - `POST /v1/organizations/{org_id}/workspaces` — body `{ "name": "<display name>", "stylebook_id": <optional int> }`; creates an empty workspace (slug derived from the name, unique per org). Session callers receive a `backfield_workspace_membership` row for the new workspace; service token may also call this route.
  - `PATCH /v1/organizations/{org_id}/workspaces/{workspace_id}` — body may include `name` and/or `stylebook_id` (omit keys you do not want to change); updates `backfield_workspace` (slug unchanged). Org admins only; workspace must belong to `org_id`; Stylebook must belong to the same org.
  - `GET /v1/organizations/{org_id}/users` — optional query `detail=true` to include `project_memberships` (legacy explicit grants) and `workspace_memberships` (`id`, `name`, `slug`) per user.
  - `POST /v1/organizations/{org_id}/users` — create user (email, password, display_name, role).
  - `PATCH /v1/organizations/{org_id}/users/{user_id}` — `display_name`, `role` (`org_admin` | `member`); cannot demote the last org admin.
  - `DELETE /v1/organizations/{org_id}/users/{user_id}` — disables the user (`disabled_at`); cannot disable self or the last org admin.
  - `PUT /v1/organizations/{org_id}/users/{user_id}/workspace-memberships` — body `{ "workspace_ids": [ … ] }` **replaces** workspace assignments for that user with the full list (workspaces must belong to `org_id`). A user may be assigned to **multiple** workspaces (one `backfield_workspace_membership` row per id). Members get access to **all** projects in each assigned workspace. Not applicable to `org_admin` users (they already have every project).
  - `PUT /v1/organizations/{org_id}/users/{user_id}/project-memberships` — **legacy:** body `{ "memberships": [ { "project_id", "role" } ] }` replaces explicit `backfield_project_membership` rows for projects in that org. Prefer `workspace-memberships` for new admin flows; `backfield_auth.gate` still unions legacy explicit rows with workspace-derived project access for members.
  - **AI model catalog** (`backfield_ai_model_config`): org admins configure routing + optional manual prices for cost tracking.
    - `GET /v1/organizations/{org_id}/ai-models/curated-options` — built-in presets (`template_id`, label, default provider/model, suggested capabilities and prices). Templates cover OpenAI, Anthropic, Gemini (`provider` slug `gemini`), OpenRouter, and Mistral; order is stable (dict insertion order).
    - `GET /v1/organizations/{org_id}/ai-models` — rows (`id`, `name`, `provider`, `provider_model_id`, optional `**litellm_model`**, optional `**integration_secret_id**` (numeric id into `**backfield_organization_integration_secret**` for custom models), `model_kind`, `capabilities`, pricing, `status`, latest connection-test metadata).
    - `POST /v1/organizations/{org_id}/ai-models` — create from `**curated_id**` (optional overrides for `name`, prices, `config_json`; do not send `**litellm_model**` / `**integration_secret_id**`) or a **custom** row with `**litellm_model`** (routing string) + `**integration_secret_id**` (must reference an `**ai.credential.***` row in the same org; the same credential may back multiple catalog models), `**name**`, `**capabilities**`, optional prices (generative only — `**embedding**` rejected). Duplicate `**name**` per org returns **409**.
    - `PATCH /v1/organizations/{org_id}/ai-models/{config_id}` — partial update (`name`, prices, `capabilities`, `config_json`, `**status`**, and for credential-backed custom rows `**litellm_model**` / `**integration_secret_id**`). Row must belong to `org_id`.
    - `DELETE /v1/organizations/{org_id}/ai-models/{config_id}` — removes the catalog row (**404** if missing / wrong org). Clears project model overrides and org/project default-role rows pointing at this model; `**backfield_ai_call_record`** rows keep history but `**model_config_id**` is set to **NULL**.
  - **Organization integration secrets** (`backfield_organization_integration_secret`): org admins manage encrypted vendor credentials (preset provider slots and custom `**ai.credential.*`** rows). Responses never include plaintext or ciphertext — only metadata (`integration_secret_id`, `integration_key`, timestamps, labels). Writes require `**MASTER_ENCRYPTION_KEY**` (same Fernet path as project secrets).
    - `GET /v1/organizations/{org_id}/integration-secrets/catalog` — unified credential catalog for AI settings UI: preset slots (`credential_kind`: `**preset**`) plus custom vendor credentials (`**credential_kind**`: `**custom**`); rows expose `**configured**`, `**linked_catalog_models**` (`id`, `name` for each organization catalog model using that credential), `**has_api_base**`, and timestamps—never secret values.
    - `GET /v1/organizations/{org_id}/integration-secrets/ai-provider-catalog` — preset-only subset of the unified catalog (legacy shape).
    - `GET /v1/organizations/{org_id}/integration-secrets` — stored rows for the org (metadata only).
    - `POST /v1/organizations/{org_id}/integration-secrets` — create a new `**ai.credential.<uuid>**` vendor row; JSON `{ "value": "<secret>", "display_name"?: "<optional label>" | null, "api_base"?: "<optional url>" | null }`; returns `**integration_secret_id**` + `**integration_key**` (never echoes `**value**`).
    - `PATCH /v1/organizations/{org_id}/integration-secrets/{integration_key}` — partial update for an existing row (`**value**`, `**display_name**`, `**api_base**`); body must include at least one field.
    - `PUT /v1/organizations/{org_id}/integration-secrets/{integration_key}` — JSON body `{ "value": "<secret>", "display_name"?: "<optional label>" | null, "api_base"?: "<optional url>" | null }`; replaces or creates **preset** slots (`**ai.provider.*`**), **platform integration** preset slots (`**platform.geocode.*`**, `**platform.search.***`, `**platform.storage.***` — see `backfield_ai.constants`), or replaces ciphertext for an existing `**ai.credential.***` row (**404** if the custom key does not exist yet—use `**POST`** first).
    - `DELETE /v1/organizations/{org_id}/integration-secrets/{integration_key}` — removes the stored secret (**404** if missing). Any organization `**ai-models`** rows using this secret are removed first (same cleanup as `**DELETE …/ai-models/{config_id}**` — overrides, default-role picks, call-record FK detach); then the secret row is deleted (**409** if the transaction cannot complete).

**Member project access (sessions / API keys):** `org_admin` sees all org projects. Other members see projects in their assigned workspaces plus any legacy explicit `backfield_project_membership` rows for that org (see `session_project_ids_for_user` in `packages/backfield-auth`).

- **Project API keys (Bearer `bfk_…`):** for callers with access to the project (`require_project_access`):
  - `GET /v1/projects/{project_id}/api-keys` — active keys (`id`, `credential_type`, `key_prefix`, `label`, `created_at`, `user_id` — `null` for `service` keys).
  - `POST /v1/projects/{project_id}/api-keys` — body `{ "credential_type": "user" | "service", "label"?: string }`. Returns `raw_key` **once** on create. `user` keys require a browser session; `service` keys require org admin. Response includes `user_id` for `user` keys.
  - `DELETE /v1/projects/{project_id}/api-keys/{credential_id}` — revoke (session rules: org admin for `service` or another user’s `user` key; owner for own `user` key).
- **Project AI catalog (any member with project access):**
  - `GET /v1/projects/{project_id}/ai-models/effective` — inherited organization **active generative** models; optional query `**capabilities`** (comma-separated); optional `**include_disabled=true**` to list models turned off for this project (workspace **Models** tab).
  - `PUT /v1/projects/{project_id}/ai-models/{model_config_id}/availability` — body `**{ "enabled": boolean }`** toggles visibility for this project only.
  - `PUT /v1/projects/{project_id}/ai-models/{model_config_id}/credential-override` — body `**{ "api_key": "<secret>", "api_base"?: "<url>" | null }**`; stores an org `**backfield_organization_integration_secret**` keyed `**ai.project_model.{project_id}.{model_config_id}**` (worker prefers it over the catalog row’s credential). **Azure** routes require `**api_base`**.
  - `DELETE …/credential-override` — removes the project-only secret and restores organization defaults for execution.

Handlers live under `[apps/core-api/src/core_api/routers/](../apps/core-api/src/core_api/routers/)` (`auth.py`, `me.py`, `admin_org.py`, `credentials.py`, `project_ai_models.py`, `org_ai_models.py`, `org_integration_secrets.py`). Shared helpers live in `[apps/core-api/src/core_api/ai_model_catalog.py](../apps/core-api/src/core_api/ai_model_catalog.py)`, `[apps/core-api/src/core_api/project_ai_catalog.py](../apps/core-api/src/core_api/project_ai_catalog.py)`, and `[apps/core-api/src/core_api/org_integration_secrets.py](../apps/core-api/src/core_api/org_integration_secrets.py)`.

## Stylebook API (`apps/stylebook-api`)

Companion service for geocode, canonical locations, and Stylebook UI (typically port **8003**). Routes are under `**/v1/...`** and use `**project_slug**` (resolved to `backfield_project.id`) plus the same **session cookie** or `**Authorization: Bearer`** (`SERVICE_API_TOKEN` / project access) as other Backfield HTTP apps. Project-scoped catalog routes accept optional query `**stylebook_slug**`: effective catalog resolution is **slug (when provided, resolved in the project’s organization, including rename redirects) → workspace `stylebook_id`** for that project. HTTP routes do not take an integer catalog override today; worker paths (**DBOutput**) may supply `**catalog_stylebook_id`** via shared `**resolve_effective_stylebook_id_for_project**` (see `**docs/ARCHITECTURE.md**` → *Catalog resolution order*).

- **Organization Stylebook library (`project_slug` not required):** routes under `**/v1/organizations/{org_id}/stylebooks…*`*. Callers must match `**organization_id**` on session auth (**403** otherwise); **service token** bypasses that check (full library access for automation). **Read:** `**GET …/stylebooks`** lists Stylebooks in the org (by name); `**GET …/stylebooks/by-slug/{slug}**` resolves the catalog row (follows **rename redirects** from `**stylebook_slug_redirect`**). **Org admin** (or service token) for writes: `**POST …/stylebooks`** body `**name**`, optional `**is_default**` — server derives `**slug**`; `**PATCH …/stylebooks/{stylebook_id}**` rename; `**POST …/stylebooks/{stylebook_id}/set-default**`; `**GET …/stylebooks/{stylebook_id}/delete-preview**` returns graph/node `**stylebook_id**` usage counts from Agate graphs; `**POST …/stylebooks/{stylebook_id}/delete**` JSON body `**confirm_name**` (must match display **name**) and optional `**replacement_default_id`** when deleting the **default** Stylebook (**204**).
- **PlaceExtract location types (taxonomy reference):** `**GET /v1/place-extract-location-types`** — returns `**{ "types": [ … ] }**` (ordered PlaceExtract `location.type` strings; same source as canonical list type filters). Authenticated like other Stylebook routes.
- **Canonical location metadata:** legacy project-scoped routes remain at `GET` / `POST` `**/v1/canonical-locations/{canonical_id}/meta`**, `PATCH` / `DELETE` `**/v1/canonical-locations/{canonical_id}/meta/{meta_id}**` with `**project_slug**`. Canonical detail now uses stylebook-scoped routes: `GET` / `POST` `**/v1/stylebooks/{stylebook_slug}/canonical-locations/{canonical_id}/meta**`, `PATCH` / `DELETE` `**/v1/stylebooks/{stylebook_slug}/canonical-locations/{canonical_id}/meta/{meta_id}**`. JSON blobs live on `**stylebook_location_meta**` (`meta_type` + `**data**`; no separate meta key column). `PATCH` accepts `**data**` and optional `**meta_type**`. List response includes `**location_id**` (same UUID string as the canonical) for UI parity.
- **Canonical location connections:** legacy project-scoped routes remain at `GET` / `POST` `**/v1/canonical-locations/{canonical_id}/connections`**, `PATCH` / `DELETE` `**/v1/canonical-locations/{canonical_id}/connections/{connection_id}**` with `**project_slug**`. Canonical detail now uses stylebook-scoped routes: `GET` / `POST` `**/v1/stylebooks/{stylebook_slug}/canonical-locations/{canonical_id}/connections**`, `PATCH` / `DELETE` `**/v1/stylebooks/{stylebook_slug}/canonical-locations/{canonical_id}/connections/{connection_id}**`. `**canonical_id**` is a **UUID**. Response and stored `**from_entity_id` / `to_entity_id`** are **strings**: UUID text for `**location`**, decimal strings for stub person/org/work ids. `**POST**` body `**to_entity_id**` accepts a UUID string, integer, or UUID object for the target entity. Listing resolves **location** display names from the stylebook; other entity types use a fallback label until those canonicals exist.

**Catalog JSON:** list and detail responses for canonical locations include `**slug`** (immutable per Stylebook) alongside `**id**`, `**label**`, and related fields. Candidate accept / link payloads use `**stylebook_location_id**` / `**stylebook_location_canonical_id**` as **UUID strings** for location canonicals.

- **Connection nature typeahead:** legacy route is `**GET /v1/connections/natures?project_slug=…`**. Canonical detail uses `**GET /v1/connections/stylebooks/{stylebook_slug}/natures**` with optional `**q**` so connection natures follow the whole stylebook rather than one project.
- **Empty canonical lists (UI stubs):** `**GET /v1/people`**, `**GET /v1/organizations**`, `**GET /v1/works**` return paginated **empty** lists (same general shape as agate-ai-platform list endpoints) so connection pickers load; `**POST`** connections to targets that are not yet backed still return **404** from validation.

Routers live under `[apps/stylebook-api/src/stylebook_api/routers/](../apps/stylebook-api/src/stylebook_api/routers/)` (`stylebooks.py`, `location_meta.py`, `connections.py`, `locations.py`, `ui_stubs.py`, …).

## Authentication

All routes except `GET /health` and `GET /nodes/metadata` require authentication:

- **Browser / UI:** `session` cookie (signed with `SESSION_SECRET`, issued by Core API login).
- **Automation:** `Authorization: Bearer <token>` where `<token>` is `SERVICE_API_TOKEN` and/or a project API key (`bfk_…` from `backfield_api_credential`).

Authorization is enforced in-process with the same Postgres tables as Core (`backfield_auth.gate`); Core remains the issuer for API keys.

## Responsibilities

- Expose health, project, graph, template, run, and node metadata routes.
- Validate request and response models at the HTTP boundary.
- Persist graph and run state through `backfield-db`.
- Enqueue run execution onto Celery.
- Keep route handlers readable and focused; move repeated logic into small helpers.

## Route ownership

- `routers/health.py`
  - Lightweight service health only.
- `routers/projects.py`
  - Project CRUD, stats, and encrypted project secrets. `**POST /projects`** accepts optional `workspace_id` (default org only). **Session callers:** `org_admin` may set `workspace_id` to any workspace in that org; **members** may only set it to a workspace where they have a `backfield_workspace_membership` row (otherwise **403**). Omitting `workspace_id` leaves the project unassigned. **Service token** calls are not restricted by workspace membership (automation). `**GET /projects`**, `**GET /projects/{id}**`, and `**GET /projects/by-slug/...**` include `workspace_id`, `workspace_stylebook_id`, `workspace_stylebook_name`, and `**workspace_stylebook_slug**` when the project’s workspace resolves a Stylebook. `**GET /projects/{id}/stats**` and `**GET /projects/by-slug/{slug}/stats**` include `**runs_succeeded**`, `**runs_in_progress**` (pending + running), and `**runs_failed**` (includes cancelled runs, which are stored as `**failed**`); `**avg_duration_ms_per_run**` is mean wall time `(updated_at - created_at)` over **succeeded** runs; `**avg_estimated_ai_cost_per_run`** is tracked LLM spend attributed to **succeeded** runs (same `**backfield_ai_call_record`** fields as the project total cost endpoint) divided by `**runs_succeeded**`, plus `**avg_estimated_ai_cost_currency**` and `**avg_estimated_ai_cost_incomplete**`. `**GET /projects/{id}/estimated-ai-cost**` includes the overall cost fields plus `**model_breakdown**`, a descending-by-cost list of provider model totals (`**provider_model_id**` + `**estimated_total**`). `**avg_duration_ms_per_item**` is the mean of per-row durations on `**agate_processed_item**` for **succeeded** runs (terminal item statuses only: succeeded / failed / timed_out / skipped); when there are no such rows (single-graph runs), it matches `**avg_duration_ms_per_run`**.
- `routers/graphs.py`
  - Graph CRUD and `GraphSpec` validation. Node params may include integer `**stylebook_id**` (catalog row id) on supported node types; Agate API rejects create/update when any referenced id is missing or belongs to another organization (**400**), using `backfield_stylebook.graph_stylebook_refs` for checks. Deleting a graph also removes its run metadata (`**agate_run**`, `**agate_processed_item**`, `**backfield_ai_call_record**`) and clears `**substrate_article.source_run_id**` / `**source_item_id**` so durable article rows are not orphaned by old execution provenance. Impact counts for a future admin delete flow use the same key via `count_stylebook_usage_in_graphs`.
- `routers/templates.py`
  - List templates and instantiate them into project graphs.
- `routers/runs.py`
  - Create, list, fetch, and cancel runs; enqueue `**worker.tasks.execute_s3_batch_setup`** when the graph spec includes an **S3Input** node, otherwise `**worker.tasks.execute_agate_run`**. `**POST /runs/{id}/cancel**` stops a `**pending**` or `**running**` run (marks the run `**failed**` with a fixed cancellation message, fails in-flight batch `**agate_processed_item**` rows). `**POST /runs/{id}/items/{item_id}/rerun**` resets one batch `**agate_processed_item**` row to `**pending**`, clears `**result_json**` / `**error_message**`, sets the parent run back to `**running**` when needed, and enqueues `**worker.tasks.execute_processed_item**` on the `**agate**` Celery queue (same as `**CELERY_QUEUE**`). `**GET /runs**` (list) includes aggregated item counts (`**total_items**`, `**pending_items**`, `**running_items**`, `**succeeded_items**`, `**failed_items**`) plus `**estimated_ai_cost_total**` / `**estimated_ai_cost_total_incomplete**` (sum of all `**backfield_ai_call_record**` rows for each run, batched in one query). `**GET /runs/{id}**` includes the same aggregated item counts, `**processed_items**` (`agate_processed_item` rows), each with `**input_preview**` (short text snippet from common input fields when available) and `**estimated_ai_cost**` / `**estimated_ai_cost_incomplete**` / `**estimated_ai_cost_currency**` rolled up from `**backfield_ai_call_record**`, plus `**whole_run_ai_cost_***` for LLM rows not tied to a batch item (single-graph runs); detail responses also include `**estimated_ai_cost_total**` matching the sum of those rollups. `**GET /runs/{id}/items/{item_id}**` returns one item’s parsed `**input**` / `**output**` (child graph `**result_json**`), additive `**overlay**` (parsed `**overlay_json**`, or `null`) and integer `**overlay_version**` (`0` when never saved), plus `**merged_locations**` and `**stale_overlay_entries**` (location merge lane; see **Processed item location overlay (v1)** below), **`article_context`** (article pane payload; see **Processed item article context (v1)** below), and the same cost rollup fields. `**PATCH /runs/{id}/items/{item_id}**` replaces the review overlay JSON; callers must send header `**If-Match**` set to the current integer `**overlay_version**` (RFC-style quoted value allowed, e.g. `**"0"**`); on success the version increments and the response body matches `**GET**` for that item. Mismatched `**If-Match**` returns **409** with `**detail.current_version**`. Synthetic whole-graph `**items/1**` rows (no `**agate_processed_item**` backing) return **404** for `**PATCH**`.
- `routers/nodes.py`
  - Surface node metadata derived from `agate-runtime`.

## Boundary rules

- Parse data at the route boundary with **Pydantic** models (`BaseModel` or shared types like `GraphSpec` from `agate-runtime`). Prefer explicit request/response models over untyped dicts.
- Prefer **strict typing** in router modules: annotated handlers and helpers, minimal use of `Any`.
- Keep DB table details in `backfield-db`, not duplicated in routers.
- Keep worker task names, queue names, and response statuses aligned with the worker implementation.
- Avoid hiding complex route logic in oversized handlers. Extract helpers when a route gets hard to scan.

## Run lifecycle

1. Client creates a run with `POST /runs`.
2. API inserts an `AgateRun` row with `pending` status.
3. API enqueues `**worker.tasks.execute_s3_batch_setup`** when the graph contains **S3Input**, otherwise `**worker.tasks.execute_agate_run`**, on the `agate` queue.
4. Worker transitions the run to `running`, executes the graph (or S3 batch orchestration + per-file graph runs), then stores `succeeded` or `failed`.
5. Client may call `**POST /runs/{id}/cancel**` while the run is `**pending**` or `**running**` to stop it; the worker cooperates by not overwriting a cancelled run when it finishes.
6. Client polls `GET /runs/{id}` until the run reaches a terminal state (refresh `**processed_items**` for per-file batch progress). For S3 batch rows, `**POST /runs/{id}/items/{item_id}/rerun**` re-queues a single file without starting a new run.
7. `POST /runs`, `GET /runs`, and `GET /runs/{id}` include `mapbox_api_token` when the run’s project has a stored `MAPBOX_API_TOKEN` secret (decrypted server-side for browser map visualizations). Otherwise the field is `null`.

## Processed item location overlay (v1)

Review overlay JSON is stored on **`agate_processed_item.overlay_json`** and updated with **`PATCH /runs/{id}/items/{item_id}`** (see runs router). The merge service reads **immutable** model output from **`output`** / **`node_outputs`** (parsed **`result_json`**) and combines it with the overlay for **`GET …/items/{item_id}`** additive fields.

**Overlay shape — `locations` subsection**

- **`locations.by_anchor`**: object mapping **anchor** string → shallow patch dict. Patches are merged into the matching model place object at the **top level** of that object (same keys as PlaceExtract output: `description`, `original_text`, nested `location`, etc.). Anchor resolution for each model row matches, in order: string **`id`**, else string **`mention_id`**, else **`{node_id}:{index}`** where `node_id` is the **`output`** key and `index` is the row’s position in that node’s **`locations`** array (or, for GeocodeAgent-style **`places`** buckets, a stable index within the flattened **`places`** walk). The merged baseline lane includes every **`locations`** array (or `{ "locations": [ … ] }`) plus flattened entries from **`places.areas.*`**, **`places.points`**, **`places.needs_review`**, and **`places.other`**. When the same anchor appears in both a **`locations`** row and a **`places`** row (typical after geocoding), the **`places`** row wins so review and map edits target geocoded payloads.
- **`locations.user_added`**: array of user-authored rows. Each row **must** have string **`id`** with prefix **`user_place:`** (stable UUID suffix). Prefer a nested **`location`** object (place-shaped dict); otherwise non-`id` top-level keys are treated as the place payload.

**Geometry (map edits, v1)**

Geometry follows **GeoJSON** types **`Point`**, **`Polygon`**, and **`MultiPolygon`** with **`coordinates`** in **`[lng, lat]`** order (same as **`@backfield/ui/LeafletMap`** and Stylebook canonical pages). The Agate verification UI should reuse that **Leaflet** map stack—not a second, incompatible map model.

- **Where geometry lives on a place row:** Geocode-shaped rows typically store map geometry at **`geocode.result.geometry`**. Some payloads may also include a top-level **`geometry`**; both are validated on save when present.
- **`locations.by_anchor` patches:** Patches are still **shallow-merged** into the frozen model place dict (see merge service). Because **`geocode`** is usually a single top-level object, a geometry-only correction from the UI should send a patch whose **`geocode`** value is the **full merged `geocode` object** with **`result.geometry`** updated (not a deep partial that omits sibling keys the model relied on). Other top-level keys (`description`, etc.) may appear in the same patch object.
- **Linked catalog rows:** Map edits remain **run-scoped overlay only**; they must **not** imply Stylebook canonical mutation until an explicit handoff flow (see PRD). The UI may show **model baseline** geometry vs **draft overlay** using separate map layers (same pattern as canonical detail: baseline vs draft).
- **`locations.user_added`:** Each row’s **`location`** (or place-shaped payload) may include the same **`geocode.result.geometry`** shape. **`user_place:`** ids must remain stable across saves.
- **Validation:** **`PATCH …/items/{item_id}`** returns **400** with `{"error": "overlay_geometry_invalid", "message": "<reason>"}` when any geometry is missing a supported **`type`**, has non-finite coordinates, coordinates outside geographic bounds, malformed rings, or exceeds a server-side coordinate budget (currently **4000** numeric positions counted recursively across all geometries in the overlay).

**GET processed item — additive response fields**

- **`merged_locations`**: array of `{ "anchor", "source": "model"|"user", "node_id", "index_in_node", "stale", "location" }`. **`stale`** is always **`false`** for rows included here; the lane lists current model rows (with patches applied) plus valid **`user_place:*`** rows.
- **`stale_overlay_entries`**: array of `{ "anchor", "reason": "anchor_missing_from_model_output", "patch" }` for **`by_anchor`** keys that no longer match any model row (for example after a rerun changed or removed that id).

**Immutability:** **`output`** and **`node_outputs`** are not modified by merge; they remain the worker/model truth. **`overlay`** continues to echo the stored overlay blob.

## Processed item article context (v1)

**`GET /runs/{id}/items/{item_id}`** includes an **`article_context`** object for the verification UI:

- **`article_id`**: substrate row id when **`resolution`** is **`substrate`**, otherwise the requested id when one was parsed but not applied, or **`null`** when none.
- **`headline`**: display headline when known (substrate row or inline fields such as **`headline`**, **`title`**, **`input_headline`** on the item **`input`**).
- **`body`**: text suitable for the article pane (substrate **`text`** when **`substrate`**, else best-effort inline body).
- **`resolution`**: **`substrate`** — row loaded from **`substrate_article`** scoped to the run’s graph **`project_id`**; **`inline_fallback`** — no usable substrate row, but inline text was derived from **`input`**; **`none`** — no article id and no non-empty inline body.
- **`reason`**: optional machine string for UI branching, including **`no_input_article_id`**, **`no_project_scope_for_article_fetch`** (graph not project-scoped), **`article_not_found`**, **`article_deleted`**, **`article_project_mismatch`** (id points at another project’s row).

**Article id on input:** Parsed from **`input_article_id`**, then **`article_id`**, then **`substrate_article_id`** on the processed item **`input`** object (from **`input_json`**).

**Inline body:** Uses the same longest-field heuristic as JSON ingest (**`resolve_document_body_text`** in **`agate-runtime`**): among **`article_text`**, **`articleBody`**, **`article_body`**, **`richTextBody`**, **`rich_text`**, **`body`**, **`content`**, **`story`**, **`full_text`**, **`html`**, **`text`**.

**Transport note (Backfield v1):** **`agate-api`** reads **`substrate_article`** in-process from the shared Postgres session after normal project access checks. A future **core-api** HTTP read proxy may replace the transport without changing this JSON shape.

## Processed item → Stylebook handoff (interim, Issue 7)

- **Save before navigation:** Agate UI must **`PATCH`** the processed item overlay (or confirm the user stays) before opening Stylebook when there are unsaved overlay edits. There is no server-side “handoff” mutation in this slice.
- **Project context for URLs:** **`GET /projects`**, **`GET /projects/{id}`**, and **`GET /projects/by-slug/{slug}`** include **`workspace_stylebook_id`**, **`workspace_stylebook_name`**, and **`workspace_stylebook_slug`** when the project’s **`workspace_id`** resolves to a **`backfield_workspace`** row whose **`stylebook_id`** points at a **`stylebook`** row. Otherwise those three fields are **`null`**.
- **Client deep links (MVP):** The verification screen opens Stylebook in a **new tab** using **`VITE_STYLEBOOK_UI_ORIGIN`** (see `apps/agate-ui` **`platformUrls`**). When the selected place row carries a catalog canonical id (**`stylebook_location_canonical_id`** or **`geocode.result.canonical_id`**), the UI navigates to **`/stylebook/<slug>/locations/canonical/<id>?project=<project_slug>`**. Otherwise it opens the canonical **list** with optional **`q`** prefilled from the place description. **Promote / create canonical from overlay** remains a follow-on once PRD Open Question #4 is settled (no dedicated POST in this slice).

## API change checklist

- Update route models and handlers together.
- Update matching frontend client code in `apps/agate-ui/src/lib/api.ts`.
- Update worker behavior when queue/task/status contracts change.
- Update docs when the API surface, smoke flow, or operational expectations change.