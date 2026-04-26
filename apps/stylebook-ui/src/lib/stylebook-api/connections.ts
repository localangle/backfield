import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface Connection {
  id: number
  from_entity_type: string
  from_entity_id: number
  from_display_name: string
  to_entity_type: string
  to_entity_id: number
  to_display_name: string
  nature: string
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
  locationCanonicalId: number,
  projectSlug: string,
): Promise<ConnectionListResponse> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<ConnectionListResponse>(
    `/v1/canonical-locations/${locationCanonicalId}/connections?${q}`,
  )
}

export async function createConnectionForLocation(
  locationCanonicalId: number,
  projectSlug: string,
  body: { to_entity_type: string; to_entity_id: number; nature: string },
): Promise<Connection> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<Connection>(
    `/v1/canonical-locations/${locationCanonicalId}/connections?${q}`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateConnectionForLocation(
  locationCanonicalId: number,
  connectionId: number,
  projectSlug: string,
  body: { nature: string },
): Promise<Connection> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<Connection>(
    `/v1/canonical-locations/${locationCanonicalId}/connections/${connectionId}?${q}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteConnectionForLocation(
  locationCanonicalId: number,
  connectionId: number,
  projectSlug: string,
): Promise<{ ok: boolean }> {
  const q = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<{ ok: boolean }>(
    `/v1/canonical-locations/${locationCanonicalId}/connections/${connectionId}?${q}`,
    { method: "DELETE" },
  )
}
