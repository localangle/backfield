/**
 * Stylebook saved-place and canonical geometry APIs for Agate Review.
 * Proxied via ``/api/stylebook`` (see ``vite.config.ts``).
 */

const stylebookBase = () => import.meta.env.VITE_STYLEBOOK_API_BASE ?? '/api/stylebook'

function formatDetail(detail: unknown): string {
  if (detail == null) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg?: unknown }).msg ?? '')
        }
        try {
          return JSON.stringify(item)
        } catch {
          return String(item)
        }
      })
      .filter((s) => s.length > 0)
      .join('; ')
  }
  if (typeof detail === 'object') {
    try {
      return JSON.stringify(detail)
    } catch {
      return String(detail)
    }
  }
  return String(detail)
}

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
      if (body.detail !== undefined) {
        const f = formatDetail(body.detail)
        if (f) msg = f
      }
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return (await r.json()) as T
}

export async function updateSavedPlace(
  locationId: number,
  projectSlug: string,
  body: {
    name?: string | null
    location_type?: string | null
    formatted_address?: string | null
  },
): Promise<void> {
  const payload: Record<string, unknown> = {}
  if (body.name !== undefined) payload.name = body.name
  if (body.location_type !== undefined) payload.location_type = body.location_type
  if (body.formatted_address !== undefined) payload.formatted_address = body.formatted_address
  await stylebookJsonFetch(`/v1/locations/${locationId}?project_slug=${encodeURIComponent(projectSlug)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteSavedPlace(
  locationId: number,
  projectSlug: string,
  articleId?: number | null,
  stylebookSlug?: string | null,
): Promise<{
  message: string
  mentions_removed: number
  location_deleted: boolean
  candidates_created?: number
}> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  const slug = typeof stylebookSlug === 'string' ? stylebookSlug.trim() : ''
  if (slug) {
    params.set('stylebook_slug', slug)
  }
  if (articleId != null && Number.isFinite(articleId) && articleId > 0) {
    params.set('article_id', String(Math.trunc(articleId)))
  }
  return stylebookJsonFetch(
    `/v1/locations/${locationId}?${params.toString()}`,
    { method: 'DELETE' },
  )
}

export async function updateSavedPlaceGeometry(
  locationId: number,
  projectSlug: string,
  geometryJson: Record<string, unknown> | null,
): Promise<void> {
  await stylebookJsonFetch(
    `/v1/locations/${locationId}/geometry?project_slug=${encodeURIComponent(projectSlug)}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ geometry_json: geometryJson }),
    },
  )
}

export type MentionOccurrencePayload = {
  id?: number
  client_id?: string
  mention_text: string
  start_char?: number | null
  end_char?: number | null
  occurrence_order?: number
  suppressed?: boolean
}

export async function replaceSavedPlaceMentionOccurrences(
  locationId: number,
  projectSlug: string,
  articleId: number,
  occurrences: MentionOccurrencePayload[],
): Promise<{ occurrences: Array<{ id: number; mention_text: string }> }> {
  const params = new URLSearchParams({
    project_slug: projectSlug,
    article_id: String(Math.trunc(articleId)),
  })
  return stylebookJsonFetch(
    `/v1/locations/${locationId}/mention-occurrences?${params.toString()}`,
    {
      method: 'PUT',
      body: JSON.stringify({ occurrences }),
    },
  )
}

export async function updateStylebookCanonicalGeometry(
  canonicalId: string,
  stylebookSlug: string,
  geometryJson: Record<string, unknown> | null,
): Promise<void> {
  await stylebookJsonFetch<{ message: string; id: string }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(
      canonicalId,
    )}/geometry`,
    {
      method: 'PATCH',
      body: JSON.stringify({ geometry_json: geometryJson }),
    },
  )
}
