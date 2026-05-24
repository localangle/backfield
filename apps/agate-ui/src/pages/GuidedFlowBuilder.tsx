import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { Node } from 'reactflow'

import AddNodeChooser from '@/components/flow-builder/AddNodeChooser'
import BookendChooser from '@/components/flow-builder/BookendChooser'
import ConfigureGatePanel from '@/components/flow-builder/ConfigureGatePanel'
import FlowStepper from '@/components/flow-builder/FlowStepper'
import GuidedFlowCanvas from '@/components/flow-builder/GuidedFlowCanvas'
import ConfirmDialog from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import {
  getInputBookendDefaultData,
  getMiddleNodeDefaultData,
  getOutputBookendDefaultData,
} from '@/lib/flowBuilderDefaults'
import {
  addSiblingBranch,
  applyLayoutToModel,
  createFlowGraphModel,
  getBranchAncestry,
  getNodeById,
  insertAfter,
  insertBetween,
  updateMiddleNode,
  type FlowGraphModel,
} from '@/lib/flowGraphModel'
import {
  canNavigateToStep,
  STEP_HEADINGS,
  type FlowBuilderStep,
} from '@/lib/flowBuilderSteps'
import { getCompatibleNextNodes } from '@/lib/nodeCompatibility'
import { getProject, listProjects, type Project } from '@/lib/api'
import { fetchProjectEffectiveAiModels } from '@/lib/core-api'
import { INPUT_BOOKEND_TYPES, OUTPUT_BOOKEND_TYPES } from '@/lib/flowValidation'
import { ArrowLeft } from 'lucide-react'

let nodeIdCounter = 0
const nextNodeId = () => `node-${nodeIdCounter++}`

export default function GuidedFlowBuilder() {
  const [searchParams] = useSearchParams()
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
  const [edgeInsert, setEdgeInsert] = useState<{ sourceId: string; targetId: string } | null>(null)
  const [resolvedFlowProject, setResolvedFlowProject] = useState<Project | null>(null)
  const [flowProjectLoading, setFlowProjectLoading] = useState(false)

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
  }, [searchParams])

  const flowProjectId = resolvedFlowProject?.id ?? null
  const workspaceStylebookId = resolvedFlowProject?.workspace_stylebook_id ?? null

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
        return createFlowGraphModel(inputBookend, outputBookend)
      }
      return {
        ...current,
        inputNode: inputBookend,
        outputNode: outputBookend,
      }
    })
  }, [activeStep, inputNode, outputNode])

  const handleStepChange = useCallback(
    (step: FlowBuilderStep) => {
      if (!canNavigateToStep(step, completedStepsReadonly)) return
      setActiveStep(step)
      setAddChooserOpen(false)
      setAddFromParentId(null)
      setEdgeInsert(null)
      if (step === 'input' && inputNode) {
        setSelectedNodeId(inputNode.id)
        setConfigureGateActive(!completedSteps.has('input'))
      } else if (step === 'output' && outputNode) {
        setSelectedNodeId(outputNode.id)
        setConfigureGateActive(!completedSteps.has('output'))
      } else {
        setSelectedNodeId(null)
        setConfigureGateActive(false)
      }
    },
    [completedStepsReadonly, inputNode, outputNode, completedSteps],
  )

  const handleInputTypeSelect = useCallback(
    (type: string) => {
      if (!(INPUT_BOOKEND_TYPES as readonly string[]).includes(type)) return
      const id = inputNode?.id ?? nextNodeId()
      const node: Node = {
        id,
        type,
        position: { x: 0, y: 0 },
        data: getInputBookendDefaultData(type),
      }
      setInputNode(node)
      setOutputNode(null)
      clearScaffold()
      setSelectedNodeId(id)
      setConfigureGateActive(true)
      setCompletedSteps(resetStepsAfterInput)
      setActiveStep('input')
    },
    [inputNode, resetStepsAfterInput, clearScaffold],
  )

  const handleOutputTypeSelect = useCallback(
    (type: string) => {
      if (!(OUTPUT_BOOKEND_TYPES as readonly string[]).includes(type)) return
      const id = outputNode?.id ?? nextNodeId()
      const node: Node = {
        id,
        type,
        position: { x: 0, y: 0 },
        data: getOutputBookendDefaultData(type, workspaceStylebookId),
      }
      setOutputNode(node)
      clearScaffold()
      setSelectedNodeId(id)
      setConfigureGateActive(true)
      setCompletedSteps(resetStepsAfterOutput)
      setActiveStep('output')
    },
    [outputNode, workspaceStylebookId, resetStepsAfterOutput, clearScaffold],
  )

  const setNodes = useCallback(
    (updater: Node[] | ((nodes: Node[]) => Node[])) => {
      if (activeStep === 'scaffold' && scaffoldModel) {
        const reactNodes: Node[] = [
          { ...scaffoldModel.inputNode, position: { x: 0, y: 0 } },
          ...scaffoldModel.middleNodes.map((n) => ({ ...n, position: n.position ?? { x: 0, y: 0 } })),
          { ...scaffoldModel.outputNode, position: { x: 0, y: 0 } },
        ]
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
    setInputNode(null)
    setOutputNode(null)
    clearScaffold()
    setSelectedNodeId(null)
    setConfigureGateActive(false)
    setCompletedSteps(resetStepsAfterInput)
  }, [resetStepsAfterInput, clearScaffold])

  const handleChangeOutputDestination = useCallback(() => {
    setOutputNode(null)
    clearScaffold()
    setSelectedNodeId(null)
    setConfigureGateActive(false)
    setCompletedSteps(resetStepsAfterOutput)
  }, [resetStepsAfterOutput, clearScaffold])

  const handleAddNodeClick = useCallback((parentNodeId: string) => {
    if (configureGateActive) return
    setEdgeInsert(null)
    setAddFromParentId(parentNodeId)
    setAddChooserOpen(true)
  }, [configureGateActive])

  const handleEdgeInsertClick = useCallback(
    (sourceId: string, targetId: string) => {
      if (configureGateActive) return
      setEdgeInsert({ sourceId, targetId })
      setAddFromParentId(sourceId)
      setAddChooserOpen(true)
    },
    [configureGateActive],
  )

  const handleTidyLayout = useCallback(() => {
    setScaffoldModel((model) => (model ? applyLayoutToModel(model) : model))
  }, [])

  const addNodeCompatibility = useMemo(() => {
    if (!scaffoldModel) {
      return { enabled: [], disabled: [] }
    }
    const parentId = edgeInsert?.sourceId ?? addFromParentId
    if (!parentId) {
      return { enabled: [], disabled: [] }
    }
    const parent = getNodeById(scaffoldModel, parentId)
    if (!parent?.type) return { enabled: [], disabled: [] }
    return getCompatibleNextNodes(parent.type, getBranchAncestry(scaffoldModel, parentId))
  }, [addFromParentId, edgeInsert, scaffoldModel])

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
        if (edgeInsert) {
          next = insertBetween(model, edgeInsert.sourceId, edgeInsert.targetId, newNode)
        } else if (addFromParentId === model.inputNode.id) {
          next = addSiblingBranch(model, addFromParentId, newNode)
        } else if (addFromParentId) {
          next = insertAfter(model, addFromParentId, newNode)
        } else {
          return model
        }
        return applyLayoutToModel(next)
      })
      setSelectedNodeId(newNode.id)
      setConfigureGateActive(true)
      setAddChooserOpen(false)
      setAddFromParentId(null)
      setEdgeInsert(null)
    },
    [addFromParentId, edgeInsert, scaffoldModel, workspaceStylebookId],
  )

  const handleNodeDoubleClick = useCallback((node: Node) => {
    if (activeStep !== 'scaffold') return
    const isMiddle = scaffoldModel?.middleNodes.some((n) => n.id === node.id)
    if (!isMiddle) return
    setSelectedNodeId(node.id)
    setConfigureGateActive(false)
  }, [activeStep, scaffoldModel])

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null
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

  const showInputChooser = activeStep === 'input' && inputNode == null
  const showInputCanvas = activeStep === 'input' && inputNode != null
  const showOutputChooser = activeStep === 'output' && outputNode == null
  const showOutputCanvas = activeStep === 'output' && outputNode != null

  const showBookendConfigurePanel =
    selectedNode &&
    (activeStep === 'input' || activeStep === 'output') &&
    (configureGateActive || completedSteps.has(activeStep))

  const showScaffoldConfigurePanel =
    selectedNode && activeStep === 'scaffold' && isMiddleSelected && configureGateActive

  const showScaffoldReviewPanel =
    selectedNode &&
    activeStep === 'scaffold' &&
    isMiddleSelected &&
    !configureGateActive &&
    selectedNodeId != null

  const handleConfigureContinue =
    activeStep === 'input'
      ? handleInputContinue
      : activeStep === 'output'
        ? handleOutputContinue
        : handleScaffoldContinue

  return (
    <div className="flex h-screen flex-col">
      <div className="sticky top-0 z-10 border-b bg-background">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <p className="flex items-center gap-4">
            <Link to="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
            <span>
              <input
                type="text"
                value={graphName}
                onChange={(e) => setGraphName(e.target.value)}
                className="border-none bg-transparent text-2xl font-bold outline-none"
                aria-label="Flow name"
              />
              <span className="mt-1 block text-xs text-muted-foreground">Set up your flow step by step</span>
            </span>
          </p>
        </div>
      </div>

      <FlowStepper
        activeStep={activeStep}
        completedSteps={completedStepsReadonly}
        onStepChange={handleStepChange}
        canNavigateTo={canNavigateTo}
      />

      <div className="relative flex-1 overflow-hidden">
        {activeStep === 'input' && (
          <div className="flex h-full flex-col">
            <div className="flex items-start justify-between gap-4 border-b px-4 py-6">
              <div>
                <h1 className="text-xl font-semibold">{STEP_HEADINGS.input}</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Choose how articles or content enter this flow.
                </p>
              </div>
              {inputNode && (
                <Button variant="outline" size="sm" onClick={handleChangeInputSource}>
                  Change source
                </Button>
              )}
            </div>
            {showInputChooser && (
              <div className="flex-1 overflow-y-auto px-4 py-8">
                <BookendChooser kind="input" onSelect={handleInputTypeSelect} />
              </div>
            )}
            {showInputCanvas && inputNode && (
              <div className="relative min-h-0 flex-1">
                <GuidedFlowCanvas inputNode={inputNode} />
              </div>
            )}
          </div>
        )}

        {activeStep === 'output' && (
          <div className="flex h-full flex-col">
            <div className="flex items-start justify-between gap-4 border-b px-4 py-6">
              <div>
                <h1 className="text-xl font-semibold">{STEP_HEADINGS.output}</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Choose where this flow saves its results.
                </p>
              </div>
              {outputNode && (
                <Button variant="outline" size="sm" onClick={handleChangeOutputDestination}>
                  Change destination
                </Button>
              )}
            </div>
            {showOutputChooser && (
              <div className="flex-1 overflow-y-auto px-4 py-8">
                <BookendChooser kind="output" onSelect={handleOutputTypeSelect} />
              </div>
            )}
            {showOutputCanvas && outputNode && (
              <div className="relative min-h-0 flex-1">
                <GuidedFlowCanvas outputNode={outputNode} />
              </div>
            )}
          </div>
        )}

        {activeStep === 'scaffold' && inputNode && outputNode && scaffoldModel && (
          <div className="flex h-full flex-col">
            <div className="border-b px-4 py-6">
              <h1 className="text-xl font-semibold">{STEP_HEADINGS.scaffold}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Add steps between your content source and where results are saved.
              </p>
            </div>
            <div className="relative min-h-0 flex-1">
              <GuidedFlowCanvas
                scaffoldModel={scaffoldModel}
                showEmptyMiddleCta={scaffoldModel.middleNodes.length === 0}
                allowAddNodes={!configureGateActive}
                onAddNodeClick={handleAddNodeClick}
                onEdgeInsertClick={handleEdgeInsertClick}
                onTidyLayout={handleTidyLayout}
                onNodeDoubleClick={handleNodeDoubleClick}
              />
            </div>
          </div>
        )}

        {(showBookendConfigurePanel || showScaffoldConfigurePanel) && selectedNode && (
          <ConfigureGatePanel
            selectedNode={selectedNode}
            gateActive={configureGateActive}
            onContinue={handleConfigureContinue}
            onClose={() => {
              setSelectedNodeId(null)
              setConfigureGateActive(false)
            }}
            onTextChange={activeStep === 'input' ? handleTextInputChange : undefined}
            setNodes={setNodes}
            graphContext={graphContext}
            isMiddleNode={isMiddleSelected}
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
            isMiddleNode
            showModal={showModal}
          />
        )}
      </div>

      <AddNodeChooser
        open={addChooserOpen}
        onOpenChange={setAddChooserOpen}
        compatibility={addNodeCompatibility}
        onSelect={handleAddNodeTypeSelect}
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
}
