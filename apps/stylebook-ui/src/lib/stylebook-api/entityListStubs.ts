import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

/** Empty canonical people list (stylebook-api stub until people are migrated). */
export async function listPeople(
  projectSlug: string,
  q?: string,
  status?: string,
  limit: number = 25,
  offset: number = 0,
): Promise<{
  people: Array<Record<string, unknown>>
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
  return stylebookJsonFetch(`/v1/people?${params}`)
}

export async function listOrganizations(
  projectSlug: string,
  q?: string,
  status?: string,
  limit: number = 25,
  offset: number = 0,
): Promise<{
  organizations: Array<Record<string, unknown>>
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
  return stylebookJsonFetch(`/v1/organizations?${params}`)
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
