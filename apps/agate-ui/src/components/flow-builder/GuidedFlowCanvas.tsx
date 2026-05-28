import {
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type MouseEvent as ReactMouseEvent,
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
  type NodeDragHandler,
  type NodeProps,
  type NodeTypes,
  type Viewport,
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
  type GuidedFlowCanvasCallbacks,
  type GuidedFlowCanvasUi,
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
  NodeComponent: ComponentType<NodeProps>
}

/**
 * Renders a single React Flow node. Reads every per-render concern (selection,
 * bookend ids, capability flags, callbacks) from the canvas context so the
 * surrounding `nodeTypes` map can stay referentially stable. If `nodeTypes`
 * changes identity, React Flow remounts every node, which drops mid-flight
 * clicks and re-triggers focus animations — the source of past "clicks do
 * nothing / middle node pulses" bugs.
 */
function GuidedNodeShell({ NodeComponent, ...nodeProps }: GuidedNodeShellProps) {
  const {
    selectedNodeId,
    inputBookendId,
    outputBookendId,
    allowAddNodes,
    allowBookendSwap,
    allowDeleteNodes,
    readOnly,
    deletableNodeIds,
    callbacks,
  } = useGuidedFlowCanvasUi()

  const guidedMode = Boolean(
    (nodeProps.data as { guidedMode?: boolean } | undefined)?.guidedMode,
  )
  const exitAnimation = Boolean(
    (nodeProps.data as { exitAnimation?: boolean } | undefined)?.exitAnimation,
  )
  const nodeSelected = Boolean(nodeProps.selected || nodeProps.id === selectedNodeId)

  const isInputBookend = inputBookendId != null && nodeProps.id === inputBookendId
  const isOutputBookendNode = outputBookendId != null && nodeProps.id === outputBookendId

  const showAddButton =
    allowAddNodes &&
    !!callbacks.current.onAddNodeClick &&
    !isOutputBookendNode &&
    !readOnly
  const showDeleteButton =
    allowDeleteNodes &&
    !!callbacks.current.onDeleteNodeClick &&
    deletableNodeIds.has(nodeProps.id) &&
    !readOnly
  const showSwapButton =
    allowBookendSwap &&
    !readOnly &&
    ((isInputBookend && !!callbacks.current.onSwapInputBookend) ||
      (isOutputBookendNode && !!callbacks.current.onSwapOutputBookend))

  const handleNodeActivate = (event: ReactMouseEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('button')) return
    event.stopPropagation()
    callbacks.current.onNodeClick?.({
      id: nodeProps.id,
      type: nodeProps.type,
      data: nodeProps.data,
      position: { x: nodeProps.xPos, y: nodeProps.yPos },
    } as Node)
  }

  const handleAddClick = () => callbacks.current.onAddNodeClick?.(nodeProps.id)
  const handleDeleteClick = () => callbacks.current.onDeleteNodeClick?.(nodeProps.id)
  const handleSwapClick = isInputBookend
    ? () => callbacks.current.onSwapInputBookend?.()
    : isOutputBookendNode
      ? () => callbacks.current.onSwapOutputBookend?.()
      : undefined

  return (
    <div
      className="group relative cursor-pointer overflow-visible"
      style={
        guidedMode
          ? { width: GUIDED_COMPACT_NODE_WIDTH, height: GUIDED_COMPACT_NODE_HEIGHT }
          : undefined
      }
      onClick={handleNodeActivate}
    >
      {guidedMode ? (
        <GuidedCompactNode {...nodeProps} exitAnimation={exitAnimation} />
      ) : (
        <Suspense fallback={<div className="h-16 w-[200px] animate-pulse rounded-lg bg-muted" />}>
          <NodeComponent {...nodeProps} />
        </Suspense>
      )}
      {showAddButton && !exitAnimation && (
        <NodeRightAddButton nodeSelected={nodeSelected} onClick={handleAddClick} />
      )}
      {showDeleteButton && !exitAnimation && (
        <NodeBottomHoverButton
          ariaLabel="Remove step"
          nodeSelected={nodeSelected}
          onClick={handleDeleteClick}
          className="text-destructive hover:border-destructive hover:bg-destructive hover:text-destructive-foreground hover:ring-destructive/30"
        >
          <Trash2 className="h-3 w-3" />
        </NodeBottomHoverButton>
      )}
      {showSwapButton && !exitAnimation && (
        <NodeBottomHoverButton
          ariaLabel={isInputBookend ? 'Change source' : 'Change destination'}
          nodeSelected={nodeSelected}
          onClick={handleSwapClick}
          className="text-foreground hover:border-primary hover:bg-primary hover:text-primary-foreground hover:ring-primary/30"
        >
          <ArrowLeftRight className="h-3 w-3" />
        </NodeBottomHoverButton>
      )}
    </div>
  )
}

/**
 * Module-level so React Flow sees a stable identity across every parent
 * render. Per-node and per-render concerns now flow through the canvas
 * context, not closure variables in this map.
 */
const GUIDED_NODE_TYPES: NodeTypes = Object.fromEntries(
  Object.entries(nodeComponents).map(([type, LazyComponent]) => [
    type,
    (props: NodeProps) => (
      <GuidedNodeShell {...props} NodeComponent={LazyComponent as ComponentType<NodeProps>} />
    ),
  ]),
)

/** Matches NodePanel (`w-96`) so fitView leaves room when the side panel is open. */
export const GUIDED_FLOW_NODE_PANEL_WIDTH_PX = 384

const FIT_VIEW_PAD_PX = 32
export const GUIDED_NODE_EXIT_MS = 440
const GUIDED_NODE_ENTER_MS = 520
const FIT_DURATION_GRAPH_CHANGE_MS = 500
const PANEL_VIEWPORT_DURATION_MS = 220
const PANEL_SELECTED_NODE_ZOOM = 1.2

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
  exitingNodeIds: ReadonlySet<string>,
): Node[] {
  const base = scaffoldModel
    ? toReactFlowNodes(scaffoldModel)
    : withBookendPositions(inputNode, outputNode)
  const outputBookendId = scaffoldModel?.outputNode.id ?? outputNode?.id ?? null

  // Leave `draggable` undefined so React Flow falls back to the canvas-level
  // `nodesDraggable` prop. If we hard-coded a per-node flag here it would get
  // baked into React Flow's internal `nodes` state on first mount and stick
  // there when the parent later toggled edit mode on (e.g. clicking "Edit
  // flow" on a saved flow), since the resync effect doesn't fire on a pure
  // `allowNodeDrag` change.
  return base.map((node) => ({
    id: node.id,
    type: node.type,
    position: node.position ?? { x: 0, y: 0 },
    data: {
      ...node.data,
      guidedMode: true,
      guidedIsOutputBookend: outputBookendId != null && node.id === outputBookendId,
      exitAnimation: exitingNodeIds.has(node.id),
    },
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
  exitingNodeIds?: ReadonlySet<string>
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
  exitingNodeIds = new Set(),
}: GuidedFlowCanvasProps) {
  const { fitView, getNodes, getViewport, setCenter, setViewport } = useReactFlow()
  const updateNodeInternals = useUpdateNodeInternals()
  const containerRef = useRef<HTMLDivElement>(null)
  const inputBookendId =
    inputBookendIdProp ?? scaffoldModel?.inputNode.id ?? inputNode?.id ?? null
  const outputBookendId =
    outputBookendIdProp ?? scaffoldModel?.outputNode.id ?? outputNode?.id ?? null
  const prevNodeIdsRef = useRef<Set<string> | null>(null)
  const prevModelNodesRef = useRef<Node[]>([])
  const isDraggingRef = useRef(false)
  const reactFlowInitializedRef = useRef(false)
  const isFirstLayoutFitRef = useRef(true)
  const viewportBeforePanelOpenRef = useRef<Viewport | null>(null)
  const previousSelectedNodeIdRef = useRef<string | null>(selectedNodeId)
  const [enteringNodeIds, setEnteringNodeIds] = useState<Set<string>>(() => new Set())
  const [exitingNodes, setExitingNodes] = useState<Map<string, Node>>(() => new Map())

  // Stable identity — see GUIDED_NODE_TYPES module-level definition above.
  const nodeTypes = GUIDED_NODE_TYPES

  /**
   * Latest callbacks for the node shell. Stored in a ref because we don't
   * want their identity churn to invalidate context consumers — and we
   * definitely don't want it to invalidate `nodeTypes`.
   */
  const callbacksRef = useRef<GuidedFlowCanvasCallbacks>({})
  callbacksRef.current = {
    onNodeClick,
    onAddNodeClick,
    onDeleteNodeClick,
    onSwapInputBookend,
    onSwapOutputBookend,
  }

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
    () => buildModelNodes(scaffoldModel, inputNode, outputNode, exitingNodeIds),
    [exitingNodeIds, inputNode, outputNode, nodesLayoutKey, scaffoldModel],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(modelNodes)
  const liveNodePositionsRef = useRef(new Map<string, { x: number; y: number }>())

  const rememberNodePosition = useCallback((nodeId: string, position: { x: number; y: number }) => {
    liveNodePositionsRef.current.set(nodeId, position)
  }, [])

  useEffect(() => {
    for (const node of nodes) {
      rememberNodePosition(node.id, node.position)
    }
  }, [nodes, rememberNodePosition])

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
      id: `${node.id}__exiting`,
      position: node.position ?? { x: 0, y: 0 },
      draggable: false,
      selectable: false,
    }))
    return [...nodes, ...exiting]
  }, [exitingNodes, nodes])

  const emptyDeletableSet = useMemo<ReadonlySet<string>>(() => new Set(), [])
  const canvasUi: GuidedFlowCanvasUi = useMemo(
    () => ({
      selectedNodeId,
      enteringNodeIds,
      inputBookendId,
      outputBookendId,
      allowAddNodes,
      allowBookendSwap,
      allowDeleteNodes,
      readOnly,
      deletableNodeIds: deletableNodeIds ?? emptyDeletableSet,
      callbacks: callbacksRef,
    }),
    [
      allowAddNodes,
      allowBookendSwap,
      allowDeleteNodes,
      deletableNodeIds,
      emptyDeletableSet,
      enteringNodeIds,
      inputBookendId,
      outputBookendId,
      readOnly,
      selectedNodeId,
    ],
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

  const modelNodesRef = useRef(modelNodes)
  modelNodesRef.current = modelNodes

  /**
   * Reads node ids through `modelNodesRef` rather than closing over `modelNodes`.
   * If this callback's identity churned every time scaffoldModel changed (i.e.
   * on every keystroke that updated node.data) the recenter effect below would
   * refire and trigger a fitView animation, making nodes appear to "jump back"
   * while the user types.
   */
  const fitGraphInView = useCallback(
    (options?: { duration?: number }) => {
      if (isDraggingRef.current) return
      const el = containerRef.current
      const currentModelNodes = modelNodesRef.current
      if (!el || currentModelNodes.length === 0) return
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
      const nodeIds = currentModelNodes.map((node) => node.id)
      if (duration > 0) {
        window.setTimeout(() => remeasureNodesRef.current(nodeIds), duration + 32)
      } else {
        remeasureNodesRef.current(nodeIds)
      }
    },
    [fitView, reserveRightPx],
  )

  const recenterGraph = useCallback(
    (options?: { duration?: number; delayMs?: number }) => {
      if (isDraggingRef.current) return
      if (!reactFlowInitializedRef.current) return
      const duration = options?.duration ?? FIT_DURATION_GRAPH_CHANGE_MS
      const delayMs = options?.delayMs ?? 0
      const run = () => {
        requestAnimationFrame(() => {
          remeasureNodesRef.current(modelNodesRef.current.map((node) => node.id))
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
    [fitGraphInView],
  )

  const restoreViewportAfterTopologyChange = useCallback(
    (viewport: Viewport) => {
      requestAnimationFrame(() => {
        void setViewport(viewport, { duration: 0 })
        requestAnimationFrame(() => {
          void setViewport(viewport, { duration: 0 })
        })
      })
    },
    [setViewport],
  )

  const centerSelectedNodeForPanel = useCallback(
    (nodeId: string, delayMs = 0) => {
      const run = () => {
        const node = modelNodesRef.current.find((entry) => entry.id === nodeId)
        if (!node) return
        const position = liveNodePositionsRef.current.get(node.id) ?? node.position ?? { x: 0, y: 0 }
        const width = typeof node.width === 'number' ? node.width : GUIDED_COMPACT_NODE_WIDTH
        const height = typeof node.height === 'number' ? node.height : GUIDED_COMPACT_NODE_HEIGHT
        void setCenter(position.x + width / 2, position.y + height / 2, {
          zoom: PANEL_SELECTED_NODE_ZOOM,
          duration: PANEL_VIEWPORT_DURATION_MS,
        })
      }
      if (delayMs > 0) {
        window.setTimeout(run, delayMs)
      } else {
        requestAnimationFrame(run)
      }
    },
    [setCenter],
  )

  const fitInitialGraphInView = useCallback(() => {
    if (!isFirstLayoutFitRef.current) return
    if (!reactFlowInitializedRef.current) return
    if (modelNodesRef.current.length === 0) return
    isFirstLayoutFitRef.current = false
    recenterGraph({ duration: 0 })
  }, [recenterGraph])

  const applySelectionToNodes = useCallback(
    (nodes: Node[]): Node[] =>
      nodes.map((node) => ({
        ...node,
        selected: selectedNodeId != null && node.id === selectedNodeId,
      })),
    [selectedNodeId],
  )

  const prevGraphNodeIdsKeyRef = useRef(graphNodeIdsKey)
  useLayoutEffect(() => {
    const topologyChanged = prevGraphNodeIdsKeyRef.current !== graphNodeIdsKey
    const viewportBeforeTopologyChange = topologyChanged ? getViewport() : null
    prevGraphNodeIdsKeyRef.current = graphNodeIdsKey

    if (!topologyChanged && isDraggingRef.current) return
    const nextModelNodes = applySelectionToNodes(modelNodesRef.current)
    if (topologyChanged) {
      setNodes(nextModelNodes)
    } else {
      const modelNodeById = new Map(nextModelNodes.map((node) => [node.id, node]))
      setNodes((current) =>
        current.map((node) => {
          const modelNode = modelNodeById.get(node.id)
          if (!modelNode) return node
          const livePosition = liveNodePositionsRef.current.get(node.id)
          return {
            ...modelNode,
            position: livePosition ?? node.position,
            positionAbsolute: node.positionAbsolute,
          }
        }),
      )
    }
    remeasureNodesRef.current(nextModelNodes.map((node) => node.id))
    if (viewportBeforeTopologyChange) {
      restoreViewportAfterTopologyChange(viewportBeforeTopologyChange)
    }
  }, [
    applySelectionToNodes,
    exitingNodeIds,
    getViewport,
    graphNodeContentKey,
    graphNodeIdsKey,
    nodesLayoutKey,
    restoreViewportAfterTopologyChange,
    setNodes,
  ])

  useEffect(() => {
    setNodes((current) => applySelectionToNodes(current))
  }, [applySelectionToNodes, setNodes])

  useEffect(() => {
    const previousSelectedNodeId = previousSelectedNodeIdRef.current
    previousSelectedNodeIdRef.current = selectedNodeId
    if (!reactFlowInitializedRef.current) return

    if (selectedNodeId && !previousSelectedNodeId) {
      viewportBeforePanelOpenRef.current = getViewport()
      centerSelectedNodeForPanel(selectedNodeId)
      return
    }

    if (selectedNodeId && selectedNodeId !== previousSelectedNodeId) {
      centerSelectedNodeForPanel(selectedNodeId)
      return
    }

    if (!selectedNodeId && previousSelectedNodeId && viewportBeforePanelOpenRef.current) {
      const viewport = viewportBeforePanelOpenRef.current
      viewportBeforePanelOpenRef.current = null
      void setViewport(viewport, { duration: PANEL_VIEWPORT_DURATION_MS })
    }
  }, [centerSelectedNodeForPanel, getViewport, selectedNodeId, setViewport])

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
        enterTimer = window.setTimeout(() => {
          setEnteringNodeIds(new Set())
          remeasureNodes(modelNodes.map((node) => node.id))
        }, GUIDED_NODE_ENTER_MS)
      } else {
        setEnteringNodeIds(new Set())
      }
    }

    if (removedNodeIds.length > 0 && animateGraphChanges) {
      const removedIdSet = new Set(removedNodeIds)
      setExitingNodes((current) => {
        const next = new Map(current)
        for (const snapshot of prevModelNodesRef.current) {
          if (!removedIdSet.has(snapshot.id)) continue
          if ((snapshot.data as { exitAnimation?: boolean } | undefined)?.exitAnimation) continue
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
      }, GUIDED_NODE_EXIT_MS)
    }

    prevModelNodesRef.current = modelNodes

    return () => {
      if (enterTimer != null) window.clearTimeout(enterTimer)
      if (exitTimer != null) window.clearTimeout(exitTimer)
    }
  }, [animateGraphChanges, modelNodes, remeasureNodes])

  useEffect(() => {
    if (modelNodes.length === 0) return
    fitInitialGraphInView()
  }, [fitInitialGraphInView, modelNodes.length])

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const filtered = changes.filter((change) => change.type !== 'remove')
      if (filtered.length === 0) return

      for (const change of filtered) {
        if (change.type !== 'position') continue
        if (allowNodeDrag && change.position) {
          rememberNodePosition(change.id, change.position)
        }
        if (!('dragging' in change) || change.dragging !== false) {
          isDraggingRef.current = true
        } else {
          isDraggingRef.current = false
          if (allowNodeDrag && change.position) {
            onNodePositionChange?.(change.id, change.position)
          }
        }
      }

      const applicable = allowNodeDrag
        ? filtered
        : filtered.filter((change) => change.type !== 'position')
      if (applicable.length > 0) {
        onNodesChange(applicable)
      }
    },
    [allowNodeDrag, onNodePositionChange, onNodesChange, rememberNodePosition],
  )

  const onNodeDragStart = useCallback(() => {
    isDraggingRef.current = true
  }, [])

  const onNodeDrag = useCallback(() => {
    isDraggingRef.current = true
  }, [])

  const onNodeDragStop: NodeDragHandler = useCallback(
    (_event, node) => {
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
    reactFlowInitializedRef.current = true
    remeasureNodes(modelNodes.map((node) => node.id))
    fitInitialGraphInView()
  }, [fitInitialGraphInView, modelNodes, remeasureNodes])

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
                ? (event, node) => {
                    event.stopPropagation()
                    onNodeClick(node)
                  }
                : undefined
            }
            maxZoom={1.2}
            nodesDraggable={allowNodeDrag}
            nodesConnectable={false}
            elementsSelectable={false}
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
        <div
          className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-background/75 px-4 backdrop-blur-[1px]"
          role="presentation"
        >
          <Card className="pointer-events-auto max-w-sm border-dashed bg-background p-6 text-center shadow-md">
            <CardTitle id="empty-flow-cta-title" className="text-base font-medium">
              Add your first step
            </CardTitle>
            <CardDescription className="mt-2 text-sm leading-relaxed">
              Use the plus button on your content source to add a step that processes your content.
            </CardDescription>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="mt-4"
              onClick={() => onEmptyMiddleCtaDismiss?.()}
            >
              Got it
            </Button>
          </Card>
        </div>
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
