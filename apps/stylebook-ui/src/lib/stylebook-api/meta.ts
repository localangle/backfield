import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface LocationMetaItem {
  id: number
  meta_type: string
  data: unknown
  created_at?: string
}

export interface LocationMetaListResponse {
  location_id: number
  meta: LocationMetaItem[]
  count: number
}

export async function getCanonicalLocationMeta(
  canonicalId: number,
  projectSlug: string,
): Promise<LocationMetaListResponse> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<LocationMetaListResponse>(
    `/v1/canonical-locations/${canonicalId}/meta?${q}`,
  )
}

export async function createCanonicalLocationMeta(
  canonicalId: number,
  projectSlug: string,
  body: { meta_type: string; data: unknown },
): Promise<LocationMetaItem> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<LocationMetaItem>(
    `/v1/canonical-locations/${canonicalId}/meta?${q}`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateCanonicalLocationMeta(
  canonicalId: number,
  metaId: number,
  projectSlug: string,
  body: { data: unknown; meta_type?: string },
): Promise<LocationMetaItem> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<LocationMetaItem>(
    `/v1/canonical-locations/${canonicalId}/meta/${metaId}?${q}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteCanonicalLocationMeta(
  canonicalId: number,
  metaId: number,
  projectSlug: string,
): Promise<{ message: string }> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/canonical-locations/${canonicalId}/meta/${metaId}?${q}`,
    { method: "DELETE" },
  )
}
