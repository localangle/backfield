import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface OrganizationCanonicalSuggestion {
  suggested_action?: string | null
  stylebook_organization_canonical_id?: string | null
  source?: string | null
  adjudication_confidence?: number | null
  adjudication_rationale?: string | null
  adjudication_model?: string | null
  adjudication_outcome?: string | null
}

export interface OrganizationCandidate {
  id: number
  project_id: number
  suggested_name?: string
  suggested_type?: string | null
  created_at?: string | null
  note?: string | null
  status: string
  defer_display_message?: string | null
  /** Human-readable ingest/policy context (open and deferred queues). */
  canonical_review_lines?: string[] | null
  canonical_suggestion?: OrganizationCanonicalSuggestion | null
}

export interface PaginatedOrganizationCandidatesResponse {
  candidates: OrganizationCandidate[]
  total: number
  has_next: boolean
  has_prev: boolean
}

export type ListOrganizationCandidatesFilterOptions = {
  type_filter?: string
  q?: string
  limit?: number
  offset?: number
  needs_review?: boolean
  nature?: string
}

function organizationCandidatesFilterParams(
  options?: ListOrganizationCandidatesFilterOptions,
): URLSearchParams {
  const params = new URLSearchParams()
  if (!options) return params
  if (options.limit !== undefined) params.append("limit", String(options.limit))
  if (options.offset !== undefined) params.append("offset", String(options.offset))
  if (options.type_filter) params.append("type_filter", options.type_filter)
  if (options.q) params.append("q", options.q)
  if (options.needs_review === true) params.append("needs_review", "true")
  if (options.needs_review === false) params.append("needs_review", "false")
  if (options.nature) params.append("nature", options.nature)
  return params
}

export async function listOrganizationCandidates(
  projectSlug: string,
  status: string = "open",
  options?: ListOrganizationCandidatesFilterOptions,
): Promise<PaginatedOrganizationCandidatesResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug, status })
  organizationCandidatesFilterParams(options).forEach((v, k) => params.set(k, v))
  return stylebookJsonFetch<PaginatedOrganizationCandidatesResponse>(
    `/v1/organizations/candidates?${params}`,
  )
}

export async function listOrganizationCandidateTypes(
  projectSlug: string,
  status: string = "open",
): Promise<{ types: string[] }> {
  const params = new URLSearchParams({ project_slug: projectSlug, status })
  return stylebookJsonFetch(`/v1/organizations/candidates/types?${params}`)
}

export type AcceptOrganizationCandidateBody = {
  create_new: boolean
  stylebook_organization_canonical_id?: string | null
  name?: string | null
  organization_type?: string | null
}

export type AcceptOrganizationCandidateResponse = {
  message: string
  stylebook_organization_canonical_id?: string
}

export async function acceptOrganizationCandidate(
  projectSlug: string,
  substrateOrganizationId: number,
  body: AcceptOrganizationCandidateBody,
): Promise<AcceptOrganizationCandidateResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<AcceptOrganizationCandidateResponse>(
    `/v1/organizations/candidates/${substrateOrganizationId}/accept?${params}`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  )
}

export async function deferOrganizationCandidate(
  projectSlug: string,
  substrateOrganizationId: number,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/organizations/candidates/${substrateOrganizationId}/defer?${params}`,
    { method: "POST" },
  )
}

export async function clearOrganizationCandidateRecommendation(
  projectSlug: string,
  substrateOrganizationId: number,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/organizations/candidates/${substrateOrganizationId}/clear-recommendation?${params}`,
    { method: "POST" },
  )
}

export interface OrganizationCandidateContextItem {
  article_id: number
  article_headline?: string | null
  article_url?: string | null
  text: string
}

export interface OrganizationCandidateContextResponse {
  substrate_organization_id: number
  created_at?: string | null
  note?: string | null
  examples: OrganizationCandidateContextItem[]
}

export async function getOrganizationCandidateContext(
  projectSlug: string,
  substrateOrganizationId: number,
  limit: number = 3,
): Promise<OrganizationCandidateContextResponse> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: String(limit),
  })
  return stylebookJsonFetch<OrganizationCandidateContextResponse>(
    `/v1/organizations/candidates/${substrateOrganizationId}/context?${params}`,
  )
}

export async function updateOrganizationCandidateNote(
  projectSlug: string,
  substrateOrganizationId: number,
  note: string | null,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/organizations/candidates/${substrateOrganizationId}/note?${params}`,
    { method: "POST", body: JSON.stringify({ note }) },
  )
}

export interface SuggestedOrganizationCanonicalItem {
  canonical_id: string
  label: string
  organization_type?: string | null
}

export interface SuggestedOrganizationCanonicalsResponse {
  suggestions: SuggestedOrganizationCanonicalItem[]
}

export async function getSuggestedOrganizationCanonicals(
  projectSlug: string,
  substrateOrganizationId: number,
  limit: number = 24,
): Promise<SuggestedOrganizationCanonicalsResponse> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: String(limit),
  })
  return stylebookJsonFetch<SuggestedOrganizationCanonicalsResponse>(
    `/v1/organizations/candidates/${substrateOrganizationId}/suggested-canonicals?${params}`,
  )
}
