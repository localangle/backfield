# Backfield

Reconstruction of the Agate-style platform focused on **Agate** (visual pipelines) and **Stylebook** (geocoding stub today; entities later). Dashboard is out of scope for this slice.

## Stack

| Piece | Port (local) | Role |
|--------|----------------|------|
| **Agate UI** | 5173 | React + React Flow canvas |
| **Agate API** | 8000 | Graphs, runs, node metadata |
| **Worker** | — | Celery executes runs (`agate` queue) |
| **Stylebook API** | 8003 | Geocode helper for `GeocodeAgent` |
| **Stylebook UI** | 5175 | Shell + health check |
| **Postgres** | 5433 | `agate_*` application tables (see [docs/DATABASE.md](docs/DATABASE.md)) |
| **Redis** | 6379 | Celery broker |

## Starter Agate nodes

1. **TextInput** — parameter text out  
2. **PlaceExtract** — City, `ST` heuristic (no LLM)  
3. **GeocodeAgent** — HTTP to Stylebook `/v1/geocode/resolve`  
4. **JsonOutput** — wraps upstream as `consolidated` JSON  

## Quick start

```bash
make bootstrap   # once: uv sync --all-packages (Python tooling + libs)
make up          # Docker Compose (foreground; Ctrl+C stops all services)
```

- Agate: http://localhost:5173 — use **Run pipeline** (saves graph, enqueues Celery run, polls result).  
- Stylebook UI: http://localhost:5175  

`agate-api` runs `alembic upgrade head` on container start so migrations apply.

## Validation

```bash
make lint
make test
make smoke   # requires a live local stack
```

### Environment

Optional shared secret for service calls (set the same value on agate-api, worker, stylebook-api):

```bash
export SERVICE_API_TOKEN=your-token
make up
```

If unset, Stylebook geocode accepts unauthenticated requests (dev only).

## Makefile (intentionally small)

| Target | Purpose |
|--------|---------|
| `make help` | List commands |
| `make up` / `make down` | Compose |
| `make logs` | Tail logs |
| `make migrate` | Re-run Alembic inside `agate-api` |
| `make reset-db` | `docker compose down -v` |
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
apps/worker       apps/stylebook-api    apps/stylebook-ui
packages/backfield-core   packages/backfield-db
infra/docker-compose.yml
```
