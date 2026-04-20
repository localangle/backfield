# Frontend

This document covers frontend conventions for `apps/agate-ui` and `apps/stylebook-ui`.

## Stylebook UI (Backfield)

- **Scope key (first slice):** the UI keeps **agate-ai-platform–style `project_slug`** in the query string (`?project=…`) as the primary navigation scope. **`stylebook-api`** resolves the slug to `backfield_project.id`. **`substrate_location`** rows are project-scoped place instances; the Stylebook **catalog** is **`stylebook_location_canonical`** (one row per editorial canonical), linked via **`substrate_location.stylebook_location_canonical_id`**.
- **First-slice routes (supported):** `/` (dashboard), `/locations/candidates`, `/locations/canonical` (lists **`GET /v1/canonical-locations`**, ids are **canonical** ids), `/locations/canonical/:id` (detail uses **`GET /v1/canonical-locations/{id}`**, **`…/mentions`**, and **`GET …/linked-substrates`** for substrate rows linked to that canonical), `/locations/create` (creates a catalog canonical only via **`POST /v1/canonical-locations`** or legacy **`POST /v1/locations`** — **no** `substrate_location` row; navigate using the returned canonical **`id`**), plus **stub** pages for import, other entity candidates, and agents so deep links do not 404.
- **Canonical linking (substrate vs catalog):** open candidates are **`substrate_location`** rows with **`canonical_link_status = pending`** and a **null** `stylebook_location_canonical_id`. The candidates table offers **Link to canonical**, which opens a modal: **`GET /v1/candidates/{substrate_location_id}/suggested-canonicals`** (ingest-style ranking; no scores in JSON) plus manual catalog search via **`GET /v1/canonical-locations?q=…`**, then confirm with **`POST /v1/locations/{substrate_location_id}/link-canonical`** (`{ "stylebook_location_canonical_id": <int> }`, idempotent `changed: false` when already on that canonical). The canonical detail page uses **one table** of linked places with article mentions nested under each place (mentions include **`substrate_location_id`** for grouping; the UI loads up to **500** mentions per canonical). **Unlink** is **`POST /v1/locations/{id}/unlink-canonical`** (returns row to the open queue; safe alias cleanup on the old canonical is server-side). **Move…** uses the same modal + link endpoint for atomic A→B relink. Legacy **`POST /v1/candidates/{id}/accept`** remains for “accept as new” / accept-by-id flows.
- **Auth:** Core API session only — `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout` with **`email` + `password`**, same as Agate UI. Use **`VITE_AUTH_API_BASE`** as empty string in dev so the browser stays on the Stylebook UI origin and the Vite proxy forwards `/v1` to Core.
- **Proxies (local dev):** [`apps/stylebook-ui/vite.config.ts`](../apps/stylebook-ui/vite.config.ts) mirrors Agate UI:
  - `/v1` → Core API (`VITE_CORE_API_PROXY_TARGET`, default `http://localhost:8004`)
  - `/api/agate` → Agate API (`VITE_AGATE_API_PROXY_TARGET`, default `http://localhost:8000`), strip prefix
  - `/api/stylebook` → Stylebook API (`VITE_STYLEBOOK_API_PROXY_TARGET`, default `http://localhost:8003`), strip prefix
- **API bases:** `VITE_AGATE_API_BASE` defaults to `/api/agate` (project picker: `GET /projects`). `VITE_STYLEBOOK_API_BASE` defaults to `/api/stylebook` (locations and UI-compat stubs under `/v1/...` on the Stylebook service). All fetches use **`credentials: 'include'`** so the Core session cookie is sent to the dev origin.
- **Client layout:** typed calls are split under `apps/stylebook-ui/src/lib/stylebook-api/` and re-exported from `src/lib/api.ts` for pages that still follow the agate-ai-platform import style.

## Agate UI responsibilities

- Render the flowbuilder and run experience.
- Own browser-facing API access through `src/lib/api.ts`.
- Consume generated node registry output from `src/nodes/registry.ts`.
- Keep page and component code readable, explicit, and easy to scan.

## Auth and API bases (Agate UI)

- **Core API (login / session):** `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout`, `POST /v1/auth/change-password`. `GET /v1/auth/me` returns `organization_name` (publication / tenant display name). `GET /v1/me/workspaces` lists workspaces and visible projects for the signed-in user (used on `/`, `/workspace/:workspaceSlug`, and in the sidebar). Organization admin routes under `/v1/organizations/{org_id}/…` (users, workspaces, workspace rename, workspace memberships — admins can assign a user to **multiple** workspaces via `PUT …/workspace-memberships`). Use `**VITE_AUTH_API_BASE`** (empty string for same-origin). Typed fetch helpers live in `**src/lib/core-api.ts**` (session cookie, `credentials: 'include'`).
- **Project Settings — two credential concepts:** (1) **API access keys** (`bfk_…`) are issued by Core API (`/v1/projects/{id}/api-keys`); the Settings tab uses `**core-api.ts`** helpers and `[ProjectAccessKeysPanel](../apps/agate-ui/src/components/ProjectAccessKeysPanel.tsx)` for Bearer access to Backfield APIs. (2) **Integration secrets** (OpenAI, Mapbox, etc.) are stored via Agate API `/projects/{id}/secrets` and `**api.ts`** — encrypted provider env for flows, not Bearer keys.
- **Agate API:** project/graph/run calls go through `**src/lib/api.ts`**. Default `**VITE_API_BASE**` is `/api/agate` so the Vite dev server can proxy to `agate-api` on one browser origin with `credentials: 'include'`. New project workspace selection should match `GET /v1/me/workspaces`; Agate API rejects `workspace_id` values the session user is not allowed to assign (see `docs/API.md`).
- **Local dev proxy:** `[apps/agate-ui/vite.config.ts](../apps/agate-ui/vite.config.ts)` proxies `/v1` → Core API and `/api/agate` → Agate API. Override targets with `VITE_CORE_API_PROXY_TARGET` / `VITE_AGATE_API_PROXY_TARGET` (e.g. in Docker Compose).

## Shared UI package (`@backfield/ui`)

- Reusable shell components for multiple Backfield apps (Agate UI now; Stylebook UI later) live in `[packages/backfield-ui](../packages/backfield-ui)`.
- **`nodeOutputs`:** `@backfield/ui/nodeOutputs` holds the canonical mapping from graph topology + node types to **`execute_graph` output keys** (snake_case slugs, legacy keys, `__outputKeysByNodeId`). Agate UI imports it through `[apps/agate-ui/src/lib/nodeOutputs.ts](../apps/agate-ui/src/lib/nodeOutputs.ts)`. Synced `backfield-core` panels use `@/lib/nodeOutputs` (resolved to that re-export). **`packages/agate-runtime`** Geocode UI sources import the same subpath so parity copies stay aligned with `backfield-ui`’s package **`exports`** (no separate filesystem-relative path).
- **Tailwind:** add `../../packages/backfield-ui/src/**/*.{ts,tsx}` to the app’s Tailwind `content` array (see `[apps/agate-ui/tailwind.config.js](../apps/agate-ui/tailwind.config.js)`).
- **Exports:** e.g. `UserAccountMenu` (account icon + dropdown: signed-in email when `userLabel` is set, change password, optional manage users for org admins, log out). Navigation is via callbacks so hosts keep their own router.

## User-facing copy

- Write UI strings for a **general audience**, including people who are **not** developers.
- Avoid internal product names for infrastructure (services, ports, proxies, cookies, paths) unless the user must act on them—and even then, prefer plain language or hide details behind help links.
- Technical detail belongs in developer docs (this file’s other sections, `docs/API.md`, `docs/OPERATIONS.md`), not in labels, descriptions, or empty states shown to typical users.

## Key conventions

- Prefer clear React components over clever abstractions.
- Extract repeated or dense logic into named helpers or smaller components.
- Keep API requests in `src/lib/api.ts` or similarly central helpers instead of scattering fetch calls.
- Keep storage keys and custom event names centralized and consistently prefixed.
- Reuse shared UI patterns instead of duplicating similar behavior per page.

## Node sync flow

- Source of truth lives in `packages/backfield-core/src/backfield_core/nodes`.
- `apps/agate-ui/scripts/sync-nodes.js` copies UI files into `apps/agate-ui/src/nodes`.
- The sync script also generates `src/nodes/registry.ts`.
- Avoid hand-editing generated registry output unless the sync flow itself is changing.
- The default Agate palette includes `TextInput`, `PlaceExtract`, `GeocodeAgent`, and `Output`. `PlaceExtract` performs editorially relevant place extraction in a **single** LLM call; there is no separate Place Filter node.

## TypeScript expectations

- Prefer explicit types for props, API responses, and helper return values.
- Avoid `any` when a concrete type is easy to add.
- Keep file and symbol names descriptive.

## Frontend change checklist

- If API contracts changed, update `src/lib/api.ts`.
- If node metadata or node UI changed, rerun the node sync/build flow.
- If browser storage or custom events changed, keep prefixes and docs aligned.
- If a page or component became large, split it into smaller readable pieces.