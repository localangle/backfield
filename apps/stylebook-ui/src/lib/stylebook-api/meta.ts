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

export interface PersonMetaItem {
  id: number
  meta_type: string
  data: unknown
  created_at?: string
}

export interface PersonMetaListResponse {
  person_id: string
  meta: PersonMetaItem[]
  count: number
}

export async function getStylebookCanonicalPersonMeta(
  stylebookSlug: string,
  canonicalId: string,
): Promise<PersonMetaListResponse> {
  return stylebookJsonFetch<PersonMetaListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(canonicalId)}/meta`,
  )
}

export async function createStylebookCanonicalPersonMeta(
  stylebookSlug: string,
  canonicalId: string,
  body: { meta_type: string; data: unknown },
): Promise<PersonMetaItem> {
  return stylebookJsonFetch<PersonMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(canonicalId)}/meta`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookCanonicalPersonMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
  body: { data: unknown; meta_type?: string },
): Promise<PersonMetaItem> {
  return stylebookJsonFetch<PersonMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(canonicalId)}/meta/${metaId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteStylebookCanonicalPersonMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
): Promise<{ message: string }> {
  return stylebookJsonFetch<{ message: string }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(canonicalId)}/meta/${metaId}`,
    { method: "DELETE" },
  )
}
