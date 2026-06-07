import { stylebookJsonFetch } from "@/lib/stylebook-api/client"
import { listCanonicalOrganizations } from "@/lib/stylebook-api/organizations"
import { listCanonicalPeople } from "@/lib/stylebook-api/people"

export interface PersonListRow {
  id: string
  project_id: number
  full_name: string
  title?: string
  affiliation?: string
  person_type?: string
  public_figure?: boolean
  status: string
  created_at: string
  updated_at: string
}

/** Canonical people list for EntitySelector (maps catalog ``label`` → ``full_name``). */
export async function listPeople(
  stylebookSlug: string,
  projectSlug: string,
  q?: string,
  _status?: string,
  limit: number = 25,
  offset: number = 0,
  options?: {
    title_filter?: string
    affiliation_filter?: string
    public_figure?: boolean
    type_filter?: string
  },
): Promise<{
  people: PersonListRow[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}> {
  const res = await listCanonicalPeople(
    stylebookSlug,
    q,
    limit,
    offset,
    options?.type_filter,
    projectSlug,
    { publicFigure: options?.public_figure },
  )
  return {
    people: res.canonicals.map((c) => ({
      id: c.id,
      project_id: 0,
      full_name: c.label,
      title: c.title ?? undefined,
      affiliation: c.affiliation ?? undefined,
      person_type: c.person_type ?? undefined,
      public_figure: c.public_figure,
      status: c.status,
      created_at: c.created_at,
      updated_at: c.updated_at,
    })),
    total: res.total,
    page: res.page,
    per_page: res.per_page,
    has_next: res.has_next,
    has_prev: res.has_prev,
  }
}

export interface OrganizationListRow {
  id: string
  project_id: number
  name: string
  organization_type?: string
  status: string
  created_at: string
  updated_at: string
}

/** Canonical organizations list for EntitySelector (maps catalog ``label`` → ``name``). */
export async function listOrganizations(
  stylebookSlug: string,
  projectSlug: string,
  q?: string,
  _status?: string,
  limit: number = 25,
  offset: number = 0,
  options?: {
    type_filter?: string
  },
): Promise<{
  organizations: OrganizationListRow[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}> {
  const res = await listCanonicalOrganizations(
    stylebookSlug,
    q,
    limit,
    offset,
    options?.type_filter,
    projectSlug,
  )
  return {
    organizations: res.canonicals.map((c) => ({
      id: c.id,
      project_id: 0,
      name: c.label,
      organization_type: c.organization_type ?? undefined,
      status: c.status,
      created_at: c.created_at,
      updated_at: c.updated_at,
    })),
    total: res.total,
    page: res.page,
    per_page: res.per_page,
    has_next: res.has_next,
    has_prev: res.has_prev,
  }
}

export async function listWorks(
  projectSlug: string,
  q?: string,
  status?: string,
  limit: number = 25,
  offset: number = 0,
): Promise<{
  works: Array<Record<string, unknown>>
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    limit: String(limit),
    offset: String(offset),
  })
  if (q) params.set("q", q)
  if (status) params.set("status", status)
  return stylebookJsonFetch(`/v1/works?${params}`)
}
