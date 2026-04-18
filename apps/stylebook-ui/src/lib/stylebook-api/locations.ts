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
  /** When set, this substrate row is linked to this Stylebook canonical id (catalog key). */
  stylebook_location_canonical_id?: number | null
}

/** One ``stylebook_location_canonical`` row (Stylebook catalog), not a substrate location. */
export interface CanonicalLocation {
  id: number
  label: string
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

export async function listCanonicalLocations(
  projectSlug: string,
  q?: string,
  limit: number = 25,
  offset: number = 0,
): Promise<PaginatedCanonicalLocationResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (q) params.append("q", q)
  params.append("limit", limit.toString())
  params.append("offset", offset.toString())
  return stylebookJsonFetch<PaginatedCanonicalLocationResponse>(`/v1/canonical-locations?${params}`)
}

export async function getCanonicalLocation(
  canonicalId: number,
  projectSlug: string,
): Promise<CanonicalLocation> {
  return stylebookJsonFetch<CanonicalLocation>(
    `/v1/canonical-locations/${canonicalId}?project_slug=${encodeURIComponent(projectSlug)}`,
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
    location_type: string
    formatted_address?: string
    geometry_json?: Record<string, unknown>
    status?: string
  },
): Promise<Location> {
  return stylebookJsonFetch<Location>(`/v1/locations?project_slug=${encodeURIComponent(projectSlug)}`, {
    method: "POST",
    body: JSON.stringify(data),
  })
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
  canonicalId: number,
  projectSlug: string,
  geometryJson: Record<string, unknown>,
): Promise<{ message: string; id: number }> {
  return stylebookJsonFetch<{ message: string; id: number }>(
    `/v1/canonical-locations/${canonicalId}/geometry?project_slug=${encodeURIComponent(projectSlug)}`,
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
  mention_id: number
  article_id: number
  article_headline?: string
  article_url?: string | null
  original_text?: string | null
  description?: string | null
}

export interface LocationMentionsResponse {
  canonical_location_id: number
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
  canonicalId: number,
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
    `/v1/canonical-locations/${canonicalId}/mentions?${params}`,
  )
}

export async function patchCanonicalLocation(
  canonicalId: number,
  projectSlug: string,
  data: { label?: string },
): Promise<CanonicalLocation> {
  return stylebookJsonFetch<CanonicalLocation>(
    `/v1/canonical-locations/${canonicalId}?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "PATCH", body: JSON.stringify(data) },
  )
}

export async function deleteCanonicalLocation(
  canonicalId: number,
  projectSlug: string,
): Promise<{ message: string; id: number; unlinked_substrate_count: number }> {
  return stylebookJsonFetch(
    `/v1/canonical-locations/${canonicalId}?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "DELETE" },
  )
}
