# Frontend

This document covers frontend conventions for `apps/agate-ui` and the lighter `apps/stylebook-ui`.

## Agate UI responsibilities

- Render the flowbuilder and run experience.
- Own browser-facing API access through `src/lib/api.ts`.
- Consume generated node registry output from `src/nodes/registry.ts`.
- Keep page and component code readable, explicit, and easy to scan.

## Auth and API bases (Agate UI)

- **Core API (login / session):** `POST /v1/auth/login`, `GET /v1/auth/me`, `POST /v1/auth/logout`, `POST /v1/auth/change-password`. Organization admin routes under `/v1/organizations/{org_id}/…` (users, workspaces, workspace memberships for access control). Use `**VITE_AUTH_API_BASE`** (empty string for same-origin). Typed fetch helpers live in `**src/lib/core-api.ts**` (session cookie, `credentials: 'include'`).
- **Project Settings — two credential concepts:** (1) **API access keys** (`bfk_…`) are issued by Core API (`/v1/projects/{id}/api-keys`); the Settings tab uses `**core-api.ts`** helpers and `[ProjectAccessKeysPanel](../apps/agate-ui/src/components/ProjectAccessKeysPanel.tsx)` for Bearer access to Backfield APIs. (2) **Integration secrets** (OpenAI, Mapbox, etc.) are stored via Agate API `/projects/{id}/secrets` and `**api.ts`** — encrypted provider env for flows, not Bearer keys.
- **Agate API:** project/graph/run calls go through `**src/lib/api.ts`**. Default `**VITE_API_BASE**` is `/api/agate` so the Vite dev server can proxy to `agate-api` on one browser origin with `credentials: 'include'`.
- **Local dev proxy:** `[apps/agate-ui/vite.config.ts](../apps/agate-ui/vite.config.ts)` proxies `/v1` → Core API and `/api/agate` → Agate API. Override targets with `VITE_CORE_API_PROXY_TARGET` / `VITE_AGATE_API_PROXY_TARGET` (e.g. in Docker Compose).

## Shared UI package (`@backfield/ui`)

- Reusable shell components for multiple Backfield apps (Agate UI now; Stylebook UI later) live in `[packages/backfield-ui](../packages/backfield-ui)`.
- **Tailwind:** add `../../packages/backfield-ui/src/**/*.{ts,tsx}` to the app’s Tailwind `content` array (see `[apps/agate-ui/tailwind.config.js](../apps/agate-ui/tailwind.config.js)`).
- **Exports:** e.g. `UserAccountMenu` (account icon + dropdown: change password, optional manage users for org admins, log out). Navigation is via callbacks so hosts keep their own router.

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

## TypeScript expectations

- Prefer explicit types for props, API responses, and helper return values.
- Avoid `any` when a concrete type is easy to add.
- Keep file and symbol names descriptive.

## Frontend change checklist

- If API contracts changed, update `src/lib/api.ts`.
- If node metadata or node UI changed, rerun the node sync/build flow.
- If browser storage or custom events changed, keep prefixes and docs aligned.
- If a page or component became large, split it into smaller readable pieces.