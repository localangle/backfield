import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { Node } from 'reactflow'

import { PageBreadcrumbs } from '@/components/PageBreadcrumbs'
import { FlowTitleRow } from '@/components/flow-builder/FlowTitleRow'
import AddNodeChooser from '@/components/flow-builder/AddNodeChooser'
import BookendChooser from '@/components/flow-builder/BookendChooser'
import BookendSwapDialog from '@/components/flow-builder/BookendSwapDialog'
import ConfigureGatePanel from '@/components/flow-builder/ConfigureGatePanel'
import FlowStepper from '@/components/flow-builder/FlowStepper'
import GuidedFlowCanvas, {
  GUIDED_NODE_EXIT_MS,
  GUIDED_FLOW_NODE_PANEL_WIDTH_PX,
} from '@/components/flow-builder/GuidedFlowCanvas'
import ConfirmDialog from '@/components/ConfirmDialog'
import RunPanel from '@/components/RunPanel'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Button } from '@/components/ui/button'
import {
  getInputBookendDefaultData,
  getMiddleNodeDefaultData,
  getOutputBookendDefaultData,
} from '@/lib/flowBuilderDefaults'
import {
  addSiblingBranch,
  applyLayoutToModel,
  canReplaceInputBookend,
  canReplaceOutputBookend,
  clearMiddleNodes,
  createFlowGraphModel,
  deleteMiddleNode,
  getInvalidFlowNodeIds,
  replaceInputBookend,
  replaceOutputBookend,
  getBranchAncestry,
  getNodeById,
  hydrateFromSpec,
  insertAfter,
  insertBetween,
  modelToGraphSpec,
  TIDY_LAYOUT_X_STEP,
  updateMiddleNode,
  toReactFlowNodes,
  updateNodePosition,
  type FlowGraphModel,
} from '@/lib/flowGraphModel'
import {
  canNavigateToStep,
  canSavePanelChanges,
  completedStepsForEdit,
  getInitialEditStep,
  isPanelGateActive,
  STEP_CHOOSER_COPY,
  type FlowBuilderStep,
} from '@/lib/flowBuilderSteps'
import { getCompatibleInsertNodes, getCompatibleNextNodes } from '@/lib/nodeCompatibility'
import { getGuidedFlowCapabilities } from '@/lib/guidedFlowCapabilities'
import { captureGuidedFlowSnapshot, type GuidedFlowSnapshot } from '@/lib/guidedFlowSnapshot'
import { nodeOutputLookupFromReactFlow } from '@/lib/nodeOutputs'
import {
  createGraph,
  getGraph,
  getProject,
  listProjects,
  updateGraph,
  type Project,
  type Run,
} from '@/lib/api'
import { buildProjectBreadcrumbItems } from '@/lib/projectBreadcrumbs'
import { fetchProjectEffectiveAiModels, listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'
import {
  INPUT_BOOKEND_TYPES,
  OUTPUT_BOOKEND_TYPES,
  paramsForGraphSave,
  validateGraphForSave,
} from '@/lib/flowValidation'
import { nodeMetadata } from '@/nodes/registry'
import { Save } from 'lucide-react'

let nodeIdCounter = 0
const nextNodeId = () => `node-${nodeIdCounter++}`

type AddNodeChooserAnchor = {
  top: number
  right: number
  bottom: number
  left: number
}

type AddNodeInsertionEdge = {
  sourceId: string
  targetId: string
}

function syncNodeIdCounter(nodes: Array<{ id: string }>): void {
  let maxIdx = 0
  for (const node of nodes) {
    const match = /^node-(\d+)$/.exec(node.id)
    if (match) maxIdx = Math.max(maxIdx, parseInt(match[1], 10) + 1)
  }
  nodeIdCounter = maxIdx
}

function buildSaveModel(
  inputNode: Node,
  outputNode: Node,
  scaffoldModel: FlowGraphModel | null,
): FlowGraphModel {
  const inputBookend = {
    id: inputNode.id,
    type: inputNode.type ?? 'TextInput',
    data: inputNode.data as Record<string, unknown>,
    position: scaffoldModel?.inputNode.position,
  }
  const outputBookend = {
    id: outputNode.id,
    type: outputNode.type ?? 'Output',
    data: outputNode.data as Record<string, unknown>,
    position: scaffoldModel?.outputNode.position,
  }
  const base = scaffoldModel ?? createFlowGraphModel(inputBookend, outputBookend)
  return applyLayoutToModel({
    ...base,
    inputNode: { ...base.inputNode, ...inputBookend },
    outputNode: { ...base.outputNode, ...outputBookend },
  })
}

function toReactFlowBookend(node: {
  id: string
  type?: string
  data?: Record<string, unknown>
  position?: { x: number; y: number }
}): Node {
  return {
    id: node.id,
    type: node.type,
    position: node.position ?? { x: 0, y: 0 },
    data: node.data ?? {},
  }
}

function flowGraphNodeToPanelNode(
  node: { id: string; type: string; data?: Record<string, unknown>; position?: { x: number; y: number } },
  reactNode: Node | null | undefined,
): Node {
  return {
    id: node.id,
    type: reactNode?.type ?? node.type,
    position: node.position ?? reactNode?.position ?? { x: 0, y: 0 },
    data: (reactNode?.data ?? node.data ?? {}) as Record<string, unknown>,
  }
}

function resolveGuidedSelectedNode(
  selectedNodeId: string,
  activeStep: FlowBuilderStep,
  inputNode: Node | null,
  outputNode: Node | null,
  scaffoldModel: FlowGraphModel | null,
): Node | null {
  if (activeStep === 'input' && inputNode?.id === selectedNodeId) return inputNode
  if (activeStep === 'output' && outputNode?.id === selectedNodeId) return outputNode
  if (!scaffoldModel) {
    if (inputNode?.id === selectedNodeId) return inputNode
    if (outputNode?.id === selectedNodeId) return outputNode
    return null
  }
  if (scaffoldModel.inputNode.id === selectedNodeId) {
    return flowGraphNodeToPanelNode(scaffoldModel.inputNode, inputNode)
  }
  if (scaffoldModel.outputNode.id === selectedNodeId) {
    return flowGraphNodeToPanelNode(scaffoldModel.outputNode, outputNode)
  }
  const middle = scaffoldModel.middleNodes.find((n) => n.id === selectedNodeId)
  if (middle) return flowGraphNodeToPanelNode(middle, null)
  if (inputNode?.id === selectedNodeId) return inputNode
  if (outputNode?.id === selectedNodeId) return outputNode
  return null
}

export type GuidedFlowBuilderVariant = 'create' | 'edit' | 'run'

export type GuidedFlowBuilderProps = {
  variant?: GuidedFlowBuilderVariant
  readOnly?: boolean
  hideHeader?: boolean
  running?: boolean
  currentRun?: Run | null
  showRunPanel?: boolean
  onCloseRunPanel?: () => void
  onSaved?: (graphId: string) => void
  onGraphLoaded?: (payload: { id: string; name: string; projectId: number }) => void
  className?: string
}

export type GuidedFlowBuilderHandle = {
  takeSnapshot: () => void
  restoreSnapshot: () => void
  save: () => Promise<boolean>
  hasNodeType: (type: string) => boolean
  isSaving: () => boolean
}

const GuidedFlowBuilder = forwardRef<GuidedFlowBuilderHandle, GuidedFlowBuilderProps>(
  function GuidedFlowBuilder(
    {
      variant: variantProp,
      readOnly = false,
      hideHeader = false,
      running = false,
      currentRun = null,
      showRunPanel = false,
      onCloseRunPanel,
      onSaved,
      onGraphLoaded,
      className,
    },
    ref,
  ) {
  const { showConfirm } = useAppMessage()
  const navigate = useNavigate()
  const { graphId: routeGraphId } = useParams<{ graphId: string }>()
  const [searchParams] = useSearchParams()
  const variant: GuidedFlowBuilderVariant =
    variantProp ?? (routeGraphId ? 'edit' : 'create')
  const isRunVariant = variant === 'run'
  const snapshotRef = useRef<GuidedFlowSnapshot | null>(null)
  const capabilities = useMemo(
    () => getGuidedFlowCapabilities({ readOnly }),
    [readOnly],
  )
  const [graphName, setGraphName] = useState('Untitled Flow')
  const [activeStep, setActiveStep] = useState<FlowBuilderStep>('input')
  const [completedSteps, setCompletedSteps] = useState<Set<FlowBuilderStep>>(new Set())
  const [inputNode, setInputNode] = useState<Node | null>(null)
  const [outputNode, setOutputNode] = useState<Node | null>(null)
  const [scaffoldModel, setScaffoldModel] = useState<FlowGraphModel | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [tidyLayoutKey, setTidyLayoutKey] = useState(0)
  const [dirtyPanelNodeIds, setDirtyPanelNodeIds] = useState<Set<string>>(new Set())
  const [savedPanelNodeIds, setSavedPanelNodeIds] = useState<Set<string>>(new Set())
  const [exitingNodeIds, setExitingNodeIds] = useState<Set<string>>(new Set())
  const deleteAnimationTimersRef = useRef(new Map<string, ReturnType<typeof window.setTimeout>>())
  const preAddLayoutSnapshotRef = useRef<{
    outputPosition?: { x: number; y: number }
    middlePositions: Map<string, { x: number; y: number }>
  } | null>(null)
  const [configureGateActive, setConfigureGateActive] = useState(false)
  const [addChooserOpen, setAddChooserOpen] = useState(false)
  const [addFromParentId, setAddFromParentId] = useState<string | null>(null)
  const [addIntoEdge, setAddIntoEdge] = useState<AddNodeInsertionEdge | null>(null)
  const [addChooserAnchor, setAddChooserAnchor] = useState<AddNodeChooserAnchor | null>(null)
  const [bookendSwapOpen, setBookendSwapOpen] = useState(false)
  const [bookendSwapKind, setBookendSwapKind] = useState<'input' | 'output'>('input')
  const [resolvedFlowProject, setResolvedFlowProject] = useState<Project | null>(null)
  const [flowWorkspace, setFlowWorkspace] = useState<WorkspaceWithProjects | null>(null)
  const [flowProjectLoading, setFlowProjectLoading] = useState(false)
  const [existingGraphId, setExistingGraphId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [graphLoading, setGraphLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [modalConfig, setModalConfig] = useState<{
    title: string
    description: string
    type: 'info' | 'warning' | 'error' | 'success'
    confirmText?: string
    onConfirm: () => void
  } | null>(null)

  const completedStepsReadonly = completedSteps as ReadonlySet<FlowBuilderStep>

  useEffect(
    () => () => {
      for (const timer of deleteAnimationTimersRef.current.values()) {
        window.clearTimeout(timer)
      }
      deleteAnimationTimersRef.current.clear()
    },
    [],
  )

  const showModal = useCallback(
    (config: {
      title: string
      description: string
      type: 'info' | 'warning' | 'error' | 'success'
      confirmText?: string
      onConfirm: () => void
    }) => {
      setModalConfig(config)
      setModalOpen(true)
    },
    [],
  )

  useEffect(() => {
    if (routeGraphId) return
    let cancelled = false
    void (async () => {
      setFlowProjectLoading(true)
      try {
        const list = await listProjects()
        if (cancelled) return
        const q = searchParams.get('project')
        const pick =
          (q &&
            (list.find((p) => p.slug === q) ?? list.find((p) => p.id.toString() === q))) ??
          list.find((p) => p.slug === 'general') ??
          list[0] ??
          null
        if (!pick) {
          setResolvedFlowProject(null)
          return
        }
        const full = await getProject(pick.id)
        if (!cancelled) setResolvedFlowProject(full)
      } catch (error) {
        console.error('Failed to resolve flow project:', error)
        if (!cancelled) setResolvedFlowProject(null)
      } finally {
        if (!cancelled) setFlowProjectLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [searchParams, routeGraphId])

  useEffect(() => {
    if (!routeGraphId) return
    let cancelled = false
    void (async () => {
      setGraphLoading(true)
      setFlowProjectLoading(true)
      try {
        const graph = await getGraph(routeGraphId)
        if (cancelled) return
        const project = await getProject(graph.project_id)
        if (cancelled) return

        const hydrated = hydrateFromSpec(graph.spec)
        if (!hydrated.ok) {
          showModal({
            title: hydrated.title,
            description: hydrated.description,
            type: 'error',
            confirmText: 'OK',
            onConfirm: () => navigate('/'),
          })
          return
        }

        syncNodeIdCounter(graph.spec.nodes)
        setExistingGraphId(graph.id)
        setGraphName(graph.name)
        setResolvedFlowProject(project)
        setScaffoldModel(applyLayoutToModel(hydrated.model))
        setInputNode(toReactFlowBookend(hydrated.model.inputNode))
        setOutputNode(toReactFlowBookend(hydrated.model.outputNode))
        setCompletedSteps(completedStepsForEdit())
        setActiveStep(getInitialEditStep())
        setSelectedNodeId(null)
        setConfigureGateActive(false)
        onGraphLoaded?.({ id: graph.id, name: graph.name, projectId: graph.project_id })
      } catch (error) {
        console.error('Failed to load graph:', error)
        if (!cancelled) navigate('/')
      } finally {
        if (!cancelled) {
          setGraphLoading(false)
          setFlowProjectLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [routeGraphId, navigate, showModal, onGraphLoaded])

  const nodeOutputLookupSpec = useMemo(() => {
    if (!isRunVariant || !scaffoldModel) return null
    const spec = modelToGraphSpec(scaffoldModel)
    const flowNodes = spec.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.params,
    }))
    const flowEdges = spec.edges.map((edge, index) => ({
      id: `edge-${index}`,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? undefined,
      targetHandle: edge.targetHandle ?? undefined,
    }))
    return nodeOutputLookupFromReactFlow(flowNodes, flowEdges)
  }, [isRunVariant, scaffoldModel])

  const flowProjectId = resolvedFlowProject?.id ?? null
  const workspaceStylebookId = resolvedFlowProject?.workspace_stylebook_id ?? null

  useEffect(() => {
    if (resolvedFlowProject?.workspace_id == null) {
      setFlowWorkspace(null)
      return
    }
    let cancelled = false
    void listMyWorkspaces()
      .then((rows) => {
        if (!cancelled) {
          setFlowWorkspace(rows.find((row) => row.id === resolvedFlowProject.workspace_id) ?? null)
        }
      })
      .catch(() => {
        if (!cancelled) setFlowWorkspace(null)
      })
    return () => {
      cancelled = true
    }
  }, [resolvedFlowProject?.workspace_id])

  const handleFlowNameSave = useCallback(
    async (nextName: string) => {
      setGraphName(nextName)
      if (!existingGraphId || !resolvedFlowProject) return
      const current = await getGraph(existingGraphId)
      await updateGraph(existingGraphId, {
        name: nextName,
        project_id: resolvedFlowProject.id,
        spec: {
          ...current.spec,
          name: nextName.toLowerCase().replace(/\s+/g, '_'),
        },
      })
    },
    [existingGraphId, resolvedFlowProject],
  )

  const headerBreadcrumbItems = useMemo(
    () =>
      buildProjectBreadcrumbItems({
        project: resolvedFlowProject,
        workspace: flowWorkspace,
        tail: [{ label: graphName.trim() || 'Untitled flow' }],
      }),
    [flowWorkspace, graphName, resolvedFlowProject],
  )

  const fetchProjectAiModels = useCallback(
    async (capabilities: string[]) => {
      if (flowProjectId == null) return []
      const rows = await fetchProjectEffectiveAiModels(flowProjectId, capabilities)
      return rows.map((r) => ({
        label:
          typeof r.name === 'string' && r.name.trim() !== ''
            ? r.name.trim()
            : String(r.provider_model_id ?? ''),
        providerModelId: r.provider_model_id,
        configId: r.id,
      }))
    },
    [flowProjectId],
  )

  const graphContext = useMemo(() => {
    if (flowProjectLoading) {
      return {
        organizationId: null as number | null,
        projectId: null as number | null,
        workspaceDefaultStylebookId: null as number | null,
        workspaceStylebookName: null as string | null,
        missingWorkspaceStylebook: false,
        flowProjectLoading: true,
      }
    }
    const p = resolvedFlowProject
    if (!p) {
      return {
        organizationId: null as number | null,
        projectId: null as number | null,
        workspaceDefaultStylebookId: null as number | null,
        workspaceStylebookName: null as string | null,
        missingWorkspaceStylebook: false,
        flowProjectLoading: false,
      }
    }
    const sid = p.workspace_stylebook_id ?? null
    const rawName = p.workspace_stylebook_name
    const nm = typeof rawName === 'string' && rawName.trim() !== '' ? rawName.trim() : null
    return {
      organizationId: p.organization_id ?? null,
      projectId: p.id ?? null,
      workspaceDefaultStylebookId: sid,
      workspaceStylebookName: nm,
      missingWorkspaceStylebook: sid == null && nm == null,
      flowProjectLoading: false,
      fetchProjectAiModels: flowProjectId != null ? fetchProjectAiModels : undefined,
    }
  }, [resolvedFlowProject, flowProjectLoading, flowProjectId, fetchProjectAiModels])

  const canNavigateTo = useCallback(
    (step: FlowBuilderStep) => canNavigateToStep(step, completedStepsReadonly),
    [completedStepsReadonly],
  )

  const resetStepsAfterInput = useCallback((prev: Set<FlowBuilderStep>) => {
    const next = new Set(prev)
    next.delete('input')
    next.delete('output')
    next.delete('scaffold')
    return next
  }, [])

  const resetStepsAfterOutput = useCallback((prev: Set<FlowBuilderStep>) => {
    const next = new Set(prev)
    next.delete('output')
    next.delete('scaffold')
    return next
  }, [])

  const clearScaffold = useCallback(() => {
    setScaffoldModel(null)
  }, [])

  useEffect(() => {
    if (activeStep !== 'scaffold' || !inputNode || !outputNode) return
    setScaffoldModel((current) => {
      const inputBookend = {
        id: inputNode.id,
        type: inputNode.type ?? 'TextInput',
        data: inputNode.data as Record<string, unknown>,
      }
      const outputBookend = {
        id: outputNode.id,
        type: outputNode.type ?? 'Output',
        data: outputNode.data as Record<string, unknown>,
      }
      if (!current) {
        return applyLayoutToModel(createFlowGraphModel(inputBookend, outputBookend), {
          relayoutBookends: true,
        })
      }
      return applyLayoutToModel(
        {
          ...current,
          inputNode: {
            ...inputBookend,
            position: current.inputNode.id === inputBookend.id ? current.inputNode.position : undefined,
          },
          outputNode: {
            ...outputBookend,
            position:
              current.outputNode.id === outputBookend.id ? current.outputNode.position : undefined,
          },
        },
      )
    })
  }, [activeStep, inputNode, outputNode])

  const handleStepChange = useCallback(
    (step: FlowBuilderStep) => {
      if (!canNavigateToStep(step, completedStepsReadonly)) return
      setActiveStep(step)
      setAddChooserOpen(false)
      setAddChooserAnchor(null)
      setAddFromParentId(null)
      setAddIntoEdge(null)
      if (step === 'input' && inputNode) {
        setSelectedNodeId(inputNode.id)
        setConfigureGateActive(!readOnly)
      } else if (step === 'output' && outputNode) {
        setSelectedNodeId(outputNode.id)
        setConfigureGateActive(!readOnly)
      } else {
        setSelectedNodeId(null)
        setConfigureGateActive(false)
      }
    },
    [completedStepsReadonly, inputNode, outputNode, completedSteps, readOnly],
  )

  const applyInputBookendSwap = useCallback(
    (type: string, options?: { activeStepAfter?: FlowBuilderStep }) => {
      if (!(INPUT_BOOKEND_TYPES as readonly string[]).includes(type)) return false

      const id = inputNode?.id ?? nextNodeId()
      const data = getInputBookendDefaultData(type) as Record<string, unknown>
      const node: Node = { id, type, data, position: inputNode?.position ?? { x: 0, y: 0 } }

      if (scaffoldModel && outputNode && inputNode) {
        if (inputNode.type === type) {
          setSelectedNodeId(id)
          return true
        }
        const check = canReplaceInputBookend(scaffoldModel, type)
        if (!check.ok) {
          showModal({
            title: 'Cannot change source',
            description: check.reason,
            type: 'warning',
            confirmText: 'OK',
            onConfirm: () => {},
          })
          return false
        }
        setInputNode(node)
        setScaffoldModel((current) =>
          current
            ? applyLayoutToModel(replaceInputBookend(current, { type, data }), {
                relayoutBookends: false,
              })
            : current,
        )
        setSelectedNodeId(id)
        setConfigureGateActive(true)
        if (options?.activeStepAfter) setActiveStep(options.activeStepAfter)
        return true
      }

      setInputNode(node)
      setSelectedNodeId(id)
      setConfigureGateActive(true)
      setActiveStep('input')

      if (!outputNode) {
        clearScaffold()
        setCompletedSteps(resetStepsAfterInput)
        return true
      }

      const outputBookend = {
        id: outputNode.id,
        type: outputNode.type ?? 'Output',
        data: outputNode.data as Record<string, unknown>,
      }
      const inputBookend = { id, type, data }
      setScaffoldModel((current) =>
        applyLayoutToModel(
          clearMiddleNodes({
            ...(current ?? createFlowGraphModel(inputBookend, outputBookend)),
            inputNode: inputBookend,
            outputNode: outputBookend,
          }),
          { relayoutBookends: true },
        ),
      )
      setCompletedSteps((prev) => new Set(prev).add('input'))
      return true
    },
    [
      inputNode,
      outputNode,
      scaffoldModel,
      resetStepsAfterInput,
      clearScaffold,
      showModal,
    ],
  )

  const applyOutputBookendSwap = useCallback(
    (type: string, options?: { activeStepAfter?: FlowBuilderStep }) => {
      if (!(OUTPUT_BOOKEND_TYPES as readonly string[]).includes(type)) return false

      const id = outputNode?.id ?? nextNodeId()
      const data = getOutputBookendDefaultData(type, workspaceStylebookId) as Record<string, unknown>
      const node: Node = { id, type, data, position: outputNode?.position ?? { x: 0, y: 0 } }

      if (scaffoldModel && inputNode && outputNode) {
        if (outputNode.type === type) {
          setSelectedNodeId(id)
          return true
        }
        const check = canReplaceOutputBookend(scaffoldModel, type)
        if (!check.ok) {
          showModal({
            title: 'Cannot change destination',
            description: check.reason,
            type: 'warning',
            confirmText: 'OK',
            onConfirm: () => {},
          })
          return false
        }
        setOutputNode(node)
        setScaffoldModel((current) =>
          current
            ? applyLayoutToModel(replaceOutputBookend(current, { type, data }), {
                relayoutBookends: false,
              })
            : current,
        )
        setSelectedNodeId(id)
        setConfigureGateActive(true)
        if (options?.activeStepAfter) setActiveStep(options.activeStepAfter)
        return true
      }

      setOutputNode(node)
      setSelectedNodeId(id)
      setConfigureGateActive(true)
      setActiveStep('output')

      if (!inputNode) {
        clearScaffold()
        setCompletedSteps(resetStepsAfterOutput)
        return true
      }

      const inputBookend = {
        id: inputNode.id,
        type: inputNode.type ?? 'TextInput',
        data: inputNode.data as Record<string, unknown>,
      }
      const outputBookend = { id, type, data }
      setScaffoldModel((current) =>
        applyLayoutToModel(
          clearMiddleNodes({
            ...(current ?? createFlowGraphModel(inputBookend, outputBookend)),
            inputNode: inputBookend,
            outputNode: outputBookend,
          }),
          { relayoutBookends: true },
        ),
      )
      return true
    },
    [
      inputNode,
      outputNode,
      scaffoldModel,
      workspaceStylebookId,
      resetStepsAfterOutput,
      clearScaffold,
      showModal,
    ],
  )

  const handleInputTypeSelect = useCallback(
    (type: string) => {
      applyInputBookendSwap(type)
    },
    [applyInputBookendSwap],
  )

  const handleOutputTypeSelect = useCallback(
    (type: string) => {
      applyOutputBookendSwap(type)
    },
    [applyOutputBookendSwap],
  )

  const handleBookendSwapSelect = useCallback(
    (type: string) => {
      if (bookendSwapKind === 'input') {
        applyInputBookendSwap(type, { activeStepAfter: 'scaffold' })
      } else {
        applyOutputBookendSwap(type, { activeStepAfter: 'scaffold' })
      }
    },
    [applyInputBookendSwap, applyOutputBookendSwap, bookendSwapKind],
  )

  const setNodes = useCallback(
    (updater: Node[] | ((nodes: Node[]) => Node[])) => {
      if (activeStep === 'scaffold' && scaffoldModel) {
        const reactNodes: Node[] = toReactFlowNodes(scaffoldModel).map((node) => ({
          id: node.id,
          type: node.type,
          position: node.position ?? { x: 0, y: 0 },
          data: node.data,
        }))
        const list = typeof updater === 'function' ? updater(reactNodes) : updater
        const previousById = new Map(reactNodes.map((node) => [node.id, node]))
        let nextModel = scaffoldModel
        for (const n of list) {
          if (previousById.get(n.id)?.data !== n.data) {
            setDirtyPanelNodeIds((prev) => new Set(prev).add(n.id))
            setSavedPanelNodeIds((prev) => {
              if (!prev.has(n.id)) return prev
              const next = new Set(prev)
              next.delete(n.id)
              return next
            })
          }
          if (n.id === scaffoldModel.inputNode.id) {
            setInputNode((prev) => (prev ? { ...prev, data: n.data } : prev))
            nextModel = { ...nextModel, inputNode: { ...nextModel.inputNode, data: n.data as Record<string, unknown> } }
          } else if (n.id === scaffoldModel.outputNode.id) {
            setOutputNode((prev) => (prev ? { ...prev, data: n.data } : prev))
            nextModel = {
              ...nextModel,
              outputNode: { ...nextModel.outputNode, data: n.data as Record<string, unknown> },
            }
          } else {
            nextModel = updateMiddleNode(nextModel, n.id, (node) => ({
              ...node,
              data: n.data as Record<string, unknown>,
            }))
          }
        }
        setScaffoldModel(nextModel)
        return
      }

      const current = [inputNode, outputNode].filter((n): n is Node => n != null)
      const list = typeof updater === 'function' ? updater(current) : updater
      const previousById = new Map(current.map((node) => [node.id, node]))
      let nextInput = inputNode
      let nextOutput = outputNode
      for (const n of list) {
        if (previousById.get(n.id)?.data !== n.data) {
          setDirtyPanelNodeIds((prev) => new Set(prev).add(n.id))
          setSavedPanelNodeIds((prev) => {
            if (!prev.has(n.id)) return prev
            const next = new Set(prev)
            next.delete(n.id)
            return next
          })
        }
        if (inputNode?.id === n.id) nextInput = n
        if (outputNode?.id === n.id) nextOutput = n
      }
      if (nextInput && nextInput !== inputNode) setInputNode(nextInput)
      if (nextOutput && nextOutput !== outputNode) setOutputNode(nextOutput)

      if (scaffoldModel) {
        setScaffoldModel((current) => {
          if (!current) return current
          let next = current
          if (nextInput && current.inputNode.id === nextInput.id) {
            const data = nextInput.data as Record<string, unknown>
            if (current.inputNode.data !== data) {
              next = { ...next, inputNode: { ...next.inputNode, data } }
            }
          }
          if (nextOutput && current.outputNode.id === nextOutput.id) {
            const data = nextOutput.data as Record<string, unknown>
            if (current.outputNode.data !== data) {
              next = { ...next, outputNode: { ...next.outputNode, data } }
            }
          }
          return next
        })
      }
    },
    [activeStep, scaffoldModel, inputNode, outputNode],
  )

  const handleTextInputChange = useCallback(
    (text: string) => {
      if (!selectedNodeId) return
      setInputNode((node) =>
        node && node.id === selectedNodeId ? { ...node, data: { ...node.data, text } } : node,
      )
      setDirtyPanelNodeIds((prev) => new Set(prev).add(selectedNodeId))
      setSavedPanelNodeIds((prev) => {
        if (!prev.has(selectedNodeId)) return prev
        const next = new Set(prev)
        next.delete(selectedNodeId)
        return next
      })
    },
    [selectedNodeId],
  )

  const handleInputContinue = useCallback(() => {
    setCompletedSteps((prev) => new Set(prev).add('input'))
    setConfigureGateActive(false)
    setSelectedNodeId(null)
    setActiveStep('output')
  }, [])

  const handleOutputContinue = useCallback(() => {
    setCompletedSteps((prev) => new Set(prev).add('output'))
    setConfigureGateActive(false)
    setSelectedNodeId(null)
    setActiveStep('scaffold')
  }, [])

  const handleInputBookendCancel = useCallback(() => {
    setInputNode(null)
    setOutputNode(null)
    clearScaffold()
    setSelectedNodeId(null)
    setConfigureGateActive(false)
    setCompletedSteps(resetStepsAfterInput)
  }, [clearScaffold, resetStepsAfterInput])

  const handleOutputBookendCancel = useCallback(() => {
    setOutputNode(null)
    clearScaffold()
    setSelectedNodeId(null)
    setConfigureGateActive(false)
    setCompletedSteps(resetStepsAfterOutput)
  }, [clearScaffold, resetStepsAfterOutput])

  const handleScaffoldContinue = useCallback(() => {
    preAddLayoutSnapshotRef.current = null
    setConfigureGateActive(false)
    setSelectedNodeId(null)
  }, [])

  /** Done configuring a bookend on the scaffold step; keep selection so the review panel opens. */
  const handleScaffoldBookendGateContinue = useCallback(() => {
    setConfigureGateActive(false)
  }, [])

  const handleChangeInputSource = useCallback(() => {
    if (inputNode && outputNode && scaffoldModel) {
      setBookendSwapKind('input')
      setBookendSwapOpen(true)
      return
    }
    setInputNode(null)
    setOutputNode(null)
    clearScaffold()
    setSelectedNodeId(null)
    setConfigureGateActive(false)
    setCompletedSteps(resetStepsAfterInput)
    setActiveStep('input')
  }, [inputNode, outputNode, scaffoldModel, resetStepsAfterInput, clearScaffold])

  const handleChangeOutputDestination = useCallback(() => {
    if (inputNode && outputNode && scaffoldModel) {
      setBookendSwapKind('output')
      setBookendSwapOpen(true)
      return
    }
    setOutputNode(null)
    clearScaffold()
    setSelectedNodeId(null)
    setConfigureGateActive(false)
    setCompletedSteps(resetStepsAfterOutput)
    setActiveStep('output')
  }, [inputNode, outputNode, scaffoldModel, resetStepsAfterOutput, clearScaffold])

  const inputBookendId = scaffoldModel?.inputNode.id ?? inputNode?.id ?? null
  const outputBookendId = scaffoldModel?.outputNode.id ?? outputNode?.id ?? null

  const bookendSwapCanvasProps = {
    allowBookendSwap: capabilities.allowBookendEdit,
    inputBookendId,
    outputBookendId,
    onSwapInputBookend: capabilities.allowBookendEdit ? handleChangeInputSource : undefined,
    onSwapOutputBookend: capabilities.allowBookendEdit ? handleChangeOutputDestination : undefined,
  }

  const handleSave = useCallback(async (options?: { stayInEditMode?: boolean }): Promise<boolean> => {
    if (!inputNode || !outputNode) {
      showModal({
        title: 'Flow not ready to save',
        description: 'Choose where content comes in and where results are saved before saving.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }

    const saveModel = buildSaveModel(inputNode, outputNode, scaffoldModel)
    const draftSpec = modelToGraphSpec(saveModel)
    const validation = validateGraphForSave({
      nodes: draftSpec.nodes.map((node) => ({
        id: node.id,
        type: node.type,
        data: node.params,
      })),
      edges: draftSpec.edges,
    })
    if (!validation.ok) {
      showModal({
        title: validation.title,
        description: validation.description,
        type: validation.severity,
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }

    if (flowProjectLoading) {
      showModal({
        title: 'Still loading',
        description: 'Project details for this flow are still loading. Try again in a moment.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }

    if (!resolvedFlowProject) {
      showModal({
        title: 'No project for this flow',
        description:
          'Could not determine which project this flow belongs to. Open the flow from a project or try reloading the page.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }

    try {
      setSaving(true)
      const graphSpec = {
        name: graphName,
        project_id: resolvedFlowProject.id,
        spec: {
          name: graphName.toLowerCase().replace(/\s+/g, '_'),
          nodes: draftSpec.nodes.map((node) => ({
            id: node.id,
            type: node.type,
            params: paramsForGraphSave({
              id: node.id,
              type: node.type,
              data: node.params,
            }),
            position: node.position,
          })),
          edges: draftSpec.edges,
        },
      }

      if (existingGraphId) {
        await updateGraph(existingGraphId, graphSpec)
        if (options?.stayInEditMode) {
          return true
        }
        if (onSaved) {
          onSaved(existingGraphId)
        } else {
          navigate(`/flow/${existingGraphId}`)
        }
      } else {
        const graph = await createGraph(graphSpec)
        if (onSaved) {
          onSaved(graph.id)
        } else {
          navigate(`/flow/${graph.id}`)
        }
      }
      return true
    } catch (error) {
      console.error('Failed to save graph:', error)
      showModal({
        title: 'Save failed',
        description: 'Failed to save flow. Please check the console for details and try again.',
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    } finally {
      setSaving(false)
    }
  }, [
    inputNode,
    outputNode,
    scaffoldModel,
    graphName,
    existingGraphId,
    flowProjectLoading,
    resolvedFlowProject,
    navigate,
    showModal,
    onSaved,
  ])

  const handlePanelSave = useCallback(async (): Promise<void> => {
    if (!selectedNodeId) return
    const saved = await handleSave({ stayInEditMode: true })
    if (!saved) return
    setDirtyPanelNodeIds((prev) => {
      const next = new Set(prev)
      next.delete(selectedNodeId)
      return next
    })
    setSavedPanelNodeIds((prev) => new Set(prev).add(selectedNodeId))
  }, [handleSave, selectedNodeId])

  const buildSnapshot = useCallback(
    (): GuidedFlowSnapshot =>
      captureGuidedFlowSnapshot({
        graphName,
        activeStep,
        completedSteps: [...completedSteps],
        inputNode,
        outputNode,
        scaffoldModel,
        selectedNodeId,
        configureGateActive,
      }),
    [
      graphName,
      activeStep,
      completedSteps,
      inputNode,
      outputNode,
      scaffoldModel,
      selectedNodeId,
      configureGateActive,
    ],
  )

  useImperativeHandle(
    ref,
    () => ({
      takeSnapshot: () => {
        snapshotRef.current = buildSnapshot()
      },
      restoreSnapshot: () => {
        const snap = snapshotRef.current
        if (!snap) return
        setGraphName(snap.graphName)
        setActiveStep(snap.activeStep)
        setCompletedSteps(new Set(snap.completedSteps))
        setInputNode(snap.inputNode)
        setOutputNode(snap.outputNode)
        setScaffoldModel(snap.scaffoldModel)
        setSelectedNodeId(snap.selectedNodeId)
        setConfigureGateActive(snap.configureGateActive)
      },
      save: () => handleSave(),
      hasNodeType: (type: string) => {
        if (inputNode?.type === type) return true
        if (outputNode?.type === type) return true
        return scaffoldModel?.middleNodes.some((node) => node.type === type) ?? false
      },
      isSaving: () => saving,
    }),
    [buildSnapshot, handleSave, inputNode, outputNode, scaffoldModel, saving],
  )

  const handleAddNodeClick = useCallback((parentNodeId: string, anchorRect: DOMRect) => {
    if (configureGateActive) return
    setAddFromParentId(parentNodeId)
    setAddIntoEdge(null)
    setAddChooserAnchor({
      top: anchorRect.top,
      right: anchorRect.right,
      bottom: anchorRect.bottom,
      left: anchorRect.left,
    })
    setAddChooserOpen(true)
  }, [configureGateActive])

  const handleAddEdgeClick = useCallback(
    (sourceId: string, targetId: string, anchorRect: DOMRect) => {
      if (configureGateActive) return
      setAddFromParentId(null)
      setAddIntoEdge({ sourceId, targetId })
      setAddChooserAnchor({
        top: anchorRect.top,
        right: anchorRect.right,
        bottom: anchorRect.bottom,
        left: anchorRect.left,
      })
      setAddChooserOpen(true)
    },
    [configureGateActive],
  )

  const handleNodePositionChange = useCallback(
    (nodeId: string, position: { x: number; y: number }) => {
      setScaffoldModel((model) => (model ? updateNodePosition(model, nodeId, position) : model))
    },
    [],
  )

  const handleTidyLayout = useCallback(() => {
    setAddChooserOpen(false)
    setAddChooserAnchor(null)
    setAddFromParentId(null)
    setAddIntoEdge(null)
    setScaffoldModel((model) =>
      model ? applyLayoutToModel(model, { relayoutBookends: true, xStep: TIDY_LAYOUT_X_STEP }) : model,
    )
    setTidyLayoutKey((key) => key + 1)
  }, [])

  const handleDeleteMiddleNode = useCallback(
    (nodeId: string) => {
      void (async () => {
        if (exitingNodeIds.has(nodeId)) return
        const node = scaffoldModel?.middleNodes.find((n) => n.id === nodeId)
        const label =
          nodeMetadata.find((m) => m.type === node?.type)?.label ?? 'this step'
        const ok = await showConfirm(
          `Remove ${label} from this flow? Any steps after it on the same branch will stay connected.`,
          {
            title: 'Remove step',
            confirmLabel: 'Remove',
            destructive: true,
          },
        )
        if (!ok || !scaffoldModel) return
        try {
          setExitingNodeIds((prev) => new Set(prev).add(nodeId))
          setSelectedNodeId(null)
          setConfigureGateActive(false)
          const timer = window.setTimeout(() => {
            deleteAnimationTimersRef.current.delete(nodeId)
            setScaffoldModel((current) => {
              if (!current?.middleNodes.some((node) => node.id === nodeId)) return current
              return deleteMiddleNode(current, nodeId)
            })
            setDirtyPanelNodeIds((prev) => {
              const next = new Set(prev)
              next.delete(nodeId)
              return next
            })
            setSavedPanelNodeIds((prev) => {
              const next = new Set(prev)
              next.delete(nodeId)
              return next
            })
            setExitingNodeIds((prev) => {
              const next = new Set(prev)
              next.delete(nodeId)
              return next
            })
          }, GUIDED_NODE_EXIT_MS)
          deleteAnimationTimersRef.current.set(nodeId, timer)
        } catch (error) {
          console.error('Failed to delete step:', error)
        }
      })()
    },
    [exitingNodeIds, scaffoldModel, showConfirm],
  )

  const handleCancelMiddleNodeAdd = useCallback(() => {
    if (!selectedNodeId) return
    const snapshot = preAddLayoutSnapshotRef.current
    setScaffoldModel((model) => {
      if (!model?.middleNodes.some((node) => node.id === selectedNodeId)) return model
      let next = deleteMiddleNode(model, selectedNodeId)
      if (snapshot) {
        next = {
          ...next,
          outputNode: {
            ...next.outputNode,
            position: snapshot.outputPosition ?? next.outputNode.position,
          },
          middleNodes: next.middleNodes.map((node) => ({
            ...node,
            position: snapshot.middlePositions.get(node.id) ?? node.position,
          })),
        }
      }
      return next
    })
    preAddLayoutSnapshotRef.current = null
    setDirtyPanelNodeIds((prev) => {
      const next = new Set(prev)
      next.delete(selectedNodeId)
      return next
    })
    setSavedPanelNodeIds((prev) => {
      const next = new Set(prev)
      next.delete(selectedNodeId)
      return next
    })
    setSelectedNodeId(null)
    setConfigureGateActive(false)
  }, [selectedNodeId])

  const deletableNodeIds = useMemo(
    () =>
      new Set(
        scaffoldModel?.middleNodes
          .filter((node) => !exitingNodeIds.has(node.id))
          .map((node) => node.id) ?? [],
      ),
    [exitingNodeIds, scaffoldModel],
  )

  const addNodeCompatibility = useMemo(() => {
    if (!scaffoldModel) {
      return { enabled: [], disabled: [] }
    }
    if (addIntoEdge) {
      const source = getNodeById(scaffoldModel, addIntoEdge.sourceId)
      const target = getNodeById(scaffoldModel, addIntoEdge.targetId)
      if (!source?.type || !target?.type) return { enabled: [], disabled: [] }
      return getCompatibleInsertNodes(
        source.type,
        target.type,
        getBranchAncestry(scaffoldModel, addIntoEdge.sourceId),
      )
    }
    const parentId = addFromParentId
    if (!parentId) {
      return { enabled: [], disabled: [] }
    }
    const parent = getNodeById(scaffoldModel, parentId)
    if (!parent?.type) return { enabled: [], disabled: [] }
    return getCompatibleNextNodes(parent.type, getBranchAncestry(scaffoldModel, parentId))
  }, [addFromParentId, addIntoEdge, scaffoldModel])

  const handleAddNodeTypeSelect = useCallback(
    (type: string) => {
      if (!scaffoldModel) return
      preAddLayoutSnapshotRef.current = {
        outputPosition: scaffoldModel.outputNode.position
          ? { ...scaffoldModel.outputNode.position }
          : undefined,
        middlePositions: new Map(
          scaffoldModel.middleNodes.map((node) => [
            node.id,
            { ...(node.position ?? { x: 0, y: 0 }) },
          ]),
        ),
      }
      const newNode = {
        id: nextNodeId(),
        type,
        data: getMiddleNodeDefaultData(type, workspaceStylebookId),
      }
      setScaffoldModel((model) => {
        if (!model) return model
        let next = model
        if (addIntoEdge) {
          next = insertBetween(model, addIntoEdge.sourceId, addIntoEdge.targetId, newNode)
        } else if (addFromParentId) {
          next = addSiblingBranch(model, addFromParentId, newNode)
        } else {
          return model
        }
        return applyLayoutToModel(next)
      })
      setSelectedNodeId(newNode.id)
      setConfigureGateActive(true)
      setAddChooserOpen(false)
      setAddChooserAnchor(null)
      setAddFromParentId(null)
      setAddIntoEdge(null)
    },
    [addFromParentId, addIntoEdge, scaffoldModel, workspaceStylebookId],
  )

  /**
   * Single click handler for every canvas. Clicking a node always opens its
   * panel. The configure gate (Continue / Cancel footer) is orthogonal: it is
   * armed when a bookend is freshly chosen on step 1/2 or a middle node is
   * freshly added on step 3, and cleared by Continue / Cancel / Close. A
   * regular click does not touch it, so re-clicking the active node keeps the
   * gate visible and clicking a different node leaves the gate state untouched
   * (the footer just attaches to whichever node is now selected).
   */
  const handleNodeClick = useCallback(
    (node: Node) => {
      setSelectedNodeId(node.id)
    },
    [],
  )

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null
    return resolveGuidedSelectedNode(selectedNodeId, activeStep, inputNode, outputNode, scaffoldModel)
  }, [activeStep, selectedNodeId, inputNode, outputNode, scaffoldModel])

  const isMiddleSelected =
    selectedNodeId != null &&
    scaffoldModel?.middleNodes.some((n) => n.id === selectedNodeId) === true

  const isBookendSelected =
    selectedNodeId != null &&
    (selectedNodeId === inputNode?.id ||
      selectedNodeId === outputNode?.id ||
      selectedNodeId === scaffoldModel?.inputNode.id ||
      selectedNodeId === scaffoldModel?.outputNode.id)

  const invalidNodeIds = useMemo(
    () => (scaffoldModel ? getInvalidFlowNodeIds(scaffoldModel) : new Set<string>()),
    [scaffoldModel],
  )
  const invalidConnectionMessage =
    selectedNodeId != null && invalidNodeIds.has(selectedNodeId)
      ? 'The upstream node is incompatible with this node type. Add a compatible node or delete this node to continue.'
      : null

  const showInputChooser = !readOnly && activeStep === 'input' && inputNode == null
  const showInputCanvas = activeStep === 'input' && inputNode != null
  const showOutputChooser = !readOnly && activeStep === 'output' && outputNode == null
  const showOutputCanvas = activeStep === 'output' && outputNode != null

  // One rule: a node is clicked, the panel opens. The gate (Continue / Cancel
  // footer) is armed for fresh configure flows and for wizard source/destination
  // steps when revisiting a bookend.
  const showNodePanel = selectedNode != null
  const panelGateActive = isPanelGateActive({
    readOnly,
    configureGateActive,
    activeStep,
    isBookendSelected,
  })
  const sidePanelOpen = showNodePanel
  const canvasFrameStyle = sidePanelOpen
    ? { marginRight: GUIDED_FLOW_NODE_PANEL_WIDTH_PX }
    : undefined
  const showEditModeCue = !readOnly && (isRunVariant || existingGraphId != null)
  const showCreateCancel = variant === 'create' && !readOnly
  const selectedPanelHasChanges = selectedNodeId != null && dirtyPanelNodeIds.has(selectedNodeId)
  const selectedPanelWasSaved = selectedNodeId != null && savedPanelNodeIds.has(selectedNodeId)

  const rootClassName = hideHeader
    ? `flex min-h-0 flex-1 flex-col ${className ?? ''}`
    : `flex h-screen flex-col ${className ?? ''}`

  const handleConfigureContinue =
    activeStep === 'input'
      ? handleInputContinue
      : activeStep === 'output'
        ? handleOutputContinue
        : handleScaffoldContinue

  const handleCancelCreateFlow = useCallback(async () => {
    const hasProgress = inputNode != null || outputNode != null
    if (hasProgress) {
      const ok = await showConfirm('Changes to this flow will be lost.', {
        title: 'Leave without saving?',
        confirmLabel: 'Leave',
        destructive: true,
      })
      if (!ok) return
    }
    const slug = resolvedFlowProject?.slug
    navigate(slug ? `/project/${encodeURIComponent(slug)}` : '/')
  }, [inputNode, navigate, outputNode, resolvedFlowProject?.slug, showConfirm])

  if (graphLoading) {
    return (
      <div
        className={
          hideHeader
            ? 'flex flex-1 items-center justify-center text-muted-foreground'
            : 'flex h-screen items-center justify-center text-muted-foreground'
        }
      >
        Loading flow…
      </div>
    )
  }

  return (
    <div className={rootClassName}>
      {!hideHeader && (
      <div className="sticky top-0 z-10 border-b bg-background">
        <div className="container mx-auto flex items-center justify-between gap-4 px-4 py-4">
          <div className="min-w-0 flex-1 space-y-2">
            <PageBreadcrumbs items={headerBreadcrumbItems} />
            <div>
              <FlowTitleRow name={graphName} onSave={handleFlowNameSave} canEdit={!readOnly} />
              {activeStep !== 'scaffold' ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {activeStep === 'input'
                    ? 'Build your flow step-by-step'
                    : 'Choose where results are saved'}
                </p>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">Set up your flow step by step</p>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {showCreateCancel ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleCancelCreateFlow()}
                disabled={flowProjectLoading}
              >
                Cancel
              </Button>
            ) : null}
            <Button
              onClick={() => void handleSave()}
              disabled={saving || !inputNode || !outputNode}
            >
              <Save className="mr-2 h-4 w-4" />
              {saving ? 'Saving…' : 'Save flow'}
            </Button>
          </div>
        </div>
      </div>
      )}

      {activeStep !== 'scaffold' && (
        <FlowStepper
          activeStep={activeStep}
          completedSteps={completedStepsReadonly}
          onStepChange={handleStepChange}
          canNavigateTo={canNavigateTo}
        />
      )}

      <div
        className={`relative flex-1 overflow-hidden transition-colors ${
          showEditModeCue ? 'bg-amber-50/25' : ''
        }`}
      >
        {showEditModeCue && (
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center border-t border-amber-200/70 bg-amber-50/40 py-2">
            <div className="rounded-full border border-amber-200 bg-background/90 px-3 py-1 text-xs font-medium text-amber-800 shadow-sm">
              Editing flow · Save changes when you're done
            </div>
          </div>
        )}
        {activeStep === 'input' && (
          <div className="flex h-full flex-col">
            {showInputChooser && (
              <div className="flex-1 overflow-y-auto px-4 py-6">
                {STEP_CHOOSER_COPY.input && (
                  <div className="mx-auto my-12 max-w-4xl px-4 text-center">
                    <h2 className="text-2xl font-semibold">{STEP_CHOOSER_COPY.input.title}</h2>
                    <p className="mx-auto mt-1 max-w-2xl text-sm text-muted-foreground">
                      {STEP_CHOOSER_COPY.input.description}
                    </p>
                  </div>
                )}
                <BookendChooser kind="input" onSelect={handleInputTypeSelect} />
              </div>
            )}
            {showInputCanvas && inputNode && (
              <div
                className="relative min-h-0 flex-1 transition-[margin] duration-300"
                style={canvasFrameStyle}
              >
                <GuidedFlowCanvas
                  inputNode={inputNode}
                  outputNode={outputNode}
                  selectedNodeId={selectedNodeId}
                  reserveRightPx={sidePanelOpen ? 1 : 0}
                  onNodeClick={handleNodeClick}
                  {...bookendSwapCanvasProps}
                />
              </div>
            )}
          </div>
        )}

        {activeStep === 'output' && (
          <div className="flex h-full flex-col">
            {showOutputChooser && (
              <div className="flex-1 overflow-y-auto px-4 py-6">
                {STEP_CHOOSER_COPY.output && (
                  <div className="mx-auto my-12 max-w-4xl px-4 text-center">
                    <h2 className="text-2xl font-semibold">{STEP_CHOOSER_COPY.output.title}</h2>
                    <p className="mx-auto mt-1 max-w-2xl text-sm text-muted-foreground">
                      {STEP_CHOOSER_COPY.output.description}
                    </p>
                  </div>
                )}
                <BookendChooser kind="output" onSelect={handleOutputTypeSelect} />
              </div>
            )}
            {showOutputCanvas && outputNode && (
              <div
                className="relative min-h-0 flex-1 transition-[margin] duration-300"
                style={canvasFrameStyle}
              >
                <GuidedFlowCanvas
                  inputNode={inputNode}
                  outputNode={outputNode}
                  selectedNodeId={selectedNodeId}
                  reserveRightPx={sidePanelOpen ? 1 : 0}
                  onNodeClick={handleNodeClick}
                  {...bookendSwapCanvasProps}
                />
              </div>
            )}
          </div>
        )}

        {activeStep === 'scaffold' && inputNode && outputNode && scaffoldModel && (
          <div className="flex h-full flex-col">
            <div className="relative min-h-0 flex-1 transition-[margin] duration-300" style={canvasFrameStyle}>
              <GuidedFlowCanvas
                scaffoldModel={scaffoldModel}
                readOnly={readOnly}
                allowAddNodes={capabilities.allowAddNodes && !configureGateActive}
                allowNodeDrag={capabilities.allowNodeDrag}
                allowDeleteNodes={capabilities.allowDelete && !configureGateActive}
                deletableNodeIds={deletableNodeIds}
                exitingNodeIds={exitingNodeIds}
                reserveRightPx={sidePanelOpen ? 1 : 0}
                selectedNodeId={selectedNodeId}
                onAddNodeClick={
                  capabilities.allowAddNodes && !configureGateActive ? handleAddNodeClick : undefined
                }
                onAddEdgeClick={
                  capabilities.allowAddNodes && !configureGateActive ? handleAddEdgeClick : undefined
                }
                onDeleteNodeClick={
                  capabilities.allowDelete ? handleDeleteMiddleNode : undefined
                }
                {...bookendSwapCanvasProps}
                onNodeClick={handleNodeClick}
                onNodePositionChange={
                  capabilities.allowNodeDrag ? handleNodePositionChange : undefined
                }
                onTidyLayout={!readOnly && existingGraphId != null ? handleTidyLayout : undefined}
                tidyLayoutKey={tidyLayoutKey}
              />
              {showRunPanel && onCloseRunPanel && (
                <RunPanel
                  onClose={onCloseRunPanel}
                  running={running}
                  currentRun={currentRun}
                />
              )}
            </div>
          </div>
        )}

        {showNodePanel && selectedNode && (
          <ConfigureGatePanel
            selectedNode={selectedNode}
            gateActive={panelGateActive}
            onContinue={
              panelGateActive
                ? activeStep === 'scaffold' && isBookendSelected
                  ? handleScaffoldBookendGateContinue
                  : handleConfigureContinue
                : handleConfigureContinue
            }
            onCancel={
              panelGateActive && activeStep === 'input'
                ? handleInputBookendCancel
                : panelGateActive && activeStep === 'output'
                  ? handleOutputBookendCancel
                  : panelGateActive && activeStep === 'scaffold' && isMiddleSelected
                    ? handleCancelMiddleNodeAdd
                    : undefined
            }
            onClose={() => {
              setSelectedNodeId(null)
              setConfigureGateActive(false)
            }}
            onSave={() => void handlePanelSave()}
            onTextChange={activeStep === 'input' ? handleTextInputChange : undefined}
            setNodes={setNodes}
            graphContext={graphContext}
            isMiddleNode={isMiddleSelected}
            viewOnly={readOnly}
            onDelete={
              capabilities.allowDelete && activeStep === 'scaffold' && isMiddleSelected && !panelGateActive
                ? handleDeleteMiddleNode
                : undefined
            }
            running={running}
            saving={saving}
            canSave={canSavePanelChanges({
              activeStep,
              inputNode,
              outputNode,
              hasChanges: selectedPanelHasChanges,
            })}
            saved={selectedPanelWasSaved}
            currentRun={currentRun}
            nodeOutputLookupSpec={nodeOutputLookupSpec}
            invalidConnectionMessage={invalidConnectionMessage}
            showModal={showModal}
          />
        )}
      </div>

      <AddNodeChooser
        open={addChooserOpen && capabilities.allowAddNodes}
        onOpenChange={(open) => {
          setAddChooserOpen(open)
          if (!open) {
            setAddChooserAnchor(null)
            setAddFromParentId(null)
            setAddIntoEdge(null)
          }
        }}
        compatibility={addNodeCompatibility}
        onSelect={handleAddNodeTypeSelect}
        anchorRect={addChooserAnchor}
      />

      <BookendSwapDialog
        open={bookendSwapOpen}
        kind={bookendSwapKind}
        selectedType={
          bookendSwapKind === 'input' ? inputNode?.type ?? undefined : outputNode?.type ?? undefined
        }
        onOpenChange={setBookendSwapOpen}
        onSelect={handleBookendSwapSelect}
      />

      {modalConfig && (
        <ConfirmDialog
          open={modalOpen}
          onOpenChange={setModalOpen}
          title={modalConfig.title}
          description={modalConfig.description}
          type={modalConfig.type}
          confirmText={modalConfig.confirmText}
          onConfirm={modalConfig.onConfirm}
        />
      )}
    </div>
  )
},
)

export default GuidedFlowBuilder
