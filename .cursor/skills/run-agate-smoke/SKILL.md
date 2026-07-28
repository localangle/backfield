---
name: run-agate-smoke
description: Validate the Backfield golden path against a live stack. Use when runtime behavior changes across Agate API, worker, Stylebook API, or the starter geocode pipeline (including DBOutput persistence).
---

# Run Agate Smoke

## Quick Start

1. Ensure the stack is running (`make up` or `make up-detached`).
2. Configure the flow's model credentials in **Settings → AI models** and any geocoder credentials in **Settings → Integrations**. CI may inject provider keys through its temporary root `.env` as an unattended fallback.
3. Run `make smoke` (runs `tests/smoke/golden_path_stack.py`; uses `SMOKE_POLL_TIMEOUT_SECONDS`, default 180s). Set **`SMOKE_EMAIL`** and **`SMOKE_PASSWORD`** for the session-shaped path (Core login → `/v1/me/workspaces` → Agate with cookie); omit for service-Bearer-only Agate calls.
4. If it fails, inspect `make logs` and the relevant service logs.

## What The Smoke Covers

- Agate API health; Stylebook API health; Core API health when using session mode
- **General** project (slug `general`, overridable) — smoke creates **Starter flow** via API when missing
- With **`SMOKE_EMAIL` / `SMOKE_PASSWORD`**: Core login, **`GET /v1/me/workspaces`**, then Agate with **`session` cookie** (UI-shaped path)
- Run enqueue on the `agate` queue for that graph; worker completion and terminal run status
- Asserts **Starter flow** `spec` matches canonical (`starter_geocode_flow_graph_spec`: GeocodeAgent → DBOutput) and the run `result` includes **`stylebook_output`** with `success: true` (no `json_output` / `__outputKeysByNodeId`)
- Does **not** delete General; smoke may leave the created starter graph in place unless you clean up manually

## When To Use It

- Queue, worker, or run lifecycle changes
- API contract changes that affect graphs, templates, projects, or runs
- Stylebook geocode integration changes
- DB changes that affect the live runtime path
