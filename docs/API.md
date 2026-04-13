# API

This document covers the Agate API in `apps/agate-api`.

## Responsibilities

- Expose health, project, graph, template, run, and node metadata routes.
- Validate request and response models at the HTTP boundary.
- Persist graph and run state through `backfield-db`.
- Enqueue run execution onto Celery.
- Keep route handlers readable and focused; move repeated logic into small helpers.

## Route ownership

- `routers/health.py`
  - Lightweight service health only.
- `routers/projects.py`
  - Project CRUD, stats, and encrypted project secrets.
- `routers/graphs.py`
  - Graph CRUD and `GraphSpec` validation.
- `routers/templates.py`
  - List templates and instantiate them into project graphs.
- `routers/runs.py`
  - Create, list, and fetch runs; enqueue `worker.tasks.execute_agate_run`.
- `routers/nodes.py`
  - Surface node metadata derived from `backfield-core`.

## Boundary rules

- Parse data at the route boundary with **Pydantic** models (`BaseModel` or shared types like `GraphSpec` from `backfield-core`). Prefer explicit request/response models over untyped dicts.
- Prefer **strict typing** in router modules: annotated handlers and helpers, minimal use of `Any`.
- Keep DB table details in `backfield-db`, not duplicated in routers.
- Keep worker task names, queue names, and response statuses aligned with the worker implementation.
- Avoid hiding complex route logic in oversized handlers. Extract helpers when a route gets hard to scan.

## Run lifecycle

1. Client creates a run with `POST /runs`.
2. API inserts an `AgateRun` row with `pending` status.
3. API enqueues `worker.tasks.execute_agate_run` on the `agate` queue.
4. Worker transitions the run to `running`, executes the graph, then stores `succeeded` or `failed`.
5. Client polls `GET /runs/{id}` until the run reaches a terminal state.

## API change checklist

- Update route models and handlers together.
- Update matching frontend client code in `apps/agate-ui/src/lib/api.ts`.
- Update worker behavior when queue/task/status contracts change.
- Update docs when the API surface, smoke flow, or operational expectations change.