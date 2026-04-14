# API

This document covers the Agate API in `apps/agate-api` and summarizes **Core API** routes used by the Agate UI for auth and org administration (`apps/core-api`).

## Core API (session and org admin)

- **Auth:** `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout`, `POST /v1/auth/change-password` (body: `current_password`, `new_password`; session cookie required).
- **Org admin** (session `org_role` = `org_admin` for the same `organization_id` as the path):
  - `GET /v1/organizations/{org_id}/projects` — projects in the org (`id`, `name`, `slug`).
  - `GET /v1/organizations/{org_id}/workspaces` — workspaces in the org, each with nested `projects` (`id`, `name`, `slug`) for admin UI context.
  - `GET /v1/organizations/{org_id}/users` — optional query `detail=true` to include `project_memberships` (legacy explicit grants) and `workspace_memberships` (`id`, `name`, `slug`) per user.
  - `POST /v1/organizations/{org_id}/users` — create user (email, password, display_name, role).
  - `PATCH /v1/organizations/{org_id}/users/{user_id}` — `display_name`, `role` (`org_admin` | `member`); cannot demote the last org admin.
  - `DELETE /v1/organizations/{org_id}/users/{user_id}` — disables the user (`disabled_at`); cannot disable self or the last org admin.
  - `PUT /v1/organizations/{org_id}/users/{user_id}/workspace-memberships` — body `{ "workspace_ids": [ … ] }` replaces workspace assignments for that user (workspaces must belong to `org_id`). Members get access to **all** projects in each assigned workspace. Not applicable to `org_admin` users (they already have every project).
  - `PUT /v1/organizations/{org_id}/users/{user_id}/project-memberships` — **legacy:** body `{ "memberships": [ { "project_id", "role" } ] }` replaces explicit `backfield_project_membership` rows for projects in that org. Prefer `workspace-memberships` for new admin flows; `backfield_auth.gate` still unions legacy explicit rows with workspace-derived project access for members.

**Member project access (sessions / API keys):** `org_admin` sees all org projects. Other members see projects in their assigned workspaces plus any legacy explicit `backfield_project_membership` rows for that org (see `session_project_ids_for_user` in `packages/backfield-auth`).

Handlers live under [`apps/core-api/src/core_api/routers/`](../apps/core-api/src/core_api/routers/) (`auth.py`, `admin_org.py`).

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
  - Project CRUD, stats, and encrypted project secrets.
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

## API change checklist

- Update route models and handlers together.
- Update matching frontend client code in `apps/agate-ui/src/lib/api.ts`.
- Update worker behavior when queue/task/status contracts change.
- Update docs when the API surface, smoke flow, or operational expectations change.