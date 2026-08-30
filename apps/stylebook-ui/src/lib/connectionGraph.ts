import type { EntityType } from "@/lib/entityTypes"
import { formatConnectionSummaryLabel } from "@/lib/connectionEvidence"
import {
  listStylebookConnectionsForLocation,
  listStylebookConnectionsForOrganization,
  listStylebookConnectionsForPerson,
  type Connection,
} from "@/lib/stylebook-api/connections"

/** Max connections fetched before prioritizing neighbors for the graph. */
export const GRAPH_HOP1_FETCH_LIMIT = 128
/** Max unique neighbors rendered in the ego graph. */
export const GRAPH_HOP1_DISPLAY_CAP = 32

export type GraphHop = 0 | 1

export interface GraphEntityRef {
  entityType: EntityType
  entityId: string
  displayName: string
}

export interface ConnectionNeighborhood {
  connections: Connection[]
  /** Total open connections for the center entity (from API). */
  totalCount: number
  /** Unique neighbors represented in `connections`. */
  displayedNeighborCount: number
  /** Unique neighbors omitted because of `GRAPH_HOP1_DISPLAY_CAP`. */
  skippedNeighborCount: number
}

export const EMPTY_CONNECTION_NEIGHBORHOOD: ConnectionNeighborhood = {
  connections: [],
  totalCount: 0,
  displayedNeighborCount: 0,
  skippedNeighborCount: 0,
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

function neighborDisplayPriority(ref: GraphEntityRef): number {
  if (ref.entityType === "organization") return 0
  if (ref.entityType === "person") return 1
  if (ref.entityType === "location") return 2
  return 3
}

export function selectConnectionsForGraphDisplay(
  connections: Connection[],
  center: GraphEntityRef,
  cap: number = GRAPH_HOP1_DISPLAY_CAP,
): {
  selected: Connection[]
  displayedNeighborCount: number
  skippedNeighborCount: number
} {
  const byNeighbor = new Map<string, { ref: GraphEntityRef; connections: Connection[] }>()
  for (const conn of connections) {
    const neighbor = neighborFromConnection(conn, center)
    if (!neighbor) continue
    const key = entityRefKey(neighbor)
    const bucket = byNeighbor.get(key)
    if (bucket) {
      bucket.connections.push(conn)
    } else {
      byNeighbor.set(key, { ref: neighbor, connections: [conn] })
    }
  }

  const groups = Array.from(byNeighbor.values()).sort((a, b) => {
    const priority = neighborDisplayPriority(a.ref) - neighborDisplayPriority(b.ref)
    if (priority !== 0) return priority
    return a.ref.displayName.localeCompare(b.ref.displayName, undefined, {
      sensitivity: "base",
    })
  })

  const picked = groups.slice(0, cap)
  const skippedNeighborCount = Math.max(0, groups.length - picked.length)
  return {
    selected: picked.flatMap((group) => group.connections),
    displayedNeighborCount: picked.length,
    skippedNeighborCount,
  }
}

async function listConnectionsForEntity(
  stylebookSlug: string,
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
  options: { limit: number; includeClosed?: boolean },
): Promise<{ connections: Connection[]; total: number }> {
  const canonicalId = String(ref.entityId)
  const fetchOptions = { limit: options.limit, offset: 0, includeClosed: options.includeClosed }
  if (ref.entityType === "person") {
    const res = await listStylebookConnectionsForPerson(stylebookSlug, canonicalId, fetchOptions)
    return { connections: res.connections, total: res.total }
  }
  if (ref.entityType === "organization") {
    const res = await listStylebookConnectionsForOrganization(
      stylebookSlug,
      canonicalId,
      fetchOptions,
    )
    return { connections: res.connections, total: res.total }
  }
  if (ref.entityType === "location") {
    const res = await listStylebookConnectionsForLocation(stylebookSlug, canonicalId, fetchOptions)
    return { connections: res.connections, total: res.total }
  }
  return { connections: [], total: 0 }
}

export async function fetchConnectionNeighborhood(
  stylebookSlug: string,
  center: GraphEntityRef,
  options?: {
    includeClosed?: boolean
    displayCap?: number
  },
): Promise<ConnectionNeighborhood> {
  const { connections: fetched, total } = await listConnectionsForEntity(stylebookSlug, center, {
    limit: GRAPH_HOP1_FETCH_LIMIT,
    includeClosed: options?.includeClosed,
  })

  const { selected, displayedNeighborCount, skippedNeighborCount } =
    selectConnectionsForGraphDisplay(fetched, center, options?.displayCap ?? GRAPH_HOP1_DISPLAY_CAP)

  return {
    connections: selected,
    totalCount: total,
    displayedNeighborCount,
    skippedNeighborCount,
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
  return connectionTouchesEntity(conn, center) ? 1 : 0
}

export const GRAPH_NODE_LAYOUT_WIDTH = 176
export const GRAPH_NODE_LAYOUT_HEIGHT = 56
const GRAPH_GRID_GAP_X = 28
const GRAPH_GRID_GAP_Y = 36

export function gridColumns(count: number): number {
  if (count <= 1) return 1
  if (count <= 4) return 2
  if (count <= 9) return 3
  if (count <= 16) return 4
  if (count <= 25) return 5
  return 6
}

function gridWidth(cols: number, count: number): number {
  const itemsInWidestRow = Math.min(cols, count)
  if (itemsInWidestRow <= 1) return GRAPH_NODE_LAYOUT_WIDTH
  return (
    (itemsInWidestRow - 1) * (GRAPH_NODE_LAYOUT_WIDTH + GRAPH_GRID_GAP_X) +
    GRAPH_NODE_LAYOUT_WIDTH
  )
}

function gridHeight(rows: number): number {
  if (rows <= 1) return GRAPH_NODE_LAYOUT_HEIGHT
  return (rows - 1) * (GRAPH_NODE_LAYOUT_HEIGHT + GRAPH_GRID_GAP_Y) + GRAPH_NODE_LAYOUT_HEIGHT
}

/** Place neighbor node centers in a compact grid above the subject. */
export function layoutNeighborGrid(
  neighborKeys: string[],
  centerX: number,
  topY: number,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  if (neighborKeys.length === 0) return positions

  const cols = gridColumns(neighborKeys.length)
  const rows = Math.ceil(neighborKeys.length / cols)

  neighborKeys.forEach((key, index) => {
    const row = Math.floor(index / cols)
    const col = index % cols
    const itemsInRow = Math.min(cols, neighborKeys.length - row * cols)
    const rowWidth = gridWidth(cols, itemsInRow)
    const x = centerX - rowWidth / 2 + col * (GRAPH_NODE_LAYOUT_WIDTH + GRAPH_GRID_GAP_X)
    const y = topY + row * (GRAPH_NODE_LAYOUT_HEIGHT + GRAPH_GRID_GAP_Y)
    positions.set(key, { x, y })
  })

  return positions
}

export function egoGraphLayoutMetrics(neighborCount: number): {
  centerX: number
  centerY: number
  neighborTopY: number
  canvasMinHeight: number
} {
  const cols = gridColumns(neighborCount)
  const rows = Math.max(1, Math.ceil(Math.max(neighborCount, 1) / cols))
  const neighborGridHeight = gridHeight(rows)
  const centerX = 500
  const neighborTopY = 48
  const centerY =
    neighborTopY + neighborGridHeight + GRAPH_NODE_LAYOUT_HEIGHT + GRAPH_GRID_GAP_Y + 24
  const canvasMinHeight = centerY + GRAPH_NODE_LAYOUT_HEIGHT + 48
  return { centerX, centerY, neighborTopY, canvasMinHeight }
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
