# Backfield documentation

Use this index to find the source of truth for the part of Backfield you are changing. Start with
[`AGENTS.md`](../AGENTS.md) for repository conventions, commands, validation defaults, and Git
workflow.

## APIs

- [`api/agate.md`](api/agate.md) — Agate routes, run lifecycle, processed items, node metadata,
  and Backfield Output persistence.
- [`api/core.md`](api/core.md) — sessions, tenancy, organization administration, project
  credentials, AI configuration, and Core API boundaries.
- [`api/stylebook.md`](api/stylebook.md) — catalogs, canonical entities, candidates, connections,
  imports, cleanup, activity, search, and geocoding.
- [`api/processed-item-review.md`](api/processed-item-review.md) — item detail, review overlays,
  entity review domains, reviewed output, and S3 synchronization.
- [`api/public.md`](api/public.md) — authenticated `/public/v1` routes, project scope,
  conventions, and OpenAPI.

## Architecture

- [`architecture/overview.md`](architecture/overview.md) — applications, shared packages, and
  dependency direction.
- [`architecture/runtime.md`](architecture/runtime.md) — run dispatch, graph execution, outputs,
  persistence, and active compatibility behavior.
- [`architecture/database.md`](architecture/database.md) — schema ownership, current tables,
  indexes, pooling, and encrypted secrets.
- [`architecture/canonicalization.md`](architecture/canonicalization.md) — entity ingest,
  per-type matching policy, reconciliation, provenance, and catalog selection.

## Development

- [`development/local-setup.md`](development/local-setup.md) — prerequisites, first run, stack
  commands, local data lifecycle, and bootstrap behavior.
- [`development/testing.md`](development/testing.md) — validation commands, test layout,
  live-stack smoke tests, and CI expectations.
- [`development/nodes.md`](development/nodes.md) — Agate node profiles, runtime and UI contracts,
  panel conventions, review integration, and implementation checklist.
- [`development/entities/overview.md`](development/entities/overview.md) — entity registry,
  substrate and canonical records, evidence scope, connections, and transfers.
- [`development/entities/implementation.md`](development/entities/implementation.md) —
  cross-layer checklist and directory map for implementing an entity type.
- [`development/frontend/conventions.md`](development/frontend/conventions.md) — user-facing copy,
  typed UI patterns, API boundaries, shared components, builds, and review checklist.
- [`development/frontend/agate.md`](development/frontend/agate.md) — flow builder, run contracts,
  processed-item links, review architecture, settings, and administration.
- [`development/frontend/stylebook.md`](development/frontend/stylebook.md) — Stylebook routes,
  entity shells, candidate queues, canonical views, review, and cross-app navigation.

## Operations

- [`operations/runtime-configuration.md`](operations/runtime-configuration.md) — service routing,
  database, auth, queues, concurrency, provider, storage, and bootstrap settings.
- [`operations/migrations.md`](operations/migrations.md) — local and deployed Alembic workflows
  and active upgrade warnings.
- [`operations/deployment.md`](operations/deployment.md) — production images, static UI builds,
  artifact publication, release aliases, and deployment order.
- [`operations/troubleshooting.md`](operations/troubleshooting.md) — setup, runtime, provider,
  worker, bundle, UI, and Docker failure recovery.

## Agent workflows

Repository rules live in [`.cursor/rules/`](../.cursor/rules/), and task playbooks live in
[`.cursor/skills/`](../.cursor/skills/). Use the relevant skill for database changes, Agate
nodes, entity types, documentation updates, smoke testing, and pre-PR reviews.
