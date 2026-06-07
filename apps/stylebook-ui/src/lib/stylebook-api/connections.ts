import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface Connection {
  id: number
  from_entity_type: string
  from_entity_id: string
  from_display_name: string
  to_entity_type: string
  to_entity_id: string
  to_display_name: string
  nature: string
  evidence_json?: Record<string, unknown> | null
  created_at?: string | null
}

export interface ConnectionListResponse {
  connections: Connection[]
}

export async function listConnectionNatures(
  projectSlug: string,
  q?: string,
): Promise<{ natures: string[] }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (q?.trim()) params.set("q", q.trim())
  return stylebookJsonFetch<{ natures: string[] }>(`/v1/connections/natures?${params}`)
}

export async function listConnectionsForLocation(
  locationCanonicalId: string,
  projectSlug: string,
): Promise<ConnectionListResponse> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<ConnectionListResponse>(
    `/v1/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections?${q}`,
  )
}

export async function createConnectionForLocation(
  locationCanonicalId: string,
  projectSlug: string,
  body: { to_entity_type: string; to_entity_id: number | string; nature: string },
): Promise<Connection> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<Connection>(
    `/v1/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections?${q}`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateConnectionForLocation(
  locationCanonicalId: string,
  connectionId: number,
  projectSlug: string,
  body: { nature: string },
): Promise<Connection> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<Connection>(
    `/v1/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections/${connectionId}?${q}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteConnectionForLocation(
  locationCanonicalId: string,
  connectionId: number,
  projectSlug: string,
): Promise<{ ok: boolean }> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ ok: boolean }>(
    `/v1/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections/${connectionId}?${q}`,
    { method: "DELETE" },
  )
}

export async function listStylebookConnectionNatures(
  stylebookSlug: string,
  q?: string,
): Promise<{ natures: string[] }> {
  const params = new URLSearchParams()
  if (q?.trim()) params.set("q", q.trim())
  const suffix = params.toString()
  return stylebookJsonFetch<{ natures: string[] }>(
    `/v1/connections/stylebooks/${encodeURIComponent(stylebookSlug)}/natures${suffix ? `?${suffix}` : ""}`,
  )
}

export async function listStylebookConnectionsForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
): Promise<ConnectionListResponse> {
  return stylebookJsonFetch<ConnectionListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections`,
  )
}

export async function createStylebookConnectionForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
  body: { to_entity_type: string; to_entity_id: number | string; nature: string },
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookConnectionForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
  connectionId: number,
  body: { nature: string },
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections/${connectionId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteStylebookConnectionForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
  connectionId: number,
): Promise<{ ok: boolean }> {
  return stylebookJsonFetch<{ ok: boolean }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections/${connectionId}`,
    { method: "DELETE" },
  )
}
