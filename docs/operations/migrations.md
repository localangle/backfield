# Database migrations

Backfield has one Alembic chain in `packages/backfield-db/alembic`. Run it once as a standalone
operation; API and worker processes do not migrate on startup.

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
