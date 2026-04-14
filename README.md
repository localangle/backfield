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
| **Stylebook UI** | 5175 | Shell + health check |
| **Postgres** | 5433 | `agate_*` application tables (see [docs/DATABASE.md](docs/DATABASE.md)) |
| **Redis** | 6379 | Celery broker |

## Starter Agate nodes

1. **TextInput** — parameter text out (non-empty validation)  
2. **PlaceExtract** — LLM extraction (ported from agate-ai-platform; needs `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` on the worker)  
3. **GeocodeAgent** — LangGraph + external geocoders / LLM (ported; optional Stylebook cache)  
4. **Output** (JSON Output in the palette) — agate-style merge into `consolidated` JSON  

## Quick start

```bash
cp .env.example .env   # optional: add OPENAI_API_KEY / ANTHROPIC_API_KEY (gitignored)
make bootstrap         # once: uv sync --all-packages (Python tooling + libs)
make up                # Docker Compose (foreground; Ctrl+C stops all services)
```

- Agate: http://localhost:5173 — home opens the **General** project; a **Starter flow** graph is created on first API boot when `BACKFIELD_LOCAL_BOOTSTRAP=1` (default in Compose).  
- Stylebook UI: http://localhost:5175  

`agate-api` runs `alembic upgrade head` on container start so migrations apply, then (when bootstrap is enabled) syncs API keys from the repo-root `.env` into encrypted **General** project secrets and ensures the starter graph exists.

`make bootstrap` installs Python dependencies only; it does **not** seed the database (that happens when the stack starts).

## Validation

```bash
make lint
make test
make smoke   # requires a live local stack
```

### Environment

- **LLM / geocoder / Mapbox keys**: add to repo-root `.env` (see [.env.example](.env.example)). Compose loads that file into `agate-api` and `worker` so PlaceExtract and GeocodeAgent can run. The same values are copied into **General** project secrets when local bootstrap runs (Fernet-encrypted in Postgres), including optional **`MAPBOX_API_TOKEN`** for map visualizations.
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
| `make up` / `make down` | Compose (`down` then prunes build cache and unused volumes) |
| `make logs` | Tail logs |
| `make migrate` | Re-run Alembic inside `agate-api` |
| `make reset-db` | `docker compose down -v` (removes Postgres volume) |
| `make docker-trim` | Prune build cache + unused volumes when Docker is low on disk |
| `make test` | All tests |
| `make lint` / `make format` | Ruff |

## Docs

- [AGENTS.md](AGENTS.md) — top-level operating guide for agent and human contributors  
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — package boundaries and runtime flow  
- [docs/API.md](docs/API.md) — Agate API conventions and orchestration  
- [docs/FRONTEND.md](docs/FRONTEND.md) — frontend conventions and node sync flow  
- [docs/LAYOUT.md](docs/LAYOUT.md) — monorepo structure and naming  
- [docs/DATABASE.md](docs/DATABASE.md) — schema ownership and redesign space  
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — compose, env vars, and troubleshooting  
- [docs/TESTING.md](docs/TESTING.md) — testing layers  
- [docs/AGENT_WORKFLOWS.md](docs/AGENT_WORKFLOWS.md) — task-specific validation guidance  
- [docs/PLANS.md](docs/PLANS.md) — planning expectations for larger changes  

## Layout

```
apps/agate-api    apps/agate-ui
apps/worker       apps/stylebook-api    apps/stylebook-ui    apps/core-api
packages/backfield-core   packages/backfield-auth   packages/backfield-db   packages/agate-runtime
infra/docker-compose.yml   .env.example
```
