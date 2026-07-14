# Local development setup

## Prerequisites

Install:

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose v2
- Node.js 20 when building the UIs outside Docker

Run commands from the repository root.

## First run

Install every Python workspace package and expose the project launcher in the virtual environment:

```bash
make bootstrap
source .venv/bin/activate
```

`make bootstrap` runs `uv sync --all-packages` and copies `scripts/backfield` to `.venv/bin/backfield`. It does not modify shell profiles or seed data. `make install-user-cli` optionally symlinks the launcher into `~/.local/bin`; remove that symlink with `make uninstall-user-cli`.

Check the host before starting:

```bash
backfield doctor
```

The doctor checks the repository, uv, Docker, `.venv`, CLI imports, the root `.env`, the Compose file, and launcher installation.

For a guided first run:

```bash
backfield init
```

`backfield init` creates the root `.env` when needed, generates `MASTER_ENCRYPTION_KEY` and `SESSION_SECRET` when absent, starts Compose, runs migrations, waits for the APIs, and seeds the initial organization and administrator. Re-runs preserve existing secrets, credentials, and renamed display names. Use `--no-browser` or `BACKFIELD_NO_BROWSER=1` to suppress the Settings page opening.

For automation, provide all requested values in a JSON config:

```bash
backfield init --non-interactive --config init.json
```

## Root environment file

Copy `.env.example` to `.env` when configuring the stack manually:

```bash
cp .env.example .env
```

The file is gitignored. Compose loads it into the API and worker containers. Add the credentials needed by the flows you run. Typically that means at least one LLM provider key; geocoding, search, and object-storage credentials can instead be configured as organization integrations in the product.

Local Compose supplies development defaults for `MASTER_ENCRYPTION_KEY`, `SESSION_SECRET`, and `SERVICE_API_TOKEN` when they are absent. Do not reuse those defaults in a deployed environment. An explicitly blank value in `.env` overrides a Compose default.

## Stack commands

The source of truth for stack orchestration is the repository launcher at `scripts/backfield`. Make targets are convenience wrappers:

```bash
make up             # foreground, builds images
make up-detached    # background, builds images
make logs
make down
```

Equivalent direct commands include:

```bash
backfield up --detached
backfield up --no-build
backfield logs agate-api worker
backfield logs --no-follow
backfield ps
backfield restart worker
```

The launcher resolves `infra/docker-compose.yml` from the repository root. Override it with `--compose-file` or `BACKFIELD_COMPOSE_FILE`. If its Python import probe fails, it repairs the workspace once with `uv sync`; a healthy install does not sync on every command.

The local services are:

- Agate UI: <http://localhost:5173>
- Stylebook UI: <http://localhost:5175>
- Agate API: <http://localhost:8000>
- Stylebook API: <http://localhost:8003>
- Core API: <http://localhost:8004>
- PostgreSQL: `localhost:5433`
- PgBouncer: `localhost:6432`
- Redis: `localhost:6379`

Compose runs migrations before the application services that require the schema. The UIs wait for their API dependencies to become healthy.

## Local data lifecycle

`make down` stops and removes containers, then runs `docker system prune -f`. It does not remove Compose volumes, so `make down` followed by `make up` preserves the `postgres_data` database volume.

Use destructive commands deliberately:

```bash
make reset-db
BACKFIELD_CONFIRM_CLEAR=1 make clear-entity-data
```

- `make reset-db` removes stack containers and volumes.
- `clear-entity-data` removes entity data and Agate runs while preserving identity rows, Stylebook catalog shells, graphs, and templates.

If a schema change is explicitly documented as incompatible with existing local catalog data, reset the database before bringing the stack back up. Do not assume a destructive migration supports an in-place upgrade.

Docker cleanup targets have different data-loss risk:

- `make docker-prune-build`: build cache only.
- `make docker-trim`: stopped containers, dangling images, unused networks, and build cache; preserves volumes.
- `make docker-prune-volumes`: all unused volumes. A stopped stack's database volume may be unused and may be deleted.
- `make docker-trim-full`: system cleanup followed by volume cleanup; treat it as destructive.

## Local bootstrap behavior

Compose defaults `BACKFIELD_LOCAL_BOOTSTRAP=1` on Agate API. After migrations, it ensures the default organization, workspace, and General project exist and copies allowlisted LLM/Azure keys from the container environment into General project secrets. It does not create graphs and does not copy geocoding, search, or S3 credentials.

To create the first administrator without the interactive initializer, either use `POST /v1/bootstrap/first-user` on an empty local database or opt into the Core API environment bootstrap described in [runtime configuration](../operations/runtime-configuration.md). Both paths are for local, demo, or CI use. Deployed environments should use the idempotent `backfield seed` command after migrations.
