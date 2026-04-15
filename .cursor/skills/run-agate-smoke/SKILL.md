---
name: run-agate-smoke
description: Validate the Backfield golden path against a live stack. Use when runtime behavior changes across Agate API, worker, Stylebook API, or the four-node starter flow.
---

# Run Agate Smoke

## Quick Start

1. Ensure the stack is running (`make up` or `make up-detached`).
2. Put `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` (and optional geocoder / `MAPBOX_API_TOKEN` keys) in **repo-root `.env`** so Compose loads them into `worker` and `agate-api` (and into General project secrets when `BACKFIELD_LOCAL_BOOTSTRAP=1`).
3. Run `make smoke` (runs `tests/smoke/golden_path_stack.py`; uses `SMOKE_POLL_TIMEOUT_SECONDS`, default 180s). Set **`SMOKE_EMAIL`** and **`SMOKE_PASSWORD`** for the session-shaped path (Core login → `/v1/me/workspaces` → Agate with cookie); omit for service-Bearer-only Agate calls.
4. If it fails, inspect `make logs` and the relevant service logs.

## What The Smoke Covers

- Agate API health; Stylebook API health; Core API health when using session mode
- **General** project (slug `general`, overridable) and **Starter flow** graph present
- With **`SMOKE_EMAIL` / `SMOKE_PASSWORD`**: Core login, **`GET /v1/me/workspaces`**, then Agate with **`session` cookie** (UI-shaped path)
- Run enqueue on the `agate` queue for that graph; worker completion and terminal run status
- Does **not** delete General or the starter graph

## When To Use It

- Queue, worker, or run lifecycle changes
- API contract changes that affect graphs, templates, projects, or runs
- Stylebook geocode integration changes
- DB changes that affect the live runtime path
