# Frontend

This document covers frontend conventions for `apps/agate-ui` and the lighter `apps/stylebook-ui`.

## Agate UI responsibilities

- Render the flowbuilder and run experience.
- Own browser-facing API access through `src/lib/api.ts`.
- Consume generated node registry output from `src/nodes/registry.ts`.
- Keep page and component code readable, explicit, and easy to scan.

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