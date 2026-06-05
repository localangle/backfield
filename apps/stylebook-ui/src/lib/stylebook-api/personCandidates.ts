import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface PersonCanonicalSuggestion {
  suggested_action?: string | null
  stylebook_person_canonical_id?: string | null
  source?: string | null
  adjudication_confidence?: number | null
  adjudication_rationale?: string | null
  adjudication_model?: string | null
  adjudication_outcome?: string | null
}

export interface PersonCandidate {
  id: number
  project_id: number
  suggested_name?: string
  suggested_title?: string | null
  suggested_affiliation?: string | null
  suggested_type?: string | null
  suggested_public_figure?: boolean | null
  created_at?: string | null
  note?: string | null
  status: string
  defer_display_message?: string | null
  /** Human-readable ingest/policy context (open and deferred queues). */
  canonical_review_lines?: string[] | null
  canonical_suggestion?: PersonCanonicalSuggestion | null
}

export interface PaginatedPersonCandidatesResponse {
  candidates: PersonCandidate[]
  total: number
  has_next: boolean
  has_prev: boolean
}

export type ListPersonCandidatesFilterOptions = {
  type_filter?: string
  q?: string
  limit?: number
  offset?: number
  needs_review?: boolean
  public_figure?: boolean
  nature?: string
}

function personCandidatesFilterParams(options?: ListPersonCandidatesFilterOptions): URLSearchParams {
  const params = new URLSearchParams()
  if (!options) return params
  if (options.limit !== undefined) params.append("limit", String(options.limit))
  if (options.offset !== undefined) params.append("offset", String(options.offset))
  if (options.type_filter) params.append("type_filter", options.type_filter)
  if (options.q) params.append("q", options.q)
  if (options.needs_review === true) params.append("needs_review", "true")
  if (options.needs_review === false) params.append("needs_review", "false")
  if (options.public_figure === true) params.append("public_figure", "true")
  if (options.public_figure === false) params.append("public_figure", "false")
  if (options.nature) params.append("nature", options.nature)
  return params
}

export async function listPersonCandidates(
  projectSlug: string,
  status: string = "open",
  options?: ListPersonCandidatesFilterOptions,
): Promise<PaginatedPersonCandidatesResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug, status })
  personCandidatesFilterParams(options).forEach((v, k) => params.set(k, v))
  return stylebookJsonFetch<PaginatedPersonCandidatesResponse>(`/v1/people/candidates?${params}`)
}

export async function listPersonCandidateTypes(
  projectSlug: string,
  status: string = "open",
): Promise<{ types: string[] }> {
  const params = new URLSearchParams({ project_slug: projectSlug, status })
  return stylebookJsonFetch(`/v1/people/candidates/types?${params}`)
}

export type AcceptPersonCandidateBody = {
  create_new: boolean
  stylebook_person_canonical_id?: string | null
  name?: string | null
  person_type?: string | null
  title?: string | null
  affiliation?: string | null
  public_figure?: boolean
}

export type AcceptPersonCandidateResponse = {
  message: string
  stylebook_person_canonical_id?: string
}

export async function acceptPersonCandidate(
  projectSlug: string,
  substratePersonId: number,
  body: AcceptPersonCandidateBody,
): Promise<AcceptPersonCandidateResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<AcceptPersonCandidateResponse>(
    `/v1/people/candidates/${substratePersonId}/accept?${params}`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  )
}

export async function deferPersonCandidate(
  projectSlug: string,
  substratePersonId: number,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/people/candidates/${substratePersonId}/defer?${params}`,
    { method: "POST" },
  )
}

export interface PersonCandidateContextItem {
  article_id: number
  article_headline?: string | null
  article_url?: string | null
  text: string
}

export interface PersonCandidateContextResponse {
  substrate_person_id: number
  created_at?: string | null
  note?: string | null
  examples: PersonCandidateContextItem[]
}

export async function getPersonCandidateContext(
  projectSlug: string,
  substratePersonId: number,
  limit: number = 3,
): Promise<PersonCandidateContextResponse> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: String(limit),
  })
  return stylebookJsonFetch<PersonCandidateContextResponse>(
    `/v1/people/candidates/${substratePersonId}/context?${params}`,
  )
}

export async function updatePersonCandidateNote(
  projectSlug: string,
  substratePersonId: number,
  note: string | null,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ message: string }>(
    `/v1/people/candidates/${substratePersonId}/note?${params}`,
    { method: "POST", body: JSON.stringify({ note }) },
  )
}

export interface SuggestedPersonCanonicalItem {
  canonical_id: string
  label: string
  person_type?: string | null
  title?: string | null
  affiliation?: string | null
}

export interface SuggestedPersonCanonicalsResponse {
  suggestions: SuggestedPersonCanonicalItem[]
}

export async function getSuggestedPersonCanonicals(
  projectSlug: string,
  substratePersonId: number,
  limit: number = 24,
): Promise<SuggestedPersonCanonicalsResponse> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: String(limit),
  })
  return stylebookJsonFetch<SuggestedPersonCanonicalsResponse>(
    `/v1/people/candidates/${substratePersonId}/suggested-canonicals?${params}`,
  )
}
