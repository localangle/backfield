# Public API endpoints (running list)

Living registry of shipped **`/public/v1`** routes. Update this file whenever a public endpoint is added or its contract changes.

Design reference: [`../../PUBLIC_API.md`](../../PUBLIC_API.md)

| Field | Value |
|-------|--------|
| **Service** | `apps/core-api` |
| **Base path** | `/public/v1` |
| **Local base URL** | `http://localhost:8004/public/v1` |
| **Auth** | `Authorization: Bearer bfk_…` (project API key). Service token accepted for automation only. |

## Planned (article hub)

| Method | Path | Phase | Notes |
|--------|------|-------|-------|
| `GET` | `…/articles/{article_id}/custom-records` | 3 | Custom Extract rows |

---

## GET `/public/v1/projects/{project_slug}`

| | |
|---|---|
| **Status** | Shipped (Phase 1) |
| **Module** | [`apps/core-api/src/core_api/routers/public/projects/routes.py`](../../../apps/core-api/src/core_api/routers/public/projects/routes.py) — `get_public_project_metadata` |
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
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/search.py`](../../../apps/core-api/src/core_api/routers/public/articles/search.py) — `search_project_articles` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/articles.py`](../../../packages/backfield-entities/src/backfield_entities/public/articles.py) |
| **Auth** | Project API key required |

### Functionality

Search non-deleted articles in a project by keyword (headline, body text, or URL), metadata tags, and publication date. Returns a paginated list without full body text. On PostgreSQL, `q` uses full-text search over headline + body + URL (not semantic embeddings).

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_slug` | string | yes | Project slug |

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `q` | string | — | Keyword match on `headline` or `url` (case-insensitive) |
| `meta_type` | string | — | Include articles with a metadata row of this type |
| `meta_category` | string | — | With `meta_type`, include articles with this category value |
| `exclude_meta_type` | string | — | Exclude articles with a metadata row of this type |
| `exclude_meta_category` | string | — | With `exclude_meta_type`, exclude articles with this category value |
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

## POST `/public/v1/projects/{project_slug}/articles/semantic-search`

| | |
|---|---|
| **Status** | Shipped |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/semantic_search.py`](../../../apps/core-api/src/core_api/routers/public/articles/semantic_search.py) — `search_project_articles_semantic` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/article_semantic_search.py`](../../../packages/backfield-entities/src/backfield_entities/public/article_semantic_search.py) |
| **Auth** | Project API key required |

### Functionality

Natural-language article search over **`substrate_article_embedding`** rows. Embeds the request `query` with the project/org default **`semantic.embedding`** model, then ranks matching embedded articles by cosine similarity. Articles without an embedding row are omitted (not an error). Keyword search remains on **`GET …/articles/search`**.

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_slug` | string | yes | Project slug |

### JSON body

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `query` | string | required | Natural-language search text |
| `meta_type` | string | — | Include articles with a metadata row of this type |
| `meta_category` | string | — | With `meta_type`, include articles with this category value |
| `exclude_meta_type` | string | — | Exclude articles with a metadata row of this type |
| `exclude_meta_category` | string | — | With `exclude_meta_type`, exclude articles with this category value |
| `pub_date_from` | string | — | ISO date `YYYY-MM-DD`, inclusive lower bound |
| `pub_date_to` | string | — | ISO date `YYYY-MM-DD`, inclusive upper bound |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |
| `include_preview` | boolean | `false` | Include truncated text preview (max 280 characters) |

### Response `200`

```json
{
  "query": "city budget debate",
  "embedding_model": "openai/text-embedding-3-small",
  "embedding_model_config_id": "…",
  "items": [
    {
      "id": 1,
      "headline": "City council votes on budget",
      "score": 0.82,
      "preview": null,
      "metadata": []
    }
  ],
  "pagination": {
    "limit": 25,
    "offset": 0,
    "total": 1
  }
}
```

Results are ordered by **`score`** descending, then `pub_date` descending, then `id` descending.

### Errors

| Status | When |
|--------|------|
| `400` | Invalid `pub_date_from` or `pub_date_to` format |
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown `project_slug` |
| `503` | No embedding model configured for semantic search |

---

## GET `/public/v1/projects/{project_slug}/articles/geo-search`

| | |
|---|---|
| **Status** | Shipped |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/geo_search.py`](../../../apps/core-api/src/core_api/routers/public/articles/geo_search.py) — `search_project_articles_by_geo` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/article_geo_search.py`](../../../packages/backfield-entities/src/backfield_entities/public/article_geo_search.py) |
| **Auth** | Project API key required |

### Functionality

Find articles that have at least one **location mention** whose substrate geometry falls within the search area. Returns each article plus the **`matching_locations`** that satisfied the filter (map-oriented location mention shape).

Use **either**:

- **Point + radius:** `center_lng`, `center_lat`, `radius_miles`
- **Bounding box:** `bbox=min_lng,min_lat,max_lng,max_lat`

Geometry comes from **`substrate_location.geometry`** (PostGIS on PostgreSQL). Articles without geocoded locations are omitted.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `center_lng` | number | — | Center longitude (point mode) |
| `center_lat` | number | — | Center latitude (point mode) |
| `radius_miles` | number | — | Radius in miles (required with center coordinates) |
| `bbox` | string | — | Bounding box `min_lng,min_lat,max_lng,max_lat` (bbox mode) |
| `location_type` | string | — | Filter matching locations by substrate `location_type` |
| `nature` | string | — | Filter matching location mentions by editorial `nature` (e.g. `primary`, `secondary`) |
| `meta_type` | string | — | Include articles with a metadata row of this type |
| `meta_category` | string | — | With `meta_type`, include articles with this category value |
| `exclude_meta_type` | string | — | Exclude articles with a metadata row of this type |
| `exclude_meta_category` | string | — | With `exclude_meta_type`, exclude articles with this category value |
| `pub_date_from` | string | — | ISO date `YYYY-MM-DD`, inclusive lower bound |
| `pub_date_to` | string | — | ISO date `YYYY-MM-DD`, inclusive upper bound |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |
| `include_preview` | boolean | `false` | Include truncated text preview per article |

### Response `200`

```json
{
  "items": [
    {
      "search_mode": "point",
      "article": {
        "id": 1,
        "headline": "City council votes on budget",
        "preview": null,
        "metadata": []
      },
      "matching_locations": [
        {
          "mention_id": 10,
          "substrate_location_id": 4,
          "label": "City Hall",
          "geometry_json": { "type": "Point", "coordinates": [-87.6, 41.8] },
          "h3_cell": "872664c1bffffff",
          "h3_resolution": 11
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

Results are ordered by article `pub_date` descending (nulls last), then `id` descending.

### Errors

| Status | When |
|--------|------|
| `400` | Invalid geo parameters, mixed point+bbox modes, or invalid dates |
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown `project_slug` |

---

## GET `/public/v1/projects/{project_slug}/articles/geo-cells`

| | |
|---|---|
| **Status** | Shipped |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/geo_cells.py`](../../../apps/core-api/src/core_api/routers/public/articles/geo_cells.py) — `aggregate_project_articles_by_geo_cells` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/article_geo_cells.py`](../../../packages/backfield-entities/src/backfield_entities/public/article_geo_cells.py) |
| **Auth** | Project API key required |

### Functionality

Return **H3 hex cells** with **distinct-article counts** for location mentions whose geometry falls inside a bounding box. Use this for zoomable hex coverage maps.

- **Count unit:** one article counts once per cell even if it has multiple place mentions in that cell.
- **Resolution `R`:** when `resolution` is omitted, derived from bbox viewport size (geometric mean of width and height). When provided, honored as the starting resolution. If aggregation exceeds the cell ceiling, the API auto-coarsens (lowers `R`) until under the cap and sets `coarsened: true`.
- **Size gate:** locations with native `h3_resolution < R` are excluded — coarse city/state mentions do not pollute fine-zoom counts. No `location_type` configuration is required.
- **Cell ceiling:** responses are capped at 5,000 cells via auto-coarsen, not a `400` error.

Only locations with populated `h3_cell` and `h3_resolution` contribute.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `bbox` | string | **required** | Bounding box `min_lng,min_lat,max_lng,max_lat` |
| `resolution` | integer | — | Optional H3 display resolution (0–15). When omitted, derived from bbox viewport size. Auto-coarsened if the cell ceiling is exceeded. |
| `location_type` | string | — | Filter matching locations by substrate `location_type` |
| `nature` | string | — | Filter matching location mentions by editorial `nature` (e.g. `primary`, `secondary`) |
| `meta_type` | string | — | Include articles with a metadata row of this type |
| `meta_category` | string | — | With `meta_type`, include articles with this category value |
| `exclude_meta_type` | string | — | Exclude articles with a metadata row of this type |
| `exclude_meta_category` | string | — | With `exclude_meta_type`, exclude articles with this category value |
| `pub_date_from` | string | — | ISO date `YYYY-MM-DD`, inclusive lower bound |
| `pub_date_to` | string | — | ISO date `YYYY-MM-DD`, inclusive upper bound |

### Response `200`

```json
{
  "resolution": 7,
  "derived_resolution": 5,
  "requested_resolution": 8,
  "bbox_extent_km": 12.4,
  "coarsened": true,
  "cells": [
    {
      "h3_cell": "872664c47ffffff",
      "article_count": 12
    }
  ]
}
```

- `resolution` — effective display resolution after auto-coarsen
- `derived_resolution` — default resolution the bbox would use when `resolution` is omitted
- `requested_resolution` — echoed when the client passed `resolution` (null otherwise)
- `bbox_extent_km` — characteristic viewport size (km)
- `coarsened` — `true` when the cell ceiling forced a lower resolution than requested/derived

Cells are ordered by `article_count` descending, then `h3_cell` ascending.

### Errors

| Status | When |
|--------|------|
| `400` | Invalid bbox, inverted bbox bounds, or invalid dates |
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown `project_slug` |
| `422` | Missing required `bbox` |

---

## GET `/public/v1/projects/{project_slug}/articles/geo-cells/{h3_cell}`

| | |
|---|---|
| **Status** | Shipped |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/geo_cell_detail.py`](../../../apps/core-api/src/core_api/routers/public/articles/geo_cell_detail.py) — `list_project_articles_in_geo_cell` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/article_geo_cell_detail.py`](../../../packages/backfield-entities/src/backfield_entities/public/article_geo_cell_detail.py) |
| **Auth** | Project API key required |

### Functionality

Return the **articles** and **in-cell location mentions** behind one `geo-cells` hex. Use this for map drill-down when a user clicks a coverage cell.

Matching uses the same H3 rollup predicate as `geo-cells`, so `pagination.total` should equal the cell's `article_count` when the same filters are applied:

- `R = h3.get_resolution(h3_cell)` (derived from the path cell; no `resolution` param)
- Include a location mention when `h3_resolution >= R` and it rolls up to the requested cell
- Coarse-native locations are excluded at fine cells (size gate)

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `h3_cell` | string | yes | H3 cell ID from a `geo-cells` response |

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `location_type` | string | — | Filter matching locations by substrate `location_type` |
| `nature` | string | — | Filter matching location mentions by editorial `nature` |
| `meta_type` | string | — | Include articles with a metadata row of this type |
| `meta_category` | string | — | With `meta_type`, include articles with this category value |
| `exclude_meta_type` | string | — | Exclude articles with a metadata row of this type |
| `exclude_meta_category` | string | — | With `exclude_meta_type`, exclude articles with this category value |
| `pub_date_from` | string | — | ISO date `YYYY-MM-DD`, inclusive lower bound |
| `pub_date_to` | string | — | ISO date `YYYY-MM-DD`, inclusive upper bound |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |
| `include_preview` | boolean | `false` | Include truncated text preview per article |

Forward the same filters active on the coverage request so counts stay consistent.

### Response `200`

```json
{
  "h3_cell": "872664c47ffffff",
  "resolution": 7,
  "items": [
    {
      "article": {
        "id": 1,
        "headline": "City council votes on budget",
        "preview": null,
        "metadata": []
      },
      "matching_locations": [
        {
          "mention_id": 10,
          "substrate_location_id": 4,
          "label": "City Hall",
          "geometry_json": { "type": "Point", "coordinates": [-87.6, 41.8] },
          "h3_cell": "892664c1a97ffff",
          "h3_resolution": 11
        }
      ]
    }
  ],
  "pagination": {
    "limit": 25,
    "offset": 0,
    "total": 12
  }
}
```

Results are ordered by article `pub_date` descending (nulls last), then `id` descending. A valid cell with no matching mentions returns `200` with empty `items` and `total: 0`.

### Errors

| Status | When |
|--------|------|
| `400` | Invalid `h3_cell` or invalid dates |
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown `project_slug` |

---

## GET `/public/v1/projects/{project_slug}/articles/{article_id}`

| | |
|---|---|
| **Status** | Shipped (Phase 2) |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/detail.py`](../../../apps/core-api/src/core_api/routers/public/articles/detail.py) — `get_project_article` |
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
| `include` | string | — | Optional embeds: `counts` (entity, custom-record, and image counts) |

### Response `200`

Same article object shape as search `items[]`, with `external_source`, `external_id`, and `entry_id` populated when present. When `include=counts`, adds a `counts` object:

```json
{
  "counts": {
    "entity_counts": { "locations": 1, "people": 1, "organizations": 0 },
    "custom_record_counts": { "contracts": 2 },
    "image_count": 1
  }
}
```

### Errors

| Status | When |
|--------|------|
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown project, unknown article, or article not in project |

---

## GET `/public/v1/projects/{project_slug}/articles/{article_id}/mentions`

| | |
|---|---|
| **Status** | Shipped (Phase 2b) |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/mentions.py`](../../../apps/core-api/src/core_api/routers/public/articles/mentions.py) — `list_project_article_mentions` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/article_hub.py`](../../../packages/backfield-entities/src/backfield_entities/public/article_hub.py) |
| **Auth** | Project API key required |

### Functionality

Paginated mention evidence for one article across location, person, and organization entities. Unified index ordered by mention `created_at` descending.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entity_type` | string | — | Filter: `location`, `person`, or `organization` |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

### Response `200`

Paginated list of mention objects with `entity_type`, `mention_id`, `substrate_entity_id`, `label`, optional `canonical`, and optional `evidence` (mention/quote spans).

---

## GET `/public/v1/projects/{project_slug}/articles/{article_id}/locations`

| | |
|---|---|
| **Status** | Shipped (Phase 2b) |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/locations.py`](../../../apps/core-api/src/core_api/routers/public/articles/locations.py) — `list_project_article_locations` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/article_hub.py`](../../../packages/backfield-entities/src/backfield_entities/public/article_hub.py) |
| **Auth** | Project API key required |

### Functionality

Map-oriented list of location mentions in one article, including geometry and formatted address when present.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

---

## GET `/public/v1/projects/{project_slug}/articles/{article_id}/images`

| | |
|---|---|
| **Status** | Shipped (Phase 2b) |
| **Module** | [`apps/core-api/src/core_api/routers/public/articles/images.py`](../../../apps/core-api/src/core_api/routers/public/articles/images.py) — `list_project_article_images` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/article_hub.py`](../../../packages/backfield-entities/src/backfield_entities/public/article_hub.py) |
| **Auth** | Project API key required |

### Functionality

List images attached to the article (`substrate_image`).

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

### Response `200`

Each item includes `id`, `image_id`, `url`, and optional `caption`.

---

<!-- Add new endpoints below in the same section format. -->

---

## GET `/public/v1/projects/{project_slug}/people`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/people/list_search.py`](../../../apps/core-api/src/core_api/routers/public/people/list_search.py) — `list_project_people` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/people.py`](../../../packages/backfield-entities/src/backfield_entities/public/people.py) |
| **Auth** | Project API key required |

### Functionality

List active canonical people in the project's Stylebook. Supports the same filters and pagination as search (alias of list behavior).

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `q` | string | — | Case-insensitive match on label, title, or affiliation |
| `person_type` | string | — | Exact person type filter |
| `public_figure` | boolean | — | Filter by public-figure flag |
| `title` | string | — | Case-insensitive substring match on title |
| `affiliation` | string | — | Case-insensitive substring match on affiliation |
| `nature` | string | — | People with at least one linked mention of this nature in the project |
| `min_mentions` | integer | `0` | Minimum project mention count |
| `sort` | string | `sort_key` | `sort_key`, `recent`, or `label` (alias for `sort_key`) |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

### Response `200`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "slug": "jane-doe",
      "label": "Jane Doe",
      "title": "Mayor",
      "affiliation": "City Hall",
      "public_figure": true,
      "person_type": "elected_official",
      "mention_count": 3
    }
  ],
  "pagination": { "limit": 25, "offset": 0, "total": 1 }
}
```

---

## GET `/public/v1/projects/{project_slug}/people/search`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/people/list_search.py`](../../../apps/core-api/src/core_api/routers/public/people/list_search.py) — `search_project_people` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/people.py`](../../../packages/backfield-entities/src/backfield_entities/public/people.py) |
| **Auth** | Project API key required |

Same parameters, response shape, and filters as `GET …/people`.

---

## GET `/public/v1/projects/{project_slug}/people/types`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/people/types.py`](../../../apps/core-api/src/core_api/routers/public/people/types.py) |
| **Auth** | Project API key required |

### Functionality

Distinct person type values for filter dropdowns (union of catalog defaults and types stored on active canonicals).

### Response `200`

```json
{ "types": ["elected_official", "other"] }
```

---

## GET `/public/v1/projects/{project_slug}/people/{person_id}`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/people/detail.py`](../../../apps/core-api/src/core_api/routers/public/people/detail.py) |
| **Auth** | Project API key required |

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `person_id` | UUID string | yes | Stylebook person canonical id |

### Response `200`

Single person object (same fields as list items).

### Errors

| Status | When |
|--------|------|
| `404` | Unknown person, inactive canonical, or wrong Stylebook |

---

## GET `/public/v1/projects/{project_slug}/people/{person_id}/mentions`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/people/mentions.py`](../../../apps/core-api/src/core_api/routers/public/people/mentions.py) |
| **Auth** | Project API key required |

### Functionality

Paginated mention evidence for one canonical person, scoped to the project. Includes article headline, mention nature, and optional quote spans.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `sort` | string | `created_at` | `created_at` or `article` (headline) |
| `sort_direction` | string | `desc` | `asc` or `desc` |
| `limit` | integer | `50` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

### Response `200`

```json
{
  "person_id": "550e8400-e29b-41d4-a716-446655440000",
  "label": "Jane Doe",
  "items": [
    {
      "mention_id": 12,
      "article": {
        "id": 1,
        "headline": "City council votes on budget",
        "url": "https://example.com/budget",
        "pub_date": "2024-03-01"
      },
      "label": "Jane Doe",
      "person_type": "elected_official",
      "title": "Mayor",
      "affiliation": "City Hall",
      "nature": "subject",
      "role_in_story": null,
      "evidence": { "mention_text": "Jane Doe", "quote_text": null }
    }
  ],
  "pagination": { "limit": 50, "offset": 0, "total": 1 }
}
```

---

## GET `/public/v1/projects/{project_slug}/people/{person_id}/connections`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/people/connections.py`](../../../apps/core-api/src/core_api/routers/public/people/connections.py) |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/connections.py`](../../../packages/backfield-entities/src/backfield_entities/public/connections.py) |
| **Auth** | Project API key required |

### Functionality

Stylebook connections where the person is either the `from` or `to` endpoint. Labels are resolved from canonical rows when available.

### Response `200`

```json
{
  "person_id": "550e8400-e29b-41d4-a716-446655440000",
  "connections": [
    {
      "id": 1,
      "from_entity_type": "person",
      "from_entity_id": "550e8400-e29b-41d4-a716-446655440000",
      "from_label": "Jane Doe",
      "to_entity_type": "location",
      "to_entity_id": "660e8400-e29b-41d4-a716-446655440001",
      "to_label": "City Hall",
      "nature": "works_at"
    }
  ]
}
```

---

## GET `/public/v1/projects/{project_slug}/organizations`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/organizations/list_search.py`](../../../apps/core-api/src/core_api/routers/public/organizations/list_search.py) — `list_project_organizations` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/organizations.py`](../../../packages/backfield-entities/src/backfield_entities/public/organizations.py) |
| **Auth** | Project API key required |

### Functionality

List active canonical organizations in the project's Stylebook. Supports the same filters and pagination as search.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `q` | string | — | Case-insensitive match on label |
| `organization_type` | string | — | Exact organization type filter |
| `nature` | string | — | Organizations with at least one linked mention of this nature in the project |
| `min_mentions` | integer | `0` | Minimum project mention count |
| `sort` | string | `label` | `label` or `recent` |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

### Response `200`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "slug": "city-council",
      "label": "City Council",
      "organization_type": "government",
      "mention_count": 3
    }
  ],
  "pagination": { "limit": 25, "offset": 0, "total": 1 }
}
```

---

## GET `/public/v1/projects/{project_slug}/organizations/search`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/organizations/list_search.py`](../../../apps/core-api/src/core_api/routers/public/organizations/list_search.py) — `search_project_organizations` |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/organizations.py`](../../../packages/backfield-entities/src/backfield_entities/public/organizations.py) |
| **Auth** | Project API key required |

Same parameters, response shape, and filters as `GET …/organizations`.

---

## GET `/public/v1/projects/{project_slug}/organizations/types`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/organizations/types.py`](../../../apps/core-api/src/core_api/routers/public/organizations/types.py) |
| **Auth** | Project API key required |

### Functionality

Distinct organization type values for filter dropdowns (union of catalog defaults and types stored on active canonicals).

### Response `200`

```json
{ "types": ["company", "government"] }
```

---

## GET `/public/v1/projects/{project_slug}/organizations/{organization_id}`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/organizations/detail.py`](../../../apps/core-api/src/core_api/routers/public/organizations/detail.py) |
| **Auth** | Project API key required |

### Path parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `organization_id` | UUID string | yes | Stylebook organization canonical id |

### Response `200`

Single organization object (same fields as list items).

### Errors

| Status | When |
|--------|------|
| `404` | Unknown organization, inactive canonical, or wrong Stylebook |

---

## GET `/public/v1/projects/{project_slug}/organizations/{organization_id}/mentions`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/organizations/mentions.py`](../../../apps/core-api/src/core_api/routers/public/organizations/mentions.py) |
| **Auth** | Project API key required |

### Functionality

Paginated mention evidence for one canonical organization, scoped to the project.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `sort` | string | `created_at` | `created_at` or `article` (headline) |
| `sort_direction` | string | `desc` | `asc` or `desc` |
| `limit` | integer | `50` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

### Response `200`

```json
{
  "organization_id": "550e8400-e29b-41d4-a716-446655440000",
  "label": "City Council",
  "items": [
    {
      "mention_id": 12,
      "article": {
        "id": 1,
        "headline": "City council votes on budget",
        "url": "https://example.com/budget",
        "pub_date": "2024-03-01"
      },
      "label": "City Council",
      "organization_type": "government",
      "nature": "actor",
      "role_in_story": null,
      "evidence": { "mention_text": "City Council", "quote_text": null }
    }
  ],
  "pagination": { "limit": 50, "offset": 0, "total": 1 }
}
```

---

## GET `/public/v1/projects/{project_slug}/organizations/{organization_id}/connections`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/organizations/connections.py`](../../../apps/core-api/src/core_api/routers/public/organizations/connections.py) |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/connections.py`](../../../packages/backfield-entities/src/backfield_entities/public/connections.py) |
| **Auth** | Project API key required |

### Functionality

Stylebook connections where the organization is either the `from` or `to` endpoint.

### Response `200`

```json
{
  "organization_id": "550e8400-e29b-41d4-a716-446655440000",
  "connections": [
    {
      "id": 1,
      "from_entity_type": "organization",
      "from_entity_id": "550e8400-e29b-41d4-a716-446655440000",
      "from_label": "City Council",
      "to_entity_type": "person",
      "to_entity_id": "660e8400-e29b-41d4-a716-446655440001",
      "to_label": "Jane Doe",
      "nature": "employs"
    }
  ]
}
```

---

## GET `/public/v1/projects/{project_slug}/locations`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/locations/list_search.py`](../../../apps/core-api/src/core_api/routers/public/locations/list_search.py) |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/locations.py`](../../../packages/backfield-entities/src/backfield_entities/public/locations.py) |
| **Auth** | Project API key required |

List active canonical locations. Response items include `geometry_json`, `geometry_type`, and native H3 metadata (`h3_cell`, `h3_resolution`) when stored on the canonical.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `q` | string | — | Case-insensitive match on label or formatted address |
| `location_type` | string | — | Exact location type filter |
| `nature` | string | — | Locations with at least one linked mention of this nature in the project |
| `min_mentions` | integer | `0` | Minimum project mention count |
| `sort` | string | `label` | `label` or `recent` |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

---

## GET `/public/v1/projects/{project_slug}/locations/search`

Same parameters and response as `GET …/locations`.

---

## GET `/public/v1/projects/{project_slug}/locations/geo-search`

| | |
|---|---|
| **Status** | Shipped (Phase 4) |
| **Module** | [`apps/core-api/src/core_api/routers/public/locations/geo_search.py`](../../../apps/core-api/src/core_api/routers/public/locations/geo_search.py) |
| **Query layer** | [`packages/backfield-entities/src/backfield_entities/public/location_geo_search.py`](../../../packages/backfield-entities/src/backfield_entities/public/location_geo_search.py) |
| **Auth** | Project API key required |

Find canonical locations whose **Stylebook geometry** intersects a search area. Requires canonical rows with stored geometry.

### Query parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `center_lng`, `center_lat`, `radius_miles` | number | — | Point + radius mode (miles) |
| `bbox` | string | — | Bounding box `min_lng,min_lat,max_lng,max_lat` (alternative to point mode) |
| `q` | string | — | Optional label or address filter |
| `location_type` | string | — | Exact location type filter |
| `nature` | string | — | Mention nature filter |
| `min_mentions` | integer | `0` | Minimum project mention count |
| `limit` | integer | `25` | Page size (1–100) |
| `offset` | integer | `0` | Offset for pagination |

Point mode results are ordered by distance from the center. Provide either point+radius **or** bbox, not both.

### Response `200`

```json
{
  "search_mode": "point",
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "slug": "city-hall",
      "label": "City Hall",
      "location_type": "place",
      "formatted_address": "123 Main St",
      "geometry_type": "Point",
      "geometry_json": { "type": "Point", "coordinates": [-87.6, 41.8] },
      "h3_cell": "872664c1bffffff",
      "h3_resolution": 11,
      "mention_count": 3
    }
  ],
  "pagination": { "limit": 25, "offset": 0, "total": 1 }
}
```

---

## GET `/public/v1/projects/{project_slug}/locations/types`

Distinct location type values for filter dropdowns.

---

## GET `/public/v1/projects/{project_slug}/locations/{location_id}`

Single location object (same fields as list items).

---

## GET `/public/v1/projects/{project_slug}/locations/{location_id}/mentions`

Paginated mention evidence for one canonical location in the project. Supports `sort` (`created_at` or `article`) and `sort_direction`.

---

## GET `/public/v1/projects/{project_slug}/locations/{location_id}/connections`

Stylebook connections where the location is either endpoint, with resolved labels.
