# Public API

Backfield's consumer-facing HTTP API is owned and served by **Core API**. Its
public namespace is:

```text
/public/v1
```

The implementation is mounted in
[`core_api.main`](../../apps/core-api/src/core_api/main.py) and assembled by the
[`core_api.routers.public`](../../apps/core-api/src/core_api/routers/public/)
package. Agate API and Stylebook API continue to own their internal workflow
surfaces; they are not alternate public API hosts.

## Local base URL

With the local stack running (`make up`), Core API listens at:

```text
http://127.0.0.1:8004
```

Public routes are therefore under `http://127.0.0.1:8004/public/v1/...`.

## Authentication and project scope

Send a project API key as a Bearer token:

```http
Authorization: Bearer bfk_...
```

Create and revoke keys from Core API under
`/v1/projects/{project_id}/api-keys` (session auth in the product UI, or see
[`core.md`](core.md)). Keys are bound to one project. Project keys include the
`read` scope when minted. Starting a run additionally requires `runs:trigger`;
that scope is limited to service-type project keys.

Public resources are project-scoped under
`/public/v1/projects/{project_slug}`. The authentication dependency validates
the key and verifies that it belongs to the requested project. Browser session
cookies are rejected on this surface. Internal service Bearer tokens are also
accepted for automation, but are not consumer credentials.

The current checks live in
[`public/deps.py`](../../apps/core-api/src/core_api/routers/public/deps.py), with
shared authentication and project authorization in
[`backfield_auth.gate`](../../packages/backfield-auth/src/backfield_auth/gate.py).

### Example

```bash
curl -sS \
  -H "Authorization: Bearer bfk_..." \
  "http://127.0.0.1:8004/public/v1/projects/<project-slug>"
```

## Shipped route families

The public router currently exposes:

- **Projects** — project metadata, effective Stylebook information, and summary
  statistics.
- **Articles** — keyword, semantic, and geographic discovery; facets and
  metadata; article detail; geo-cell coverage and drill-down; and
  article-scoped mentions, locations, people, organizations, custom records,
  and images.
- **Mentions** — project-wide search, facets, and evidence detail across
  locations, people, and organizations.
- **People, organizations, and locations** — list and search, available types,
  canonical detail, mention evidence and timelines, related articles, and
  connections. Locations also provide geographic search.
- **Runs** — triggering an API-enabled Agate graph and polling the resulting run.

There is no public `works` router or project-wide custom-record search router in
the current implementation. The article-scoped custom-record route is present.

## Pagination and errors

- Structured boundaries use Pydantic response models. Paginated collections
  generally return `items` plus `pagination` containing `limit`, `offset`, and
  `total`; individual routes define their precise schema in OpenAPI.
- Errors use FastAPI's JSON `detail` response. Missing or out-of-project
  resources are resolved within project scope, while an API key for another
  project is rejected.
- The surface is read-oriented except for the scoped run trigger.

## Run trigger and polling

1. `POST /public/v1/projects/{project_slug}/runs` with a body that includes
   `graph_id` and `inputs`. Requires a service-type project key with
   `runs:trigger`. The target graph must have public run trigger enabled.
2. Poll `GET /public/v1/projects/{project_slug}/runs/{run_id}` until status and
   item counts settle.

## OpenAPI artifact

A filtered public-only OpenAPI document is committed at
[`public.openapi.json`](public.openapi.json). Regenerate after route changes:

```bash
uv run python scripts/export_public_openapi.py
```

Core API also serves the full schema at `/openapi.json` and interactive docs at
`/docs`; public operations are identifiable by their `/public/v1` paths.

## Related documentation

- [`agate.md`](agate.md) — internal Agate API conventions and orchestration
- [`core.md`](core.md) — Core API auth, projects, and API keys
- [`../architecture/overview.md`](../architecture/overview.md) — service and package boundaries
- [`apps/core-api/src/core_api/routers/public/`](../../apps/core-api/src/core_api/routers/public/)
  — public route implementation
- [`packages/backfield-entities/src/backfield_entities/public/`](../../packages/backfield-entities/src/backfield_entities/public/)
  — shared public query and serialization logic
