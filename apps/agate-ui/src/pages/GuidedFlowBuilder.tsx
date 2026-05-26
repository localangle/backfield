import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { Node } from 'reactflow'

import { PageBreadcrumbs } from '@/components/PageBreadcrumbs'
import AddNodeChooser from '@/components/flow-builder/AddNodeChooser'
import BookendChooser from '@/components/flow-builder/BookendChooser'
import BookendSwapDialog from '@/components/flow-builder/BookendSwapDialog'
import ConfigureGatePanel from '@/components/flow-builder/ConfigureGatePanel'
import FlowStepper from '@/components/flow-builder/FlowStepper'
import GuidedFlowCanvas, {
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
  replaceInputBookend,
  replaceOutputBookend,
  getBranchAncestry,
  getNodeById,
  hydrateFromSpec,
  insertAfter,
  modelToGraphSpec,
  updateMiddleNode,
  toReactFlowNodes,
  updateNodePosition,
  type FlowGraphModel,
} from '@/lib/flowGraphModel'
import {
  canNavigateToStep,
  completedStepsForEdit,
  getInitialEditStep,
  STEP_CHOOSER_COPY,
  type FlowBuilderStep,
} from '@/lib/flowBuilderSteps'
import { getCompatibleNextNodes } from '@/lib/nodeCompatibility'
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
  const [configureGateActive, setConfigureGateActive] = useState(false)
  const [addChooserOpen, setAddChooserOpen] = useState(false)
  const [addFromParentId, setAddFromParentId] = useState<string | null>(null)
  const [bookendSwapOpen, setBookendSwapOpen] = useState(false)
  const [bookendSwapKind, setBookendSwapKind] = useState<'input' | 'output'>('input')
  /** After the first middle step is added or the empty-flow CTA is dismissed, do not show it again. */
  const [firstStepIntroComplete, setFirstStepIntroComplete] = useState(false)
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
        setScaffoldModel(applyLayoutToModel(hydrated.model, { relayoutBookends: true }))
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
    setFirstStepIntroComplete(false)
  }, [])

  useEffect(() => {
    if ((scaffoldModel?.middleNodes.length ?? 0) > 0) {
      setFirstStepIntroComplete(true)
    }
  }, [scaffoldModel?.middleNodes.length])

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
        { relayoutBookends: true },
      )
    })
  }, [activeStep, inputNode, outputNode])

  const handleStepChange = useCallback(
    (step: FlowBuilderStep) => {
      if (!canNavigateToStep(step, completedStepsReadonly)) return
      setActiveStep(step)
      setAddChooserOpen(false)
      setAddFromParentId(null)
      if (step === 'input' && inputNode) {
        setSelectedNodeId(inputNode.id)
        setConfigureGateActive(!readOnly && !completedSteps.has('input'))
      } else if (step === 'output' && outputNode) {
        setSelectedNodeId(outputNode.id)
        setConfigureGateActive(!readOnly && !completedSteps.has('output'))
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
      setCompletedSteps((prev) => new Set(prev).add('output'))
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
        let nextModel = scaffoldModel
        for (const n of list) {
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
      for (const n of list) {
        if (inputNode?.id === n.id) setInputNode(n)
        if (outputNode?.id === n.id) setOutputNode(n)
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

  const handleScaffoldContinue = useCallback(() => {
    setConfigureGateActive(false)
    setSelectedNodeId(null)
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

  const handleSave = useCallback(async (): Promise<boolean> => {
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

  const handleAddNodeClick = useCallback((parentNodeId: string) => {
    if (configureGateActive) return
    setAddFromParentId(parentNodeId)
    setAddChooserOpen(true)
  }, [configureGateActive])

  const handleNodePositionChange = useCallback(
    (nodeId: string, position: { x: number; y: number }) => {
      setScaffoldModel((model) => (model ? updateNodePosition(model, nodeId, position) : model))
    },
    [],
  )

  const handleDeleteMiddleNode = useCallback(
    (nodeId: string) => {
      void (async () => {
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
          setScaffoldModel(deleteMiddleNode(scaffoldModel, nodeId))
          setSelectedNodeId(null)
          setConfigureGateActive(false)
        } catch (error) {
          console.error('Failed to delete step:', error)
        }
      })()
    },
    [scaffoldModel, showConfirm],
  )

  const deletableNodeIds = useMemo(
    () => new Set(scaffoldModel?.middleNodes.map((node) => node.id) ?? []),
    [scaffoldModel],
  )

  const addNodeCompatibility = useMemo(() => {
    if (!scaffoldModel) {
      return { enabled: [], disabled: [] }
    }
    const parentId = addFromParentId
    if (!parentId) {
      return { enabled: [], disabled: [] }
    }
    const parent = getNodeById(scaffoldModel, parentId)
    if (!parent?.type) return { enabled: [], disabled: [] }
    return getCompatibleNextNodes(parent.type, getBranchAncestry(scaffoldModel, parentId))
  }, [addFromParentId, scaffoldModel])

  const handleAddNodeTypeSelect = useCallback(
    (type: string) => {
      if (!scaffoldModel) return
      const newNode = {
        id: nextNodeId(),
        type,
        data: getMiddleNodeDefaultData(type, workspaceStylebookId),
      }
      setScaffoldModel((model) => {
        if (!model) return model
        let next = model
        if (addFromParentId === model.inputNode.id) {
          next = addSiblingBranch(model, addFromParentId, newNode)
        } else if (addFromParentId) {
          next = insertAfter(model, addFromParentId, newNode)
        } else {
          return model
        }
        return applyLayoutToModel(next, { relayoutBookends: true })
      })
      setSelectedNodeId(newNode.id)
      setConfigureGateActive(true)
      setAddChooserOpen(false)
      setAddFromParentId(null)
    },
    [addFromParentId, scaffoldModel, workspaceStylebookId],
  )

  const handleScaffoldNodeSelect = useCallback(
    (node: Node) => {
      if (activeStep !== 'scaffold') return

      const isMiddle = scaffoldModel?.middleNodes.some((n) => n.id === node.id) ?? false
      const isBookend = node.id === inputNode?.id || node.id === outputNode?.id
      if (!isMiddle && !isBookend) return

      setSelectedNodeId(node.id)
      setConfigureGateActive(false)
    },
    [activeStep, scaffoldModel, inputNode, outputNode],
  )

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null
    if (scaffoldModel?.inputNode.id === selectedNodeId) {
      return {
        ...scaffoldModel.inputNode,
        position: scaffoldModel.inputNode.position ?? { x: 0, y: 0 },
      } as Node
    }
    if (scaffoldModel?.outputNode.id === selectedNodeId) {
      return {
        ...scaffoldModel.outputNode,
        position: scaffoldModel.outputNode.position ?? { x: 0, y: 0 },
      } as Node
    }
    if (inputNode?.id === selectedNodeId) return inputNode
    if (outputNode?.id === selectedNodeId) return outputNode
    const middle = scaffoldModel?.middleNodes.find((n) => n.id === selectedNodeId)
    if (middle) {
      return { ...middle, position: middle.position ?? { x: 0, y: 0 } } as Node
    }
    return null
  }, [selectedNodeId, inputNode, outputNode, scaffoldModel])

  const isMiddleSelected =
    selectedNodeId != null &&
    scaffoldModel?.middleNodes.some((n) => n.id === selectedNodeId) === true

  const isBookendSelected =
    selectedNodeId != null &&
    (selectedNodeId === inputNode?.id || selectedNodeId === outputNode?.id)

  const showInputChooser = !readOnly && activeStep === 'input' && inputNode == null
  const showInputCanvas = activeStep === 'input' && inputNode != null
  const showOutputChooser = !readOnly && activeStep === 'output' && outputNode == null
  const showOutputCanvas = activeStep === 'output' && outputNode != null

  const showBookendConfigurePanel =
    selectedNode &&
    (activeStep === 'input' || activeStep === 'output') &&
    (readOnly || configureGateActive || completedSteps.has(activeStep))

  const showScaffoldConfigurePanel =
    selectedNode &&
    activeStep === 'scaffold' &&
    isMiddleSelected &&
    configureGateActive &&
    !readOnly

  const showScaffoldReviewPanel =
    selectedNode &&
    activeStep === 'scaffold' &&
    (isMiddleSelected || isBookendSelected) &&
    (readOnly || !configureGateActive) &&
    selectedNodeId != null

  const sidePanelOpen =
    showScaffoldReviewPanel || showScaffoldConfigurePanel || showBookendConfigurePanel
  const canvasFrameStyle = sidePanelOpen
    ? { marginRight: GUIDED_FLOW_NODE_PANEL_WIDTH_PX }
    : undefined

  const rootClassName = hideHeader
    ? `flex min-h-0 flex-1 flex-col ${className ?? ''}`
    : `flex h-screen flex-col ${className ?? ''}`

  const handleConfigureContinue =
    activeStep === 'input'
      ? handleInputContinue
      : activeStep === 'output'
        ? handleOutputContinue
        : handleScaffoldContinue

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
              <input
                type="text"
                value={graphName}
                onChange={(e) => setGraphName(e.target.value)}
                className="w-full min-w-0 border-none bg-transparent text-2xl font-bold outline-none"
                aria-label="Flow name"
              />
              {activeStep !== 'scaffold' ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {activeStep === 'input'
                    ? 'Choose where content comes in'
                    : 'Choose where results are saved'}
                </p>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">Set up your flow step by step</p>
              )}
            </div>
          </div>
          <Button
            onClick={() => void handleSave()}
            disabled={saving || !inputNode || !outputNode}
          >
            <Save className="mr-2 h-4 w-4" />
            {saving ? 'Saving…' : 'Save flow'}
          </Button>
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

      <div className="relative flex-1 overflow-hidden">
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
                showEmptyMiddleCta={
                  !readOnly &&
                  scaffoldModel.middleNodes.length === 0 &&
                  !firstStepIntroComplete
                }
                onEmptyMiddleCtaDismiss={() => setFirstStepIntroComplete(true)}
                allowAddNodes={capabilities.allowAddNodes}
                allowNodeDrag={capabilities.allowNodeDrag}
                allowDeleteNodes={capabilities.allowDelete && !configureGateActive}
                deletableNodeIds={deletableNodeIds}
                reserveRightPx={sidePanelOpen ? 1 : 0}
                selectedNodeId={selectedNodeId}
                onAddNodeClick={capabilities.allowAddNodes ? handleAddNodeClick : undefined}
                onDeleteNodeClick={
                  capabilities.allowDelete ? handleDeleteMiddleNode : undefined
                }
                {...bookendSwapCanvasProps}
                onNodeClick={handleScaffoldNodeSelect}
                onNodePositionChange={
                  capabilities.allowNodeDrag ? handleNodePositionChange : undefined
                }
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

        {(showBookendConfigurePanel || showScaffoldConfigurePanel) && selectedNode && (
          <ConfigureGatePanel
            selectedNode={selectedNode}
            gateActive={configureGateActive && !readOnly}
            onContinue={handleConfigureContinue}
            onClose={() => {
              setSelectedNodeId(null)
              setConfigureGateActive(false)
            }}
            onTextChange={activeStep === 'input' ? handleTextInputChange : undefined}
            setNodes={setNodes}
            graphContext={graphContext}
            isMiddleNode={isMiddleSelected}
            viewOnly={readOnly}
            onDelete={
              capabilities.allowDelete && isMiddleSelected ? handleDeleteMiddleNode : undefined
            }
            running={running}
            currentRun={currentRun}
            nodeOutputLookupSpec={nodeOutputLookupSpec}
            showModal={showModal}
          />
        )}

        {showScaffoldReviewPanel && selectedNode && (
          <ConfigureGatePanel
            selectedNode={selectedNode}
            gateActive={false}
            onContinue={handleScaffoldContinue}
            onClose={() => setSelectedNodeId(null)}
            setNodes={setNodes}
            graphContext={graphContext}
            isMiddleNode={isMiddleSelected}
            viewOnly={readOnly}
            onDelete={
              capabilities.allowDelete && isMiddleSelected ? handleDeleteMiddleNode : undefined
            }
            running={running}
            currentRun={currentRun}
            nodeOutputLookupSpec={nodeOutputLookupSpec}
            showModal={showModal}
          />
        )}
      </div>

      <AddNodeChooser
        open={addChooserOpen && capabilities.allowAddNodes}
        onOpenChange={setAddChooserOpen}
        compatibility={addNodeCompatibility}
        onSelect={handleAddNodeTypeSelect}
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
