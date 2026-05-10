import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface Location {
  id: number
  project_id: number
  name: string
  location_type: string
  formatted_address?: string
  geometry_json?: Record<string, unknown>
  geometry_type?: string
  status: string
  created_by_user_id?: number
  created_at: string
  updated_at: string
  mention_count?: number
  canonical_link_status?: string
  canonical_review_reasons_json?: unknown
  /** When set, this substrate row is linked to this Stylebook canonical id (catalog UUID string). */
  stylebook_location_canonical_id?: string | null
}

/** One ``stylebook_location_canonical`` row (Stylebook catalog), not a substrate location. */
export interface CanonicalLocation {
  id: string
  slug: string
  label: string
  location_type?: string | null
  formatted_address?: string | null
  geometry_json?: Record<string, unknown> | null
  geometry_type?: string | null
  status: string
  linked_substrate_count: number
  mention_count: number
  created_at: string
  updated_at: string
}

export interface PaginatedCanonicalLocationResponse {
  canonicals: CanonicalLocation[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export interface PaginatedLocationResponse {
  locations: Location[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export const LOCATION_TYPES = [
  "address",
  "area",
  "city",
  "community_area",
  "county",
  "district",
  "intersection_highway",
  "intersection_road",
  "natural",
  "neighborhood",
  "place",
  "point",
  "region_city",
  "region_state",
  "state",
  "street_road",
  "town",
] as const

export async function listLocations(
  projectSlug: string,
  q?: string,
  status?: string,
  typeFilter?: string,
  limit: number = 25,
  offset: number = 0,
): Promise<PaginatedLocationResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (q) params.append("q", q)
  if (status) params.append("status", status)
  if (typeFilter && typeFilter !== "all") params.append("type_filter", typeFilter)
  params.append("limit", limit.toString())
  params.append("offset", offset.toString())
  return stylebookJsonFetch<PaginatedLocationResponse>(`/v1/locations?${params}`)
}

export type CanonicalListSort = "label" | "recent"

export async function listCanonicalLocations(
  stylebookSlug: string,
  q?: string,
  limit: number = 25,
  offset: number = 0,
  typeFilter?: string,
  projectFilterSlug?: string,
  options?: { minMentions?: number; sort?: CanonicalListSort },
): Promise<PaginatedCanonicalLocationResponse> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.append("project", projectFilterSlug)
  if (q) params.append("q", q)
  if (typeFilter && typeFilter !== "all") params.append("type_filter", typeFilter)
  const minMentions = options?.minMentions ?? 0
  if (minMentions > 0) params.append("min_mentions", String(minMentions))
  const sort = options?.sort ?? "label"
  if (sort !== "label") params.append("sort", sort)
  params.append("limit", limit.toString())
  params.append("offset", offset.toString())
  return stylebookJsonFetch<PaginatedCanonicalLocationResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations?${params}`,
  )
}

/** Legacy project-scoped canonical list (kept for project workflows like linking). */
export async function listCanonicalLocationsLegacy(
  projectSlug: string,
  q?: string,
  limit: number = 25,
  offset: number = 0,
  typeFilter?: string,
): Promise<PaginatedCanonicalLocationResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (q) params.append("q", q)
  if (typeFilter && typeFilter !== "all") params.append("type_filter", typeFilter)
  params.append("limit", limit.toString())
  params.append("offset", offset.toString())
  return stylebookJsonFetch<PaginatedCanonicalLocationResponse>(`/v1/canonical-locations?${params}`)
}

export async function listCanonicalLocationTypes(stylebookSlug: string): Promise<{ types: string[] }> {
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/types`,
  )
}

export async function getCanonicalLocation(
  canonicalId: string,
  stylebookSlug: string,
  projectFilterSlug?: string,
): Promise<CanonicalLocation> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalLocation>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(canonicalId)}?${params}`,
  )
}

/** Legacy project-scoped canonical detail (kept for project workflows like linking). */
export async function getCanonicalLocationLegacy(
  canonicalId: string,
  projectSlug: string,
): Promise<CanonicalLocation> {
  return stylebookJsonFetch<CanonicalLocation>(
    `/v1/canonical-locations/${encodeURIComponent(canonicalId)}?project_slug=${encodeURIComponent(projectSlug)}`,
  )
}

export interface LinkedSubstrateItem {
  id: number
  name: string
  normalized_name: string
  location_type: string
  canonical_link_status: string
  formatted_address?: string | null
}

export interface LinkedSubstratesResponse {
  substrates: LinkedSubstrateItem[]
}

export async function listCanonicalLinkedSubstrates(
  canonicalId: string,
  stylebookSlug: string,
  projectFilterSlug?: string,
): Promise<LinkedSubstratesResponse> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<LinkedSubstratesResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(
      canonicalId,
    )}/linked-substrates?${params}`,
  )
}

export async function unlinkSubstrateFromCanonical(
  substrateLocationId: number,
  projectSlug: string,
): Promise<{ message: string }> {
  return stylebookJsonFetch<{ message: string }>(
    `/v1/locations/${substrateLocationId}/unlink-canonical?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "POST" },
  )
}

export async function linkSubstrateToCanonical(
  substrateLocationId: number,
  projectSlug: string,
  stylebookLocationCanonicalId: string,
): Promise<{ changed: boolean }> {
  return stylebookJsonFetch<{ changed: boolean }>(
    `/v1/locations/${substrateLocationId}/link-canonical?project_slug=${encodeURIComponent(projectSlug)}`,
    {
      method: "POST",
      body: JSON.stringify({ stylebook_location_canonical_id: stylebookLocationCanonicalId }),
    },
  )
}

export async function listLocationOptions(
  projectSlug: string,
  q?: string,
  status: string = "active",
  limit: number = 100,
  offset: number = 0,
): Promise<{ locations: Array<{ id: number; name: string; location_type: string }> }> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    status,
    limit: limit.toString(),
    offset: offset.toString(),
  })
  if (q) params.append("q", q)
  return stylebookJsonFetch(`/v1/locations/options?${params}`)
}

export async function getLocation(locationId: number, projectSlug: string): Promise<Location> {
  return stylebookJsonFetch<Location>(`/v1/locations/${locationId}?project_slug=${encodeURIComponent(projectSlug)}`)
}

export async function createLocation(
  projectSlug: string,
  data: {
    name: string
    location_type?: string
    formatted_address?: string
    geometry_json?: Record<string, unknown>
    status?: string
  },
): Promise<CanonicalLocation> {
  return stylebookJsonFetch<CanonicalLocation>(
    `/v1/locations?project_slug=${encodeURIComponent(projectSlug)}`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  )
}

/** Create a catalog canonical only (no project substrate row). Prefer over legacy ``createLocation``. */
export async function createCanonicalLocation(
  stylebookSlug: string,
  data: {
    label: string
    location_type?: string | null
    formatted_address?: string | null
    geometry_json?: Record<string, unknown>
  },
  projectFilterSlug?: string,
): Promise<CanonicalLocation> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalLocation>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations?${params}`,
    {
      method: "POST",
      body: JSON.stringify({
        label: data.label,
        location_type: data.location_type,
        formatted_address: data.formatted_address,
        geometry_json: data.geometry_json,
      }),
    },
  )
}

export async function updateLocation(
  locationId: number,
  projectSlug: string,
  data: {
    name?: string
    location_type?: string
    formatted_address?: string
    status?: string
  },
): Promise<Location> {
  return stylebookJsonFetch<Location>(
    `/v1/locations/${locationId}?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "PATCH", body: JSON.stringify(data) },
  )
}

export async function updateLocationGeometry(
  locationId: number,
  projectSlug: string,
  geometryJson: Record<string, unknown>,
): Promise<Location> {
  return stylebookJsonFetch<Location>(
    `/v1/locations/${locationId}/geometry?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "PATCH", body: JSON.stringify({ geometry_json: geometryJson }) },
  )
}

export async function updateCanonicalLocationGeometry(
  canonicalId: string,
  stylebookSlug: string,
  geometryJson: Record<string, unknown> | null,
): Promise<{ message: string; id: string }> {
  return stylebookJsonFetch<{ message: string; id: string }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(
      canonicalId,
    )}/geometry`,
    { method: "PATCH", body: JSON.stringify({ geometry_json: geometryJson }) },
  )
}

export async function deleteLocation(
  locationId: number,
  projectSlug: string,
): Promise<{ message: string; candidates_created: number; links_deactivated: number }> {
  return stylebookJsonFetch(
    `/v1/locations/${locationId}?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "DELETE" },
  )
}

export interface LinkedMention {
  substrate_location_id: number
  mention_id: number
  article_id: number
  article_headline?: string
  article_url?: string | null
  original_text?: string | null
  /** PlaceExtract editorial ``nature`` (primary, secondary, …) persisted on the mention. */
  mention_nature?: string | null
  description?: string | null
  location_name?: string | null
  location_type?: string | null
  formatted_address?: string | null
  geometry_type?: string | null
  geometry_json?: Record<string, unknown> | null
  has_geometry?: boolean | null
  created_at?: string | null
  link_location_mention_id?: number | null
}

export interface LocationMentionsResponse {
  canonical_location_id: string
  canonical_name: string
  mentions: LinkedMention[]
  total: number
  limit: number
  offset: number
}

export async function getLocationMentions(
  locationId: number,
  projectSlug: string,
  limit: number = 50,
  offset: number = 0,
  _sort?: string,
  sortDirection: "asc" | "desc" = "desc",
): Promise<LocationMentionsResponse> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: limit.toString(),
    offset: offset.toString(),
    sort_direction: sortDirection,
  })
  return stylebookJsonFetch<LocationMentionsResponse>(
    `/v1/locations/${locationId}/mentions?${params}`,
  )
}

export async function getCanonicalLocationMentions(
  canonicalId: string,
  stylebookSlug: string,
  limit: number = 50,
  offset: number = 0,
  _sort?: string,
  sortDirection: "asc" | "desc" = "desc",
  projectFilterSlug?: string,
): Promise<LocationMentionsResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
    sort_direction: sortDirection,
  })
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<LocationMentionsResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(
      canonicalId,
    )}/mentions?${params}`,
  )
}

export async function patchCanonicalLocation(
  canonicalId: string,
  stylebookSlug: string,
  data: { label?: string; location_type?: string | null; formatted_address?: string | null },
  projectFilterSlug?: string,
): Promise<CanonicalLocation> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalLocation>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(
      canonicalId,
    )}?${params}`,
    { method: "PATCH", body: JSON.stringify(data) },
  )
}

export async function deleteCanonicalLocation(
  canonicalId: string,
  stylebookSlug: string,
): Promise<{ message: string; id: string; unlinked_substrate_count: number }> {
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(
      canonicalId,
    )}`,
    { method: "DELETE" },
  )
}
