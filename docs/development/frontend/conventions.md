# Frontend conventions

These conventions apply to `apps/agate-ui`, `apps/stylebook-ui`, `apps/api-playground`, and shared
UI in `packages/backfield-ui`.

## User-facing copy

- Write every label, button, tooltip, placeholder, empty state, error, onboarding
  message, and dialog for a non-technical user doing editorial or operational work.
- Describe outcomes in plain language. Do not expose stack traces, type names, JSON
  paths, HTTP details, database or queue names, environment variables, file paths, or
  developer shorthand on ordinary product screens.
- Prefer product terms to implementation terms. In review and cross-app handoffs use
  **Stylebook**, not “catalog”; use **locations**, **candidates**, and **canonicals**
  where those are the product concepts.
- In story review, say **mention**, not “occurrence.” A place editor exposes
  **Mentions in story**, with **Add mention**, **Remove mention**, and reorder controls.
- Keep technical detail in developer documentation or an explicitly developer-only
  screen.
- `apps/api-playground` is explicitly developer-only, so HTTP and OpenAPI terminology is
  appropriate there. Keep labels direct and explain secret-handling behavior in product copy.

## Components and state

- Prefer clear, typed React components over clever abstractions.
- Extract dense or repeated logic into named helpers or focused components.
- Keep API requests in typed modules under `src/lib/`; do not scatter raw `fetch`
  calls through pages.
- Reuse shared shells, primitives, and hooks before creating per-page copies.
- Keep browser storage keys and custom events centralized and app-prefixed.
- Use explicit types for props, API responses, and helper return values. Avoid `any`
  when a concrete type is practical.

## Messages and confirmations

Do not use browser `alert()` or `confirm()`. Each app mounts
`AppMessageProvider` inside `AuthProvider`; use `useAppMessage()`:

- `showMessage(description, options)` for a notice.
- `showError(description, options)` for a failure.
- `await showConfirm(description, options)` for a two-action confirmation.

The shared dialog treatment keeps copy, destructive styling, keyboard behavior, and
accessibility consistent.

## API and authentication boundaries

- Both apps use the Core API session cookie and send requests with
  `credentials: "include"`.
- Agate graph, project, and run calls belong in `apps/agate-ui/src/lib/api.ts`.
- Stylebook calls are split under `apps/stylebook-ui/src/lib/stylebook-api/` and
  re-exported from `src/lib/api.ts` where older callers still use the flat module.
- Core account and organization calls in Agate belong in
  `apps/agate-ui/src/lib/core-api.ts`.
- Cross-app URLs belong in each app's `platformUrls.ts` helpers.

Local development keeps one browser origin per UI and proxies:

- `/v1` to Core API
- `/api/agate` to Agate API
- `/api/stylebook` to Stylebook API

The production bundles use the same relative paths. `VITE_AGATE_UI_ORIGIN` and
`VITE_STYLEBOOK_UI_ORIGIN` are optional cross-app origin overrides. When unset,
shared multi-client artifacts derive the sibling host from the current origin
(`agate.{client}…` ↔ `stylebook.{client}…`) so one UI build works for every
tenant. Non-split hosts (local same-origin, custom domains) keep
`window.location.origin`.

## Shared UI package

Reusable shell components live in `packages/backfield-ui`. The package exports the
shared product brand and account menu, and `@backfield/ui/nodeOutputs` is the
canonical mapping from graph topology and node types to executor output keys.
Agate re-exports that mapping from `apps/agate-ui/src/lib/nodeOutputs.ts` for node
panels.

When an app consumes shared Tailwind components, include
`../../packages/backfield-ui/src/**/*.{ts,tsx}` in its Tailwind content paths.

## Builds

Use the repository targets:

```bash
make agate-ui-build
make stylebook-ui-build
make api-playground-build
make ui-build
```

Build output is written to each app's `dist/` directory. Production bundles must not
embed absolute API hosts.

## Frontend change checklist

- Apply the user-facing copy rules to every new or changed string.
- Use `useAppMessage` for notices, errors, and confirmations.
- Update the appropriate typed API module when a contract changes.
- Preserve URL-backed filters and deep-link state when changing navigation.
- Reuse shared shells and split components that have become hard to scan.
- For node metadata or panel changes, follow
  [`../nodes.md`](../nodes.md); package node UI is the source of truth.
