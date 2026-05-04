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

**Member project access (sessions / API keys):** `org_admin` sees all org projects. Other members see projects in their assigned workspaces plus any legacy explicit `backfield_project_membership` rows for that org (see `session_project_ids_for_user` in `packages/backfield-auth`).

- **Project API keys (Bearer `bfk_…`):** for callers with access to the project (`require_project_access`):
  - `GET /v1/projects/{project_id}/api-keys` — active keys (`id`, `credential_type`, `key_prefix`, `label`, `created_at`, `user_id` — `null` for `service` keys).
  - `POST /v1/projects/{project_id}/api-keys` — body `{ "credential_type": "user" | "service", "label"?: string }`. Returns `raw_key` **once** on create. `user` keys require a browser session; `service` keys require org admin. Response includes `user_id` for `user` keys.
  - `DELETE /v1/projects/{project_id}/api-keys/{credential_id}` — revoke (session rules: org admin for `service` or another user’s `user` key; owner for own `user` key).

Handlers live under [`apps/core-api/src/core_api/routers/`](../apps/core-api/src/core_api/routers/) (`auth.py`, `me.py`, `admin_org.py`, `credentials.py`).

## Stylebook API (`apps/stylebook-api`)

Companion service for geocode, canonical locations, and Stylebook UI (typically port **8003**). Routes are under **`/v1/...`** and use **`project_slug`** (resolved to `backfield_project.id`) plus the same **session cookie** or **`Authorization: Bearer`** (`SERVICE_API_TOKEN` / project access) as other Backfield HTTP apps. Project-scoped catalog routes accept optional query **`stylebook_slug`**: when set, the catalog is resolved in the **project’s organization** (including rename redirects); when omitted, the **workspace** Stylebook for the project is used.

- **Organization Stylebook library (`project_slug` not required):** routes under **`/v1/organizations/{org_id}/stylebooks…`**. Callers must match **`organization_id`** on session auth (**403** otherwise); **service token** bypasses that check (full library access for automation). **Read:** **`GET …/stylebooks`** lists Stylebooks in the org (by name); **`GET …/stylebooks/by-slug/{slug}`** resolves the catalog row (follows **rename redirects** from **`stylebook_slug_redirect`**). **Org admin** (or service token) for writes: **`POST …/stylebooks`** body **`name`**, optional **`is_default`** — server derives **`slug`**; **`PATCH …/stylebooks/{stylebook_id}`** rename; **`POST …/stylebooks/{stylebook_id}/set-default`**; **`GET …/stylebooks/{stylebook_id}/delete-preview`** returns graph/node **`stylebook_id`** usage counts from Agate graphs; **`POST …/stylebooks/{stylebook_id}/delete`** JSON body **`confirm_name`** (must match display **name**) and optional **`replacement_default_id`** when deleting the **default** Stylebook (**204**).

- **PlaceExtract location types (taxonomy reference):** **`GET /v1/place-extract-location-types`** — returns **`{ "types": [ … ] }`** (ordered PlaceExtract `location.type` strings; same source as canonical list type filters). Authenticated like other Stylebook routes.

- **Canonical location metadata:** `GET` / `POST` **`/v1/canonical-locations/{canonical_id}/meta`**, `PATCH` / `DELETE` **`/v1/canonical-locations/{canonical_id}/meta/{meta_id}`** — **`canonical_id`** is a **location canonical UUID** (path segment). JSON blobs live on **`stylebook_location_meta`** (`meta_type` + **`data`**; no separate meta key column). `PATCH` accepts **`data`** and optional **`meta_type`**. List response includes **`location_id`** (same UUID string as the canonical) for UI parity.
- **Canonical location connections:** `GET` / `POST` **`/v1/canonical-locations/{canonical_id}/connections`**, `PATCH` / `DELETE` **`/v1/canonical-locations/{canonical_id}/connections/{connection_id}`** — **`canonical_id`** is a **UUID**. Response and stored **`from_entity_id` / `to_entity_id`** are **strings**: UUID text for **`location`**, decimal strings for stub person/org/work ids. **`POST`** body **`to_entity_id`** accepts a UUID string, integer, or UUID object for the target entity. Listing resolves **location** display names from the project’s Stylebook; other entity types use a fallback label until those canonicals exist.

**Catalog JSON:** list and detail responses for canonical locations include **`slug`** (immutable per Stylebook) alongside **`id`**, **`label`**, and related fields. Candidate accept / link payloads use **`stylebook_location_id`** / **`stylebook_location_canonical_id`** as **UUID strings** for location canonicals.
- **Connection nature typeahead:** **`GET /v1/connections/natures?project_slug=…`** optional **`q`** — distinct **`nature`** values for the project (substring filter).
- **Empty canonical lists (UI stubs):** **`GET /v1/people`**, **`GET /v1/organizations`**, **`GET /v1/works`** return paginated **empty** lists (same general shape as agate-ai-platform list endpoints) so connection pickers load; **`POST`** connections to targets that are not yet backed still return **404** from validation.

Routers live under [`apps/stylebook-api/src/stylebook_api/routers/`](../apps/stylebook-api/src/stylebook_api/routers/) (`stylebooks.py`, `location_meta.py`, `connections.py`, `locations.py`, `ui_stubs.py`, …).

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
  - Project CRUD, stats, and encrypted project secrets. **`POST /projects`** accepts optional `workspace_id` (default org only). **Session callers:** `org_admin` may set `workspace_id` to any workspace in that org; **members** may only set it to a workspace where they have a `backfield_workspace_membership` row (otherwise **403**). Omitting `workspace_id` leaves the project unassigned. **Service token** calls are not restricted by workspace membership (automation). **`GET /projects`**, **`GET /projects/{id}`**, and **`GET /projects/by-slug/...`** include `workspace_id`, `workspace_stylebook_id`, `workspace_stylebook_name`, and **`workspace_stylebook_slug`** when the project’s workspace resolves a Stylebook.
- `routers/graphs.py`
  - Graph CRUD and `GraphSpec` validation. Node params may include integer **`stylebook_id`** (catalog row id) on supported node types; Agate API rejects create/update when any referenced id is missing or belongs to another organization (**400**), using `backfield_stylebook.graph_stylebook_refs` for checks. Impact counts for a future admin delete flow use the same key via `count_stylebook_usage_in_graphs`.
- `routers/templates.py`
  - List templates and instantiate them into project graphs.
- `routers/runs.py`
  - Create, list, and fetch runs; enqueue **`worker.tasks.execute_s3_batch_setup`** when the graph spec includes an **S3Input** node, otherwise **`worker.tasks.execute_agate_run`**. **`GET /runs/{id}`** includes **`processed_items`** (``agate_processed_item`` rows). **`GET /runs/{id}/items/{item_id}`** returns one item’s parsed **`input`** / **`output`** (child graph **`result_json`**).
- `routers/nodes.py`
  - Surface node metadata derived from `backfield-core`.

## Boundary rules

- Parse data at the route boundary with **Pydantic** models (`BaseModel` or shared types like `GraphSpec` from `backfield-core`). Prefer explicit request/response models over untyped dicts.
- Prefer **strict typing** in router modules: annotated handlers and helpers, minimal use of `Any`.
- Keep DB table details in `backfield-db`, not duplicated in routers.
- Keep worker task names, queue names, and response statuses aligned with the worker implementation.
- Avoid hiding complex route logic in oversized handlers. Extract helpers when a route gets hard to scan.

## Run lifecycle

1. Client creates a run with `POST /runs`.
2. API inserts an `AgateRun` row with `pending` status.
3. API enqueues **`worker.tasks.execute_s3_batch_setup`** when the graph contains **S3Input**, otherwise **`worker.tasks.execute_agate_run`**, on the `agate` queue.
4. Worker transitions the run to `running`, executes the graph (or S3 batch orchestration + per-file graph runs), then stores `succeeded` or `failed`.
5. Client polls `GET /runs/{id}` until the run reaches a terminal state (refresh **`processed_items`** for per-file batch progress).
6. `POST /runs`, `GET /runs`, and `GET /runs/{id}` include `mapbox_api_token` when the run’s project has a stored `MAPBOX_API_TOKEN` secret (decrypted server-side for browser map visualizations). Otherwise the field is `null`.

## API change checklist

- Update route models and handlers together.
- Update matching frontend client code in `apps/agate-ui/src/lib/api.ts`.
- Update worker behavior when queue/task/status contracts change.
- Update docs when the API surface, smoke flow, or operational expectations change.