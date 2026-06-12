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

<!-- Add new endpoints below in the same section format. -->
