# Backfield documentation

Repository documentation for people using, integrating with, or changing Backfield.
Human contribution workflow: [`CONTRIBUTING.md`](../CONTRIBUTING.md). Engineering and agent
conventions: [`AGENTS.md`](../AGENTS.md).

**Support promise:** this checkout targets **local development and source inspection**.
Production self-hosting is unsupported here; see [deployment](operations/deployment.md).

## Users

Product and platform guides for editors and operators of a running Backfield environment:

- [docs.backfield.news](https://docs.backfield.news) — primary product documentation
- [Simple example](https://docs.backfield.news/platform/simple-example/) — story → reusable data
- [Agate](https://docs.backfield.news/platform/agate/) — flows and processing
- [Stylebook](https://docs.backfield.news/platform/stylebook/) — canonical records

## API consumers

Authenticated HTTP surfaces and review contracts:

- [`api/public.md`](api/public.md) — `/public/v1`, project scope, conventions, OpenAPI
- [`../apps/api-playground/README.md`](../apps/api-playground/README.md) — interactive schema
  browsing, request controls, and key handling
- [`api/core.md`](api/core.md) — sessions, tenancy, credentials, AI configuration
- [`api/agate.md`](api/agate.md) — runs, processed items, node metadata, persistence
- [`api/stylebook.md`](api/stylebook.md) — catalogs, entities, candidates, bundles
- [`api/processed-item-review.md`](api/processed-item-review.md) — review overlays and domains

## Contributors

Getting a local stack running and validating changes:

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — contribution process and PR expectations
- [`development/local-setup.md`](development/local-setup.md) — prerequisites, `init`/`seed`, stack lifecycle
- [`development/testing.md`](development/testing.md) — lint, unit/integration tests, smoke, CI
- [`development/nodes.md`](development/nodes.md) — Agate node contracts and checklist
- [`development/entities/overview.md`](development/entities/overview.md) — entity model
- [`development/entities/implementation.md`](development/entities/implementation.md) — cross-layer entity checklist
- [`development/frontend/conventions.md`](development/frontend/conventions.md) — UI copy and patterns
- [`development/frontend/agate.md`](development/frontend/agate.md) — Agate UI architecture
- [`development/frontend/stylebook.md`](development/frontend/stylebook.md) — Stylebook UI architecture
- [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) — community standards
- [`../SECURITY.md`](../SECURITY.md) — private vulnerability reporting

## Maintainers and operators

Runtime knobs, migrations, artifacts, and failure recovery for local (and artifact-consuming) work:

- [`operations/runtime-configuration.md`](operations/runtime-configuration.md) — env vars and service contracts
- [`operations/migrations.md`](operations/migrations.md) — Alembic workflows
- [`operations/deployment.md`](operations/deployment.md) — artifact builds (no in-repo deploy)
- [`operations/troubleshooting.md`](operations/troubleshooting.md) — common local failures

## Architecture

Boundaries and runtime behavior:

- [`architecture/overview.md`](architecture/overview.md) — apps, packages, dependency direction
- [`architecture/runtime.md`](architecture/runtime.md) — run dispatch, graph execution, persistence
- [`architecture/database.md`](architecture/database.md) — schema ownership, pooling, secrets
- [`architecture/canonicalization.md`](architecture/canonicalization.md) — ingest and matching policy

## Agent workflows

Cursor rules live in [`.cursor/rules/`](../.cursor/rules/); task playbooks live in
[`.cursor/skills/`](../.cursor/skills/). Prefer the matching skill for database changes, Agate
nodes, entity types, documentation updates, smoke testing, and pre-PR reviews. Humans should
still start from [`CONTRIBUTING.md`](../CONTRIBUTING.md).
