import { useState, useCallback, useRef, useMemo, Suspense, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import ReactFlow, {
  Node,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  NodeTypes,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import NodePalette from '@/components/NodePalette'
import NodePanel from '@/components/NodePanel'
import ConfirmDialog from '@/components/ConfirmDialog'
import { nodeComponents, nodeMetadata } from '@/nodes/registry'
import {
  createGraph,
  getGraph,
  getProject,
  listProjects,
  updateGraph,
  type Project,
} from '@/lib/api'
import { ArrowLeft, Save, Info } from 'lucide-react'
import { Link } from 'react-router-dom'

let id = 0
const getId = () => `node-${id++}`

export default function GraphBuilder() {
  const navigate = useNavigate()
  const { graphId: routeGraphId } = useParams<{ graphId: string }>()
  const [searchParams] = useSearchParams()
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null)
  const [graphName, setGraphName] = useState('Untitled Flow')
  const [saving, setSaving] = useState(false)
  /** Project for this flow (from graph, URL, or default); includes workspace Stylebook fields. */
  const [resolvedFlowProject, setResolvedFlowProject] = useState<Project | null>(null)
  const [flowProjectLoading, setFlowProjectLoading] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [existingGraphId, setExistingGraphId] = useState<string | null>(null)
  
  // Modal dialog state
  const [modalOpen, setModalOpen] = useState(false)
  const [modalConfig, setModalConfig] = useState<{
    title: string
    description: string
    type: 'info' | 'warning' | 'error' | 'success'
    confirmText?: string
    cancelText?: string
    onConfirm: () => void
    onCancel?: () => void
  } | null>(null)

  // Find the selected node
  const selectedNode = nodes.find(n => n.id === selectedNodeId)

  const graphContext = useMemo(() => {
    if (flowProjectLoading) {
      return {
        organizationId: null as number | null,
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
        workspaceDefaultStylebookId: null as number | null,
        workspaceStylebookName: null as string | null,
        missingWorkspaceStylebook: false,
        flowProjectLoading: false,
      }
    }
    const sid = p.workspace_stylebook_id ?? null
    const rawName = p.workspace_stylebook_name
    const nm =
      typeof rawName === 'string' && rawName.trim() !== '' ? rawName.trim() : null
    return {
      organizationId: p.organization_id ?? null,
      workspaceDefaultStylebookId: sid,
      workspaceStylebookName: nm,
      missingWorkspaceStylebook: sid == null && nm == null,
      flowProjectLoading: false,
    }
  }, [resolvedFlowProject, flowProjectLoading])

  // Node click handlers
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  // Handle text input changes for TextInput nodes
  const handleTextInputChange = useCallback((text: string) => {
    if (selectedNodeId) {
      setNodes((nds) =>
        nds.map((node) =>
          node.id === selectedNodeId
            ? { ...node, data: { ...node.data, text } }
            : node
        )
      )
    }
  }, [selectedNodeId, setNodes])

  /** New flow: infer project from `?project=` slug/id, else General (or first visible). */
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
          setSelectedProjectId('')
          return
        }
        const full = await getProject(pick.id)
        if (cancelled) return
        setResolvedFlowProject(full)
        setSelectedProjectId(String(full.id))
      } catch (error) {
        console.error('Failed to resolve flow project:', error)
        if (!cancelled) {
          setResolvedFlowProject(null)
          setSelectedProjectId('')
        }
      } finally {
        if (!cancelled) setFlowProjectLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [searchParams, routeGraphId])

  // Helper function to show modal
  const showModal = (config: typeof modalConfig) => {
    setModalConfig(config)
    setModalOpen(true)
  }

  useEffect(() => {
    if (!routeGraphId) return
    let cancelled = false
    void (async () => {
      setFlowProjectLoading(true)
      try {
        const g = await getGraph(routeGraphId)
        if (cancelled) return
        const proj = await getProject(g.project_id)
        if (cancelled) return
        setExistingGraphId(g.id)
        setGraphName(g.name)
        setSelectedProjectId(String(proj.id))
        setResolvedFlowProject(proj)
        setNodes(
          g.spec.nodes.map((n) => ({
            id: n.id,
            type: n.type,
            position: n.position ?? { x: 0, y: 0 },
            data: (n.params ?? {}) as Record<string, unknown>,
          }))
        )
        setEdges(
          (g.spec.edges ?? []).map((e) => ({
            id: `${e.source}-${e.target}-${e.sourceHandle ?? ''}-${e.targetHandle ?? ''}`,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle ?? undefined,
            targetHandle: e.targetHandle ?? undefined,
          }))
        )
        let maxIdx = 0
        for (const n of g.spec.nodes) {
          const m = /^node-(\d+)$/.exec(n.id)
          if (m) maxIdx = Math.max(maxIdx, parseInt(m[1], 10) + 1)
        }
        id = maxIdx
      } catch (e) {
        console.error('Failed to load graph', e)
        navigate('/')
      } finally {
        if (!cancelled) setFlowProjectLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [routeGraphId, navigate])

  // Define custom node types
  const nodeTypes: NodeTypes = useMemo(
    () => Object.entries(nodeComponents).reduce((acc, [type, Component]) => {
      acc[type] = Component
      return acc
    }, {} as NodeTypes),
    []
  )

  // Helper function to check if a node has upstream nodes of a specific type
  const hasUpstreamNodeOfType = useCallback((
    nodeId: string, 
    requiredType: string, 
    nodes: Node[], 
    edges: any[]
  ): boolean => {
    // Recursively check all upstream nodes
    const incomingEdges = edges.filter(e => e.target === nodeId)
    for (const edge of incomingEdges) {
      const sourceNode = nodes.find(n => n.id === edge.source)
      if (sourceNode?.type === requiredType) return true
      // Recursive check
      if (hasUpstreamNodeOfType(edge.source, requiredType, nodes, edges)) {
        return true
      }
    }
    return false
  }, [])

  // Validate upstream dependencies for node connections
  const validateUpstreamDependencies = useCallback((connection: Connection) => {
    const targetNode = nodes.find(n => n.id === connection.target)
    const sourceNode = nodes.find(n => n.id === connection.source)
    
    if (!targetNode || !sourceNode) return true
    
    const metadata = nodeMetadata.find(m => m.type === targetNode.type)
    if (!metadata?.requiredUpstreamNodes) return true
    
    // If requiredUpstreamNodes is empty, allow input nodes (TextInput, JSONInput, S3Input)
    const inputNodeTypes = ['TextInput', 'JSONInput', 'S3Input']
    if (metadata.requiredUpstreamNodes.length === 0) {
      if (inputNodeTypes.includes(sourceNode.type!)) {
        return true
      }
      // For nodes with no dependencies, still allow any connection
      return true
    }
    
    // Check if the source node type is one of the required upstream node types
    const isSourceNodeRequired = metadata.requiredUpstreamNodes.includes(sourceNode.type!)
    
    // Also allow input nodes for nodes with dependencies (they can accept input nodes as well)
    const isInputNode = inputNodeTypes.includes(sourceNode.type!)
    
    if (!isSourceNodeRequired && !isInputNode) {
      const targetLabel = metadata.label || targetNode.type
      const sourceLabel = nodeMetadata.find(m => m.type === sourceNode.type)?.label || sourceNode.type
      const requiredLabels = metadata.requiredUpstreamNodes
        .map(type => nodeMetadata.find(m => m.type === type)?.label || type)
        .join(' or ')
      
      let description = `${targetLabel} requires ${requiredLabels} node upstream, but you're connecting from ${sourceLabel}.`
      
      if (metadata.dependencyHelperText) {
        description += ` ${metadata.dependencyHelperText}`
      }
      
      showModal({
        title: 'Invalid Connection',
        description,
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }
    return true
  }, [nodes, showModal])

  const onConnect = useCallback(
    (params: Connection) => {
      if (!validateUpstreamDependencies(params)) return
      setEdges((eds) => addEdge(params, eds))
    },
    [setEdges, validateUpstreamDependencies]
  )
  
  const onNodesDelete = useCallback((deleted: Node[]) => {
    const deletedIds = deleted.map(n => n.id)
    // Remove edges connected to deleted nodes
    setEdges((eds) => eds.filter(
      (e) => !deletedIds.includes(e.source) && !deletedIds.includes(e.target)
    ))
  }, [setEdges])

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const getDefaultNodeData = useCallback((type: string) => {
    switch (type) {
      case 'TextInput':
        return {
          text: '',
        }
      case 'JSONInput':
        return {
          text: '',
        }
      case 'S3Input':
        return {
          bucket: '',
          folder_path: '',
        }
      case 'APIInput':
        return {
          enable_api_access: true,
          sample_json: '',
        }
      case 'Embed':
        return {
          model: 'text-embedding-3-small',
          dimensions: 1536,
        }
      case 'LLMEnrich':
        return {
          model: 'gpt-4o-mini',
          prompt: 'Analyze the following text: {text}',
          json_format: '{"sentiment": "positive|negative|neutral", "confidence": 0.95}',
          output_name: 'enriched_data',
        }
      case 'PeopleExtract': {
        const meta = nodeMetadata.find((m) => m.type === 'PeopleExtract')
        return meta?.defaultParams ?? { model: 'gpt-4o-mini' }
      }
      case 'PlaceExtract': {
        const meta = nodeMetadata.find((m) => m.type === 'PlaceExtract')
        return meta?.defaultParams ?? { model: 'gpt-4o-mini' }
      }
      case 'GeocodeAgent': {
        const meta = nodeMetadata.find((m) => m.type === 'GeocodeAgent')
        return meta?.defaultParams ?? {}
      }
      case 'AdvancedGeocodeAgent': {
        const meta = nodeMetadata.find((m) => m.type === 'AdvancedGeocodeAgent')
        return meta?.defaultParams ?? {}
      }
      case 'GeocodeSimple':
        return {
          user_agent: 'agate-ai-platform/1.0',
          rate_limit: 1.0,
        }
      case 'Gather':
        return {}
      case 'Output':
        return {}
      case 'S3Output':
        return {
          bucket: '',
          folder_path: '',
          filename_pattern: 'output_{timestamp}.json',
          public_read: false,
        }
      default:
        return {}
    }
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()

      const type = event.dataTransfer.getData('application/reactflow')
      if (!type || !reactFlowWrapper.current) {
        return
      }

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const newNode: Node = {
        id: getId(),
        type,
        position,
        data: getDefaultNodeData(type),
      }

      setNodes((nds) => nds.concat(newNode))
    },
    [reactFlowInstance, setNodes, getDefaultNodeData]
  )

  const validateFlow = () => {
    // Check for at least one Input node
    const hasInputNode = nodes.some(node => node.type === 'TextInput' || node.type === 'JSONInput' || node.type === 'S3Input' || node.type === 'APIInput' || node.type === 'DBInput')
    if (!hasInputNode) {
      showModal({
        title: 'Missing Input Node',
        description: 'Flow must have at least one Input node (TextInput, JSONInput, S3Input, APIInput, or DBInput) to be valid.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }

    // Check that flow doesn't have both S3Input and APIInput
    const hasS3Input = nodes.some(node => node.type === 'S3Input')
    const hasAPIInput = nodes.some(node => node.type === 'APIInput')
    if (hasS3Input && hasAPIInput) {
      showModal({
        title: 'Invalid Input Node Configuration',
        description: 'Flow cannot have both S3Input and APIInput nodes. Use only one input node type.',
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }

    // Check that APIInput is the first node (has no incoming edges)
    if (hasAPIInput) {
      const apiInputNodes = nodes.filter(node => node.type === 'APIInput')
      const nodesWithInput = new Set<string>()
      edges.forEach(edge => {
        nodesWithInput.add(edge.target)
      })
      
      const apiInputNotFirst = apiInputNodes.some(node => nodesWithInput.has(node.id))
      if (apiInputNotFirst) {
        showModal({
          title: 'API Input Node Position',
          description: 'APIInput node must be the first node in the flow (no incoming connections).',
          type: 'error',
          confirmText: 'OK',
          onConfirm: () => {},
        })
        return false
      }
    }

    // Check for at least one Output node
    const hasOutputNode = nodes.some(node => node.type === 'Output' || node.type === 'S3Output' || node.type === 'DBOutput')
    if (!hasOutputNode) {
      showModal({
        title: 'Missing Output Node',
        description: 'Flow must have at least one Output node to be valid.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }

    return true
  }

  const validateNoOrphans = () => {
    // Get all connected node IDs
    const connectedNodeIds = new Set<string>()
    edges.forEach(edge => {
      connectedNodeIds.add(edge.source)
      connectedNodeIds.add(edge.target)
    })
    
    // Find orphan nodes (nodes with no connections)
    const orphanNodes = nodes.filter(node => !connectedNodeIds.has(node.id))
    
    if (orphanNodes.length > 0) {
      const orphanNames = orphanNodes.map(n => `${n.type} (${n.id})`).join(', ')
      showModal({
        title: 'Orphan Nodes Detected',
        description: `The following nodes are not connected to the flow: ${orphanNames}. Please connect or delete them before saving.`,
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }
    
    return true
  }

  const validateInputConnections = () => {
    // Get all nodes that have incoming edges (receive input)
    const nodesWithInput = new Set<string>()
    edges.forEach(edge => {
      nodesWithInput.add(edge.target)
    })
    
    // Find non-Input nodes that don't receive input from another node
    const nodesWithoutInput = nodes.filter(node => {
      // Skip Input nodes (they don't need input from other nodes)
      if (node.type === 'TextInput' || node.type === 'JSONInput' || node.type === 'S3Input' || node.type === 'APIInput' || node.type === 'DBInput') {
        return false
      }
      // Check if this node receives input from another node
      return !nodesWithInput.has(node.id)
    })
    
    if (nodesWithoutInput.length > 0) {
      const nodeNames = nodesWithoutInput.map(n => `${n.type} (${n.id})`).join(', ')
      showModal({
        title: 'Nodes Without Input Detected',
        description: `The following nodes are not receiving input from another node: ${nodeNames}. All non-Input nodes must be connected to receive data from upstream nodes.`,
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return false
    }
    
    return true
  }

  const handleSave = async () => {
    // Validate flow before saving
    if (!validateFlow()) {
      return
    }

    // Validate no orphan nodes
    if (!validateNoOrphans()) {
      return
    }

    // Validate that non-Input nodes receive input
    if (!validateInputConnections()) {
      return
    }

    if (flowProjectLoading) {
      showModal({
        title: 'Still loading',
        description: 'Project details for this flow are still loading. Try again in a moment.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return
    }

    if (!selectedProjectId || !resolvedFlowProject) {
      showModal({
        title: 'No project for this flow',
        description:
          'Could not determine which project this flow belongs to. Open the flow from a project or try reloading the page.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return
    }

    try {
      setSaving(true)

      // Convert React Flow data to API format
      const graphSpec = {
        name: graphName,
        project_id: parseInt(selectedProjectId, 10),
        spec: {
          name: graphName.toLowerCase().replace(/\s+/g, '_'),
          nodes: nodes.map((node) => ({
            id: node.id,
            type: node.type!,
            params: node.data,
            position: { x: node.position.x, y: node.position.y },
          })),
          edges: edges.map((edge) => ({
            source: edge.source,
            target: edge.target,
            sourceHandle: edge.sourceHandle || null,
            targetHandle: edge.targetHandle || null,
          })),
        },
      }

      if (existingGraphId) {
        await updateGraph(existingGraphId, graphSpec)
        navigate(`/flow/${existingGraphId}`)
      } else {
        const graph = await createGraph(graphSpec)
        navigate(`/flow/${graph.id}`)
      }
    } catch (error) {
      console.error('Failed to save graph:', error)
      showModal({
        title: 'Save Failed',
        description: 'Failed to save flow. Please check the console for details and try again.',
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="h-screen flex flex-col">
      <div className="sticky top-0 z-10 border-b bg-background">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
            <div className="flex items-center gap-4">
              <div>
                <input
                  type="text"
                  value={graphName}
                  onChange={(e) => setGraphName(e.target.value)}
                  className="text-2xl font-bold bg-transparent border-none outline-none"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Drag nodes to build your flow
                </p>
              </div>
            </div>
          </div>
          <Button onClick={handleSave} disabled={saving || nodes.length === 0}>
            <Save className="mr-2 h-4 w-4" />
            {saving ? 'Saving...' : 'Save Flow'}
          </Button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <NodePalette />
        
        <div className="flex-1 relative" ref={reactFlowWrapper}>
          <Suspense fallback={<div className="flex items-center justify-center h-full">Loading...</div>}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodesDelete={onNodesDelete}
              onInit={setReactFlowInstance}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onNodeClick={onNodeClick}
              onPaneClick={onPaneClick}
              nodeTypes={nodeTypes}
              fitView
              maxZoom={1}
              fitViewOptions={{ padding: 0.3 }}
              deleteKeyCode={['Backspace', 'Delete']}
            >
              <Background variant={BackgroundVariant.Dots} />
              <Controls />
            </ReactFlow>
          </Suspense>

          {/* Node Panel */}
          {selectedNode && (
            <NodePanel
              selectedNode={selectedNode}
              onClose={() => setSelectedNodeId(null)}
              onTextChange={handleTextInputChange}
              onDelete={undefined} // No delete handler needed for new flows
              running={false}
              currentRun={undefined}
              editMode={true}
              setNodes={setNodes}
              showModal={showModal}
              graphContext={graphContext}
            />
          )}

          {nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <Card className="p-8 text-center pointer-events-auto">
                <p className="text-lg font-medium mb-3">Drag nodes from the palette</p>
                <div className="text-sm text-muted-foreground space-y-1 mb-4">
                  <p>• Drag nodes from the palette to the canvas</p>
                  <p>• Click on nodes to configure their settings</p>
                  <p>• Connect them together to build your flow</p>
                  <p>• Press Delete or Backspace to remove nodes</p>
                </div>
                <div className="flex items-start gap-2 p-3 bg-muted rounded-md">
                  <Info className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-muted-foreground">
                    Flows require at least one Input and one Output node
                  </p>
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* Modal Dialog */}
      {modalConfig && (
        <ConfirmDialog
          open={modalOpen}
          onOpenChange={setModalOpen}
          title={modalConfig.title}
          description={modalConfig.description}
          type={modalConfig.type}
          confirmText={modalConfig.confirmText}
          cancelText={modalConfig.cancelText}
          onConfirm={modalConfig.onConfirm}
          onCancel={modalConfig.onCancel}
        />
      )}
    </div>
  )
}

