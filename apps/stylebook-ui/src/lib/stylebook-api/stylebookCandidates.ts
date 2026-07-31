import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export type CandidateEntityType = "locations" | "people" | "organizations"

export type CandidateProjectCount = {
  project_id: number
  project_slug: string
  project_name: string
  count: number
}

export type CandidateCountResponse = {
  total: number
  projects: CandidateProjectCount[]
}

export function candidateProjectFilterState(
  projectSlug: string,
  projects: CandidateProjectCount[],
): { value: string; visible: boolean } {
  return {
    value: projectSlug || "all",
    visible:
      projectSlug.trim().length > 0 ||
      projects.filter((project) => project.count > 0).length > 1,
  }
}

export function candidateProjectOptions(
  projectSlug: string,
  projects: CandidateProjectCount[],
): CandidateProjectCount[] {
  return projects.filter(
    (project) => project.count > 0 || project.project_slug === projectSlug,
  )
}

export function canStartCandidateAiReview(projectSlug: string): boolean {
  return projectSlug.trim().length > 0
}

export type StylebookCandidateFilters = {
  project_slug?: string
  type_filter?: string
  q?: string
  limit?: number
  offset?: number
  needs_review?: boolean
}

function candidateParams(
  status: string,
  filters?: StylebookCandidateFilters,
): URLSearchParams {
  const params = new URLSearchParams({ status })
  if (!filters) return params
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value))
  }
  return params
}

export async function listStylebookCandidates<TCandidate>(
  stylebookSlug: string,
  entityType: CandidateEntityType,
  status: string,
  filters?: StylebookCandidateFilters,
): Promise<{ candidates: TCandidate[]; total: number; has_next: boolean; has_prev: boolean }> {
  const params = candidateParams(status, filters)
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/candidates/${entityType}?${params}`,
  )
}

export async function countStylebookCandidates(
  stylebookSlug: string,
  entityType: CandidateEntityType,
  status: string,
  filters?: StylebookCandidateFilters,
): Promise<CandidateCountResponse> {
  const params = candidateParams(status, filters)
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/candidates/${entityType}/count?${params}`,
  )
}

export async function listStylebookCandidateTypes(
  stylebookSlug: string,
  entityType: CandidateEntityType,
  projectSlug: string | undefined,
  status: string,
): Promise<{ types: string[] }> {
  const params = candidateParams(status, { project_slug: projectSlug })
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/candidates/${entityType}/types?${params}`,
  )
}
