import { useMemo, useEffect, useCallback } from 'react'
import ReactFlow, {
  Node,
  Edge,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import type { Connection } from "@/lib/stylebook-api/connections"
import type { ConnectionsEntityType } from "@/lib/connectionsEntityTypes"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"

const CENTER_X = 280
const CENTER_Y = 200
const RADIUS = 220

function nodeId(entityType: string, entityId: string | number): string {
  return `${entityType}-${entityId}`
}

function getDetailUrl(
  entityType: ConnectionsEntityType,
  entityId: string | number,
  scopeSuffix: string,
): string {
  const base = window.location.origin
  if (entityType === "person") {
    return `${base}/people/canonical/${entityId}${scopeSuffix}`
  }
  if (entityType === "organization") {
    return `${base}/organizations/canonical/${entityId}${scopeSuffix}`
  }
  if (entityType === "work") {
    return `${base}/works/canonical/${entityId}${scopeSuffix}`
  }
  return `${base}/locations/canonical/${entityId}${scopeSuffix}`
}

interface ConnectionsGraphProps {
  entityType: ConnectionsEntityType
  entityId: string | number
  projectSlug: string
  entityDisplayName: string
  connections: Connection[]
}

export default function ConnectionsGraph({
  entityType,
  entityId,
  projectSlug,
  entityDisplayName,
  connections,
}: ConnectionsGraphProps) {
  const { scopeSuffix } = useProjectCatalogScope()
  const { initialNodes, initialEdges } = useMemo(() => {
    const centerId = nodeId(entityType, entityId)
    const nodeMap = new Map<string, string>()
    nodeMap.set(centerId, entityDisplayName)

    const edges: Edge[] = []
    connections.forEach((conn) => {
      const fromId = nodeId(conn.from_entity_type, conn.from_entity_id)
      const toId = nodeId(conn.to_entity_type, conn.to_entity_id)
      nodeMap.set(fromId, conn.from_display_name)
      nodeMap.set(toId, conn.to_display_name)
      edges.push({
        id: `e-${conn.id}`,
        source: fromId,
        target: toId,
        label: conn.nature,
        markerEnd: { type: MarkerType.ArrowClosed },
        type: 'straight',
      })
    })

    const nodeIds = Array.from(nodeMap.keys())
    const centerIndex = nodeIds.indexOf(centerId)
    if (centerIndex !== -1) {
      nodeIds.splice(centerIndex, 1)
      nodeIds.unshift(centerId)
    }

    const nodes: Node[] = nodeIds.map((id, i) => {
      const label = nodeMap.get(id) || id
      if (i === 0) {
        return {
          id,
          type: 'default',
          position: { x: CENTER_X, y: CENTER_Y },
          data: { label },
          style: { fontWeight: 600, background: 'hsl(var(--primary))', color: 'hsl(var(--primary-foreground))' },
        }
      }
      const angle = ((i - 1) / Math.max(1, nodeIds.length - 1)) * 2 * Math.PI - Math.PI / 2
      const x = CENTER_X + RADIUS * Math.cos(angle)
      const y = CENTER_Y + RADIUS * Math.sin(angle)
      return {
        id,
        type: 'default',
        position: { x, y },
        data: { label },
      }
    })

    return { initialNodes: nodes, initialEdges: edges }
  }, [entityType, entityId, entityDisplayName, connections])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const id = node.id
      const match = id.match(/^(person|location|organization)-(\d+)$/)
      if (match) {
        const type = match[1] as ConnectionsEntityType
        const numId = parseInt(match[2], 10)
        window.open(getDetailUrl(type, numId, scopeSuffix), "_blank", "noopener,noreferrer")
      }
    },
    [scopeSuffix]
  )

  if (connections.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center rounded-md border bg-muted/30 text-muted-foreground">
        No connections yet.
      </div>
    )
  }

  return (
    <div className="connections-graph h-[400px] w-full rounded-md border bg-background [&_.react-flow__handle]:hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        proOptions={{ hideAttribution: true }}
      >
        <Controls />
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
      </ReactFlow>
    </div>
  )
}
