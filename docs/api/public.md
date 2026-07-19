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

## API Playground

The local stack serves the interactive API Playground at
[localhost:5176](http://localhost:5176). It loads the public OpenAPI contract immediately, so the
endpoint catalog and request fields can be browsed without authentication. Apply a project API key
in the Playground to execute requests and load project-scoped choices. Generated curl commands use
`$BACKFIELD_PROJECT_API_KEY` instead of embedding the key.

See the [`apps/api-playground` guide](../../apps/api-playground/README.md) for interaction,
security, and frontend development details.

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
cookies are rejected on this surface. Internal service Bearer tokens remain
runtime-compatible for trusted automation, but are not part of the public
credential contract.

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
- Every public error uses one envelope:
  `{"error":{"code":"...","message":"...","details":...},"request_id":"..."}`.
  Codes such as `unauthorized`, `forbidden`, `not_found`, and
  `validation_error` are stable identifiers; message text is explanatory.
  Error responses include `X-Request-ID`. Internal APIs retain FastAPI's
  existing error shape.
- The surface is read-oriented except for the scoped run trigger.
- Successful responses include `RateLimit-Limit`, `RateLimit-Remaining`, and
  `RateLimit-Reset` (seconds until reset). Limits use per-key and project-aggregate
  one-minute buckets. A `429` also includes `Retry-After`. Redis failures are
  logged and fail open so rate limiting never turns into an authentication outage.

Article and mention metadata filters use repeatable `meta` values. Publication
filters use `external_source`; compatibility aliases and single metadata-field
parameters are not part of the v1 contract.

Article keyword search accepts `sort=relevance|pub_date` and
`sort_direction=asc|desc`. With `q`, the default is relevance descending;
without `q`, the default is publication date descending. Relevance sorting
requires a non-empty `q`. Responses echo the effective sort and direction.

Canonical person, organization, and location article-list endpoints accept the same
repeatable `meta` grammar plus `author`, `external_source`, and repeatable
`include=counts`. Article-scoped people, organizations, and locations share
`nature` and `quote` filters; location lists additionally accept
`location_type`. Entity connection lists use the standard `items` and
`pagination` envelope, default to 25 items (maximum 100), and accept
`to_entity_type` and `nature`.

## Run trigger and polling

1. `POST /public/v1/projects/{project_slug}/runs` with a body that includes
   `graph_id` and `inputs`. Requires a service-type project key with
   `runs:trigger`. The target graph must have public run trigger enabled. The
   response is `202 Accepted` with `Location` and `Retry-After`.
2. Poll `GET /public/v1/projects/{project_slug}/runs/{run_id}` until status and
   item counts settle. Pending and running responses include `Retry-After`.

Clients may send an `Idempotency-Key` of 1–128 URL-safe visible characters.
For seven days, repeating the key with the same canonical JSON body returns the
current snapshot of the original run and `Idempotency-Replayed: true`; reusing it
with a different body returns `409`. Only a SHA-256 request hash is retained, not
the request body or credentials.

Default one-minute limits are 600 standard reads, 60 semantic/geographic
searches, and 5 run triggers per API key. Each project's aggregate limit is four
times its corresponding per-key limit. Internal service tokens receive bounded
token-derived identities and use the same limits.

## OpenAPI artifact

A filtered public-only OpenAPI document is committed at
[`public.openapi.json`](public.openapi.json). Regenerate after route changes:

```bash
uv run python scripts/export_public_openapi.py
```

Core API serves this public-only contract without authentication at
`/public/v1/openapi.json`. The document contains only public paths and schemas
reachable from them, declares project API key Bearer authentication, and lists
production and local server URLs. Paths retain the `/public/v1` prefix, so
clients append them directly to the server URL. The full internal schema
remains available at `/openapi.json`.

## Related documentation

- [`agate.md`](agate.md) — internal Agate API conventions and orchestration
- [`core.md`](core.md) — Core API auth, projects, and API keys
- [`../architecture/overview.md`](../architecture/overview.md) — service and package boundaries
- [`apps/core-api/src/core_api/routers/public/`](../../apps/core-api/src/core_api/routers/public/)
  — public route implementation
- [`packages/backfield-entities/src/backfield_entities/public/`](../../packages/backfield-entities/src/backfield_entities/public/)
  — shared public query and serialization logic
