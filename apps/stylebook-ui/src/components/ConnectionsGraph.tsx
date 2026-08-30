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
  bundleEdgeLabel,
  egoGraphLayoutMetrics,
  entityRefKey,
  GRAPH_NODE_LAYOUT_HEIGHT,
  GRAPH_NODE_LAYOUT_WIDTH,
  groupConnectionsByDirectedEdge,
  layoutNeighborGrid,
  neighborFromConnection,
  type ConnectionNeighborhood,
  type GraphEntityRef,
  type GraphHop,
} from "@/lib/connectionGraph"
import { cn } from "@/lib/utils"
import type { Connection } from "@/lib/stylebook-api/connections"
import type { EntityType as ConnectionsEntityType } from "@/lib/entityTypes"
import { entityDisplayName as catalogEntityLabel } from "@/lib/entityRegistry"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"

type ConnectionGraphNodeData = {
  label: string
  entityType: ConnectionsEntityType
  hop: GraphHop
  isCenter: boolean
  isSelected: boolean
}

function nodeId(entityType: string, entityId: string | number): string {
  return `${entityType}-${entityId}`
}

function parseNodeId(id: string): { entityType: ConnectionsEntityType; entityId: string } | null {
  const match = id.match(/^(person|location|organization|work)-(.+)$/)
  if (!match) return null
  return { entityType: match[1] as ConnectionsEntityType, entityId: match[2] }
}

function buildGraphLayout(
  center: GraphEntityRef,
  connections: Connection[],
  selection: GraphSelection | null,
): { nodes: Node<ConnectionGraphNodeData>[]; edges: Edge[] } {
  const centerKey = entityRefKey(center)
  const neighborKeys: string[] = []
  const neighborMeta = new Map<string, GraphEntityRef>()

  for (const conn of connections) {
    const neighbor = neighborFromConnection(conn, center)
    if (!neighbor) continue
    const key = entityRefKey(neighbor)
    if (!neighborMeta.has(key)) {
      neighborMeta.set(key, neighbor)
      neighborKeys.push(key)
    }
  }

  neighborKeys.sort((a, b) =>
    (neighborMeta.get(a)?.displayName ?? "").localeCompare(
      neighborMeta.get(b)?.displayName ?? "",
      undefined,
      { sensitivity: "base" },
    ),
  )

  const { centerX, centerY, neighborTopY } = egoGraphLayoutMetrics(neighborKeys.length)
  const positions = layoutNeighborGrid(neighborKeys, centerX, neighborTopY)
  positions.set(centerKey, { x: centerX, y: centerY })

  const selectedNodeId =
    selection?.kind === "node"
      ? nodeId(selection.entityType, selection.entityId)
      : null
  const selectedConnectionIds =
    selection?.kind === "edge" ? new Set(selection.connectionIds) : null

  const nodes: Node<ConnectionGraphNodeData>[] = [
    {
      id: nodeId(center.entityType, center.entityId),
      type: "connectionGraph",
      position: {
        x: centerX - GRAPH_NODE_LAYOUT_WIDTH / 2,
        y: centerY - GRAPH_NODE_LAYOUT_HEIGHT / 2,
      },
      data: {
        label: center.displayName,
        entityType: center.entityType,
        hop: 0,
        isCenter: true,
        isSelected: selectedNodeId === nodeId(center.entityType, center.entityId),
      },
      selected: selectedNodeId === nodeId(center.entityType, center.entityId),
    },
    ...neighborKeys.map((key) => {
      const ref = neighborMeta.get(key)!
      const pos = positions.get(key) ?? { x: centerX, y: centerY }
      const id = nodeId(ref.entityType, ref.entityId)
      return {
        id,
        type: "connectionGraph" as const,
        position: {
          x: pos.x - GRAPH_NODE_LAYOUT_WIDTH / 2,
          y: pos.y - GRAPH_NODE_LAYOUT_HEIGHT / 2,
        },
        data: {
          label: ref.displayName,
          entityType: ref.entityType,
          hop: 1 as GraphHop,
          isCenter: false,
          isSelected: id === selectedNodeId,
        },
        selected: id === selectedNodeId,
      }
    }),
  ]

  const edges: Edge[] = Array.from(groupConnectionsByDirectedEdge(connections).entries()).map(
    ([bundleKey, bundleConnections]) => {
      const conn = bundleConnections[0]!
      const connectionIds = bundleConnections.map((row) => row.id)
      const isSelected = connectionIds.some((id) => selectedConnectionIds?.has(id))
      const strokeColor = "hsl(var(--primary))"
      return {
        id: `bundle-${bundleKey}`,
        source: nodeId(conn.from_entity_type, conn.from_entity_id),
        target: nodeId(conn.to_entity_type, conn.to_entity_id),
        label: bundleEdgeLabel(bundleConnections),
        data: { connectionIds },
        type: "smoothstep",
        pathOptions: { borderRadius: 16, offset: 12 },
        animated: false,
        selected: isSelected,
        style: {
          stroke: strokeColor,
          strokeWidth: isSelected ? 3 : 2,
          opacity: 1,
        },
        labelStyle: {
          fill: "hsl(var(--foreground))",
          fontSize: 11,
          fontWeight: 600,
        },
        labelBgStyle: {
          fill: "hsl(var(--background))",
          fillOpacity: 0.95,
        },
        labelBgPadding: [8, 4] as [number, number],
        labelBgBorderRadius: 6,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: strokeColor,
          width: 16,
          height: 16,
        },
      }
    },
  )

  return { nodes, edges }
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

const ConnectionGraphNode = memo(function ConnectionGraphNode({
  data,
}: NodeProps<ConnectionGraphNodeData>) {
  const Icon = ENTITY_ICON[data.entityType]
  const typeLabel = catalogEntityLabel(data.entityType)
  return (
    <div
      className={cn(
        "w-[176px] rounded-xl border px-3 py-2 shadow-sm transition-shadow hover:shadow-md",
        data.isCenter
          ? "border-primary bg-primary text-primary-foreground ring-2 ring-primary/20"
          : ENTITY_RING_CLASS[data.entityType],
        data.isSelected && !data.isCenter && "ring-2 ring-primary/50 shadow-md",
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
  onConnectionsChanged?: () => void
}

export default function ConnectionsGraph({
  entityType,
  entityId,
  entityDisplayName,
  stylebookSlug,
  projectSlug,
  centerProfileLines,
  neighborhood,
  onConnectionsChanged,
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

  const { initialNodes, initialEdges } = useMemo(() => {
    const layout = buildGraphLayout(center, neighborhood.connections, selection)
    return {
      initialNodes: layout.nodes,
      initialEdges: layout.edges,
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
    const connectionIds = (edge.data as { connectionIds?: number[] } | undefined)?.connectionIds
    if (!connectionIds?.length) return
    setSelection({ kind: "edge", connectionIds })
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
          onSelectConnection={(connectionIds) =>
            setSelection({ kind: "edge", connectionIds })
          }
          onSelectNode={(entityType, entityId) =>
            setSelection({ kind: "node", entityType, entityId })
          }
          onConnectionsChanged={onConnectionsChanged}
        />
      ) : null}
    </div>
  )
}
