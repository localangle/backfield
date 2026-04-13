# Backfield Agent Guide

Use this file as the entry point for working in this repository. Keep it short, then follow the linked docs for details.

## Repo map

- `apps/agate-api`: FastAPI control plane for projects, graphs, runs, templates, and node metadata.
- `apps/agate-ui`: React/React Flow UI for building and running Agate flows.
- `apps/worker`: Celery worker that executes Agate runs from the `agate` queue.
- `apps/stylebook-api`: Companion FastAPI service for geocode and future Stylebook entities.
- `apps/stylebook-ui`: Minimal Stylebook shell UI.
- `packages/backfield-core`: Graph types, executor, starter node implementations, and node metadata.
- `packages/backfield-db`: SQLModel models, crypto helpers, engine/session helpers, and Alembic migrations.
- `infra/docker-compose.yml`: Local multi-service stack.

## Canonical commands

- `make bootstrap`: install Python workspace dependencies with `uv`.
- `make up` / `make down`: start and stop the local stack.
- `make logs`: follow compose logs.
- `make migrate`: run Alembic in the `agate-api` container.
- `make lint`: run Ruff checks.
- `make test`: run unit, integration, and structural tests.
- `make smoke`: run the golden-path HTTP smoke against a live stack.

## Docs map

- `README.md`: quick start, ports, and top-level layout.
- `docs/ARCHITECTURE.md`: package boundaries, runtime flow, and dependency direction.
- `docs/API.md`: Agate API conventions, route responsibilities, and run orchestration.
- `docs/FRONTEND.md`: Agate UI conventions, node sync flow, and API client usage.
- `docs/DATABASE.md`: schema ownership, prefixes, migrations, and indexing expectations.
- `docs/OPERATIONS.md`: compose lifecycle, env vars, queue names, and troubleshooting.
- `docs/TESTING.md`: validation ladder and when to run which checks.
- `docs/AGENT_WORKFLOWS.md`: task-specific guidance for backend, frontend, DB, docs, and review work.
- `docs/PLANS.md`: how to track larger changes and refactors.

## Engineering posture

- Think before coding. If the request is ambiguous, surface assumptions instead of guessing.
- Keep changes surgical. Every changed line should trace back to the task.
- Prefer existing commands, docs, and package boundaries over inventing new workflows.
- Update the matching source-of-truth doc when behavior, architecture, or operations change.
- Keep work reviewable: one task per branch, one coherent diff, no unrelated cleanup.

## Style constraints

- Put Python imports at the top of the file unless a local import is needed to avoid a circular import or heavy optional dependency. Add a short comment when making that exception.
- Prefer human readability over clever or heavily idiomatic code.
- Break large functions into smaller focused helpers, including private helpers, when that improves readability.
- Use clear descriptive names for files, functions, classes, variables, and tests.
- Avoid speculative abstraction. Start with the simplest implementation that solves the real problem.
- Database tables must be namespaced by app prefix, such as `agate_` or future `stylebook_`.
- Add indexes intentionally for expected filter, join, and lookup paths. If a new query path matters, consider the indexing decision part of the change.

## Validation defaults

- Docs-only changes: update the relevant docs and run any targeted checks if examples or commands changed.
- Python/backend changes: run `make lint` and `make test`.
- DB changes: run `make lint`, `make test`, and the relevant migration/smoke flow.
- Runtime/integration changes: run `make lint`, `make test`, and `make smoke` when the live stack behavior changed.
- UI changes: run `make lint`, `make test`, and the relevant frontend build or smoke check when applicable.

## Git workflow

- Work from a clean branch for each task.
- Prefer short-lived branches and small diffs over stacking unrelated changes.
- Use git status and diff frequently to confirm the task boundary before finishing.