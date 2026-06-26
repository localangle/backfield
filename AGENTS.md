# Backfield Agent Guide

Use this file as the entry point for working in this repository. Keep it short, then follow the linked docs for details.

## Repo map

- `apps/agate-api`: FastAPI control plane for projects, graphs, runs, templates, and node metadata.
- `apps/agate-ui`: React/React Flow UI for building and running Agate flows.
- `apps/worker`: Celery worker that executes Agate runs from the `agate` queue.
- `apps/stylebook-api`: Companion FastAPI service for geocode and future Stylebook entities.
- `apps/stylebook-ui`: Minimal Stylebook shell UI.
- `apps/core-api`: Core domain HTTP API (article import and shared endpoints later); auth/session testing today.
- `packages/backfield-agate`: Agate graph types, executor, node definitions (including `src/agate_nodes/*/ui/` — the **source of truth** for synced Agate UI node panels), vendored PlaceExtract/GeocodeAgent runtime, and geocoding/LLM utilities.
- `packages/backfield-ui`: Shared shell components and `@backfield/ui/nodeOutputs` (executor output-key helpers for TS panels).
- `packages/backfield-auth`: Shared session cookies and service Bearer token dependencies for FastAPI apps.
- `packages/backfield-db`: SQLModel models, crypto helpers, engine/session helpers, and Alembic migrations.
- `packages/backfield-entities`: Entity domain helpers shared by worker, stylebook-api, core-api, and agate-runtime. Layout: `catalog/` (Stylebook rows + resolve), `registry/` (entity type slugs), `canonical/` + `entities/` (matching + per-type policy/persist), `ingest/` (DBOutput settings, geocode cache, semantic indexing).
- `infra/docker-compose.yml`: Local multi-service stack.

## Canonical commands

- `make bootstrap`: install Python workspace dependencies with `uv` (does not seed DB data; local seeding runs when the stack starts — see `BACKFIELD_LOCAL_BOOTSTRAP` in [docs/OPERATIONS.md](docs/OPERATIONS.md)).
- `make up` / `make down`: start and stop the local stack (`down` also runs `docker system prune` only — no `docker volume prune`, so Postgres/compose volumes survive across `down`/`up`). Use `make docker-prune-volumes` or `make docker-trim-full` when you explicitly want unused volumes removed.
- `make logs`: follow compose logs.
- `make migrate`: run Alembic in the `agate-api` container.
- `make lint`: run Ruff checks.
- `make test`: run unit, integration, and structural tests.
- `make smoke`: run the golden-path HTTP smoke against a live stack.

## Docs map

- `docs/AGENTIC.md`: orientation for agentic workflows — rules/skills overview, per-task-type checklists (backend, DB, frontend, runtime, review), and planning guidance.
- `README.md`: quick start, ports, and top-level layout.
- `docs/ARCHITECTURE.md`: package boundaries, runtime flow, and dependency direction.
- `docs/ENTITY_TYPES.md`: entity layout, catalog transfer, **per-type implementation patterns** (required shell vs opt-in); use with `.cursor/skills/add-entity-type` when adding types.
- `docs/NODES.md`: Agate pipeline node profiles, end-to-end layer map, review tiers, and checklists; use with `.cursor/skills/add-agate-node` when adding net-new nodes.
- `docs/API.md`: Agate API conventions, route responsibilities, and run orchestration.
- `docs/PUBLIC_API.md`: consumer-facing `/public/v1` design (Core API), endpoint taxonomy, and rollout phases; see `docs/public-api/reference/` for agent-ready route docs.
- `docs/FRONTEND.md`: Agate UI conventions, node sync flow, and API client usage.
- `docs/DATABASE.md`: schema ownership, prefixes, migrations, and indexing expectations.
- `docs/OPERATIONS.md`: compose lifecycle, env vars, queue names, and troubleshooting.
- `docs/TESTING.md`: validation ladder and when to run which checks.

## Engineering posture

- Think before coding. If the request is ambiguous, surface assumptions instead of guessing.
- Keep changes surgical. Every changed line should trace back to the task.
- Prefer existing commands, docs, and package boundaries over inventing new workflows.
- Update the matching source-of-truth doc when behavior, architecture, or operations change.
- Keep work reviewable: one task per branch, one coherent diff, no unrelated cleanup.
- In user-facing UI copy and frontend docs, prefer **product language** (e.g. “locations”, “candidates”, “canonicals”) over internal database terms like **“substrate”**.
- **Frontend copy** (`apps/agate-ui`, `apps/stylebook-ui`, shared UI in `packages/backfield-ui`, node panels synced into apps): write for a **non-technical end user** and **avoid technical or code-related language** in any string shown in the product (see `docs/FRONTEND.md` → **User-facing copy**).

## Style constraints

- Prefer **strict typing** in Python: annotate public functions, methods, and non-obvious variables; avoid untyped payloads and `Any` unless there is a clear reason.
- Prefer **Pydantic** (and SQLModel where that is already the layer) for structured data at boundaries: request/response bodies, JSON blobs, and settings that cross layers. Parse at the boundary instead of passing loose `dict`/`list` through the stack.
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

- **When you begin writing code, use a fresh branch** (cut from the agreed base, usually `main`) unless the task explicitly says to continue on an existing branch. This is the default for humans and agents alike.
- **Start a new branch for each task**—especially for large or unrelated changes. Do not pile new work onto whatever branch happens to be checked out (for example another feature or setup branch) unless it is explicitly the same task.
- Work from a clean working tree when you branch; keep one coherent task per branch and per diff.
- Prefer short-lived branches and small diffs over stacking unrelated changes.
- Use `git status` and `git diff` frequently to confirm the task boundary before finishing.
- Before creating a PR, run a code review and an architecture review using the project skills in `.cursor/skills/`, and address the findings or open questions first.