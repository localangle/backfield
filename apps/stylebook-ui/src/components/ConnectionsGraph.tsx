import { memo, useCallback, useEffect, useMemo, useState } from "react"
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Edge,
  Handle,
  MarkerType,
  Node,
  NodeProps,
  Position,
  useEdgesState,
  useNodesState,
} from "reactflow"
import "reactflow/dist/style.css"
import { Building2, MapPin, User } from "lucide-react"

import ConnectionGraphDetailPanel, {
  type GraphSelection,
} from "@/components/ConnectionGraphDetailPanel"
import type { GraphEntityProfileLines } from "@/lib/connectionGraphEntityProfile"
import {
  classifyConnectionHop,
  entityRefKey,
  type ConnectionNeighborhood,
  type GraphEntityRef,
  type GraphHop,
} from "@/lib/connectionGraph"
import { cn } from "@/lib/utils"
import { formatConnectionSummaryLabel } from "@/lib/connectionEvidence"
import type { Connection } from "@/lib/stylebook-api/connections"
import type { EntityType as ConnectionsEntityType } from "@/lib/entityTypes"
import { entityDisplayName as catalogEntityLabel } from "@/lib/entityRegistry"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"

const LAYOUT_CENTER_X = 500
const NODE_LAYOUT_WIDTH = 176
const NODE_LAYOUT_HEIGHT = 56
const HOP_GAP_X = 28
const HOP_GAP_Y = 36
const HUB_GAP_X = 72

type ConnectionGraphNodeData = {
  label: string
  entityType: ConnectionsEntityType
  hop: GraphHop
  isCenter: boolean
  isSelected: boolean
}

const ENTITY_ICON: Record<ConnectionsEntityType, typeof User> = {
  person: User,
  organization: Building2,
  location: MapPin,
  work: Building2,
}

const ENTITY_RING_CLASS: Record<ConnectionsEntityType, string> = {
  person: "border-sky-200 bg-sky-50 text-sky-950",
  organization: "border-violet-200 bg-violet-50 text-violet-950",
  location: "border-emerald-200 bg-emerald-50 text-emerald-950",
  work: "border-amber-200 bg-amber-50 text-amber-950",
}

function nodeId(entityType: string, entityId: string | number): string {
  return `${entityType}-${entityId}`
}

function parseNodeId(id: string): { entityType: ConnectionsEntityType; entityId: string } | null {
  const match = id.match(/^(person|location|organization|work)-(.+)$/)
  if (!match) return null
  return { entityType: match[1] as ConnectionsEntityType, entityId: match[2] }
}

function connectionEdgeLabel(conn: Connection): string {
  const nature = conn.nature?.trim().replace(/_/g, " ")
  if (nature) return nature
  const summary = formatConnectionSummaryLabel(conn)
  return summary.length > 36 ? `${summary.slice(0, 33)}…` : summary
}

function entityFromConnectionEnd(
  conn: Connection,
  side: "from" | "to",
): GraphEntityRef {
  if (side === "from") {
    return {
      entityType: conn.from_entity_type as ConnectionsEntityType,
      entityId: String(conn.from_entity_id),
      displayName: conn.from_display_name,
    }
  }
  return {
    entityType: conn.to_entity_type as ConnectionsEntityType,
    entityId: String(conn.to_entity_id),
    displayName: conn.to_display_name,
  }
}

function hop1AnchorKey(
  hop2Key: string,
  connections: Connection[],
  center: GraphEntityRef,
  hop1Keys: ReadonlySet<string>,
): string | null {
  for (const conn of connections) {
    if (classifyConnectionHop(conn, center) !== 2) continue
    const ends = [entityFromConnectionEnd(conn, "from"), entityFromConnectionEnd(conn, "to")]
    if (!ends.some((end) => entityRefKey(end) === hop2Key)) continue
    for (const end of ends) {
      const key = entityRefKey(end)
      if (hop1Keys.has(key)) return key
    }
  }
  return null
}

function gridColumns(count: number): number {
  if (count <= 1) return 1
  if (count <= 4) return 2
  if (count <= 9) return 3
  if (count <= 16) return 4
  if (count <= 25) return 5
  return 6
}

function gridWidth(cols: number, count: number): number {
  const itemsInWidestRow = Math.min(cols, count)
  if (itemsInWidestRow <= 1) return NODE_LAYOUT_WIDTH
  return (itemsInWidestRow - 1) * (NODE_LAYOUT_WIDTH + HOP_GAP_X) + NODE_LAYOUT_WIDTH
}

function gridHeight(rows: number): number {
  if (rows <= 1) return NODE_LAYOUT_HEIGHT
  return (rows - 1) * (NODE_LAYOUT_HEIGHT + HOP_GAP_Y) + NODE_LAYOUT_HEIGHT
}

function layoutGrid(
  keys: string[],
  centerX: number,
  topY: number,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  if (keys.length === 0) return positions

  const cols = gridColumns(keys.length)
  const rows = Math.ceil(keys.length / cols)

  keys.forEach((key, index) => {
    const row = Math.floor(index / cols)
    const col = index % cols
    const itemsInRow = Math.min(cols, keys.length - row * cols)
    const rowWidth = gridWidth(cols, itemsInRow)
    const x = centerX - rowWidth / 2 + col * (NODE_LAYOUT_WIDTH + HOP_GAP_X)
    const y = topY + row * (NODE_LAYOUT_HEIGHT + HOP_GAP_Y)
    positions.set(key, { x, y })
  })

  return positions
}

function buildGraphLayout(
  center: GraphEntityRef,
  connections: Connection[],
  selection: GraphSelection | null,
): { nodes: Node<ConnectionGraphNodeData>[]; edges: Edge[] } {
  const centerKey = entityRefKey(center)
  const nodeMeta = new Map<string, { ref: GraphEntityRef; hop: GraphHop }>()

  nodeMeta.set(centerKey, { ref: center, hop: 0 })

  for (const conn of connections) {
    const hop = classifyConnectionHop(conn, center)
    const ends = [entityFromConnectionEnd(conn, "from"), entityFromConnectionEnd(conn, "to")]
    for (const end of ends) {
      const key = entityRefKey(end)
      if (key === centerKey) continue
      const existing = nodeMeta.get(key)
      const nextHop = hop === 1 ? 1 : Math.max(existing?.hop ?? 2, 2)
      if (!existing) {
        nodeMeta.set(key, { ref: end, hop: nextHop as GraphHop })
      } else if (nextHop < existing.hop) {
        nodeMeta.set(key, { ...existing, hop: nextHop as GraphHop })
      }
    }
  }

  const hop1Keys = Array.from(nodeMeta.entries())
    .filter(([, meta]) => meta.hop === 1)
    .map(([key]) => key)
    .sort((a, b) =>
      (nodeMeta.get(a)?.ref.displayName ?? "").localeCompare(
        nodeMeta.get(b)?.ref.displayName ?? "",
        undefined,
        { sensitivity: "base" },
      ),
    )

  const hop2Keys = Array.from(nodeMeta.entries())
    .filter(([, meta]) => meta.hop === 2)
    .map(([key]) => key)

  const hop1KeySet = new Set(hop1Keys)
  const hop2ByHop1 = new Map<string, string[]>()
  const orphanHop2: string[] = []

  for (const key of hop2Keys) {
    const anchor = hop1AnchorKey(key, connections, center, hop1KeySet)
    if (anchor) {
      const bucket = hop2ByHop1.get(anchor) ?? []
      bucket.push(key)
      hop2ByHop1.set(anchor, bucket)
    } else {
      orphanHop2.push(key)
    }
  }

  for (const [anchor, group] of hop2ByHop1) {
    group.sort((a, b) =>
      (nodeMeta.get(a)?.ref.displayName ?? "").localeCompare(
        nodeMeta.get(b)?.ref.displayName ?? "",
        undefined,
        { sensitivity: "base" },
      ),
    )
    hop2ByHop1.set(anchor, group)
  }
  orphanHop2.sort((a, b) =>
    (nodeMeta.get(a)?.ref.displayName ?? "").localeCompare(
      nodeMeta.get(b)?.ref.displayName ?? "",
      undefined,
      { sensitivity: "base" },
    ),
  )

  type HubPlan = {
    hop1Key: string
    hop2Keys: string[]
    cols: number
    rows: number
    width: number
    height: number
  }

  const hubPlans: HubPlan[] = hop1Keys.map((hop1Key) => {
    const group = hop2ByHop1.get(hop1Key) ?? []
    const cols = gridColumns(group.length)
    const rows = Math.max(1, Math.ceil(group.length / cols))
    return {
      hop1Key,
      hop2Keys: group,
      cols,
      rows: group.length === 0 ? 0 : rows,
      width: gridWidth(cols, group.length),
      height: group.length === 0 ? 0 : gridHeight(rows),
    }
  })

  if (orphanHop2.length > 0) {
    const cols = gridColumns(orphanHop2.length)
    const rows = Math.ceil(orphanHop2.length / cols)
    hubPlans.push({
      hop1Key: "__orphans__",
      hop2Keys: orphanHop2,
      cols,
      rows,
      width: gridWidth(cols, orphanHop2.length),
      height: gridHeight(rows),
    })
  }

  hubPlans.sort((a, b) => b.hop2Keys.length - a.hop2Keys.length)

  const totalHubWidth = hubPlans.reduce(
    (sum, plan, index) => sum + plan.width + (index > 0 ? HUB_GAP_X : 0),
    0,
  )
  const maxHop2Height = Math.max(0, ...hubPlans.map((plan) => plan.height))
  const centerY = 120 + maxHop2Height + NODE_LAYOUT_HEIGHT + HOP_GAP_Y + NODE_LAYOUT_HEIGHT + 48
  const hop1Y = centerY - NODE_LAYOUT_HEIGHT - HOP_GAP_Y - NODE_LAYOUT_HEIGHT
  const hop2TopY = 80

  const positions = new Map<string, { x: number; y: number }>()
  positions.set(centerKey, { x: LAYOUT_CENTER_X, y: centerY })

  let cursorX = LAYOUT_CENTER_X - totalHubWidth / 2
  for (const plan of hubPlans) {
    const hubX = cursorX + plan.width / 2

    if (plan.hop1Key !== "__orphans__") {
      positions.set(plan.hop1Key, { x: hubX, y: hop1Y })
    }

    if (plan.hop2Keys.length > 0) {
      const gridPositions = layoutGrid(plan.hop2Keys, hubX, hop2TopY)
      for (const [key, pos] of gridPositions) {
        positions.set(key, pos)
      }
    }

    cursorX += plan.width + HUB_GAP_X
  }

  // Single hop-1 with no hop-2: keep hub centered above subject.
  if (hop1Keys.length === 1 && hop2Keys.length === 0) {
    positions.set(hop1Keys[0], { x: LAYOUT_CENTER_X, y: hop1Y })
  }

  const selectedNodeId =
    selection?.kind === "node"
      ? nodeId(selection.entityType, selection.entityId)
      : null
  const selectedConnectionId = selection?.kind === "edge" ? selection.connectionId : null

  const nodes: Node<ConnectionGraphNodeData>[] = Array.from(nodeMeta.entries()).map(
    ([key, meta]) => {
      const colon = key.indexOf(":")
      const entityType = key.slice(0, colon) as ConnectionsEntityType
      const entityId = key.slice(colon + 1)
      const pos = positions.get(key) ?? { x: LAYOUT_CENTER_X, y: centerY }
      const id = nodeId(entityType, entityId)
      return {
        id,
        type: "connectionGraph",
        position: { x: pos.x - NODE_LAYOUT_WIDTH / 2, y: pos.y - NODE_LAYOUT_HEIGHT / 2 },
        data: {
          label: meta.ref.displayName,
          entityType,
          hop: meta.hop,
          isCenter: key === centerKey,
          isSelected: id === selectedNodeId,
        },
        selected: id === selectedNodeId,
      }
    },
  )

  const edges: Edge[] = connections.map((conn) => {
    const hop = classifyConnectionHop(conn, center)
    const summary = formatConnectionSummaryLabel(conn)
    const showLabel = hop === 1
    const isSelected = selectedConnectionId === conn.id
    const strokeColor =
      hop === 1 ? "hsl(var(--primary))" : "hsl(var(--muted-foreground) / 0.45)"
    return {
      id: `e-${conn.id}`,
      source: nodeId(conn.from_entity_type, conn.from_entity_id),
      target: nodeId(conn.to_entity_type, conn.to_entity_id),
      label: showLabel ? connectionEdgeLabel(conn) : undefined,
      title: summary,
      type: "smoothstep",
      pathOptions: { borderRadius: 16, offset: hop === 1 ? 12 : 4 },
      animated: false,
      selected: isSelected,
      style: {
        stroke: strokeColor,
        strokeWidth: isSelected ? (hop === 1 ? 3 : 2) : hop === 1 ? 2 : 1,
        opacity: isSelected ? 1 : hop === 1 ? 1 : 0.7,
      },
      labelStyle: showLabel
        ? {
            fill: "hsl(var(--foreground))",
            fontSize: 11,
            fontWeight: 600,
          }
        : undefined,
      labelBgStyle: showLabel
        ? {
            fill: "hsl(var(--background))",
            fillOpacity: 0.95,
          }
        : undefined,
      labelBgPadding: showLabel ? ([8, 4] as [number, number]) : undefined,
      labelBgBorderRadius: showLabel ? 6 : undefined,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: hop === 1 ? 16 : 12,
        height: hop === 1 ? 16 : 12,
      },
    }
  })

  return { nodes, edges }
}

const ConnectionGraphNode = memo(function ConnectionGraphNode({
  data,
}: NodeProps<ConnectionGraphNodeData>) {
  const Icon = ENTITY_ICON[data.entityType]
  const typeLabel = catalogEntityLabel(data.entityType)
  const isLeaf = data.hop === 2
  return (
    <div
      className={cn(
        "w-[176px] rounded-xl border px-3 py-2 shadow-sm transition-shadow hover:shadow-md",
        data.isCenter
          ? "border-primary bg-primary text-primary-foreground ring-2 ring-primary/20"
          : ENTITY_RING_CLASS[data.entityType],
        data.isSelected && !data.isCenter && "ring-2 ring-primary/50 shadow-md",
        isLeaf && "opacity-95",
      )}
    >
      <Handle
        type="target"
        position={Position.Bottom}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/40"
      />
      <div className="flex items-start gap-2">
        <div
          className={cn(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
            data.isCenter ? "bg-primary-foreground/15" : "bg-background/80",
          )}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden />
        </div>
        <div className="min-w-0">
          <div
            className={cn(
              "text-[10px] font-medium uppercase tracking-wide",
              data.isCenter ? "text-primary-foreground/80" : "text-muted-foreground",
            )}
          >
            {typeLabel}
          </div>
          <div
            className={cn(
              "text-sm font-semibold leading-snug line-clamp-2",
              data.isCenter ? "text-primary-foreground" : "text-foreground",
            )}
            title={data.label}
          >
            {data.label}
          </div>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Top}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/40"
      />
    </div>
  )
})

const nodeTypes = { connectionGraph: ConnectionGraphNode }

interface ConnectionsGraphProps {
  entityType: ConnectionsEntityType
  entityId: string | number
  entityDisplayName: string
  stylebookSlug: string
  projectSlug?: string
  centerProfileLines?: GraphEntityProfileLines
  neighborhood: ConnectionNeighborhood
}

export default function ConnectionsGraph({
  entityType,
  entityId,
  entityDisplayName,
  stylebookSlug,
  projectSlug,
  centerProfileLines,
  neighborhood,
}: ConnectionsGraphProps) {
  const { catalogScopeSuffix, catalogBasePath } = useProjectCatalogScope()
  const [selection, setSelection] = useState<GraphSelection | null>(null)
  const center: GraphEntityRef = useMemo(
    () => ({
      entityType,
      entityId: String(entityId),
      displayName: entityDisplayName,
    }),
    [entityType, entityId, entityDisplayName],
  )

  const connectionsById = useMemo(
    () => new Map(neighborhood.connections.map((conn) => [conn.id, conn])),
    [neighborhood.connections],
  )

  const { initialNodes, initialEdges, statsLine } = useMemo(() => {
    const layout = buildGraphLayout(center, neighborhood.connections, selection)
    const statsParts = [`${neighborhood.hop1ConnectionCount} direct`]
    if (neighborhood.hop2ConnectionCount > 0) {
      statsParts.push(`${neighborhood.hop2ConnectionCount} extended`)
    }
    if (neighborhood.neighborsSkipped > 0) {
      statsParts.push(`${neighborhood.neighborsSkipped} neighbors not expanded`)
    }
    return {
      initialNodes: layout.nodes,
      initialEdges: layout.edges,
      statsLine: statsParts.join(" · "),
    }
  }, [center, neighborhood, selection])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setSelection(null)
  }, [center.entityType, center.entityId, neighborhood.connections])

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node<ConnectionGraphNodeData>) => {
    const parsed = parseNodeId(node.id)
    if (!parsed) return
    setSelection({ kind: "node", entityType: parsed.entityType, entityId: parsed.entityId })
  }, [])

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    const match = edge.id.match(/^e-(\d+)$/)
    if (!match) return
    setSelection({ kind: "edge", connectionId: Number(match[1]) })
  }, [])

  const onPaneClick = useCallback(() => {
    setSelection(null)
  }, [])

  if (neighborhood.connections.length === 0) {
    return (
      <div className="flex h-[320px] items-center justify-center rounded-xl border border-dashed bg-muted/20 text-sm text-muted-foreground">
        No connections yet.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{statsLine}</span>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded bg-primary" />
            Direct
          </span>
          {neighborhood.hop2ConnectionCount > 0 ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 rounded bg-muted-foreground/60" />
              Extended
            </span>
          ) : null}
        </div>
      </div>
      <div className="flex h-[min(560px,68vh)] min-h-[400px] overflow-hidden rounded-xl border bg-gradient-to-b from-muted/15 to-background">
        <div className="connections-graph h-full min-w-0 flex-1 [&_.react-flow__controls-button]:border-border [&_.react-flow__controls-button]:bg-background">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            fitView
            fitViewOptions={{ padding: 0.14, maxZoom: 1 }}
            minZoom={0.12}
            maxZoom={1.2}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            proOptions={{ hideAttribution: true }}
          >
            <Controls showInteractive={false} position="bottom-left" />
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="hsl(var(--border))" />
          </ReactFlow>
        </div>
        {selection ? (
          <ConnectionGraphDetailPanel
            selection={selection}
            center={center}
            connections={neighborhood.connections}
            connectionsById={connectionsById}
            stylebookSlug={stylebookSlug}
            projectSlug={projectSlug}
            centerProfileLines={centerProfileLines}
            catalogBasePath={catalogBasePath}
            catalogScopeSuffix={catalogScopeSuffix}
            onClear={() => setSelection(null)}
            onSelectConnection={(connectionId) =>
              setSelection({ kind: "edge", connectionId })
            }
            onSelectNode={(entityType, entityId) =>
              setSelection({ kind: "node", entityType, entityId })
            }
          />
        ) : null}
      </div>
      <p className="text-[11px] text-muted-foreground">
        Click a node or line for relationship details. Use the panel to browse roles and open
        catalog entries.
      </p>
    </div>
  )
}
