# Backfield

Reconstruction of the Agate-style platform focused on **Agate** (visual pipelines) and **Stylebook** (geocoding stub today; entities later). Dashboard is out of scope for this slice.

## Stack

| Piece | Port (local) | Role |
|--------|----------------|------|
| **Agate UI** | 5173 | React + React Flow canvas |
| **Agate API** | 8000 | Graphs, runs, node metadata |
| **Worker** | — | Celery executes runs (`agate` queue) |
| **Stylebook API** | 8003 | Geocode helper for `GeocodeAgent` |
| **Core API** | 8004 | Shared domain API (auth + future import routes) |
| **Stylebook UI** | 5175 | Stylebook shell (Core auth + project-scoped locations against `stylebook-api` / `substrate_location`) |
| **Postgres** | 5433 | `agate_*` application tables (see [docs/DATABASE.md](docs/DATABASE.md)) |
| **Redis** | 6379 | Celery broker |

## Reference starter flow (not bootstrapped)

The canonical **Starter flow** spec lives in code (`starter_geocode_flow_graph_spec`) for smoke tests and templates:

1. **TextInput** — parameter text out (non-empty validation)  
2. **PlaceExtract** — LLM extraction (needs `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` on the worker)  
3. **GeocodeAgent** — LangGraph + external geocoders / LLM (optional Stylebook cache)  
4. **DBOutput** (Backfield Output in the palette) — persists consolidated upstream JSON into shared **`substrate_*`** tables (worker-local). Wire **GeocodeAgent → DBOutput** directly; add **Output** (JSON Output) if you want a `consolidated` JSON view on the canvas.  

Create graphs in the Agate UI or from the **Geocode pipeline** template (`agate_template`, seeded by migration).

## Quick start

```bash
cp .env.example .env   # optional: add OPENAI_API_KEY / ANTHROPIC_API_KEY (gitignored)
make bootstrap         # once: uv sync --all-packages (Python tooling + libs)
make up                # Docker Compose (foreground; Ctrl+C stops all services)
```

- Agate: http://localhost:5173 — home opens the **General** project (empty until you create a flow).  
- Stylebook UI: http://localhost:5175  

`agate-api` runs `alembic upgrade head` on container start so migrations apply, then (when bootstrap is enabled) syncs API keys from the repo-root `.env` into encrypted **General** project secrets.

`make bootstrap` installs Python dependencies only; it does **not** seed the database (that happens when the stack starts).

## Validation

```bash
make lint
make test
make stylebook-ui-build   # when apps/stylebook-ui changes
make smoke-fast   # auth + deterministic Agate/Stylebook smoke lanes
make smoke        # live-stack Agate -> Stylebook handoff lane
make smoke-runtime   # handoff + worker lifecycle bundle
make smoke-place-geocode   # optional: PlaceExtract + GeocodeAgent corpus (docs/TESTING.md)
```

### Environment

- **LLM / geocoder / AWS keys**: add to repo-root `.env` (see [.env.example](.env.example)). Compose loads that file into `agate-api` and `worker` so PlaceExtract and GeocodeAgent can run. LLM keys are copied into **General** project secrets when local bootstrap runs (Fernet-encrypted in Postgres). Optional **`AWS_ACCESS_KEY_ID`** / **`AWS_SECRET_ACCESS_KEY`** (and **`AWS_SESSION_TOKEN`** if needed) for S3 Input are not bootstrap-synced—use worker env or organization integrations.
- **Shared service token** (optional): set the same value on agate-api, worker, and stylebook-api:

```bash
export SERVICE_API_TOKEN=your-token
make up
```

If unset, Stylebook geocode accepts unauthenticated requests (dev only).

## Makefile (intentionally small)

| Target | Purpose |
|--------|---------|
| `make help` | List commands |
| `make up` / `make down` | Compose; `down` then `docker system prune` only (keeps compose DB volumes) |
| `make logs` | Tail logs |
| `make migrate` | Re-run Alembic inside `agate-api` |
| `make reset-db` | `docker compose down -v` (removes Postgres volume) |
| `make docker-trim` | `docker system prune -f` when Docker is low on disk (does not run `docker volume prune`) |
| `make docker-trim-full` | `docker-trim` then `docker volume prune -f` for aggressive reclaim |
| `make test` | All tests |
| `make lint` / `make format` | Ruff |
| `make smoke-fast` / `make smoke` / `make smoke-runtime` / `make smoke-slower` | Smoke bundles by cadence (see [docs/TESTING.md](docs/TESTING.md)) |

## Docs

- [AGENTS.md](AGENTS.md) — top-level operating guide for agent and human contributors  
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — package boundaries and runtime flow  
- [docs/API.md](docs/API.md) — Agate API conventions and orchestration  
- [docs/PUBLIC_API.md](docs/PUBLIC_API.md) — public `/public/v1` API design and rollout plan  
- [docs/FRONTEND.md](docs/FRONTEND.md) — frontend conventions and node sync flow  
- [docs/DATABASE.md](docs/DATABASE.md) — schema ownership and redesign space  
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — compose, env vars, and troubleshooting  
- [docs/TESTING.md](docs/TESTING.md) — testing layers  
- [docs/AGENTIC.md](docs/AGENTIC.md) — agentic workflow orientation: rules/skills, per-task checklists, and planning  

## Layout

```
apps/agate-api    apps/agate-ui
apps/worker       apps/stylebook-api    apps/stylebook-ui    apps/core-api
packages/backfield-agate  packages/backfield-auth   packages/backfield-db   packages/backfield-ui
infra/docker-compose.yml   .env.example
```
