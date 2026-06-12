# Public API endpoints (running list)

Living registry of shipped **`/public/v1`** routes. Update this file whenever a public endpoint is added or its contract changes.

Design reference: [`../../PUBLIC_API.md`](../../PUBLIC_API.md)

| Field | Value |
|-------|--------|
| **Service** | `apps/core-api` |
| **Base path** | `/public/v1` |
| **Local base URL** | `http://localhost:8004/public/v1` |
| **Auth** | `Authorization: Bearer bfk_…` (project API key). Service token accepted for automation only. |

---

## GET `/public/v1/projects/{project_slug}`

| | |
|---|---|
| **Status** | Shipped (Phase 1) |
| **Module** | [`apps/core-api/src/core_api/routers/public/projects.py`](../../../apps/core-api/src/core_api/routers/public/projects.py) — `get_public_project_metadata` |
| **Auth** | Project API key required |

### Functionality

Returns minimal project metadata for the given slug. Resolves the effective Stylebook catalog used for public entity queries (organization default when no slug override). Returns **404** when the slug does not exist or the API key cannot access that project.

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_slug` | string | yes | Project slug (e.g. `general`) |

### Response `200`

```json
{
  "id": 1,
  "name": "General",
  "slug": "general",
  "stylebook_slug": "default",
  "stylebook_name": "Default Stylebook"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Internal project id |
| `name` | string | Display name |
| `slug` | string | URL slug |
| `stylebook_slug` | string \| null | Effective Stylebook slug for this project, when resolvable |
| `stylebook_name` | string \| null | Effective Stylebook display name |

### Errors

| Status | When |
|--------|------|
| `401` | Missing or invalid API key; session cookie not accepted |
| `403` | API key is valid but not for this project |
| `404` | Unknown `project_slug` or project outside caller scope |

---

## GET `/public/v1/projects/{project_slug}/articles/search`

| | |
|---|---|
| **Status** | Shipped (Phase 2) |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles.py`](../../../apps/core-api/src/core_api/routers/public/articles.py) — `search_project_articles` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/articles.py`](../../../packages/backfield-entities/src/backfield_entities/public/articles.py) |
| **Auth** | Project API key required |

### Functionality

Search non-deleted articles in a project by keyword (headline or URL), metadata tags, and publication date. Returns a paginated list without full body text.

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_slug` | string | yes | Project slug |

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `q` | string | — | Keyword match on `headline` or `url` (case-insensitive) |
| `meta_type` | string | — | Filter to articles with a metadata row of this type |
| `meta_category` | string | — | With `meta_type`, filter to this category value |
| `pub_date_from` | string | — | ISO date `YYYY-MM-DD`, inclusive lower bound |
| `pub_date_to` | string | — | ISO date `YYYY-MM-DD`, inclusive upper bound |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |
| `include_preview` | boolean | `false` | Include truncated text preview (max 280 characters) |

### Response `200`

```json
{
  "items": [
    {
      "id": 1,
      "headline": "City council votes on budget",
      "url": "https://example.com/budget",
      "author": "Jane Doe",
      "pub_date": "2024-03-01",
      "external_source": null,
      "external_id": null,
      "entry_id": null,
      "preview": null,
      "metadata": [
        {
          "meta_type": "subject",
          "category": "local_government_politics",
          "confidence": 0.92
        }
      ]
    }
  ],
  "pagination": {
    "limit": 25,
    "offset": 0,
    "total": 1
  }
}
```

Results are ordered by `pub_date` descending (nulls last), then `id` descending.

### Errors

| Status | When |
|--------|------|
| `400` | Invalid `pub_date_from` or `pub_date_to` format |
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown `project_slug` |

---

## GET `/public/v1/projects/{project_slug}/articles/{article_id}`

| | |
|---|---|
| **Status** | Shipped (Phase 2) |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles.py`](../../../apps/core-api/src/core_api/routers/public/articles.py) — `get_project_article` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/articles.py`](../../../packages/backfield-entities/src/backfield_entities/public/articles.py) |
| **Auth** | Project API key required |

### Functionality

Return one article by id. Does **not** include full body text. Includes metadata tags and optional short preview.

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_slug` | string | yes | Project slug |
| `article_id` | integer | yes | `substrate_article.id` |

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `include_preview` | boolean | `true` | Include truncated text preview (max 280 characters) |

### Response `200`

Same article object shape as search `items[]`, with `external_source`, `external_id`, and `entry_id` populated when present.

### Errors

| Status | When |
|--------|------|
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown project, unknown article, or article not in project |

---

<!-- Add new endpoints below in the same section format. -->
