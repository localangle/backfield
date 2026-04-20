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
  - Project CRUD, stats, and encrypted project secrets. **`POST /projects`** accepts optional `workspace_id` (default org only). **Session callers:** `org_admin` may set `workspace_id` to any workspace in that org; **members** may only set it to a workspace where they have a `backfield_workspace_membership` row (otherwise **403**). Omitting `workspace_id` leaves the project unassigned. **Service token** calls are not restricted by workspace membership (automation).
- `routers/graphs.py`
  - Graph CRUD and `GraphSpec` validation.
- `routers/templates.py`
  - List templates and instantiate them into project graphs.
- `routers/runs.py`
  - Create, list, and fetch runs; enqueue `worker.tasks.execute_agate_run`.
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
3. API enqueues `worker.tasks.execute_agate_run` on the `agate` queue.
4. Worker transitions the run to `running`, executes the graph, then stores `succeeded` or `failed`.
5. Client polls `GET /runs/{id}` until the run reaches a terminal state.
6. `POST /runs`, `GET /runs`, and `GET /runs/{id}` include `mapbox_api_token` when the run’s project has a stored `MAPBOX_API_TOKEN` secret (decrypted server-side for browser map visualizations). Otherwise the field is `null`.

## API change checklist

- Update route models and handlers together.
- Update matching frontend client code in `apps/agate-ui/src/lib/api.ts`.
- Update worker behavior when queue/task/status contracts change.
- Update docs when the API surface, smoke flow, or operational expectations change.