/**
 * Stylebook service (org catalog admin). Same session cookie as Core; base defaults to
 * `/api/stylebook` (Vite proxy to stylebook-api).
 */

const stylebookBase = () => import.meta.env.VITE_STYLEBOOK_API_BASE ?? "/api/stylebook"

function formatDetail(detail: unknown): string {
  if (detail == null) return ""
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg?: unknown }).msg ?? "")
        }
        try {
          return JSON.stringify(item)
        } catch {
          return String(item)
        }
      })
      .filter((s) => s.length > 0)
      .join("; ")
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail)
    } catch {
      return String(detail)
    }
  }
  return String(detail)
}

async function stylebookJsonFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(`${stylebookBase()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })
  if (!r.ok) {
    let msg = r.statusText
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (body.detail !== undefined) {
        const f = formatDetail(body.detail)
        if (f) msg = f
      }
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  if (r.status === 204) {
    return undefined as T
  }
  return (await r.json()) as Promise<T>
}

export interface StylebookCatalogRow {
  id: number
  organization_id: number
  name: string
  slug: string
  is_default: boolean
  created_at: string
  updated_at: string
}

export async function listStylebookCatalogs(
  orgId: number,
): Promise<StylebookCatalogRow[]> {
  return stylebookJsonFetch<StylebookCatalogRow[]>(
    `/v1/organizations/${orgId}/stylebooks`,
  )
}

export async function createStylebookCatalog(
  orgId: number,
  body: { name: string; is_default: boolean },
): Promise<StylebookCatalogRow> {
  return stylebookJsonFetch<StylebookCatalogRow>(
    `/v1/organizations/${orgId}/stylebooks`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function renameStylebookCatalog(
  orgId: number,
  catalogId: number,
  body: { name: string },
): Promise<StylebookCatalogRow> {
  return stylebookJsonFetch<StylebookCatalogRow>(
    `/v1/organizations/${orgId}/stylebooks/${catalogId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function setDefaultStylebookCatalog(
  orgId: number,
  catalogId: number,
): Promise<StylebookCatalogRow> {
  return stylebookJsonFetch<StylebookCatalogRow>(
    `/v1/organizations/${orgId}/stylebooks/${catalogId}/set-default`,
    { method: "POST" },
  )
}

export interface CatalogDeletePreview {
  stylebook_id: number
  name: string
  is_default: boolean
  is_only_stylebook_in_org: boolean
  graphs_referencing: number
  nodes_referencing: number
}

export async function getStylebookCatalogDeletePreview(
  orgId: number,
  catalogId: number,
): Promise<CatalogDeletePreview> {
  return stylebookJsonFetch<CatalogDeletePreview>(
    `/v1/organizations/${orgId}/stylebooks/${catalogId}/delete-preview`,
  )
}

export async function deleteStylebookCatalog(
  orgId: number,
  catalogId: number,
  body: { confirm_name: string; replacement_default_id?: number | null },
): Promise<void> {
  await stylebookJsonFetch<void>(
    `/v1/organizations/${orgId}/stylebooks/${catalogId}/delete`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

/** Org-admin only: explicit editors who may mutate canonicals / imports in this stylebook. */
export interface StylebookEditorMember {
  user_id: number
  email: string
  role: string
  created_at: string
}

export async function listStylebookEditors(
  orgId: number,
  stylebookId: number,
): Promise<StylebookEditorMember[]> {
  return stylebookJsonFetch<StylebookEditorMember[]>(
    `/v1/organizations/${orgId}/stylebooks/${stylebookId}/members`,
  )
}

export async function addStylebookEditor(
  orgId: number,
  stylebookId: number,
  body: { email: string },
): Promise<StylebookEditorMember[]> {
  return stylebookJsonFetch<StylebookEditorMember[]>(
    `/v1/organizations/${orgId}/stylebooks/${stylebookId}/members`,
    { method: "POST", body: JSON.stringify({ email: body.email.trim(), role: "editor" }) },
  )
}

export async function removeStylebookEditor(
  orgId: number,
  stylebookId: number,
  userId: number,
): Promise<void> {
  await stylebookJsonFetch<void>(
    `/v1/organizations/${orgId}/stylebooks/${stylebookId}/members/${userId}`,
    { method: "DELETE" },
  )
}

/** Async full-catalog ZIP export/import job (org admin). */
export interface StylebookBundleJobRow {
  id: string
  organization_id: number
  kind: string
  status: string
  source_stylebook_id: number | null
  result_stylebook_id: number | null
  s3_bucket: string | null
  s3_key: string | null
  download_url: string | null
  upload_url: string | null
  progress_json: Record<string, unknown> | unknown[] | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface StylebookBundleManifestPreview {
  schema_version: number | null
  source_stylebook?: { id?: number; name?: string; slug?: string }
  project_slices: Array<{
    project_id: number
    project_slug: string
    meta_row_count: number
    connection_row_count: number
  }>
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

export async function createBundleExportJob(
  orgId: number,
  stylebookId: number,
): Promise<StylebookBundleJobRow> {
  return stylebookJsonFetch<StylebookBundleJobRow>(
    `/v1/organizations/${orgId}/stylebooks/${stylebookId}/bundle-export-jobs`,
    { method: "POST" },
  )
}

export async function getBundleJob(
  orgId: number,
  jobId: string,
): Promise<StylebookBundleJobRow> {
  return stylebookJsonFetch<StylebookBundleJobRow>(
    `/v1/organizations/${orgId}/stylebook-bundle-jobs/${encodeURIComponent(jobId)}`,
  )
}

export async function pollBundleJob(
  orgId: number,
  jobId: string,
  opts?: { intervalMs?: number; maxAttempts?: number },
): Promise<StylebookBundleJobRow> {
  const intervalMs = opts?.intervalMs ?? 2000
  const maxAttempts = opts?.maxAttempts ?? 300
  for (let i = 0; i < maxAttempts; i++) {
    const job = await getBundleJob(orgId, jobId)
    if (job.status === "succeeded" || job.status === "failed") return job
    await sleep(intervalMs)
  }
  throw new Error(
    "This is taking longer than expected. Refresh the page and check again in a moment.",
  )
}

export async function previewBundleManifest(
  orgId: number,
  file: File,
): Promise<StylebookBundleManifestPreview> {
  const form = new FormData()
  form.append("bundle", file)
  const r = await fetch(
    `${stylebookBase()}/v1/organizations/${orgId}/stylebook-bundles/manifest-preview`,
    { method: "POST", credentials: "include", body: form },
  )
  if (!r.ok) {
    let msg = r.statusText
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (body.detail !== undefined) {
        const f = formatDetail(body.detail)
        if (f) msg = f
      }
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return (await r.json()) as StylebookBundleManifestPreview
}

export async function createBundleImportJob(
  orgId: number,
  body: { new_stylebook_name: string; project_mappings: Record<string, number> },
): Promise<StylebookBundleJobRow> {
  return stylebookJsonFetch<StylebookBundleJobRow>(
    `/v1/organizations/${orgId}/stylebook-bundle-import-jobs`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function finalizeBundleImportJob(
  orgId: number,
  jobId: string,
): Promise<StylebookBundleJobRow> {
  return stylebookJsonFetch<StylebookBundleJobRow>(
    `/v1/organizations/${orgId}/stylebook-bundle-jobs/${encodeURIComponent(jobId)}/finalize`,
    { method: "POST" },
  )
}

/** Upload ZIP through stylebook-api (same origin) so the browser does not hit S3 CORS. */
export async function uploadBundleZipViaApi(
  orgId: number,
  jobId: string,
  file: File,
): Promise<void> {
  const form = new FormData()
  form.append("bundle", file)
  const r = await fetch(
    `${stylebookBase()}/v1/organizations/${orgId}/stylebook-bundle-jobs/${encodeURIComponent(jobId)}/upload`,
    { method: "POST", credentials: "include", body: form },
  )
  if (!r.ok) {
    let msg = r.statusText
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (body.detail !== undefined) {
        const f = formatDetail(body.detail)
        if (f) msg = f
      }
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
}
