import {
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type MouseEvent,
  type ReactNode,
} from 'react'
import { cn } from '@/lib/utils'
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  Position,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  useUpdateNodeInternals,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type NodeTypes,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { bookendPreviewEdge, withBookendPositions } from '@/lib/flowBuilderLayout'
import { deriveEdges, toReactFlowNodes, type FlowGraphModel } from '@/lib/flowGraphModel'
import { nodeComponents } from '@/nodes/registry'
import {
  GuidedFlowCanvasUiContext,
  useGuidedFlowCanvasUi,
} from '@/components/flow-builder/guidedFlowCanvasUi'
import GuidedCompactNode, {
  GUIDED_COMPACT_NODE_HEIGHT,
  GUIDED_COMPACT_NODE_WIDTH,
} from '@/components/flow-builder/GuidedCompactNode'
import { ArrowLeftRight, Plus, Trash2 } from 'lucide-react'

type NodeBottomHoverButtonProps = {
  ariaLabel: string
  nodeSelected: boolean
  onClick?: () => void
  className?: string
  children: ReactNode
}

/** Circle chrome for add / swap / delete — outlined when the parent node is not selected. */
function nodeActionCircleClass(nodeSelected: boolean, size: 'sm' | 'md'): string {
  return cn(
    'nodrag nopan rounded-full bg-background shadow-sm',
    size === 'md' ? 'h-7 w-7' : 'h-6 w-6',
    nodeSelected ? 'border-2 border-background' : 'border border-border ring-1 ring-border/60',
  )
}

function NodeRightAddButton({
  nodeSelected,
  onClick,
}: {
  nodeSelected: boolean
  onClick?: () => void
}) {
  return (
    <div className="pointer-events-auto absolute right-0 top-1/2 z-20 -translate-y-1/2 translate-x-1/2">
      <Button
        type="button"
        size="icon"
        className={cn(
          nodeActionCircleClass(nodeSelected, 'md'),
          'text-foreground hover:border-primary hover:bg-primary hover:text-primary-foreground hover:ring-primary/30',
        )}
        aria-label="Add next step"
        onClick={(event) => {
          event.stopPropagation()
          onClick?.()
        }}
      >
        <Plus className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}

function NodeBottomHoverButton({
  ariaLabel,
  nodeSelected,
  onClick,
  className,
  children,
}: NodeBottomHoverButtonProps) {
  return (
    <div className="pointer-events-none absolute bottom-0 left-1/2 z-10 -translate-x-1/2 translate-y-1/2 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100">
      <Button
        type="button"
        size="icon"
        className={cn(nodeActionCircleClass(nodeSelected, 'sm'), className)}
        aria-label={ariaLabel}
        onClick={(event) => {
          event.stopPropagation()
          onClick?.()
        }}
      >
        {children}
      </Button>
    </div>
  )
}

type GuidedNodeShellProps = NodeProps & {
  showAddButton: boolean
  onAddClick?: () => void
  showDeleteButton: boolean
  onDeleteClick?: () => void
  showSwapButton: boolean
  swapAriaLabel?: string
  onSwapClick?: () => void
  NodeComponent: ComponentType<NodeProps>
}

function GuidedNodeShell({
  showAddButton,
  onAddClick,
  showDeleteButton,
  onDeleteClick,
  showSwapButton,
  swapAriaLabel,
  onSwapClick,
  NodeComponent,
  ...nodeProps
}: GuidedNodeShellProps) {
  const guidedMode = Boolean(
    (nodeProps.data as { guidedMode?: boolean } | undefined)?.guidedMode,
  )
  const exitAnimation = Boolean(
    (nodeProps.data as { exitAnimation?: boolean } | undefined)?.exitAnimation,
  )
  const { selectedNodeId } = useGuidedFlowCanvasUi()
  const nodeSelected = Boolean(nodeProps.selected || nodeProps.id === selectedNodeId)

  return (
    <div
      className="group relative overflow-visible"
      style={
        guidedMode
          ? { width: GUIDED_COMPACT_NODE_WIDTH, height: GUIDED_COMPACT_NODE_HEIGHT }
          : undefined
      }
    >
      {guidedMode ? (
        <GuidedCompactNode {...nodeProps} exitAnimation={exitAnimation} />
      ) : (
        <Suspense fallback={<div className="h-16 w-[200px] animate-pulse rounded-lg bg-muted" />}>
          <NodeComponent {...nodeProps} />
        </Suspense>
      )}
      {showAddButton && !exitAnimation && (
        <NodeRightAddButton nodeSelected={nodeSelected} onClick={onAddClick} />
      )}
      {showDeleteButton && !exitAnimation && (
        <NodeBottomHoverButton
          ariaLabel="Remove step"
          nodeSelected={nodeSelected}
          onClick={onDeleteClick}
          className="text-destructive hover:border-destructive hover:bg-destructive hover:text-destructive-foreground hover:ring-destructive/30"
        >
          <Trash2 className="h-3 w-3" />
        </NodeBottomHoverButton>
      )}
      {showSwapButton && !exitAnimation && (
        <NodeBottomHoverButton
          ariaLabel={swapAriaLabel ?? 'Change bookend'}
          nodeSelected={nodeSelected}
          onClick={onSwapClick}
          className="text-foreground hover:border-primary hover:bg-primary hover:text-primary-foreground hover:ring-primary/30"
        >
          <ArrowLeftRight className="h-3 w-3" />
        </NodeBottomHoverButton>
      )}
    </div>
  )
}

/** Matches NodePanel (`w-96`) so fitView leaves room when the side panel is open. */
export const GUIDED_FLOW_NODE_PANEL_WIDTH_PX = 384

const FIT_VIEW_PAD_PX = 32
const GUIDED_NODE_EXIT_MS = 440
const GUIDED_NODE_ENTER_MS = 520
const FIT_DURATION_GRAPH_CHANGE_MS = 500
const FIT_DURATION_PANEL_MS = 300

const SOLID_EDGE_STYLE = { stroke: '#000000', strokeWidth: 1 }
const SOLID_EDGE_MARKER = {
  type: MarkerType.ArrowClosed,
  color: '#000000',
  width: 18,
  height: 18,
}

/** Scaffold edges omit handle ids so React Flow uses node sides (stable in guided compact layout). */
function toGuidedScaffoldEdge(edge: {
  id: string
  source: string
  target: string
}): Edge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'smoothstep',
    animated: false,
    markerEnd: SOLID_EDGE_MARKER,
    style: SOLID_EDGE_STYLE,
  }
}

function buildModelNodes(
  scaffoldModel: FlowGraphModel | null,
  inputNode: Node | null,
  outputNode: Node | null,
  allowNodeDrag: boolean,
): Node[] {
  const base = scaffoldModel
    ? toReactFlowNodes(scaffoldModel)
    : withBookendPositions(inputNode, outputNode)

  return base.map((node) => ({
    id: node.id,
    type: node.type,
    position: node.position ?? { x: 0, y: 0 },
    data: { ...node.data, guidedMode: true },
    draggable: allowNodeDrag,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    width: GUIDED_COMPACT_NODE_WIDTH,
    height: GUIDED_COMPACT_NODE_HEIGHT,
  }))
}

type GuidedFlowCanvasProps = {
  inputNode?: Node | null
  outputNode?: Node | null
  scaffoldModel?: FlowGraphModel | null
  readOnly?: boolean
  showEmptyMiddleCta?: boolean
  onEmptyMiddleCtaDismiss?: () => void
  allowAddNodes?: boolean
  allowNodeDrag?: boolean
  allowDeleteNodes?: boolean
  deletableNodeIds?: ReadonlySet<string>
  allowBookendSwap?: boolean
  inputBookendId?: string | null
  outputBookendId?: string | null
  reserveRightPx?: number
  selectedNodeId?: string | null
  onAddNodeClick?: (parentNodeId: string) => void
  onDeleteNodeClick?: (nodeId: string) => void
  onSwapInputBookend?: () => void
  onSwapOutputBookend?: () => void
  onNodeClick?: (node: Node) => void
  onNodePositionChange?: (nodeId: string, position: { x: number; y: number }) => void
}

function GuidedFlowCanvasInner({
  inputNode = null,
  outputNode = null,
  scaffoldModel = null,
  readOnly = false,
  showEmptyMiddleCta = false,
  onEmptyMiddleCtaDismiss,
  allowAddNodes = false,
  allowNodeDrag = false,
  allowDeleteNodes = false,
  deletableNodeIds,
  allowBookendSwap = false,
  inputBookendId: inputBookendIdProp = null,
  outputBookendId: outputBookendIdProp = null,
  reserveRightPx = 0,
  selectedNodeId = null,
  onAddNodeClick,
  onDeleteNodeClick,
  onSwapInputBookend,
  onSwapOutputBookend,
  onNodeClick,
  onNodePositionChange,
}: GuidedFlowCanvasProps) {
  const { fitView, getNodes } = useReactFlow()
  const updateNodeInternals = useUpdateNodeInternals()
  const containerRef = useRef<HTMLDivElement>(null)
  const inputBookendId =
    inputBookendIdProp ?? scaffoldModel?.inputNode.id ?? inputNode?.id ?? null
  const outputBookendId =
    outputBookendIdProp ?? scaffoldModel?.outputNode.id ?? outputNode?.id ?? null
  const prevNodeIdsRef = useRef<Set<string> | null>(null)
  const prevModelNodesRef = useRef<Node[]>([])
  const isDraggingRef = useRef(false)
  const isFirstLayoutFitRef = useRef(true)
  const [enteringNodeIds, setEnteringNodeIds] = useState<Set<string>>(() => new Set())
  const [exitingNodes, setExitingNodes] = useState<Map<string, Node>>(() => new Map())

  const nodeTypes: NodeTypes = useMemo(() => {
    const wrapped: NodeTypes = {}
    for (const [type, LazyComponent] of Object.entries(nodeComponents)) {
      wrapped[type] = (props: NodeProps) => {
        const isOutputBookendNode = outputBookendId != null && props.id === outputBookendId
        const showAddButton = Boolean(
          allowAddNodes && onAddNodeClick && !isOutputBookendNode && !readOnly,
        )
        const showDeleteButton = Boolean(
          allowDeleteNodes &&
            onDeleteNodeClick &&
            deletableNodeIds?.has(props.id) &&
            !readOnly,
        )
        const isInputBookend = inputBookendId != null && props.id === inputBookendId
        const showSwapButton = Boolean(
          allowBookendSwap &&
            !readOnly &&
            ((isInputBookend && onSwapInputBookend) || (isOutputBookendNode && onSwapOutputBookend)),
        )
        return (
          <GuidedNodeShell
            {...props}
            NodeComponent={LazyComponent as ComponentType<NodeProps>}
            showAddButton={showAddButton}
            onAddClick={() => onAddNodeClick?.(props.id)}
            showDeleteButton={showDeleteButton}
            onDeleteClick={() => onDeleteNodeClick?.(props.id)}
            showSwapButton={showSwapButton}
            swapAriaLabel={isInputBookend ? 'Change source' : 'Change destination'}
            onSwapClick={
              isInputBookend
                ? onSwapInputBookend
                : isOutputBookendNode
                  ? onSwapOutputBookend
                  : undefined
            }
          />
        )
      }
    }
    return wrapped
  }, [
    allowAddNodes,
    allowBookendSwap,
    allowDeleteNodes,
    deletableNodeIds,
    inputBookendId,
    onAddNodeClick,
    onDeleteNodeClick,
    onSwapInputBookend,
    onSwapOutputBookend,
    outputBookendId,
    readOnly,
  ])

  const nodesLayoutKey = useMemo(() => {
    if (scaffoldModel) {
      const middlePositions = scaffoldModel.middleNodes
        .map((n) => `${n.id}:${n.position?.x ?? ''}:${n.position?.y ?? ''}`)
        .join('|')
      return [
        scaffoldModel.middleNodes.length,
        middlePositions,
        scaffoldModel.outputNode.position?.x ?? 0,
        scaffoldModel.outputNode.position?.y ?? 0,
        scaffoldModel.inputNode.position?.x ?? 0,
        scaffoldModel.inputNode.position?.y ?? 0,
      ].join(':')
    }
    return `${inputNode?.id ?? ''}:${outputNode?.id ?? ''}`
  }, [scaffoldModel, inputNode?.id, outputNode?.id])

  const graphNodeIdsKey = useMemo(() => {
    if (scaffoldModel) {
      return [
        scaffoldModel.inputNode.id,
        ...scaffoldModel.middleNodes.map((n) => n.id),
        scaffoldModel.outputNode.id,
      ].join(',')
    }
    return [inputNode?.id, outputNode?.id].filter(Boolean).join(',')
  }, [scaffoldModel, inputNode?.id, outputNode?.id])

  const graphNodeContentKey = useMemo(() => {
    const nodes = scaffoldModel
      ? [scaffoldModel.inputNode, ...scaffoldModel.middleNodes, scaffoldModel.outputNode]
      : [inputNode, outputNode].filter((node): node is Node => node != null)

    return nodes
      .map((node) =>
        [
          node.id,
          node.type ?? '',
          JSON.stringify(node.data ?? {}),
        ].join(':'),
      )
      .join('|')
  }, [inputNode, outputNode, scaffoldModel])

  const modelNodes = useMemo(
    () => buildModelNodes(scaffoldModel, inputNode, outputNode, allowNodeDrag),
    [allowNodeDrag, inputNode, outputNode, nodesLayoutKey, scaffoldModel],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(modelNodes)

  const derivedEdges = useMemo(() => {
    if (scaffoldModel) {
      return deriveEdges(scaffoldModel).map(toGuidedScaffoldEdge)
    }
    if (inputNode && outputNode) {
      const preview = bookendPreviewEdge(inputNode, outputNode)
      return [
        {
          id: preview.id,
          source: preview.source,
          target: preview.target,
          type: 'smoothstep',
          animated: false,
          markerEnd: SOLID_EDGE_MARKER,
          style: SOLID_EDGE_STYLE,
        } satisfies Edge,
      ]
    }
    return []
  }, [inputNode, outputNode, scaffoldModel])

  const displayNodes = useMemo(() => {
    const exiting = [...exitingNodes.values()].map((node) => ({
      ...node,
      position: node.position ?? { x: 0, y: 0 },
      draggable: false,
      selectable: false,
    }))
    return [...nodes, ...exiting]
  }, [exitingNodes, nodes])

  const canvasUi = useMemo(
    () => ({ selectedNodeId, enteringNodeIds }),
    [enteringNodeIds, selectedNodeId],
  )
  const animateGraphChanges = scaffoldModel != null
  const wasAnimatingGraphChangesRef = useRef(animateGraphChanges)

  const remeasureNodes = useCallback(
    (nodeIds: string[]) => {
      if (nodeIds.length === 0) return
      requestAnimationFrame(() => {
        updateNodeInternals(nodeIds)
        requestAnimationFrame(() => {
          updateNodeInternals(nodeIds)
        })
      })
    },
    [updateNodeInternals],
  )
  const remeasureNodesRef = useRef(remeasureNodes)
  remeasureNodesRef.current = remeasureNodes

  const fitGraphInView = useCallback(
    (options?: { duration?: number }) => {
      if (isDraggingRef.current) return
      const el = containerRef.current
      if (!el || modelNodes.length === 0) return
      const w = el.clientWidth
      const h = el.clientHeight
      if (w <= 0 || h <= 0) return

      const duration = options?.duration ?? 0
      const rightInset = reserveRightPx + FIT_VIEW_PAD_PX
      const padding = Math.min(
        0.72,
        Math.max(FIT_VIEW_PAD_PX / Math.min(w, h), rightInset / w),
      )
      fitView({
        padding,
        maxZoom: 1.2,
        duration,
      })
      if (duration > 0) {
        window.setTimeout(() => remeasureNodes(modelNodes.map((node) => node.id)), duration + 32)
      } else {
        remeasureNodes(modelNodes.map((node) => node.id))
      }
    },
    [fitView, modelNodes, remeasureNodes, reserveRightPx],
  )

  const recenterGraph = useCallback(
    (options?: { duration?: number; delayMs?: number }) => {
      if (isDraggingRef.current) return
      const duration = options?.duration ?? FIT_DURATION_GRAPH_CHANGE_MS
      const delayMs = options?.delayMs ?? 0
      const run = () => {
        requestAnimationFrame(() => {
          remeasureNodes(modelNodes.map((node) => node.id))
          requestAnimationFrame(() => {
            fitGraphInView({ duration })
          })
        })
      }
      if (delayMs > 0) {
        window.setTimeout(run, delayMs)
      } else {
        run()
      }
    },
    [fitGraphInView, modelNodes, remeasureNodes],
  )

  const modelNodesRef = useRef(modelNodes)
  modelNodesRef.current = modelNodes

  const prevGraphNodeIdsKeyRef = useRef(graphNodeIdsKey)
  useLayoutEffect(() => {
    const topologyChanged = prevGraphNodeIdsKeyRef.current !== graphNodeIdsKey
    prevGraphNodeIdsKeyRef.current = graphNodeIdsKey

    if (!topologyChanged && isDraggingRef.current) return

    setNodes(modelNodesRef.current)
    remeasureNodesRef.current(modelNodesRef.current.map((node) => node.id))
  }, [graphNodeContentKey, graphNodeIdsKey, nodesLayoutKey, setNodes])

  useEffect(() => {
    const currentIds = new Set(modelNodes.map((node) => node.id))
    const prevIds = prevNodeIdsRef.current
    const isEnteringAnimatedMode = animateGraphChanges && !wasAnimatingGraphChangesRef.current
    wasAnimatingGraphChangesRef.current = animateGraphChanges

    if (prevIds === null || isEnteringAnimatedMode) {
      prevNodeIdsRef.current = currentIds
      prevModelNodesRef.current = modelNodes
      setEnteringNodeIds(new Set())
      setExitingNodes(new Map())
      recenterGraph({ duration: 0 })
      return
    }

    const addedNodeIds = [...currentIds].filter((id) => !prevIds.has(id))
    const removedNodeIds = [...prevIds].filter((id) => !currentIds.has(id))
    prevNodeIdsRef.current = currentIds

    let enterTimer: ReturnType<typeof setTimeout> | undefined
    let exitTimer: ReturnType<typeof setTimeout> | undefined

    if (addedNodeIds.length > 0) {
      if (animateGraphChanges) {
        setEnteringNodeIds(new Set(addedNodeIds))
        recenterGraph({ duration: FIT_DURATION_GRAPH_CHANGE_MS, delayMs: 48 })
        enterTimer = window.setTimeout(() => {
          setEnteringNodeIds(new Set())
          remeasureNodes(modelNodes.map((node) => node.id))
        }, GUIDED_NODE_ENTER_MS)
      } else {
        setEnteringNodeIds(new Set())
        recenterGraph({ duration: 0 })
      }
    }

    if (removedNodeIds.length > 0 && animateGraphChanges) {
      const removedIdSet = new Set(removedNodeIds)
      setExitingNodes((current) => {
        const next = new Map(current)
        for (const snapshot of prevModelNodesRef.current) {
          if (!removedIdSet.has(snapshot.id)) continue
          next.set(snapshot.id, {
            ...snapshot,
            data: {
              ...snapshot.data,
              exitAnimation: true,
            },
          })
        }
        return next
      })

      exitTimer = window.setTimeout(() => {
        setExitingNodes(new Map())
        recenterGraph({ duration: FIT_DURATION_GRAPH_CHANGE_MS, delayMs: 32 })
      }, GUIDED_NODE_EXIT_MS)
    }

    prevModelNodesRef.current = modelNodes

    return () => {
      if (enterTimer != null) window.clearTimeout(enterTimer)
      if (exitTimer != null) window.clearTimeout(exitTimer)
    }
  }, [animateGraphChanges, modelNodes, recenterGraph, remeasureNodes])

  useEffect(() => {
    if (modelNodes.length === 0) return
    const duration =
      isFirstLayoutFitRef.current || !animateGraphChanges ? 0 : FIT_DURATION_GRAPH_CHANGE_MS
    isFirstLayoutFitRef.current = false
    recenterGraph({ duration })
  }, [animateGraphChanges, graphNodeIdsKey, modelNodes.length, recenterGraph])

  const prevReserveRightRef = useRef(reserveRightPx)
  useEffect(() => {
    if (modelNodes.length === 0) return
    if (prevReserveRightRef.current === reserveRightPx) return
    prevReserveRightRef.current = reserveRightPx
    recenterGraph({ duration: FIT_DURATION_PANEL_MS })
  }, [modelNodes.length, recenterGraph, reserveRightPx])

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const filtered = changes.filter((change) => change.type !== 'remove')
      if (filtered.length === 0) return

      for (const change of filtered) {
        if (change.type !== 'position') continue
        if (!('dragging' in change) || change.dragging !== false) {
          isDraggingRef.current = true
        } else {
          isDraggingRef.current = false
        }
      }
      if (allowNodeDrag) {
        onNodesChange(filtered)
      }
    },
    [allowNodeDrag, onNodesChange],
  )

  const onNodeDragStart = useCallback(() => {
    isDraggingRef.current = true
  }, [])

  const onNodeDrag = useCallback(() => {
    isDraggingRef.current = true
  }, [])

  const onNodeDragStop = useCallback(
    (_event: MouseEvent, node: Node) => {
      isDraggingRef.current = false
      const live = getNodes().find((entry) => entry.id === node.id)
      const position = live?.position ?? node.position
      if (position) {
        onNodePositionChange?.(node.id, position)
      }
      remeasureNodes(modelNodesRef.current.map((entry) => entry.id))
    },
    [getNodes, onNodePositionChange, remeasureNodes],
  )

  const handleInit = useCallback(() => {
    remeasureNodes(modelNodes.map((node) => node.id))
  }, [modelNodes, remeasureNodes])

  if (modelNodes.length === 0) {
    return null
  }

  const showScaffoldEmptyCta =
    showEmptyMiddleCta && scaffoldModel != null && scaffoldModel.middleNodes.length === 0

  return (
    <div ref={containerRef} className="guided-flow-canvas relative h-full min-h-0">
      <GuidedFlowCanvasUiContext.Provider value={canvasUi}>
        <Suspense fallback={<div className="flex h-full items-center justify-center">Loading…</div>}>
          <ReactFlow
            nodes={displayNodes}
            edges={derivedEdges}
            onNodesChange={handleNodesChange}
            deleteKeyCode={null}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{
              type: 'smoothstep',
              animated: false,
              markerEnd: SOLID_EDGE_MARKER,
              style: SOLID_EDGE_STYLE,
            }}
            autoPanOnNodeDrag={false}
            onInit={handleInit}
            onNodeDragStart={allowNodeDrag ? onNodeDragStart : undefined}
            onNodeDrag={allowNodeDrag ? onNodeDrag : undefined}
            onNodeDragStop={allowNodeDrag ? onNodeDragStop : undefined}
            onNodeClick={
              onNodeClick
                ? (_event, node) => {
                    onNodeClick(node)
                  }
                : undefined
            }
            maxZoom={1.2}
            nodesDraggable={allowNodeDrag}
            nodesConnectable={false}
            elementsSelectable={!readOnly}
            selectNodesOnDrag={false}
            panOnDrag
            zoomOnScroll
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </Suspense>
      </GuidedFlowCanvasUiContext.Provider>
      {showScaffoldEmptyCta && (
        <button
          type="button"
          className="absolute inset-0 z-20 flex cursor-default items-center justify-center bg-background/75 px-4 backdrop-blur-[1px]"
          aria-label="Dismiss getting started message"
          onClick={() => onEmptyMiddleCtaDismiss?.()}
        >
          <Card
            className="max-w-sm border-dashed bg-background p-6 text-center shadow-md pointer-events-none"
            role="presentation"
          >
            <CardTitle id="empty-flow-cta-title" className="text-base font-medium">
              Add your first step
            </CardTitle>
            <CardDescription className="mt-2 text-sm leading-relaxed">
              Use the plus button on your content source to add a step that processes your content.
            </CardDescription>
          </Card>
        </button>
      )}
    </div>
  )
}

export default function GuidedFlowCanvas(props: GuidedFlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <GuidedFlowCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
