# Frontend

This document covers frontend conventions for `apps/agate-ui` and `apps/stylebook-ui`.

## Stylebook UI (Backfield)

- **Scope key (first slice):** the UI keeps **agate-ai-platform–style `project_slug`** in the query string (`?project=…`) as the primary navigation scope. **`stylebook-api`** resolves the slug to `backfield_project.id`. **`substrate_location`** rows are project-scoped place instances; the Stylebook **catalog** is **`stylebook_location_canonical`** (one row per editorial canonical), linked via **`substrate_location.stylebook_location_canonical_id`**.
- **Canonical list ordering:** **`GET /v1/canonical-locations`** returns rows sorted alphabetically by **`label`** (case-insensitive, then **`id`** for a stable order within pagination). Search (`q`) and `type_filter` keep that same sort. The canonical list page shows each row’s **geography type** (canonical **`location_type`**, same PlaceExtract taxonomy as the Type filter—including **political district** for wards and numbered legislative districts) alongside status, linked substrate count, and mention count.
- **First-slice routes (supported):** `/` (dashboard), `/locations/candidates`, `/locations/canonical` (lists **`GET /v1/canonical-locations`**; each row’s **`id`** is a **canonical UUID string**; the API may include a catalog **`slug`** but the Stylebook UI does not surface it), `/locations/canonical/:id` (**`:id`** is that UUID; detail uses **`GET /v1/canonical-locations/{id}`**, **`…/mentions`**, and **`GET …/linked-substrates`**), **`GET|POST …/meta`** and **`PATCH|DELETE …/meta/{meta_id}`** for catalog JSON metadata, **`GET|POST …/connections`** plus **`PATCH|DELETE …/connections/{id}`** for the directed connections graph (and **`GET /v1/connections/natures`** for nature typeahead), `/locations/create` (creates a catalog canonical only via **`POST /v1/canonical-locations`** or legacy **`POST /v1/locations`** — **no** `substrate_location` row; navigate using the returned canonical **`id`**), **`/import/locations`** (GeoJSON FeatureCollection wizard: **`POST /v1/import/geojson/analyze`** then **`POST /v1/import/geojson`** with `mappings` plus optional top-level **`meta_property_mappings`** — an optional **Metadata** step maps `properties` keys to `StylebookLocationMeta.meta_type` per feature, persisting **`data`** as **`{ "<property_key>": <value> }`** so the metadata card can show Key / Value; skip sends `[]`), plus **stub** pages for other entity candidates, and agents so deep links do not 404. The canonical detail page includes **Metadata** (single card with **Add Meta** in the card header and per-entry **Edit** / **Delete** on each row) and **Connections** (single card with **Add connection** in the card header, then list + **reactflow** graph tab) aligned with agate-ai-platform; person / organization / work canonical pickers use **empty-list stub** APIs until those entities are migrated. Metadata **data** defaults to a **key / value table** when the stored JSON is a flat object with scalar values (strings, numbers, booleans, null); otherwise the UI shows formatted JSON. **Table** and **JSON** toggles let editors switch modes; the API still stores arbitrary JSON-serializable payloads.
- **Location candidates review queue:** `/locations/candidates` calls **`GET /v1/candidates`** with **`limit=100`**, **`offset`**, and the tab / type / search filters; the UI shows Previous/Next using **`total`**, **`has_next`**, and **`has_prev`**. Changing tab, type filter, or debounced search resets to **page 1**.
- **Instance geometry dialog:** on the canonical detail linked-places table, **View geometry** opens **Instance Geometry** (map + collapsible **GeoJSON**, collapsed by default) and **Adopt for canonical** (dark button) to copy that instance’s geometry onto the catalog canonical.
- **Canonical linking (substrate vs catalog):** open candidates are **`substrate_location`** rows with **`canonical_link_status = pending`** and a **null** `stylebook_location_canonical_id`. The **Deferred** tab lists waived rows (`status=deferred`); list payloads may include **`defer_display_message`** when **`canonical_review_reasons_json`** carries a human-readable **`message`** from ingest or policy (for example **private place or residence**). The candidates table offers **Link to canonical**, which opens a modal: **`GET /v1/candidates/{substrate_location_id}/suggested-canonicals`** (ingest-style ranking; no scores in JSON) plus manual catalog search via **`GET /v1/canonical-locations?q=…`**, then confirm with **`POST /v1/locations/{substrate_location_id}/link-canonical`** (`{ "stylebook_location_canonical_id": "<uuid>" }`, idempotent `changed: false` when already on that canonical). The canonical detail page uses **one table** of linked places with article mentions nested under each place (mentions include **`substrate_location_id`** for grouping; the UI loads up to **500** mentions per canonical). **Unlink** is **`POST /v1/locations/{id}/unlink-canonical`** (returns row to the open queue; safe alias cleanup on the old canonical is server-side). **Move…** uses the same modal + link endpoint for atomic A→B relink. Legacy **`POST /v1/candidates/{id}/accept`** remains for “accept as new” / accept-by-id flows. **Create new canonical** opens a **dialog** to confirm or edit the catalog **label** (defaults from the substrate name), then posts **`{ "create_new": true, "name": "<label>" }`** to that accept route. **`POST /v1/candidates/{id}/accept`** returns **`message`** and **`stylebook_location_canonical_id`** (the canonical the substrate was linked to) so the UI can run the same **`GET /v1/candidates?project_slug=…&status=open&limit=100&offset=0&q=…`** preflight as “similar candidates” and link matches to that canonical from a follow-up dialog.
- **Auth:** Core API session only — `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout` with **`email` + `password`**, same as Agate UI. Use **`VITE_AUTH_API_BASE`** as empty string in dev so the browser stays on the Stylebook UI origin and the Vite proxy forwards `/v1` to Core.
- **Proxies (local dev):** [`apps/stylebook-ui/vite.config.ts`](../apps/stylebook-ui/vite.config.ts) mirrors Agate UI:
  - `/v1` → Core API (`VITE_CORE_API_PROXY_TARGET`, default `http://localhost:8004`)
  - `/api/agate` → Agate API (`VITE_AGATE_API_PROXY_TARGET`, default `http://localhost:8000`), strip prefix
  - `/api/stylebook` → Stylebook API (`VITE_STYLEBOOK_API_PROXY_TARGET`, default `http://localhost:8003`), strip prefix
- **API bases:** `VITE_AGATE_API_BASE` defaults to `/api/agate` (`GET /projects` seeds the default **`?project=…`** when it is missing; the Stylebook shell header does not include a project picker). `VITE_STYLEBOOK_API_BASE` defaults to `/api/stylebook` (locations and UI-compat stubs under `/v1/...` on the Stylebook service). All fetches use **`credentials: 'include'`** so the Core session cookie is sent to the dev origin.
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

- Reusable shell components for multiple Backfield apps (Agate UI and Stylebook UI) live in `[packages/backfield-ui](../packages/backfield-ui)`.
- **`LeafletMap` geocoder:** optional **`geocoder`** prop shows a compact place/address search while editing geography. It uses the public **[Photon](https://photon.komoot.io)** API (OpenStreetMap data, no API key): viewport **`lat`/`lon`/`zoom`** bias and **`location_bias_scale`**, **`dedupe=0`** when the query contains digits (better house-level matches), a **global** `/api` retry if the biased search is empty, optional **`/structured`** fallback for `housenumber street, city` patterns, then **setView** / **fit bounds** without animation (avoids bad map clicks mid-transition) (Photon `extent` is **`[lon, lat, lon, lat]`** for two corners, not min/max ordered) plus a **non-interactive** temporary blue dot at the hit (cleared when the geocoder unmounts). Results do not change saved geometry by themselves.
- **`nodeOutputs`:** `@backfield/ui/nodeOutputs` holds the canonical mapping from graph topology + node types to **`execute_graph` output keys** (snake_case slugs, legacy keys, `__outputKeysByNodeId`). Agate UI imports it through `[apps/agate-ui/src/lib/nodeOutputs.ts](../apps/agate-ui/src/lib/nodeOutputs.ts)`. Synced `backfield-core` panels use `@/lib/nodeOutputs` (resolved to that re-export). **`packages/backfield-agate`** Geocode UI sources import the same subpath so parity copies stay aligned with `backfield-ui`’s package **`exports`** (no separate filesystem-relative path).
- **Tailwind:** add `../../packages/backfield-ui/src/**/*.{ts,tsx}` to the app’s Tailwind `content` array (see `[apps/agate-ui/tailwind.config.js](../apps/agate-ui/tailwind.config.js)`).
- **Exports:** `ShellProductBrand` (large product title + “Backfield Platform” subtitle, `Link` to home); `UserAccountMenu` (account icon + dropdown: signed-in email when `userLabel` is set, optional change password when `onChangePassword` is provided, optional manage users for org admins, log out). Navigation is via callbacks so hosts keep their own router.

## User-facing copy

- Write **every** user-visible string (labels, buttons, tooltips, placeholders, empty states, errors shown in the shell, onboarding, dialogs) for a **non-technical end user**: someone who uses the product to do editorial or operational work, not someone reading source code or RFCs.
- **Avoid technical or code-related language at all costs** in the UI: no stack traces, type names, JSON field paths, HTTP verbs or status codes, database or queue names, environment variable names, file paths, or “developer shorthand” unless you are deliberately building a **developer-only** screen (rare). Prefer plain English; if precision matters, describe the outcome (“We couldn’t save your changes”) not the mechanism.
- Write for a **general audience**, including people who are **not** developers.
- Avoid internal product names for infrastructure (services, ports, proxies, cookies, paths) unless the user must act on them—and even then, prefer plain language or hide details behind help links.
- Technical detail belongs in developer docs (this file’s other sections, `docs/API.md`, `docs/OPERATIONS.md`), not in labels, descriptions, or empty states shown to typical users.

## In-app messages (no browser `alert` / `confirm`)

- **Do not use** `alert()`, `window.alert`, `confirm()`, or `window.confirm` for user-visible notices or confirmations. They break visual consistency and are poor for accessibility.
- **Do use** the shared **`AppMessageProvider`** + **`useAppMessage()`** hook from each app’s `@/components/AppMessageProvider` (same implementation in **`apps/agate-ui`** and **`apps/stylebook-ui`**). The provider is mounted in each app’s root **`App.tsx`**, wrapping routes **inside** **`AuthProvider`** so every screen can call it.
- **API:**
  - **`showMessage(description, { title?, variant? })`** — single-action notice (OK). Default title is “Notice”; use **`variant: "destructive"`** (or **`showError`**) for failures.
  - **`showError(description, { title? })`** — shorthand for an error-styled notice (default title “Error”).
  - **`showConfirm(description, { title?, confirmLabel?, cancelLabel?, destructive? })`** → **`Promise<boolean>`** — two-action modal; resolves **`true`** when the user confirms, **`false`** on cancel or dismiss.
- Implementation uses the app’s existing **shadcn `Dialog`** primitives (`DialogContent` at **`sm:max-w-md`**) so copy matches the rest of the shell. Prefer this for **`catch`** blocks, validation messages, and destructive confirmations (revoke key, cancel run, delete geometry, etc.).

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
- The default Agate palette includes `TextInput`, `JSONInput`, `S3Input`, `PlaceExtract`, `GeocodeAgent`, and `Output`. `PlaceExtract` performs editorially relevant place extraction in a **single** LLM call; there is no separate Place Filter node.

## TypeScript expectations

- Prefer explicit types for props, API responses, and helper return values.
- Avoid `any` when a concrete type is easy to add.
- Keep file and symbol names descriptive.

## Frontend change checklist

- For new user-facing errors or confirmations, use **`useAppMessage`** (see **In-app messages** above), not browser dialogs.
- If API contracts changed, update `src/lib/api.ts`.
- If node metadata or node UI changed, rerun the node sync/build flow.
- If browser storage or custom events changed, keep prefixes and docs aligned.
- If a page or component became large, split it into smaller readable pieces.