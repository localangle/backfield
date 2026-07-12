import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface Connection {
  id: number
  from_entity_type: string
  from_entity_id: string
  from_display_name: string
  to_entity_type: string
  to_entity_id: string
  to_display_name: string
  description?: string | null
  nature?: string | null
  evidence_json?: Record<string, unknown> | null
  created_at?: string | null
}

export type ConnectionWriteBody = {
  to_entity_type?: string
  to_entity_id?: number | string
  nature?: string | null
  description?: string | null
}

export type ConnectionUpdateBody = {
  nature?: string | null
  description?: string | null
}

export interface ConnectionListResponse {
  connections: Connection[]
  total: number
  limit: number
  offset: number
}

export const CONNECTIONS_PER_PAGE = 10
export const CONNECTIONS_GRAPH_FETCH_LIMIT = 500

/** Coerce list payloads so pagination never receives NaN from legacy API responses. */
export function normalizeConnectionListResponse(
  raw: Partial<ConnectionListResponse> & { connections?: Connection[] },
  requested?: { limit?: number; offset?: number },
): ConnectionListResponse {
  const connections = Array.isArray(raw.connections) ? raw.connections : []
  const limit =
    typeof raw.limit === "number" && Number.isFinite(raw.limit)
      ? raw.limit
      : (requested?.limit ?? CONNECTIONS_PER_PAGE)
  const offset =
    typeof raw.offset === "number" && Number.isFinite(raw.offset)
      ? raw.offset
      : (requested?.offset ?? 0)
  let total =
    typeof raw.total === "number" && Number.isFinite(raw.total) ? raw.total : undefined
  if (total === undefined) {
    // Legacy responses return the full connection set without pagination metadata.
    total =
      connections.length < limit ? offset + connections.length : Math.max(connections.length, offset + limit)
  }
  return { connections, total, limit, offset }
}

function connectionsQuery(limit?: number, offset?: number): string {
  const params = new URLSearchParams()
  if (limit != null) params.set("limit", String(limit))
  if (offset != null) params.set("offset", String(offset))
  const q = params.toString()
  return q ? `?${q}` : ""
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
  body: ConnectionWriteBody,
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
  body: ConnectionUpdateBody,
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
  options?: { limit?: number; offset?: number },
): Promise<ConnectionListResponse> {
  const raw = await stylebookJsonFetch<ConnectionListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections${connectionsQuery(options?.limit, options?.offset)}`,
  )
  return normalizeConnectionListResponse(raw, options)
}

export async function listStylebookConnectionsForPerson(
  stylebookSlug: string,
  personCanonicalId: string,
  options?: { limit?: number; offset?: number },
): Promise<ConnectionListResponse> {
  const raw = await stylebookJsonFetch<ConnectionListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(personCanonicalId)}/connections${connectionsQuery(options?.limit, options?.offset)}`,
  )
  return normalizeConnectionListResponse(raw, options)
}

export async function listStylebookConnectionsForOrganization(
  stylebookSlug: string,
  organizationCanonicalId: string,
  options?: { limit?: number; offset?: number },
): Promise<ConnectionListResponse> {
  const raw = await stylebookJsonFetch<ConnectionListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(organizationCanonicalId)}/connections${connectionsQuery(options?.limit, options?.offset)}`,
  )
  return normalizeConnectionListResponse(raw, options)
}

export async function createStylebookConnectionForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
  body: ConnectionWriteBody,
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
  body: ConnectionUpdateBody,
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

export async function createStylebookConnectionForPerson(
  stylebookSlug: string,
  personCanonicalId: string,
  body: ConnectionWriteBody,
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(personCanonicalId)}/connections`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookConnectionForPerson(
  stylebookSlug: string,
  personCanonicalId: string,
  connectionId: number,
  body: ConnectionUpdateBody,
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(personCanonicalId)}/connections/${connectionId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteStylebookConnectionForPerson(
  stylebookSlug: string,
  personCanonicalId: string,
  connectionId: number,
): Promise<{ ok: boolean }> {
  return stylebookJsonFetch<{ ok: boolean }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(personCanonicalId)}/connections/${connectionId}`,
    { method: "DELETE" },
  )
}

export async function createStylebookConnectionForOrganization(
  stylebookSlug: string,
  organizationCanonicalId: string,
  body: ConnectionWriteBody,
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(organizationCanonicalId)}/connections`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export async function updateStylebookConnectionForOrganization(
  stylebookSlug: string,
  organizationCanonicalId: string,
  connectionId: number,
  body: ConnectionUpdateBody,
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(organizationCanonicalId)}/connections/${connectionId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  )
}

export async function deleteStylebookConnectionForOrganization(
  stylebookSlug: string,
  organizationCanonicalId: string,
  connectionId: number,
): Promise<{ ok: boolean }> {
  return stylebookJsonFetch<{ ok: boolean }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(organizationCanonicalId)}/connections/${connectionId}`,
    { method: "DELETE" },
  )
}
