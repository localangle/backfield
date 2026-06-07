const stylebookBase = () => import.meta.env.VITE_STYLEBOOK_API_BASE ?? '/api/stylebook'

async function stylebookJsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${stylebookBase()}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!r.ok) {
    let msg = r.statusText
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') msg = body.detail
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return (await r.json()) as T
}

export async function updateSavedOrganization(
  organizationId: number,
  projectSlug: string,
  body: {
    name?: string | null
    organization_type?: string | null
    role_in_story?: string | null
    nature?: string | null
    nature_secondary_tags?: string[] | null
  },
  articleId?: number | null,
): Promise<void> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (typeof articleId === 'number' && articleId > 0) {
    params.set('article_id', String(articleId))
  }
  await stylebookJsonFetch(`/v1/organizations/${organizationId}?${params.toString()}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export type OrganizationMentionOccurrencePayload = {
  id?: number
  client_id?: string
  mention_text: string
  quote_text?: string
  start_char?: number | null
  end_char?: number | null
  occurrence_order?: number
  suppressed?: boolean
  is_quote?: boolean
}

export async function replaceSavedOrganizationMentionOccurrences(
  organizationId: number,
  projectSlug: string,
  articleId: number,
  occurrences: OrganizationMentionOccurrencePayload[],
): Promise<{ occurrences: Array<{ id: number; mention_text: string }> }> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    article_id: String(Math.trunc(articleId)),
  })
  return stylebookJsonFetch(
    `/v1/organizations/${organizationId}/mention-occurrences?${params.toString()}`,
    {
      method: 'PUT',
      body: JSON.stringify({ occurrences }),
    },
  )
}

export async function deleteSavedOrganization(
  organizationId: number,
  projectSlug: string,
  articleId?: number | null,
  stylebookSlug?: string | null,
): Promise<{
  message: string
  mentions_removed: number
  organization_deleted: boolean
  candidates_created?: number
}> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  const slug = typeof stylebookSlug === 'string' ? stylebookSlug.trim() : ''
  if (slug) {
    params.set('stylebook_slug', slug)
  }
  if (typeof articleId === 'number' && articleId > 0) {
    params.set('article_id', String(articleId))
  }
  return stylebookJsonFetch(`/v1/organizations/${organizationId}?${params.toString()}`, {
    method: 'DELETE',
  })
}

export type CreateSavedOrganizationFromArticleEvidenceBody = {
  article_id: number
  run_id: string
  name: string
  mention_text: string
  quote_text: string
  start_char: number
  end_char: number
  organization_type?: string | null
  nature?: string | null
  role_in_story?: string | null
}

export type CreatedSavedOrganizationFromArticleEvidence = {
  organization: {
    id: number
    name: string
    organization_type: string | null
    status: string
    canonical_link_status: string | null
    stylebook_organization_canonical_id: string | null
  }
  mention_id: number
  occurrence_id: number
  anchor: string
}

export async function createSavedOrganizationFromArticleEvidence(
  projectSlug: string,
  body: CreateSavedOrganizationFromArticleEvidenceBody,
): Promise<CreatedSavedOrganizationFromArticleEvidence> {
  return stylebookJsonFetch(
    `/v1/organizations/from-article-evidence?project_slug=${encodeURIComponent(projectSlug)}`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}
