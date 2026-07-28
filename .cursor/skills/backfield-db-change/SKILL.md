---
name: backfield-db-change
description: Review and implement Backfield database changes. Use when editing SQLModel models, Alembic migrations, encrypted secrets, or DB-facing API and worker code.
---

# Backfield DB Change

## Quick Start

1. Read `docs/architecture/database.md`, `docs/operations/migrations.md`, and the relevant runtime-configuration or deployment section.
2. Inspect the owning models in `packages/backfield-db`.
3. Check affected API and worker call sites for naming or contract drift.
4. Treat indexing decisions as part of the change, not an afterthought.
5. Update database docs when schema behavior changes.

## Checklist

- [ ] Table names use the owning app prefix.
- [ ] Models, migrations, and docs agree on names and behavior.
- [ ] Expected lookup, join, and filter paths have an intentional indexing decision.
- [ ] API and worker code stay aligned with the DB contract.
- [ ] `make lint` and `make test` pass.
- [ ] Run `make smoke` when the change affects runtime flow.
