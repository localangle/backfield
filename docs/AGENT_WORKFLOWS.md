# Agent Workflows

Use this file to decide what to read and which checks to run for common task types.

## Docs-only changes

- Read the matching source-of-truth doc before editing.
- Keep terminology consistent with `AGENTS.md` and other docs.
- Run any targeted checks if commands, code examples, or generated references changed.

## Backend or Python changes

- Read `AGENTS.md`, `docs/ARCHITECTURE.md`, and the relevant domain doc.
- Keep imports at the top unless there is a documented exception.
- Prefer readable helpers over long route handlers or utility functions.
- Run `make lint` and `make test`.

## Database changes

- Read `docs/DATABASE.md` and `docs/OPERATIONS.md` first.
- Keep table names namespaced by app prefix.
- Treat indexing decisions as part of the schema change, not an afterthought.
- Run `make lint`, `make test`, and the relevant migration or smoke flow.

## Frontend changes

- Read `docs/FRONTEND.md`.
- Update `src/lib/api.ts` when API contracts move.
- Reuse existing UI patterns before creating new ones.
- Run the relevant lint/build flow and smoke checks for user-visible behavior changes.

## Runtime or orchestration changes

- Check Agate API, worker, DB, and docs together.
- Keep queue/task/status naming aligned across API, worker, and tests.
- Run `make lint`, `make test`, and `make smoke`.

## Review workflow

- Confirm the diff is scoped to the task.
- Check docs when behavior changed.
- Check tests and smoke coverage for meaningful runtime changes.
- Flag oversized functions, unclear naming, or mismatched cross-layer contracts.