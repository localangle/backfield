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

export async function updateSavedPerson(
  personId: number,
  projectSlug: string,
  body: {
    name?: string | null
    title?: string | null
    affiliation?: string | null
    person_type?: string | null
    role_in_story?: string | null
    nature?: string | null
    public_figure?: boolean | null
  },
  articleId?: number | null,
): Promise<void> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (typeof articleId === 'number' && articleId > 0) {
    params.set('article_id', String(articleId))
  }
  await stylebookJsonFetch(`/v1/people/${personId}?${params.toString()}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteSavedPerson(
  personId: number,
  projectSlug: string,
  articleId?: number | null,
): Promise<void> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (typeof articleId === 'number' && articleId > 0) {
    params.set('article_id', String(articleId))
  }
  await stylebookJsonFetch(`/v1/people/${personId}?${params.toString()}`, {
    method: 'DELETE',
  })
}

export type CreateSavedPersonFromArticleEvidenceBody = {
  article_id: number
  run_id: string
  name: string
  mention_text: string
  quote_text: string
  start_char: number
  end_char: number
  person_type?: string | null
  title?: string | null
  affiliation?: string | null
  public_figure?: boolean
  nature?: string | null
  role_in_story?: string | null
}

export type CreatedSavedPersonFromArticleEvidence = {
  person: {
    id: number
    name: string
    title: string | null
    affiliation: string | null
    public_figure: boolean
    person_type: string | null
    status: string
    canonical_link_status: string | null
    stylebook_person_canonical_id: string | null
  }
  mention_id: number
  occurrence_id: number
  anchor: string
}

export async function createSavedPersonFromArticleEvidence(
  projectSlug: string,
  body: CreateSavedPersonFromArticleEvidenceBody,
): Promise<CreatedSavedPersonFromArticleEvidence> {
  return stylebookJsonFetch(
    `/v1/people/from-article-evidence?project_slug=${encodeURIComponent(projectSlug)}`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}
