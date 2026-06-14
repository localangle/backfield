# Backfield Public API Reference

Agent-oriented documentation for the consumer-facing HTTP API. **Source of truth for design and phases:** [`../PUBLIC_API.md`](../PUBLIC_API.md).

## Base URL

| Environment | Base URL |
|-------------|----------|
| Local | `http://localhost:8004/public/v1` |

Production base URL is deployment-specific.

## Authentication

```http
Authorization: Bearer bfk_<project_api_key>
```

Keys are created in the product (org admin → project API keys). Each request must target a project the key may access.

## Project scope

All resources live under:

```text
/public/v1/projects/{project_slug}/…
```

## Conventions

### Pagination

Query: `limit` (default 25, max 100), `offset` (default 0).

List response:

```json
{
  "items": [],
  "pagination": {
    "limit": 25,
    "offset": 0,
    "total": 0
  }
}
```

### Errors

JSON body `{ "detail": "<message>" }`. Missing or inaccessible project-scoped resources return **404**.

### Dates

Query parameters use ISO dates: `YYYY-MM-DD`.

## Route index

Core API public routers live under `apps/core-api/src/core_api/routers/public/`:

| Folder | Routes |
|--------|--------|
| `projects/` | Project metadata |
| `articles/` | Search, semantic search, geo search, geo cells, detail, and hub sub-routes (one module per endpoint) |
| `people/` | List, search, types, detail, mentions, and connections |
| `organizations/` | List, search, types, detail, mentions, and connections |
| `locations/` | List, search, geo search, types, detail, mentions, and connections |

| Doc | Status |
|-----|--------|
| **[endpoints.md](endpoints.md)** | **Running list** of shipped routes (location, args, behavior) |
| **[geo-cells-map-clients.md](geo-cells-map-clients.md)** | Map-client integration guide for hex coverage (`/articles/geo-cells`) |
| [capability-matrix.md](capability-matrix.md) | Query modes by resource |
| Articles | Shipped — see `endpoints.md` |
| People | Shipped — see `endpoints.md` |
| Organizations | Shipped — see `endpoints.md` |
| Locations | Shipped — see `endpoints.md` |
| `custom-records.md` | Phase 3 |
| `locations.md` | Shipped in `endpoints.md` (Phase 4) |
| `people.md` | Shipped in `endpoints.md` (Phase 4) |
| `organizations.md` | Shipped in `endpoints.md` (Phase 4) |
| `geo.md` | Phase 6 |
| `runs.md` | Phase 7 |

## OpenAPI

When implemented, export the `/public/v1` OpenAPI subset from Core API for machine-readable schemas. Internal Agate and Stylebook OpenAPI specs are not part of the public contract.
