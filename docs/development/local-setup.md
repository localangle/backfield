# Local development setup

This checkout is for **local development and source inspection**. Published Compose ports bind to
`127.0.0.1`. Production self-hosting is unsupported; see [deployment](../operations/deployment.md).

## Prerequisites

Install:

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker Engine with Compose v2
- Node.js 20 when building or typechecking the UIs outside Docker

Run commands from the repository root.

## First run

Install every Python workspace package and expose the project launcher in the virtual environment:

```bash
make bootstrap
source .venv/bin/activate
```

`make bootstrap` runs `uv sync --all-packages` and copies `scripts/backfield` to `.venv/bin/backfield`.
It does not modify shell profiles or seed data. `make install-user-cli` optionally symlinks the
launcher into `~/.local/bin`; remove that symlink with `make uninstall-user-cli`.

### Guided init

```bash
backfield init
```

`backfield init` creates the root `.env` when needed, generates `MASTER_ENCRYPTION_KEY` and
`SESSION_SECRET` when absent, starts Compose, runs migrations, waits for the APIs, and seeds the
initial organization and administrator. Re-runs preserve existing secrets, credentials, and renamed
display names. Use `--no-browser` or `BACKFIELD_NO_BROWSER=1` to suppress the Settings page opening.

After init completes, verify the host:

```bash
backfield doctor
```

The doctor checks the repository, uv, Docker, `.venv`, CLI imports, the root `.env`, the Compose
file, and launcher installation. Run doctor **after** init so `.env` and the stack already exist.

Then open Agate, sign in, and configure **Settings → AI models** (and **Settings → Integrations**
for geocoding, search, or flow object storage as needed).

### Non-interactive init

For automation, provide values in a JSON config. Prefer `admin_password_file` so the password does
not appear on the command line or in shell history:

```bash
printf '%s\n' 'choose-a-strong-local-password' > /tmp/backfield-admin-password
chmod 600 /tmp/backfield-admin-password

cat > init.json <<'EOF'
{
  "admin_email": "admin@example.com",
  "admin_password_file": "/tmp/backfield-admin-password",
  "admin_display_name": "Local Admin",
  "org_name": "Backfield",
  "stylebook_name": "Default Stylebook",
  "open_browser": false
}
EOF

backfield init --non-interactive --config init.json
backfield doctor
```

Provide exactly one of `admin_password` or `admin_password_file`. Optional fields:

| Field | Meaning |
| --- | --- |
| `skip_stack` | Skip Compose up / migrate / readiness when the stack is already running |
| `open_browser` | Whether interactive init may open Settings in a browser (default `true`) |

### Seed-only provisioning

First-admin creation uses **`backfield seed`** (or the seed step inside **`backfield init`**). There
is no HTTP bootstrap endpoint and no Core API environment-variable admin bootstrap.

When the stack and schema already exist:

```bash
backfield seed \
  --admin-email admin@example.com \
  --admin-password-file /tmp/backfield-admin-password
```

`backfield seed` is idempotent: it ensures the organization and administrator exist, but re-runs do
not change an existing administrator’s password or role.

## Root environment file

Copy `.env.example` to `.env` when configuring the stack manually:

```bash
cp .env.example .env
```

The file is gitignored. Compose loads it into the APIs and worker for shared local secrets, runtime
overrides, and optional bundle infrastructure. Configure model credentials in **Settings → AI models**
and geocoding, search, and flow object-storage credentials in **Settings → Integrations** rather than
adding provider API keys to `.env`.

Local Compose may supply development defaults for `MASTER_ENCRYPTION_KEY`, `SESSION_SECRET`, and
`SERVICE_API_TOKEN` when they are absent. Application code requires a non-empty `SESSION_SECRET`
when services start without that Compose default path. Do not reuse Compose defaults outside local
development. An explicitly blank value in `.env` overrides a Compose default.

## Stack commands

The source of truth for stack orchestration is the repository launcher at `scripts/backfield`. Make
targets are convenience wrappers:

```bash
make up             # background, builds images, waits for APIs, prints ready summary
make up-detached    # same as make up (kept for compatibility)
make logs
make down           # stop this Compose project only
```

Equivalent direct commands include:

```bash
backfield up
backfield up --foreground
backfield up --no-build
backfield logs agate-api worker
backfield logs --no-follow
backfield ps
backfield restart worker
```

`backfield up` starts Compose detached (`-d`), waits for API readiness, then prints the same
apps/CLI summary as `backfield init` (without the first-run Next steps section). Use
`--foreground` to attach to Compose logs instead.

The launcher resolves `infra/docker-compose.yml` from the repository root. Override it with
`--compose-file` or `BACKFIELD_COMPOSE_FILE`. If its Python import probe fails, it repairs the
workspace once with `uv sync`; a healthy install does not sync on every command.

### Migrations

| Target | Path |
| --- | --- |
| `make migrate` | One-off Compose **`migrate`** service (`docker compose … run --rm migrate`) |
| `make migrate-host` | Host CLI (`backfield migrate`) against Postgres published on `127.0.0.1:5433` |

Prefer `make migrate` when working entirely through Compose. Use `make migrate-host` when you want
the host-installed CLI and direct database URL behavior.

### Local services (localhost-bound)

All published ports bind to `127.0.0.1`:

- Agate UI: <http://localhost:5173>
- Stylebook UI: <http://localhost:5175>
- Agate API: <http://localhost:8000>
- Stylebook API: <http://localhost:8003>
- Core API: <http://localhost:8004>
- PostgreSQL: `127.0.0.1:5433`
- PgBouncer: `127.0.0.1:6432`
- Redis: `127.0.0.1:6379`

Compose runs migrations before the application services that require the schema. The UIs wait for
their API dependencies to become healthy.

## Local data lifecycle

`make down` / `backfield down` stops and removes this project’s Compose containers. It does **not**
run a global Docker prune and does **not** remove Compose volumes, so `make down` followed by
`make up` preserves the `postgres_data` database volume.

Docker cleanup is **opt-in**:

- `make docker-trim`: stopped containers, dangling images, unused networks, and build cache;
  preserves volumes. This is host-wide Docker cleanup—use deliberately.
- `make docker-trim-full`: docker-trim plus unused volumes; treat it as destructive because a
  stopped stack’s database volume may be deleted.

Use destructive stack commands deliberately:

```bash
make reset-db
BACKFIELD_CONFIRM_CLEAR=1 make clear-entity-data
```

- `make reset-db` removes stack containers and volumes.
- `clear-entity-data` removes entity data and Agate runs while preserving identity rows, Stylebook
  catalog shells, graphs, and templates.

If a schema change is explicitly documented as incompatible with existing local catalog data, reset
the database before bringing the stack back up. Do not assume a destructive migration supports an
in-place upgrade.

## Troubleshooting

### Apple Silicon: postgres healthcheck hangs

Local Postgres should build as `linux/arm64`. If Compose prints
`requested image's platform (linux/amd64) does not match ... (linux/arm64/v8)` for `postgres`, an
old amd64 image is still tagged. Rebuild that service and restart:

```bash
docker compose -f infra/docker-compose.yml build --no-cache postgres
make down
make up
```

Also keep Buildx on the Desktop builder for day-to-day local work
(`docker buildx use desktop-linux`). Leave cloud/canary builders such as `canarybuilder` for amd64
release bakes only.

### CLI: “could not repair the Backfield CLI in .venv”

Usually a stale editable install (or two checkouts fighting over one global launcher). Prefer **one**
primary clone. Then from that checkout:

```bash
deactivate 2>/dev/null || true
unset VIRTUAL_ENV
uv sync --all-packages --reinstall
source .venv/bin/activate
make install-user-cli   # re-points ~/.local/bin/backfield at this checkout
backfield doctor
```

If you keep multiple clones, do not activate checkout A’s `.venv` while running commands in
checkout B — `VIRTUAL_ENV` can point `uv` at the wrong environment.

## Local workspace bootstrap (not admin seeding)

Compose defaults `BACKFIELD_LOCAL_BOOTSTRAP=1` on Agate API. After migrations, it ensures the default
organization, workspace, and General project exist. For unattended local or CI compatibility,
explicitly injected LLM/Azure environment keys may also be copied into General project secrets;
normal interactive setup should use the Settings screens. This path does **not** create the first
administrator—use `backfield init` or `backfield seed` for that. Bootstrap does not create graphs and
does not copy geocoding, search, or S3 credentials.
