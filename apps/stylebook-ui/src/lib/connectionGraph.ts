import type { EntityType } from "@/lib/entityTypes"
import { formatConnectionSummaryLabel } from "@/lib/connectionEvidence"
import {
  listStylebookConnectionsForLocation,
  listStylebookConnectionsForOrganization,
  listStylebookConnectionsForPerson,
  type Connection,
} from "@/lib/stylebook-api/connections"

export const GRAPH_HOP1_LIMIT = 500
export const GRAPH_HOP2_NEIGHBOR_CAP = 18
export const GRAPH_HOP2_PER_NEIGHBOR_LIMIT = 40

export type GraphHop = 0 | 1 | 2

export interface GraphEntityRef {
  entityType: EntityType
  entityId: string
  displayName: string
}

export interface ConnectionNeighborhood {
  connections: Connection[]
  hop1ConnectionCount: number
  hop2ConnectionCount: number
  neighborsExpanded: number
  neighborsSkipped: number
}

export const EMPTY_CONNECTION_NEIGHBORHOOD: ConnectionNeighborhood = {
  connections: [],
  hop1ConnectionCount: 0,
  hop2ConnectionCount: 0,
  neighborsExpanded: 0,
  neighborsSkipped: 0,
}

export function entityRefKey(ref: Pick<GraphEntityRef, "entityType" | "entityId">): string {
  return `${ref.entityType}:${ref.entityId}`
}

export function neighborFromConnection(
  conn: Connection,
  center: Pick<GraphEntityRef, "entityType" | "entityId">,
): GraphEntityRef | null {
  const centerKey = entityRefKey(center)
  const fromKey = entityRefKey({
    entityType: conn.from_entity_type as EntityType,
    entityId: String(conn.from_entity_id),
  })
  const toKey = entityRefKey({
    entityType: conn.to_entity_type as EntityType,
    entityId: String(conn.to_entity_id),
  })
  if (fromKey === centerKey) {
    return {
      entityType: conn.to_entity_type as EntityType,
      entityId: String(conn.to_entity_id),
      displayName: conn.to_display_name,
    }
  }
  if (toKey === centerKey) {
    return {
      entityType: conn.from_entity_type as EntityType,
      entityId: String(conn.from_entity_id),
      displayName: conn.from_display_name,
    }
  }
  return null
}

export function dedupeConnections(connections: Connection[]): Connection[] {
  const seen = new Set<number>()
  const out: Connection[] = []
  for (const conn of connections) {
    if (seen.has(conn.id)) continue
    seen.add(conn.id)
    out.push(conn)
  }
  return out
}

function neighborExpansionPriority(ref: GraphEntityRef): number {
  if (ref.entityType === "organization") return 0
  if (ref.entityType === "person") return 1
  if (ref.entityType === "location") return 2
  return 3
}

export function selectNeighborsForHop2Expansion(
  neighbors: GraphEntityRef[],
  cap: number = GRAPH_HOP2_NEIGHBOR_CAP,
): { selected: GraphEntityRef[]; skipped: number } {
  const unique = new Map<string, GraphEntityRef>()
  for (const ref of neighbors) {
    unique.set(entityRefKey(ref), ref)
  }
  const sorted = Array.from(unique.values()).sort((a, b) => {
    const priority = neighborExpansionPriority(a) - neighborExpansionPriority(b)
    if (priority !== 0) return priority
    return a.displayName.localeCompare(b.displayName, undefined, { sensitivity: "base" })
  })
  if (sorted.length <= cap) {
    return { selected: sorted, skipped: 0 }
  }
  return { selected: sorted.slice(0, cap), skipped: sorted.length - cap }
}

async function listConnectionsForEntity(
  stylebookSlug: string,
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
  options: { limit: number; includeClosed?: boolean },
): Promise<Connection[]> {
  const canonicalId = String(ref.entityId)
  const fetchOptions = { limit: options.limit, offset: 0, includeClosed: options.includeClosed }
  if (ref.entityType === "person") {
    return (await listStylebookConnectionsForPerson(stylebookSlug, canonicalId, fetchOptions))
      .connections
  }
  if (ref.entityType === "organization") {
    return (
      await listStylebookConnectionsForOrganization(stylebookSlug, canonicalId, fetchOptions)
    ).connections
  }
  if (ref.entityType === "location") {
    return (await listStylebookConnectionsForLocation(stylebookSlug, canonicalId, fetchOptions))
      .connections
  }
  return []
}

async function mapConcurrent<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T) => Promise<R>,
): Promise<R[]> {
  if (items.length === 0) return []
  const results: R[] = new Array(items.length)
  let index = 0
  const workers = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (index < items.length) {
      const current = index
      index += 1
      results[current] = await fn(items[current])
    }
  })
  await Promise.all(workers)
  return results
}

export async function fetchConnectionNeighborhood(
  stylebookSlug: string,
  center: GraphEntityRef,
  options?: {
    includeClosed?: boolean
    expandHops?: 1 | 2
    hop2NeighborCap?: number
  },
): Promise<ConnectionNeighborhood> {
  const expandHops = options?.expandHops ?? 1
  const hop1 = await listConnectionsForEntity(stylebookSlug, center, {
    limit: GRAPH_HOP1_LIMIT,
    includeClosed: options?.includeClosed,
  })

  if (expandHops < 2) {
    return {
      connections: hop1,
      hop1ConnectionCount: hop1.length,
      hop2ConnectionCount: 0,
      neighborsExpanded: 0,
      neighborsSkipped: 0,
    }
  }

  const hop1Neighbors = hop1
    .map((conn) => neighborFromConnection(conn, center))
    .filter((ref): ref is GraphEntityRef => ref !== null)

  const { selected, skipped } = selectNeighborsForHop2Expansion(
    hop1Neighbors,
    options?.hop2NeighborCap ?? GRAPH_HOP2_NEIGHBOR_CAP,
  )

  const hop2Batches = await mapConcurrent(selected, 6, (neighbor) =>
    listConnectionsForEntity(stylebookSlug, neighbor, {
      limit: GRAPH_HOP2_PER_NEIGHBOR_LIMIT,
      includeClosed: options?.includeClosed,
    }),
  )

  const hop2: Connection[] = []
  for (const batch of hop2Batches) {
    for (const conn of batch) {
      const fromKey = entityRefKey({
        entityType: conn.from_entity_type as EntityType,
        entityId: String(conn.from_entity_id),
      })
      const toKey = entityRefKey({
        entityType: conn.to_entity_type as EntityType,
        entityId: String(conn.to_entity_id),
      })
      if (fromKey === entityRefKey(center) || toKey === entityRefKey(center)) {
        continue
      }
      hop2.push(conn)
    }
  }

  const merged = dedupeConnections([...hop1, ...hop2])
  const hop1Ids = new Set(hop1.map((c) => c.id))
  const hop2Only = merged.filter((c) => !hop1Ids.has(c.id))

  return {
    connections: merged,
    hop1ConnectionCount: hop1.length,
    hop2ConnectionCount: hop2Only.length,
    neighborsExpanded: selected.length,
    neighborsSkipped: skipped,
  }
}

export function connectionTouchesEntity(
  conn: Connection,
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
): boolean {
  const key = entityRefKey(ref)
  return (
    entityRefKey({
      entityType: conn.from_entity_type as EntityType,
      entityId: String(conn.from_entity_id),
    }) === key ||
    entityRefKey({
      entityType: conn.to_entity_type as EntityType,
      entityId: String(conn.to_entity_id),
    }) === key
  )
}

export function classifyConnectionHop(
  conn: Connection,
  center: Pick<GraphEntityRef, "entityType" | "entityId">,
): GraphHop {
  if (connectionTouchesEntity(conn, center)) return 1
  return 2
}

export function formatNatureLabel(nature?: string | null): string | null {
  const trimmed = nature?.trim()
  if (!trimmed) return null
  return trimmed.replace(/_/g, " ")
}

export function otherEndFromConnection(
  conn: Connection,
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
): GraphEntityRef | null {
  const key = entityRefKey(ref)
  const from: GraphEntityRef = {
    entityType: conn.from_entity_type as EntityType,
    entityId: String(conn.from_entity_id),
    displayName: conn.from_display_name,
  }
  const to: GraphEntityRef = {
    entityType: conn.to_entity_type as EntityType,
    entityId: String(conn.to_entity_id),
    displayName: conn.to_display_name,
  }
  if (entityRefKey(from) === key) return to
  if (entityRefKey(to) === key) return from
  return null
}

export function connectionsTouchingEntity(
  connections: Connection[],
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
): Connection[] {
  return connections.filter((conn) => connectionTouchesEntity(conn, ref))
}

export function directedEdgeBundleKey(conn: Connection): string {
  return `${conn.from_entity_type}:${conn.from_entity_id}->${conn.to_entity_type}:${conn.to_entity_id}`
}

export function groupConnectionsByDirectedEdge(
  connections: Connection[],
): Map<string, Connection[]> {
  const groups = new Map<string, Connection[]>()
  for (const conn of connections) {
    const key = directedEdgeBundleKey(conn)
    const bucket = groups.get(key) ?? []
    bucket.push(conn)
    groups.set(key, bucket)
  }
  for (const [key, bucket] of groups) {
    bucket.sort((a, b) => a.id - b.id)
    groups.set(key, bucket)
  }
  return groups
}

export function singleConnectionEdgeLabel(conn: Connection): string {
  const nature = formatNatureLabel(conn.nature)
  if (nature) return nature
  const summary = formatConnectionSummaryLabel(conn)
  return summary.length > 36 ? `${summary.slice(0, 33)}…` : summary
}

export function bundleEdgeLabel(connections: Connection[]): string | undefined {
  if (connections.length === 0) return undefined
  if (connections.length === 1) return singleConnectionEdgeLabel(connections[0]!)

  const labels: string[] = []
  const seen = new Set<string>()
  for (const conn of connections) {
    const label = singleConnectionEdgeLabel(conn)
    if (!seen.has(label)) {
      seen.add(label)
      labels.push(label)
    }
  }

  if (labels.length === 1) {
    return `${labels[0]} (${connections.length})`
  }
  if (labels.length === 2) {
    const combined = `${labels[0]} · ${labels[1]}`
    return combined.length > 40 ? `${combined.slice(0, 37)}…` : combined
  }
  const head = `${labels[0]} · ${labels[1]}`
  return head.length > 32 ? `${head.slice(0, 29)}… +${labels.length - 2}` : `${head} +${labels.length - 2}`
}
