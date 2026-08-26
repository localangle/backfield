import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface ConnectionEvidence {
  id?: number | null
  article_id?: number | null
  description?: string | null
  quote?: string | null
  reason?: string | null
  confidence?: number | null
  source?: string | null
  prompt_version?: string | null
  run_id?: string | null
  processed_item_id?: number | null
  match_basis?: string | null
  asserted_currentness?: "current" | "former" | "unspecified"
  currentness_review_source?: "unreviewed" | "llm" | "manual" | "deterministic"
  observed_at?: string | null
}

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
  temporal_kind?: "static" | "dynamic" | null
  currentness?: "current" | "former" | "unknown" | null
  currentness_as_of?: string | null
  evidence_json?: Record<string, unknown> | null
  evidence?: ConnectionEvidence[]
  closed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type ConnectionWriteBody = {
  to_entity_type?: string
  to_entity_id?: number | string
  nature?: string | null
  description?: string | null
  asserted_currentness?: "current" | "former" | "unspecified"
}

export type ConnectionUpdateBody = {
  nature?: string | null
  description?: string | null
  asserted_currentness?: "current" | "former" | "unspecified" | null
}

export interface ConnectionListResponse {
  connections: Connection[]
  total: number
  limit: number
  offset: number
}

export interface NatureEntry {
  slug: string
  label: string
  source: "preferred" | "custom"
  equivalent_to?: string | null
  temporal_kind?: string | null
}

export const CONNECTIONS_PER_PAGE = 10

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
    total =
      connections.length < limit ? offset + connections.length : Math.max(connections.length, offset + limit)
  }
  return { connections, total, limit, offset }
}

function connectionsQuery(
  limit?: number,
  offset?: number,
  includeClosed?: boolean,
): string {
  const params = new URLSearchParams()
  if (limit != null) params.set("limit", String(limit))
  if (offset != null) params.set("offset", String(offset))
  if (includeClosed) params.set("include_closed", "true")
  const q = params.toString()
  return q ? `?${q}` : ""
}

function natureSlugs(payload: { natures?: NatureEntry[] | string[] }): string[] {
  const rows = payload.natures ?? []
  return rows.map((row) => (typeof row === "string" ? row : row.slug))
}

export async function listConnectionNatures(
  projectSlug: string,
  q?: string,
): Promise<{ natures: string[]; entries: NatureEntry[] }> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  if (q?.trim()) params.set("q", q.trim())
  const raw = await stylebookJsonFetch<{ natures: NatureEntry[] | string[] }>(
    `/v1/connections/natures?${params}`,
  )
  const entries = (raw.natures ?? []).map((row) =>
    typeof row === "string"
      ? { slug: row, label: row.replace(/_/g, " "), source: "preferred" as const }
      : row,
  )
  return { natures: natureSlugs(raw), entries }
}

export async function listStylebookConnectionNatures(
  stylebookSlug: string,
  q?: string,
): Promise<{ natures: string[]; entries: NatureEntry[] }> {
  const params = new URLSearchParams()
  if (q?.trim()) params.set("q", q.trim())
  const suffix = params.toString()
  const raw = await stylebookJsonFetch<{ natures: NatureEntry[] | string[] }>(
    `/v1/connections/stylebooks/${encodeURIComponent(stylebookSlug)}/natures${suffix ? `?${suffix}` : ""}`,
  )
  const entries = (raw.natures ?? []).map((row) =>
    typeof row === "string"
      ? { slug: row, label: row.replace(/_/g, " "), source: "preferred" as const }
      : row,
  )
  return { natures: natureSlugs(raw), entries }
}

export async function listStylebookConnectionsForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
  options?: { limit?: number; offset?: number; includeClosed?: boolean },
): Promise<ConnectionListResponse> {
  const raw = await stylebookJsonFetch<ConnectionListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections${connectionsQuery(options?.limit, options?.offset, options?.includeClosed)}`,
  )
  return normalizeConnectionListResponse(raw, options)
}

export async function listStylebookConnectionsForPerson(
  stylebookSlug: string,
  personCanonicalId: string,
  options?: { limit?: number; offset?: number; includeClosed?: boolean },
): Promise<ConnectionListResponse> {
  const raw = await stylebookJsonFetch<ConnectionListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(personCanonicalId)}/connections${connectionsQuery(options?.limit, options?.offset, options?.includeClosed)}`,
  )
  return normalizeConnectionListResponse(raw, options)
}

export async function listStylebookConnectionsForOrganization(
  stylebookSlug: string,
  organizationCanonicalId: string,
  options?: { limit?: number; offset?: number; includeClosed?: boolean },
): Promise<ConnectionListResponse> {
  const raw = await stylebookJsonFetch<ConnectionListResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(organizationCanonicalId)}/connections${connectionsQuery(options?.limit, options?.offset, options?.includeClosed)}`,
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

export async function closeStylebookConnectionForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
  connectionId: number,
): Promise<{ ok: boolean; closed?: boolean }> {
  return stylebookJsonFetch<{ ok: boolean; closed?: boolean }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections/${connectionId}`,
    { method: "DELETE" },
  )
}

export async function reopenStylebookConnectionForLocation(
  stylebookSlug: string,
  locationCanonicalId: string,
  connectionId: number,
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-locations/${encodeURIComponent(locationCanonicalId)}/connections/${connectionId}/reopen`,
    { method: "POST" },
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

export async function closeStylebookConnectionForPerson(
  stylebookSlug: string,
  personCanonicalId: string,
  connectionId: number,
): Promise<{ ok: boolean; closed?: boolean }> {
  return stylebookJsonFetch<{ ok: boolean; closed?: boolean }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(personCanonicalId)}/connections/${connectionId}`,
    { method: "DELETE" },
  )
}

export async function reopenStylebookConnectionForPerson(
  stylebookSlug: string,
  personCanonicalId: string,
  connectionId: number,
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-people/${encodeURIComponent(personCanonicalId)}/connections/${connectionId}/reopen`,
    { method: "POST" },
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

export async function closeStylebookConnectionForOrganization(
  stylebookSlug: string,
  organizationCanonicalId: string,
  connectionId: number,
): Promise<{ ok: boolean; closed?: boolean }> {
  return stylebookJsonFetch<{ ok: boolean; closed?: boolean }>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(organizationCanonicalId)}/connections/${connectionId}`,
    { method: "DELETE" },
  )
}

export async function reopenStylebookConnectionForOrganization(
  stylebookSlug: string,
  organizationCanonicalId: string,
  connectionId: number,
): Promise<Connection> {
  return stylebookJsonFetch<Connection>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/canonical-organizations/${encodeURIComponent(organizationCanonicalId)}/connections/${connectionId}/reopen`,
    { method: "POST" },
  )
}

/** Soft-close a connection using either endpoint as the API path. */
export async function closeStylebookConnection(
  stylebookSlug: string,
  conn: Connection,
): Promise<{ ok: boolean; closed?: boolean }> {
  const ends: Array<{ entityType: string; entityId: string }> = [
    { entityType: conn.from_entity_type, entityId: String(conn.from_entity_id) },
    { entityType: conn.to_entity_type, entityId: String(conn.to_entity_id) },
  ]
  for (const end of ends) {
    if (end.entityType === "person") {
      return closeStylebookConnectionForPerson(stylebookSlug, end.entityId, conn.id)
    }
    if (end.entityType === "organization") {
      return closeStylebookConnectionForOrganization(stylebookSlug, end.entityId, conn.id)
    }
    if (end.entityType === "location") {
      return closeStylebookConnectionForLocation(stylebookSlug, end.entityId, conn.id)
    }
  }
  throw new Error("This connection cannot be closed from Stylebook yet.")
}

/** Reopen a soft-closed connection using either endpoint as the API path. */
export async function reopenStylebookConnection(
  stylebookSlug: string,
  conn: Connection,
): Promise<Connection> {
  const ends: Array<{ entityType: string; entityId: string }> = [
    { entityType: conn.from_entity_type, entityId: String(conn.from_entity_id) },
    { entityType: conn.to_entity_type, entityId: String(conn.to_entity_id) },
  ]
  for (const end of ends) {
    if (end.entityType === "person") {
      return reopenStylebookConnectionForPerson(stylebookSlug, end.entityId, conn.id)
    }
    if (end.entityType === "organization") {
      return reopenStylebookConnectionForOrganization(stylebookSlug, end.entityId, conn.id)
    }
    if (end.entityType === "location") {
      return reopenStylebookConnectionForLocation(stylebookSlug, end.entityId, conn.id)
    }
  }
  throw new Error("This connection cannot be reopened from Stylebook yet.")
}
