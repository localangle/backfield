import { Suspense, useMemo, type ComponentType } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  NodeToolbar,
  Panel,
  Position,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  type NodeTypes,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { bookendPreviewEdge, withBookendPositions } from '@/lib/flowBuilderLayout'
import {
  deriveEdges,
  isOutputBookendType,
  toReactFlowNodes,
  type FlowGraphEdge,
  type FlowGraphModel,
} from '@/lib/flowGraphModel'
import { nodeComponents } from '@/nodes/registry'
import { Plus } from 'lucide-react'

type GuidedNodeShellProps = NodeProps & {
  showAddButton: boolean
  onAddClick?: () => void
  NodeComponent: ComponentType<NodeProps>
}

function GuidedNodeShell({
  showAddButton,
  onAddClick,
  NodeComponent,
  ...nodeProps
}: GuidedNodeShellProps) {
  return (
    <div className="relative">
      <Suspense fallback={<div className="h-24 w-[280px] animate-pulse rounded-lg bg-muted" />}>
        <NodeComponent {...nodeProps} />
      </Suspense>
      {showAddButton && (
        <NodeToolbar isVisible position={Position.Right} offset={12} align="center">
          <Button
            type="button"
            size="icon"
            className="h-8 w-8 rounded-full shadow-md"
            aria-label="Add next step"
            onClick={(event) => {
              event.stopPropagation()
              onAddClick?.()
            }}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </NodeToolbar>
      )}
    </div>
  )
}

type GuidedSerialEdgeProps = EdgeProps & {
  allowEdgeAdd?: boolean
  onEdgeAddClick?: (sourceId: string, targetId: string) => void
}

function GuidedSerialEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  allowEdgeAdd,
  onEdgeAddClick,
}: GuidedSerialEdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {allowEdgeAdd && onEdgeAddClick && (
        <EdgeLabelRenderer>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="h-7 w-7 rounded-full border shadow-sm"
            aria-label="Insert step here"
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            onClick={(event) => {
              event.stopPropagation()
              onEdgeAddClick(source, target)
            }}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

type GuidedFlowCanvasProps = {
  inputNode?: Node | null
  outputNode?: Node | null
  scaffoldModel?: FlowGraphModel | null
  readOnly?: boolean
  showEmptyMiddleCta?: boolean
  allowAddNodes?: boolean
  onAddNodeClick?: (parentNodeId: string) => void
  onEdgeInsertClick?: (sourceId: string, targetId: string) => void
  onTidyLayout?: () => void
  onNodeClick?: (node: Node) => void
  onNodeDoubleClick?: (node: Node) => void
}

export default function GuidedFlowCanvas({
  inputNode = null,
  outputNode = null,
  scaffoldModel = null,
  readOnly = false,
  showEmptyMiddleCta = false,
  allowAddNodes = false,
  onAddNodeClick,
  onEdgeInsertClick,
  onTidyLayout,
  onNodeClick,
  onNodeDoubleClick,
}: GuidedFlowCanvasProps) {
  const outputBookendId = scaffoldModel?.outputNode.id ?? outputNode?.id ?? null

  const nodeTypes: NodeTypes = useMemo(() => {
    const wrapped: NodeTypes = {}
    for (const [type, LazyComponent] of Object.entries(nodeComponents)) {
      wrapped[type] = (props: NodeProps) => {
        const isOutputBookend =
          props.id === outputBookendId || isOutputBookendType(String(props.type))
        const showAddButton = Boolean(
          allowAddNodes && onAddNodeClick && !isOutputBookend && !readOnly,
        )
        return (
          <GuidedNodeShell
            {...props}
            NodeComponent={LazyComponent as ComponentType<NodeProps>}
            showAddButton={showAddButton}
            onAddClick={() => onAddNodeClick?.(props.id)}
          />
        )
      }
    }
    return wrapped
  }, [allowAddNodes, onAddNodeClick, outputBookendId, readOnly])

  const edgeTypes = useMemo(
    () => ({
      guidedSerial: (props: EdgeProps) => (
        <GuidedSerialEdge
          {...props}
          allowEdgeAdd={Boolean(allowAddNodes && onEdgeInsertClick && !readOnly)}
          onEdgeAddClick={onEdgeInsertClick}
        />
      ),
    }),
    [allowAddNodes, onEdgeInsertClick, readOnly],
  )

  const { nodes, edges } = useMemo(() => {
    if (scaffoldModel) {
      const flowNodes = toReactFlowNodes(scaffoldModel).map((n) => ({
        ...n,
        data: { ...n.data, guidedMode: true },
      }))
      const flowEdges: Edge[] = deriveEdges(scaffoldModel).map((e: FlowGraphEdge) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: e.kind === 'serial' ? 'guidedSerial' : 'default',
        animated: false,
        style:
          e.kind === 'tip'
            ? { strokeDasharray: '6 4', opacity: 0.55 }
            : undefined,
      }))
      return { nodes: flowNodes, edges: flowEdges }
    }

    const bookendNodes = withBookendPositions(inputNode, outputNode).map((n) => ({
      ...n,
      data: { ...n.data, guidedMode: true },
    }))
    const previewEdges =
      showEmptyMiddleCta && inputNode && outputNode
        ? [bookendPreviewEdge(inputNode, outputNode)]
        : []
    return { nodes: bookendNodes, edges: previewEdges }
  }, [scaffoldModel, inputNode, outputNode, showEmptyMiddleCta])

  if (nodes.length === 0) {
    return null
  }

  const showScaffoldEmptyCta =
    showEmptyMiddleCta && scaffoldModel != null && scaffoldModel.middleNodes.length === 0

  return (
    <div className="guided-flow-canvas relative h-full min-h-0">
      <Suspense fallback={<div className="flex h-full items-center justify-center">Loading…</div>}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={
            onNodeClick
              ? (_event, node) => {
                  onNodeClick(node)
                }
              : undefined
          }
          onNodeDoubleClick={
            onNodeDoubleClick
              ? (_event, node) => {
                  onNodeDoubleClick(node)
                }
              : undefined
          }
          fitView
          fitViewOptions={{ padding: 0.35 }}
          maxZoom={1.2}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={!readOnly}
          panOnDrag
          zoomOnScroll
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} />
          <Controls showInteractive={false} />
          {onTidyLayout && scaffoldModel && !readOnly && (
            <Panel position="top-right" className="m-2">
              <Button type="button" variant="outline" size="sm" onClick={onTidyLayout}>
                Tidy layout
              </Button>
            </Panel>
          )}
        </ReactFlow>
      </Suspense>
      {showScaffoldEmptyCta && (
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center px-4"
          aria-hidden
        >
          <Card className="max-w-sm border-dashed bg-background/95 p-6 text-center shadow-sm">
            <CardTitle className="text-base font-medium">Add your first step</CardTitle>
            <CardDescription className="mt-2 text-sm leading-relaxed">
              Use the plus button on your content source to add a step that processes your content.
            </CardDescription>
          </Card>
        </div>
      )}
    </div>
  )
}
