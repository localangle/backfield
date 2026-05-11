# Monorepo layout

Backfield keeps a **tightly coupled monorepo** similar in spirit to Agate: multiple deployable services, shared Python packages, one Compose stack, room to add Terraform/Copilot later.

## Services (`apps/`)


| Directory       | Product name | Role                                                  |
| --------------- | ------------ | ----------------------------------------------------- |
| `agate-api`     | Agate        | Graph CRUD, run enqueue, node metadata API            |
| `agate-ui`      | Agate        | React + React Flow editor                             |
| `worker`        | Agate        | Celery consumer; executes graphs via `backfield-agate` |
| `stylebook-api` | Stylebook    | Geocode stub + future entity APIs                     |
| `stylebook-ui`  | Stylebook    | Thin shell; links to Agate                            |
| `core-api`      | Core API     | Domain HTTP API (article import later); auth testing now |


## Shared packages (`packages/`)


| Package            | Responsibility                                                                                  |
| ------------------ | ----------------------------------------------------------------------------------------------- |
| `backfield-agate`  | `GraphSpec`, synchronous executor, starter flow helpers, node definitions, and vendored Agate runtime |
| `backfield-auth`   | Session signing, service tokens, FastAPI dependencies (`require_auth_or_service`, etc.)          |
| `backfield-db`     | SQLModel models (`agate_`* tables), Alembic migrations, session helpers                          |
| `backfield-ui`     | Shared React UI (`@backfield/ui`), e.g. account menu; consumed by Agate UI and future apps     |


## Infrastructure

- `infra/docker-compose.yml` — local Postgres, Redis, all services above, UIs.
- `docs/DATABASE.md` — schema ownership and redesign notes.
- `docs/TESTING.md` — test layers and CI hints.

## Naming

User-facing and code branding: **Agate**. Internal Python package names use `backfield_`* to avoid clashing with any legacy `flowbuilder` installs.