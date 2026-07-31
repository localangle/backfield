# Database migrations

Backfield has one Alembic chain in `packages/backfield-db/alembic`. Run it once as a standalone
operation; API and worker processes do not migrate on startup.

## Tenancy preflight

Before applying organization-tenancy migrations to retained data, run the read-only audit:

```bash
backfield tenancy-audit --json
```

The command supports databases before the additive project `stylebook_id` column exists, emits a
typed JSON report, and exits `1` when it finds blockers. It checks orphaned projects;
project/workspace and workspace/Stylebook organization mismatches; unresolved or
cross-organization direct project Stylebooks; conflicting or multi-Stylebook graph node
references; linked location, person, and organization canonicals from another Stylebook; and
duplicate project slugs within an organization. The audit does not create workspaces, rewrite
projects or graphs, or change canonical links. Canonical-link mismatches are aggregated by
project, entity type, expected Stylebook, and actual Stylebook, with an affected count and a
five-id sample so large datasets still produce practical reports.

The strict project runtime migration validates retained projects before making `workspace_id` and
`stylebook_id` required. It stops with the first project or workspace that has a null, missing, or
cross-organization assignment. Repair those rows and rerun the migration; it does not guess a
replacement catalog.

## Local workflow

With the Compose stack configuration:

```bash
make migrate
```

This runs the one-off `migrate` service against Postgres through
`BACKFIELD_DATABASE_URL_DIRECT`.

When Postgres is reachable from the host:

```bash
make migrate-host
```

That command delegates to `backfield migrate`. The migration entrypoint ensures the database
exists, retries transient startup and connection failures, and applies `alembic upgrade head`.

After a schema change, run the repository's database validation and live migration/smoke flow
appropriate to the change. Do not use `SQLModel.metadata.create_all` as a deployment migration.

## Deployment

Run `backfield migrate` or the `backfield-migrate` entrypoint as one release task before starting
updated application tasks. Do not let several services race to upgrade the same database.

Use a direct Postgres connection for migrations:

- `BACKFIELD_DATABASE_URL_DIRECT` is preferred for DDL and database creation.
- `BACKFIELD_DATABASE_URL` remains the runtime application connection and may point to PgBouncer.
- `BACKFIELD_ALEMBIC_ROOT` must point to the directory containing `alembic.ini` and `alembic/`
  when those assets are outside the installed Python package.

Back up production data before applying schema changes and verify the current
`alembic_version.version_num` when the upgrade path crosses a destructive warning.

## Active upgrade warnings

- The project-scoped S3 ingestion ledger migration (`068_s3_ledger_project_scope`) permits
  otherwise-identical revisions in different projects. After such rows exist, downgrading to
  `067_s3_ingestion_ledger` cannot restore the former global uniqueness constraint without
  manually reconciling those rows. Prefer forward repair after deployment.
- The location-canonical UUID migration (`019_sb_loc_canon_uuid`) drops and recreates location
  canonical-linked tables and does not preserve their rows. A database whose current revision is
  before this migration must not be upgraded in place when that catalog data matters. Rebuild a
  disposable local database with `make reset-db`; use an explicit export/rebuild/import procedure
  for retained environments.
- Postgres upgrades require permission and server support for PostGIS, `pg_trgm`, pgvector's
  `vector` extension, and H3. The migration fails if a required extension cannot be installed.
  Provision those extensions before upgrading managed databases where the migration role cannot
  create them.

`make reset-db` is destructive: it removes the local database data. It is not an upgrade command
for retained environments.
