import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

/** One ``stylebook_person_canonical`` row (Stylebook catalog), not a substrate person. */
export interface CanonicalPerson {
  id: string
  slug: string
  label: string
  title?: string | null
  affiliation?: string | null
  public_figure: boolean
  person_type?: string | null
  sort_key?: string | null
  status: string
  linked_substrate_count: number
  mention_count: number
  created_at: string
  updated_at: string
}

export interface Person {
  id: number
  project_id: number
  name: string
  title?: string | null
  affiliation?: string | null
  public_figure: boolean
  person_type?: string | null
  sort_key?: string | null
  status: string
  created_by_user_id?: number
  created_at: string
  updated_at: string
  mention_count?: number
  canonical_link_status?: string
  canonical_review_reasons_json?: unknown
  /** When set, this substrate row is linked to this Stylebook canonical id (catalog UUID string). */
  stylebook_person_canonical_id?: string | null
}

export interface PaginatedCanonicalPersonResponse {
  canonicals: CanonicalPerson[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export type CanonicalPersonListSort = "sort_key" | "recent"

export type CanonicalPersonListFilters = {
  minMentions?: number
  sort?: CanonicalPersonListSort
  publicFigure?: boolean
  /** Case-insensitive substring match on canonical title. */
  title?: string
  /** Case-insensitive substring match on canonical affiliation. */
  affiliation?: string
  /** Editorial mention nature filter when supported by the API. */
  nature?: string
}

export async function listCanonicalPeople(
  stylebookSlug: string,
  q?: string,
  limit: number = 25,
  offset: number = 0,
  typeFilter?: string,
  projectFilterSlug?: string,
  options?: CanonicalPersonListFilters,
): Promise<PaginatedCanonicalPersonResponse> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.append("project", projectFilterSlug)
  if (q) params.append("q", q)
  if (typeFilter && typeFilter !== "all") params.append("type_filter", typeFilter)
  const minMentions = options?.minMentions ?? 0
  if (minMentions > 0) params.append("min_mentions", String(minMentions))
  const sort = options?.sort ?? "sort_key"
  if (sort !== "sort_key") params.append("sort", sort)
  if (options?.publicFigure === true) params.append("public_figure", "true")
  if (options?.publicFigure === false) params.append("public_figure", "false")
  const title = options?.title?.trim()
  if (title) params.append("title_filter", title)
  const affiliation = options?.affiliation?.trim()
  if (affiliation) params.append("affiliation_filter", affiliation)
  if (options?.nature && options.nature !== "all") params.append("nature", options.nature)
  params.append("limit", limit.toString())
  params.append("offset", offset.toString())
  return stylebookJsonFetch<PaginatedCanonicalPersonResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people?${params}`,
  )
}

export async function listCanonicalPersonTypes(stylebookSlug: string): Promise<{ types: string[] }> {
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/types`,
  )
}

export async function getCanonicalPerson(
  canonicalId: string,
  stylebookSlug: string,
  projectFilterSlug?: string,
): Promise<CanonicalPerson> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalPerson>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(canonicalId)}?${params}`,
  )
}

export interface LinkedPersonSubstrateItem {
  id: number
  name: string
  normalized_name: string
  person_type?: string | null
  title?: string | null
  affiliation?: string | null
  public_figure: boolean
  canonical_link_status: string
  project_id: number
  project_slug: string
  project_name: string
}

export interface LinkedPersonSubstratesResponse {
  substrates: LinkedPersonSubstrateItem[]
}

export async function listCanonicalLinkedPersonSubstrates(
  canonicalId: string,
  stylebookSlug: string,
  projectFilterSlug?: string,
): Promise<LinkedPersonSubstratesResponse> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<LinkedPersonSubstratesResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(
      canonicalId,
    )}/linked-substrates?${params}`,
  )
}

export interface LinkedPersonMention {
  substrate_person_id: number
  mention_id: number
  article_id: number
  article_headline?: string | null
  article_url?: string | null
  original_text?: string | null
  mention_nature?: string | null
  description?: string | null
  person_name?: string | null
  person_type?: string | null
  title?: string | null
  affiliation?: string | null
  created_at?: string | null
}

export interface PersonMentionsResponse {
  canonical_person_id: string
  canonical_name: string
  mentions: LinkedPersonMention[]
  total: number
  limit: number
  offset: number
}

export async function getCanonicalPersonMentions(
  canonicalId: string,
  stylebookSlug: string,
  limit: number = 50,
  offset: number = 0,
  _sort?: string,
  sortDirection: "asc" | "desc" = "desc",
  projectFilterSlug?: string,
): Promise<PersonMentionsResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
    sort_direction: sortDirection,
  })
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<PersonMentionsResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(
      canonicalId,
    )}/mentions?${params}`,
  )
}

export async function unlinkPersonSubstrateFromCanonical(
  substratePersonId: number,
  projectSlug: string,
): Promise<{ message: string }> {
  return stylebookJsonFetch<{ message: string }>(
    `/v1/people/${substratePersonId}/unlink-canonical?project_slug=${encodeURIComponent(projectSlug)}`,
    { method: "POST" },
  )
}

export async function linkPersonSubstrateToCanonical(
  substratePersonId: number,
  projectSlug: string,
  stylebookPersonCanonicalId: string,
): Promise<{ changed: boolean }> {
  return stylebookJsonFetch<{ changed: boolean }>(
    `/v1/people/${substratePersonId}/link-canonical?project_slug=${encodeURIComponent(projectSlug)}`,
    {
      method: "POST",
      body: JSON.stringify({ stylebook_person_canonical_id: stylebookPersonCanonicalId }),
    },
  )
}

export async function getPerson(personId: number, projectSlug: string): Promise<Person> {
  return stylebookJsonFetch<Person>(
    `/v1/people/${personId}?project_slug=${encodeURIComponent(projectSlug)}`,
  )
}

export async function createCanonicalPerson(
  stylebookSlug: string,
  data: {
    label: string
    title?: string | null
    affiliation?: string | null
    person_type?: string | null
    public_figure?: boolean
    sort_key?: string | null
  },
  projectFilterSlug?: string,
): Promise<CanonicalPerson> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalPerson>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people?${params}`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  )
}

export async function patchCanonicalPerson(
  canonicalId: string,
  stylebookSlug: string,
  data: {
    label?: string
    title?: string | null
    affiliation?: string | null
    person_type?: string | null
    public_figure?: boolean
    sort_key?: string | null
  },
  projectFilterSlug?: string,
): Promise<CanonicalPerson> {
  const params = new URLSearchParams()
  if (projectFilterSlug) params.set("project", projectFilterSlug)
  return stylebookJsonFetch<CanonicalPerson>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(
      canonicalId,
    )}?${params}`,
    { method: "PATCH", body: JSON.stringify(data) },
  )
}

export async function deleteCanonicalPerson(
  canonicalId: string,
  stylebookSlug: string,
): Promise<{ message: string; id: string; unlinked_substrate_count: number }> {
  return stylebookJsonFetch(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(
      canonicalId,
    )}`,
    { method: "DELETE" },
  )
}
