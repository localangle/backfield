# Public API — runs (automation)

Trigger Agate graph runs and poll status. Requires a project API key with the **`runs:trigger`** scope (service keys only; org-admin mint).

Design reference: [`../../PUBLIC_API.md`](../../PUBLIC_API.md) — Run trigger section.

| Field | Value |
|-------|--------|
| **Base path** | `/public/v1/projects/{project_slug}/runs` |
| **Auth** | `Authorization: Bearer bfk_…` with **`runs:trigger`** scope |
| **Graph gate** | Target graph must have **`public_run_enabled: true`** (toggle **Enable API runs** on the content-source node in Agate UI, or set via Agate API graph create/update) |

## POST `/public/v1/projects/{project_slug}/runs`

Start a run. Returns immediately with a run handle; poll **`GET …/runs/{run_id}`** for progress.

### Request body

```json
{
  "graph_id": "uuid-of-agate-graph",
  "inputs": {
    "article": { "text": "Body to process." }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `graph_id` | string | yes | Agate graph id (must belong to the project in the URL path) |
| `inputs` | object | no | Per-alias ingress overrides. Omitted → use saved graph ingress params (UI-equivalent). |

### Ingress aliases

Each ingress node gets a stable alias in its graph params: **`public_alias`** (string). The Agate UI sets this automatically from the node name when **Enable API runs** is on (for example **Text Input** → `text_input`). When `inputs` is provided, it must contain **exactly one** key matching that alias.

Supported ingress types (one per graph):

| Node type | `inputs[alias]` shape | Notes |
|-----------|----------------------|-------|
| **TextInput** | `{ "text": "<non-empty string>" }` | Replaces `params.text` |
| **JSONInput** | JSON object with a resolvable article body | Same keys as the node panel (`text`, `headline`, …); normalized like JSONInput at run time |
| **S3Input** | `{ "bucket"?, "prefix"?, "max_files"? }` | Merged over saved node params; `prefix` maps to `folder_path`; `max_files` capped server-side (max 10_000) |

At trigger time the API computes an **effective graph spec** (saved params ⊕ `inputs`) and pins it on the run. Text/JSON payloads become **`agate_processed_item.input_json`**; S3 location params are read from the pinned spec during batch setup.

### Response `200`

```json
{
  "run_id": "uuid",
  "status": "pending | running",
  "counts": {
    "total": 0,
    "pending": 0,
    "running": 0,
    "succeeded": 0,
    "failed": 0
  },
  "created_at": "2026-06-25T12:00:00Z",
  "updated_at": "2026-06-25T12:00:00Z",
  "error_message": null
}
```

Single-item runs typically return `status: "running"` with `counts.total: 1`. S3 batch runs start as `pending` with zero counts until batch setup creates items.

### Errors

| Status | When |
|--------|------|
| **400** | Invalid `inputs` (unknown alias, empty text, bad shape) |
| **403** | Missing `runs:trigger` scope; graph not `public_run_enabled` |
| **404** | Unknown `graph_id` or wrong project |

## GET `/public/v1/projects/{project_slug}/runs/{run_id}`

Poll run status and item counts. Does not return per-item bodies, AI costs, or review overlays.

### Response `200`

Same shape as POST response. `counts` reflect **`agate_processed_item`** row statuses when present.

### Errors

| Status | When |
|--------|------|
| **404** | Unknown run or run not belonging to this project |

## Out of scope (public API)

- Cancel, rerun, review overlay, per-item detail — Agate API `/runs` only
- Idempotency keys and rate limits — deferred
