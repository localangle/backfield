import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export type MetaValueType = "text" | "number" | "boolean"

export interface CanonicalMetaItem {
  id: number
  meta_type: string
  value_type: MetaValueType
  value: string | number | boolean
  created_at?: string
}

export interface CanonicalMetaWriteBody {
  meta_type: string
  value_type: MetaValueType
  value: string | number | boolean
}

export interface CanonicalMetaUpdateBody {
  meta_type?: string
  value_type: MetaValueType
  value: string | number | boolean
}

export interface LocationMetaListResponse {
  location_id: string
  meta: CanonicalMetaItem[]
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
  body: CanonicalMetaWriteBody,
): Promise<CanonicalMetaItem> {
  return stylebookJsonFetch<CanonicalMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(canonicalId)}/meta`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookCanonicalLocationMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
  body: CanonicalMetaUpdateBody,
): Promise<CanonicalMetaItem> {
  return stylebookJsonFetch<CanonicalMetaItem>(
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

export interface PersonMetaListResponse {
  person_id: string
  meta: CanonicalMetaItem[]
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
  body: CanonicalMetaWriteBody,
): Promise<CanonicalMetaItem> {
  return stylebookJsonFetch<CanonicalMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(canonicalId)}/meta`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookCanonicalPersonMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
  body: CanonicalMetaUpdateBody,
): Promise<CanonicalMetaItem> {
  return stylebookJsonFetch<CanonicalMetaItem>(
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

export interface OrganizationMetaListResponse {
  organization_id: string
  meta: CanonicalMetaItem[]
  count: number
}

export async function getStylebookCanonicalOrganizationMeta(
  stylebookSlug: string,
  canonicalId: string,
): Promise<OrganizationMetaListResponse> {
  return stylebookJsonFetch<OrganizationMetaListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(canonicalId)}/meta`,
  )
}

export async function createStylebookCanonicalOrganizationMeta(
  stylebookSlug: string,
  canonicalId: string,
  body: CanonicalMetaWriteBody,
): Promise<CanonicalMetaItem> {
  return stylebookJsonFetch<CanonicalMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(canonicalId)}/meta`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookCanonicalOrganizationMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
  body: CanonicalMetaUpdateBody,
): Promise<CanonicalMetaItem> {
  return stylebookJsonFetch<CanonicalMetaItem>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(canonicalId)}/meta/${metaId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteStylebookCanonicalOrganizationMeta(
  stylebookSlug: string,
  canonicalId: string,
  metaId: number,
): Promise<{ message: string }> {
  return stylebookJsonFetch<{ message: string }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(canonicalId)}/meta/${metaId}`,
    { method: "DELETE" },
  )
}
