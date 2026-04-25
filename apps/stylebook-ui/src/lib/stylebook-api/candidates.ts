import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface CanonicalSuggestion {
  suggested_action?: string | null
  stylebook_location_canonical_id?: number | null
  source?: string | null
  adjudication_confidence?: number | null
  adjudication_rationale?: string | null
  adjudication_model?: string | null
  adjudication_outcome?: string | null
}

export interface Candidate {
  id: number
  project_id: number
  suggested_name?: string
  suggested_type?: string
  suggested_formatted_address?: string | null
  created_at?: string | null
  note?: string | null
  status: string
  /** Human-readable ingest/policy reason when present (e.g. deferred private residence). */
  defer_display_message?: string | null
  canonical_suggestion?: CanonicalSuggestion | null
}

export interface CandidateCluster {
  cluster_id: string
  representative_name: string
  candidates: Candidate[]
  count: number
}

export interface PaginatedClustersResponse {
  clusters: CandidateCluster[]
  total: number
  limit: number
  offset: number
  has_next: boolean
  has_prev: boolean
}

export interface PaginatedCandidatesResponse {
  candidates: Candidate[]
  total: number
  has_next: boolean
  has_prev: boolean
}

export type ListCandidatesFilterOptions = {
  type_filter?: string
  q?: string
  limit?: number
  offset?: number
  needs_review?: boolean
}

export type ListClustersOptions = ListCandidatesFilterOptions & {
  cluster_mode?: string
  cluster_threshold?: number
  cluster_by_type?: boolean
}

function candidatesFilterParams(options?: ListCandidatesFilterOptions): URLSearchParams {
  const params = new URLSearchParams()
  if (!options) return params
  if (options.limit !== undefined) params.append("limit", String(options.limit))
  if (options.offset !== undefined) params.append("offset", String(options.offset))
  if (options.type_filter) params.append("type_filter", options.type_filter)
  if (options.q) params.append("q", options.q)
  if (options.needs_review === true) params.append("needs_review", "true")
  if (options.needs_review === false) params.append("needs_review", "false")
  return params
}

export async function listClusters(
  projectSlug: string,
  status: string = "open",
  options?: ListClustersOptions,
): Promise<PaginatedClustersResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug, status })
  candidatesFilterParams(options).forEach((v, k) => params.set(k, v))
  if (options?.cluster_mode) params.set("cluster_mode", options.cluster_mode)
  if (options?.cluster_threshold !== undefined) {
    params.set("cluster_threshold", String(options.cluster_threshold))
  }
  if (options?.cluster_by_type) params.set("cluster_by_type", "true")
  return stylebookJsonFetch<PaginatedClustersResponse>(`/v1/candidates/clusters?${params}`)
}

export async function listCandidates(
  projectSlug: string,
  status: string = "open",
  _clusterUnused: boolean = false,
  options?: ListCandidatesFilterOptions,
): Promise<PaginatedCandidatesResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug, status })
  candidatesFilterParams(options).forEach((v, k) => params.set(k, v))
  return stylebookJsonFetch<PaginatedCandidatesResponse>(`/v1/candidates?${params}`)
}

export async function listLocationCandidateTypes(
  projectSlug: string,
  status: string = "open",
): Promise<{ types: string[] }> {
  const params = new URLSearchParams({ project_slug: projectSlug, status })
  return stylebookJsonFetch(`/v1/candidates/types?${params}`)
}

export type AcceptCandidateBody = {
  create_new: boolean
  stylebook_location_id?: number | null
  name?: string | null
  geometry_json?: Record<string, unknown> | null
}

export type AcceptCandidateResponse = {
  message: string
  stylebook_location_canonical_id?: number
}

export async function acceptCandidate(
  projectSlug: string,
  substrateLocationId: number,
  body: AcceptCandidateBody,
): Promise<AcceptCandidateResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<AcceptCandidateResponse>(
    `/v1/candidates/${substrateLocationId}/accept?${params}`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  )
}

export async function deferCandidate(
  projectSlug: string,
  substrateLocationId: number,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/candidates/${substrateLocationId}/defer?${params}`,
    { method: "POST" },
  )
}

export interface CandidateContextItem {
  article_id: number
  article_headline?: string | null
  article_url?: string | null
  text: string
}

export interface CandidateContextResponse {
  substrate_location_id: number
  created_at?: string | null
  note?: string | null
  examples: CandidateContextItem[]
}

export async function getCandidateContext(
  projectSlug: string,
  substrateLocationId: number,
  limit: number = 3,
): Promise<CandidateContextResponse> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: String(limit),
  })
  return stylebookJsonFetch<CandidateContextResponse>(
    `/v1/candidates/${substrateLocationId}/context?${params}`,
  )
}

export async function updateCandidateNote(
  projectSlug: string,
  substrateLocationId: number,
  note: string | null,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/candidates/${substrateLocationId}/note?${params}`,
    { method: "POST", body: JSON.stringify({ note }) },
  )
}

export interface SuggestedCanonicalItem {
  canonical_id: number
  label: string
}

export interface SuggestedCanonicalsResponse {
  suggestions: SuggestedCanonicalItem[]
}

export async function getSuggestedCanonicals(
  projectSlug: string,
  substrateLocationId: number,
  limit: number = 24,
): Promise<SuggestedCanonicalsResponse> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: String(limit),
  })
  return stylebookJsonFetch<SuggestedCanonicalsResponse>(
    `/v1/candidates/${substrateLocationId}/suggested-canonicals?${params}`,
  )
}
