# Backfield Agent Guide

Use this file for engineering and agent conventions in this repository. Keep it short, then follow
the linked docs for details. **Human contributors** should start with
[CONTRIBUTING.md](CONTRIBUTING.md) (setup, PR process, project status). This file remains the
canonical agent/engineering checklist.

## Repo map

- `apps/agate-api`: FastAPI service for projects, flows, templates, runs, processed-item review, and node metadata.
- `apps/agate-ui`: React/React Flow application for building flows and reviewing runs.
- `apps/worker`: Celery execution, Backfield Output persistence, and background Stylebook and semantic-indexing jobs.
- `apps/stylebook-api`: FastAPI service for catalogs, canonical entities, candidates, cleanup, activity, relationships, geocoding, and bundles.
- `apps/stylebook-ui`: Stylebook catalog, candidate, cleanup, activity, and relationship interfaces.
- `apps/core-api`: Sessions, users, organization and project administration, integrations, AI configuration, and `/public/v1`.
- `packages/backfield-agate`: `agate-runtime` graph types, execution, run helpers, node definitions, metadata, and node-panel source files.
- `packages/backfield-ai`: Model resolution, LiteLLM integration, embeddings, and AI call accounting.
- `packages/backfield-ui`: Shared React components and `@backfield/ui/nodeOutputs`.
- `packages/backfield-auth`: Session, service, and project API-key authentication.
- `packages/backfield-db`: SQLModel models, database sessions, encryption, seeding, and Alembic migrations.
- `packages/backfield-entities`: Entity registry, catalog resolution, canonicalization, public queries, ingest, cleanup, connections, and semantic synchronization.
- `packages/backfield-cli`: Stack lifecycle, migration, seeding, and data-maintenance commands.
- `infra/docker-compose.yml`: Local multi-service stack (localhost-bound ports).

## Canonical commands

- `make bootstrap`: install Python workspace dependencies with `uv`; see [local setup](docs/development/local-setup.md).
- `make up` / `make down`: start and stop the local stack. These are thin wrappers around the **`backfield` CLI** (`backfield up` / `backfield down`), which is the source of truth for stack operations. `make down` stops this Compose project only—it does **not** prune Docker globally. Use `make docker-trim` / `make docker-trim-full` when you explicitly want host-wide cleanup (full also prunes unused volumes).
- `make logs`: follow stack logs (wraps `backfield logs`). `backfield ps` / `backfield restart` list and restart containers.
- `make migrate`: run Alembic via the one-off Compose **`migrate`** service. Use `make migrate-host` (or `backfield migrate`) for the host CLI path against local Postgres.
- `make lint`: run Ruff checks.
- `make test`: run unit, integration, and structural tests.
- `make smoke-fast` / `make smoke`: live-stack smoke; see [testing](docs/development/testing.md).

## Docs map

- `README.md`: product story, project status, and local quick start.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): human contribution entry point.
- [`docs/README.md`](docs/README.md): audience-based documentation index.
- [`docs/architecture/overview.md`](docs/architecture/overview.md): application and package boundaries and dependency direction.
- [`docs/development/entities/overview.md`](docs/development/entities/overview.md): entity model; use with `.cursor/skills/add-entity-type`.
- [`docs/development/nodes.md`](docs/development/nodes.md): Agate node contracts and checklists; use with `.cursor/skills/add-agate-node`.
- [`docs/development/frontend/conventions.md`](docs/development/frontend/conventions.md): shared frontend and user-facing copy rules.
- [`docs/development/testing.md`](docs/development/testing.md): validation ladder and smoke-test guidance.
- [`docs/development/local-setup.md`](docs/development/local-setup.md): prerequisites, first run, stack commands, and local data lifecycle.

## Engineering posture

- Think before coding. If the request is ambiguous, surface assumptions instead of guessing.
- Keep changes surgical. Every changed line should trace back to the task.
- Prefer existing commands, docs, and package boundaries over inventing new workflows.
- Update the matching source-of-truth doc when behavior, architecture, or operations change.
- Keep work reviewable: one task per branch, one coherent diff, no unrelated cleanup.
- In user-facing UI copy and frontend docs, prefer **product language** (e.g. “locations”, “candidates”, “canonicals”) over internal database terms like **“substrate”**.
- **Frontend copy** (`apps/agate-ui`, `apps/stylebook-ui`, shared UI in `packages/backfield-ui`, node panels synced into apps): write for a **non-technical end user** and **avoid technical or code-related language** in any string shown in the product (see [`docs/development/frontend/conventions.md`](docs/development/frontend/conventions.md) → **User-facing copy**).

## Style constraints

- Prefer **strict typing** in Python: annotate public functions, methods, and non-obvious variables; avoid untyped payloads and `Any` unless there is a clear reason.
- Prefer **Pydantic** (and SQLModel where that is already the layer) for structured data at boundaries: request/response bodies, JSON blobs, and settings that cross layers. Parse at the boundary instead of passing loose `dict`/`list` through the stack.
- Put Python imports at the top of the file unless a local import is needed to avoid a circular import or heavy optional dependency. Add a short comment when making that exception.
- Prefer human readability over clever or heavily idiomatic code.
- Break large functions into smaller focused helpers, including private helpers, when that improves readability.
- Use clear descriptive names for files, functions, classes, variables, and tests.
- Avoid speculative abstraction. Start with the simplest implementation that solves the real problem.
- Database tables must be namespaced by app prefix, such as `agate_` or `stylebook_`.
- Add indexes intentionally for expected filter, join, and lookup paths. If a new query path matters, consider the indexing decision part of the change.

## Validation defaults

- Docs-only changes: update the relevant docs and run any targeted checks if examples or commands changed.
- Python/backend changes: run `make lint` and `make test`.
- DB changes: run `make lint`, `make test`, and the relevant migration/smoke flow.
- Runtime/integration changes: run `make lint`, `make test`, and `make smoke` when the live stack behavior changed.
- UI changes: run `make lint`, `make test`, and the relevant frontend build or smoke check when applicable.

## Planning and reviews

- Workspace rules in `.cursor/rules/` are binding alongside this guide; use playbooks in `.cursor/skills/` when a task matches.
- Plan changes that span apps or packages, include migrations or queue changes, carry operational risk, or need phased rollout. Record the goal, implementation phases, validation, and material risks; keep the plan current or retire it.
- Before opening a PR, run the code and architecture review skills and resolve findings or open questions.

## Git workflow

- **When you begin writing code, use a fresh branch** (cut from the agreed base, usually `main`) unless the task explicitly says to continue on an existing branch. This is the default for humans and agents alike.
- **Start a new branch for each task**—especially for large or unrelated changes. Do not pile new work onto whatever branch happens to be checked out (for example another feature or setup branch) unless it is explicitly the same task.
- Work from a clean working tree when you branch; keep one coherent task per branch and per diff.
- Prefer short-lived branches and small diffs over stacking unrelated changes.
- Use `git status` and `git diff` frequently to confirm the task boundary before finishing.
