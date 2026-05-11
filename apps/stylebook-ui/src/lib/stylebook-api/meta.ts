import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface LocationMetaItem {
  id: number
  meta_type: string
  data: unknown
  created_at?: string
}

export interface LocationMetaListResponse {
  location_id: string
  meta: LocationMetaItem[]
  count: number
}

export async function getCanonicalLocationMeta(
  canonicalId: string,
  projectSlug: string,
): Promise<LocationMetaListResponse> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<LocationMetaListResponse>(
    `/v1/canonical-locations/${encodeURIComponent(canonicalId)}/meta?${q}`,
  )
}

export async function createCanonicalLocationMeta(
  canonicalId: string,
  projectSlug: string,
  body: { meta_type: string; data: unknown },
): Promise<LocationMetaItem> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<LocationMetaItem>(
    `/v1/canonical-locations/${encodeURIComponent(canonicalId)}/meta?${q}`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateCanonicalLocationMeta(
  canonicalId: string,
  metaId: number,
  projectSlug: string,
  body: { data: unknown; meta_type?: string },
): Promise<LocationMetaItem> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<LocationMetaItem>(
    `/v1/canonical-locations/${encodeURIComponent(canonicalId)}/meta/${metaId}?${q}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteCanonicalLocationMeta(
  canonicalId: string,
  metaId: number,
  projectSlug: string,
): Promise<{ message: string }> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/canonical-locations/${encodeURIComponent(canonicalId)}/meta/${metaId}?${q}`,
    { method: "DELETE" },
  )
}

export async function getStylebookCanonicalLocationMeta(
  stylebookSlug: string,
  canonicalId: string,
): Promise<LocationMetaListResponse> {
  return stylebookJsonFetch<LocationMetaListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(canonicalId)}/meta`,
  )
}

export async function createStylebookCanonicalLocationMeta(
  stylebookSlug: string,
  canonicalId: string,
  body: { meta_type: string; data: unknown },
): Promise<LocationMetaItem> {
  return stylebookJsonFetch<LocationMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(canonicalId)}/meta`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookCanonicalLocationMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
  body: { data: unknown; meta_type?: string },
): Promise<LocationMetaItem> {
  return stylebookJsonFetch<LocationMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(canonicalId)}/meta/${metaId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteStylebookCanonicalLocationMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
): Promise<{ message: string }> {
  return stylebookJsonFetch<{ message: string }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(canonicalId)}/meta/${metaId}`,
    { method: "DELETE" },
  )
}
