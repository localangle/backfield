import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface Candidate {
  id: number
  project_id: number
  suggested_name?: string
  suggested_type?: string
  status: string
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
  limit?: number
  offset?: number
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
