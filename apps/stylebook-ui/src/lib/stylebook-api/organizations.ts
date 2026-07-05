import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

/** One ``stylebook_organization_canonical`` row (Stylebook catalog), not a substrate organization. */
export interface CanonicalOrganization {
  id: string
  slug: string
  label: string
  organization_type?: string | null
  status: string
  linked_substrate_count: number
  mention_count: number
  created_at: string
  updated_at: string
}

export interface Organization {
  id: number
  project_id: number
  name: string
  organization_type?: string | null
  status: string
  created_by_user_id?: number
  created_at: string
  updated_at: string
  mention_count?: number
  canonical_link_status?: string
  canonical_review_reasons_json?: unknown
  /** When set, this substrate row is linked to this Stylebook canonical id (catalog UUID string). */
  stylebook_organization_canonical_id?: string | null
}

export interface PaginatedCanonicalOrganizationResponse {
  canonicals: CanonicalOrganization[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export type CanonicalOrganizationListSort = "label" | "recent"

export type CanonicalOrganizationListFilters = {
  minMentions?: number
  sort?: CanonicalOrganizationListSort
  /** Editorial mention nature filter when supported by the API. */
  nature?: string
}

export async function listCanonicalOrganizations(
  stylebookSlug: string,
  q?: string,
  limit: number = 25,
  offset: number = 0,
  typeFilter?: string,
  projectFilterSlug?: string,
  options?: CanonicalOrganizationListFilters,
): Promise<PaginatedCanonicalOrganizationResponse> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.append("project", projectFilterSlug)
  if (q) params.append("q", q)
  if (typeFilter && typeFilter !== "all") params.append("type_filter", typeFilter)
  const minMentions = options?.minMentions ?? 0
  if (minMentions > 0) params.append("min_mentions", String(minMentions))
  const sort = options?.sort ?? "label"
  if (sort !== "label") params.append("sort", sort)
  if (options?.nature && options.nature !== "all") params.append("nature", options.nature)
  params.append("limit", limit.toString())
  params.append("offset", offset.toString())
  return stylebookJsonFetch<PaginatedCanonicalOrganizationResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations?${params}`,
  )
}

export async function listCanonicalOrganizationTypes(
  stylebookSlug: string,
): Promise<{ types: string[] }> {
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/types`,
  )
}

export async function getCanonicalOrganization(
  canonicalId: string,
  stylebookSlug: string,
  projectFilterSlug?: string,
): Promise<CanonicalOrganization> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalOrganization>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(canonicalId)}?${params}`,
  )
}

export interface LinkedOrganizationSubstrateItem {
  id: number
  name: string
  normalized_name: string
  mention_count?: number
  organization_type?: string | null
  canonical_link_status: string
  project_id: number
  project_slug: string
  project_name: string
}

export interface LinkedOrganizationSubstratesResponse {
  substrates: LinkedOrganizationSubstrateItem[]
}

export async function listCanonicalLinkedOrganizationSubstrates(
  canonicalId: string,
  stylebookSlug: string,
  projectFilterSlug?: string,
): Promise<LinkedOrganizationSubstratesResponse> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<LinkedOrganizationSubstratesResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(
      canonicalId,
    )}/linked-substrates?${params}`,
  )
}

export interface LinkedOrganizationMention {
  substrate_organization_id: number
  mention_id: number
  article_id: number
  article_headline?: string | null
  article_url?: string | null
  original_text?: string | null
  mention_nature?: string | null
  description?: string | null
  organization_name?: string | null
  organization_type?: string | null
  created_at?: string | null
}

export interface OrganizationMentionsResponse {
  canonical_organization_id: string
  canonical_name: string
  mentions: LinkedOrganizationMention[]
  total: number
  limit: number
  offset: number
}

export async function getCanonicalOrganizationMentions(
  canonicalId: string,
  stylebookSlug: string,
  limit: number = 50,
  offset: number = 0,
  _sort?: string,
  sortDirection: "asc" | "desc" = "desc",
  projectFilterSlug?: string,
): Promise<OrganizationMentionsResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
    sort_direction: sortDirection,
  })
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<OrganizationMentionsResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(
      canonicalId,
    )}/mentions?${params}`,
  )
}

export async function unlinkOrganizationSubstrateFromCanonical(
  substrateOrganizationId: number,
  projectSlug: string,
): Promise<{ message: string }> {
  return stylebookJsonFetch<{ message: string }>(
    `/v1/organizations/${substrateOrganizationId}/unlink-canonical?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "POST" },
  )
}

export async function linkOrganizationSubstrateToCanonical(
  substrateOrganizationId: number,
  projectSlug: string,
  stylebookOrganizationCanonicalId: string,
): Promise<{ changed: boolean }> {
  return stylebookJsonFetch<{ changed: boolean }>(
    `/v1/organizations/${substrateOrganizationId}/link-canonical?project_slug=${encodeURIComponent(projectSlug)}`,
    {
      method: "POST",
      body: JSON.stringify({
        stylebook_organization_canonical_id: stylebookOrganizationCanonicalId,
      }),
    },
  )
}

export async function getOrganization(
  organizationId: number,
  projectSlug: string,
): Promise<Organization> {
  return stylebookJsonFetch<Organization>(
    `/v1/organizations/${organizationId}?project_slug=${encodeURIComponent(projectSlug)}`,
  )
}

export async function createCanonicalOrganization(
  stylebookSlug: string,
  data: {
    label: string
    organization_type?: string | null
  },
  projectFilterSlug?: string,
): Promise<CanonicalOrganization> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalOrganization>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations?${params}`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  )
}

export async function patchCanonicalOrganization(
  canonicalId: string,
  stylebookSlug: string,
  data: {
    label?: string
    organization_type?: string | null
  },
  projectFilterSlug?: string,
): Promise<CanonicalOrganization> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalOrganization>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(
      canonicalId,
    )}?${params}`,
    { method: "PATCH", body: JSON.stringify(data) },
  )
}

export async function deleteCanonicalOrganization(
  canonicalId: string,
  stylebookSlug: string,
): Promise<{ message: string; id: string; unlinked_substrate_count: number }> {
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(
      canonicalId,
    )}`,
    { method: "DELETE" },
  )
}
