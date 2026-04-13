import { useState, useEffect, useCallback, useMemo, useRef, Suspense } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import ReactFlow, {
  Node,
  Edge as FlowEdge,
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
import { nodeComponents, nodeMetadata } from '@/nodes/registry'
import NodePanel from '@/components/NodePanel'
import NodePalette from '@/components/NodePalette'
import RunPanel from '@/components/RunPanel'
import ConfirmDialog from '@/components/ConfirmDialog'
import { getGraph, createRun, getRun, updateGraph, deleteGraph, type Graph, type Run } from '@/lib/api'
import { ArrowLeft, Save, Edit, Loader2, Play, Trash2 } from 'lucide-react'

export default function RunGraph() {
  const { graphId } = useParams<{ graphId: string }>()
  const navigate = useNavigate()
  const [graph, setGraph] = useState<Graph | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [currentRun, setCurrentRun] = useState<Run | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [saving, setSaving] = useState(false)
  
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [originalNodes, setOriginalNodes] = useState<Node[]>([])
  const [originalEdges, setOriginalEdges] = useState<FlowEdge[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleValue, setTitleValue] = useState('')
  const [showRunPanel, setShowRunPanel] = useState(false)
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const autoSaveTimeoutRef = useRef<number | null>(null)
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  
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
  
  // Node ID counter
  const nodeIdCounter = useRef(0)

  // Helper function to show modal
  const showModal = (config: typeof modalConfig) => {
    setModalConfig(config)
    setModalOpen(true)
  }

  // Handle cancel edit mode - reset to original state
  const handleCancelEdit = () => {
    setNodes(originalNodes)
    setEdges(originalEdges)
    setSelectedNodeId(null)
    setEditMode(false)
  }

  // Define custom node types
  const nodeTypes: NodeTypes = useMemo(
    () => Object.entries(nodeComponents).reduce((acc, [type, Component]) => {
      acc[type] = Component
      return acc
    }, {} as NodeTypes),
    []
  )

  useEffect(() => {
    if (graphId) {
      loadGraph(graphId)
    }
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current)
        pollTimeoutRef.current = null
      }
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current)
      }
    }
  }, [graphId])

  useEffect(() => {
    if (graph) {
      // Calculate node positions based on execution order
      const getNodePosition = (nodeId: string, nodes: any[], edges: any[]) => {
        // Find execution level using topological sort
        const nodeMap = new Map(nodes.map(n => [n.id, n]))
        const inDegree = new Map(nodes.map(n => [n.id, 0]))
        
        // Calculate in-degrees
        edges.forEach(edge => {
          if (inDegree.has(edge.target)) {
            inDegree.set(edge.target, inDegree.get(edge.target)! + 1)
          }
        })
        
        // Topological sort to find levels
        const levels = new Map<string, number>()
        const queue = nodes.filter(n => inDegree.get(n.id) === 0)
        let level = 0
        
        while (queue.length > 0) {
          const currentLevel = [...queue]
          queue.length = 0
          
          currentLevel.forEach(node => {
            levels.set(node.id, level)
            
            // Add children to next level
            edges.forEach(edge => {
              if (edge.source === node.id) {
                const targetInDegree = inDegree.get(edge.target)!
                inDegree.set(edge.target, targetInDegree - 1)
                if (targetInDegree === 1) {
                  queue.push(nodeMap.get(edge.target)!)
                }
              }
            })
          })
          
          level++
        }
        
        return levels.get(nodeId) || 0
      }

      // Convert graph spec to React Flow format
      const flowNodes: Node[] = graph.spec.nodes.map((node) => {
        const nodeData = { ...node.params }

        // Add onChange handler for TextInput nodes
        if (node.type === 'TextInput') {
          nodeData.onChange = (text: string) => {
            setNodes((nds) =>
              nds.map((n) =>
                n.id === node.id
                  ? { ...n, data: { ...n.data, text } }
                  : n
              )
            )
          }
        }
        
        // Use saved position if available, otherwise calculate based on execution order
        let position: { x: number; y: number }
        if (node.position && node.position.x !== undefined && node.position.y !== undefined) {
          position = { x: node.position.x, y: node.position.y }
        } else {
          const executionLevel = getNodePosition(node.id, graph.spec.nodes, graph.spec.edges || [])
          position = { x: executionLevel * 350, y: 100 }
        }
        
        return {
          id: node.id,
          type: node.type,
          position,
          data: nodeData,
        }
      })

      const flowEdges: FlowEdge[] = (graph.spec.edges || []).map((edge: any, index: number) => ({
        id: `edge-${index}`,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle || undefined,
        targetHandle: edge.targetHandle || undefined,
      }))

      setNodes(flowNodes)
      setEdges(flowEdges)
      
      // Store original nodes and edges for cancel functionality
      setOriginalNodes(flowNodes)
      setOriginalEdges(flowEdges)
      
      // Initialize node counter to avoid ID collisions
      // Find the highest existing node number and start from there
      const existingNodeNumbers = graph.spec.nodes
        .map(n => {
          const match = n.id.match(/^node-(\d+)$/)
          return match ? parseInt(match[1], 10) : -1
        })
        .filter(n => n >= 0)
      
      if (existingNodeNumbers.length > 0) {
        nodeIdCounter.current = Math.max(...existingNodeNumbers) + 1
      } else {
        nodeIdCounter.current = 0
      }
    }
  }, [graph, setNodes, setEdges])

  async function loadGraph(id: string) {
    try {
      setLoading(true)
      const data = await getGraph(id)
      setGraph(data)
      setTitleValue(data.name)
    } catch (error) {
      console.error('Failed to load graph:', error)
    } finally {
      setLoading(false)
    }
  }
  
  const handleTitleClick = () => {
    setEditingTitle(true)
  }
  
  const handleTitleSave = async () => {
    if (!graph || !titleValue.trim()) {
      setEditingTitle(false)
      setTitleValue(graph?.name || '')
      return
    }
    
    try {
      // Update the existing graph with new name
      const updatedSpec = {
        name: titleValue,
        project_id: graph.project_id,
        spec: {
          ...graph.spec,
          name: titleValue.toLowerCase().replace(/\s+/g, '_'),
        },
      }
      
      await updateGraph(graph.id, updatedSpec)
      // Reload the graph data to reflect the changes
      await loadGraph(graph.id)
      setEditingTitle(false)
    } catch (error) {
      console.error('Failed to update title:', error)
      setEditingTitle(false)
      setTitleValue(graph.name)
    }
  }
  
  const handleTitleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleTitleSave()
    } else if (e.key === 'Escape') {
      setEditingTitle(false)
      setTitleValue(graph?.name || '')
    }
  }

  const handleDeleteFlow = () => {
    setDeleteDialogOpen(true)
  }

  const confirmDeleteFlow = async () => {
    if (!graph) return
    
    try {
      await deleteGraph(graph.id)
      navigate('/')
    } catch (error) {
      console.error('Failed to delete flow:', error)
      showModal({
        title: 'Delete Failed',
        description: 'Failed to delete flow. Please check the console for details and try again.',
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
    } finally {
      setDeleteDialogOpen(false)
    }
  }

  // Helper function to check if a node has upstream nodes of a specific type
  const hasUpstreamNodeOfType = useCallback((
    nodeId: string, 
    requiredType: string, 
    nodes: Node[], 
    edges: FlowEdge[]
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
    
    // If requiredUpstreamNodes is empty, allow input nodes (TextInput, JSONInput, S3Input, APIInput, DBInput)
    const inputNodeTypes = ['TextInput', 'JSONInput', 'S3Input', 'APIInput', 'DBInput']
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
  
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id)
  }, [])
  
  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])
  
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()

      const type = event.dataTransfer.getData('application/reactflow')
      if (!type || !reactFlowWrapper.current || !reactFlowInstance) {
        return
      }

      const reactFlowBounds = reactFlowWrapper.current.getBoundingClientRect()
      const position = reactFlowInstance.project({
        x: event.clientX - reactFlowBounds.left,
        y: event.clientY - reactFlowBounds.top,
      })

      const newNode: Node = {
        id: `node-${nodeIdCounter.current++}`,
        type,
        position,
        data: getDefaultNodeData(type),
      }

      setNodes((nds) => nds.concat(newNode))
    },
    [reactFlowInstance, setNodes]
  )

  const getDefaultNodeData = (type: string) => {
    switch (type) {
      case 'TextInput':
        return {
          text: '',
          onChange: (text: string) => {
            setNodes((nds) =>
              nds.map((node) =>
                node.type === 'TextInput'
                  ? { ...node, data: { ...node.data, text } }
                  : node
              )
            )
          },
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
        }
      case 'PlaceExtract':
        return {
          model: 'gpt-4o-mini',
        }
      case 'GeocodeSimple':
        return {
          user_agent: 'agate-ai-platform/1.0',
          rate_limit: 1.0,
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
      case 'Output':
        return {}
      default:
        return {}
    }
  }
  
  const handleDeleteNode = useCallback((nodeId: string) => {
    // Remove the node
    setNodes((nds) => nds.filter((n) => n.id !== nodeId))
    // Remove any connected edges
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId))
    // Close the panel
    setSelectedNodeId(null)
  }, [setNodes, setEdges])
  
  const onNodesDelete = useCallback((deleted: Node[]) => {
    const deletedIds = deleted.map(n => n.id)
    // Remove edges connected to deleted nodes
    setEdges((eds) => eds.filter(
      (e) => !deletedIds.includes(e.source) && !deletedIds.includes(e.target)
    ))
    // Close panel if deleted node was selected
    if (selectedNodeId && deletedIds.includes(selectedNodeId)) {
      setSelectedNodeId(null)
    }
  }, [setEdges, selectedNodeId])
  
  const handleInputTextChange = useCallback((newText: string) => {
    // Update the TextInput node's data locally immediately
    setNodes((nds) =>
      nds.map((node) =>
        node.type === 'TextInput'
          ? { ...node, data: { ...node.data, text: newText } }
          : node
      )
    )

    // Clear any existing timeout
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current)
    }

    // Set a new timeout for auto-save (debounced)
    autoSaveTimeoutRef.current = setTimeout(async () => {
      if (graph && graphId) {
        try {
          const updatedNodes = nodes.map((node) =>
            node.type === 'TextInput'
              ? { ...node, data: { ...node.data, text: newText } }
              : node
          )

          const updatedSpec = {
            name: graph.spec.name,
            nodes: updatedNodes.map((node) => ({
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
          }

          await updateGraph(graphId, {
            name: graph.name,
            project_id: graph.project_id,
            spec: updatedSpec,
          })

          // Update the local graph state
          setGraph({
            ...graph,
            spec: updatedSpec,
          })
        } catch (error) {
          console.error('Failed to auto-save text input:', error)
          // Don't show an alert for auto-save failures to avoid interrupting the user
        }
      }
    }, 1000) // 1 second debounce
  }, [setNodes, graph, graphId, nodes])

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

  async function handleSaveGraph() {
    if (!graph) return

    // Close right panels when saving
    setSelectedNodeId(null)
    setShowRunPanel(false)

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

    try {
      setSaving(true)

      // Convert React Flow data back to API format
      const updatedSpec = {
        name: graph.name,
        project_id: graph.project_id,
        spec: {
          name: graph.spec.name,
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

      // Always update the existing graph (overwrite)
      await updateGraph(graph.id, updatedSpec)
      
      // Reload the graph data
      await loadGraph(graph.id)
      
      setEditMode(false)
    } catch (error) {
      console.error('Failed to save flow:', error)
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

  async function handleRunFlow() {
    if (!graphId) return

    // Check if flow has APIInput node
    const hasAPIInput = nodes.some(node => node.type === 'APIInput')
    if (hasAPIInput) {
      // Show warning but allow the run to proceed
      const apiInputNode = nodes.find(node => node.type === 'APIInput')
      const sampleJson = apiInputNode?.data?.sample_json || ''
      
      if (!sampleJson.trim()) {
        showModal({
          title: 'API Input Flow - Manual Testing',
          description: 'This flow uses an API Input node and is designed to be triggered via API calls. Manual testing may be limited since the node requires S3 bucket/path information. Consider using the API endpoint shown in the API Input node panel for full functionality.',
          type: 'warning',
          confirmText: 'Continue Anyway',
          onConfirm: () => {
            // Continue with the run after user confirms
            executeRun()
          },
        })
        return
      }
      
      // If sample JSON is provided, show info but still allow run
      showModal({
        title: 'API Input Flow - Manual Testing',
        description: 'This flow uses an API Input node and is designed to be triggered via API calls. Manual testing with sample JSON may be limited. The flow will attempt to run, but the API Input node requires S3 bucket/path information that may not be available in manual mode.',
        type: 'info',
        confirmText: 'Continue',
        onConfirm: () => {
          // Continue with the run after user confirms
          executeRun()
        },
      })
      return
    }

    // Execute the run (extracted to a function so it can be called from modal callbacks)
    executeRun()
  }

  async function executeRun() {
    if (!graphId) return

    try {
      setRunning(true)
      setShowRunPanel(true)
      // The input is now part of the graph itself (TextInput node params)
      // We pass an empty object since the worker will get input from the graph spec
      const run = await createRun(graphId, {
        input: {},
      })
      setCurrentRun(run)

      const pollRunStatus = async () => {
        try {
          const updatedRun = await getRun(run.id)
          setCurrentRun(updatedRun)
          return updatedRun
        } catch (error) {
          console.error('Failed to poll run status:', error)
          return null
        }
      }

      const checkDone = (updated: Run | null) =>
        updated?.status === 'completed' || updated?.status === 'completed_with_errors'

      // First poll after 1s to catch "running" quickly, then every 2s
      pollTimeoutRef.current = window.setTimeout(async () => {
        pollTimeoutRef.current = null
        const updated = await pollRunStatus()
        if (checkDone(updated)) {
          window.clearInterval(interval)
          setPollingInterval(null)
          setRunning(false)
        }
      }, 1000)

      const interval = window.setInterval(async () => {
        const updated = await pollRunStatus()
        if (checkDone(updated)) {
          window.clearInterval(interval)
          if (pollTimeoutRef.current) {
            window.clearTimeout(pollTimeoutRef.current)
            pollTimeoutRef.current = null
          }
          setPollingInterval(null)
          setRunning(false)
        }
      }, 2000)

      setPollingInterval(interval)
    } catch (error) {
      console.error('Failed to create run:', error)
      showModal({
        title: 'Run Failed',
        description: 'Failed to create run. Please check the console for details and try again.',
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      setRunning(false)
      setShowRunPanel(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!graph) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Flow not found</p>
        <Link to="/">
          <Button variant="link" className="mt-4">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Flows
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="sticky top-0 z-10 border-b bg-background">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
            <div>
              {editingTitle ? (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={titleValue}
                    onChange={(e) => setTitleValue(e.target.value)}
                    onBlur={handleTitleSave}
                    onKeyDown={handleTitleKeyDown}
                    autoFocus
                    className="text-2xl font-bold bg-transparent border-b-2 border-primary outline-none px-1"
                  />
                </div>
              ) : (
                <h1 
                  className="text-2xl font-bold cursor-pointer hover:text-primary transition-colors"
                  onClick={handleTitleClick}
                  title="Click to edit title"
                >
                  {graph.name}
                </h1>
              )}
              <p className="text-sm text-muted-foreground">
                {editMode ? 'Edit mode - Click nodes to modify, drag to rearrange' : 'Click any node to view details and run this flow'}
              </p>
            </div>
          </div>
          
          {editMode ? (
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleCancelEdit}>
                Cancel
              </Button>
              <Button onClick={handleSaveGraph} disabled={saving}>
                <Save className="mr-2 h-4 w-4" />
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
              <Button 
                variant="destructive" 
                onClick={handleDeleteFlow}
                className="text-white"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete Flow
              </Button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button 
                onClick={handleRunFlow} 
                disabled={running}
                className="bg-black text-white hover:bg-gray-800"
              >
                {running ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Run Flow
                  </>
                )}
              </Button>
              <Button variant="outline" onClick={() => setEditMode(true)}>
                <Edit className="mr-2 h-4 w-4" />
                Edit Flow
              </Button>
              <Button 
                variant="destructive" 
                onClick={handleDeleteFlow}
                className="text-white"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete Flow
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Full-screen Graph */}
      <div className="flex-1 flex overflow-hidden">
        {/* Node Palette (only in edit mode) */}
        {editMode && <NodePalette />}
        
        <div className="flex-1 relative" ref={reactFlowWrapper}>
          <Suspense fallback={<div className="flex items-center justify-center h-full">Loading...</div>}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={editMode ? onNodesChange : undefined}
              onEdgesChange={editMode ? onEdgesChange : undefined}
              onConnect={editMode ? onConnect : undefined}
              onNodesDelete={editMode ? onNodesDelete : undefined}
              onNodeClick={onNodeClick}
              onPaneClick={onPaneClick}
              onInit={setReactFlowInstance}
              onDrop={editMode ? onDrop : undefined}
              onDragOver={editMode ? onDragOver : undefined}
              nodeTypes={nodeTypes}
              fitView
              maxZoom={1}
              fitViewOptions={{ padding: 0.3 }}
              nodesDraggable={editMode}
              nodesConnectable={editMode}
              elementsSelectable={true}
              deleteKeyCode={editMode ? ['Backspace', 'Delete'] : null}
            >
              <Background variant={BackgroundVariant.Dots} />
              <Controls />
            </ReactFlow>
          </Suspense>

          {/* Side Panel */}
          {selectedNode && (
            <NodePanel
              selectedNode={selectedNode}
              onClose={() => setSelectedNodeId(null)}
              onTextChange={handleInputTextChange}
              onDelete={editMode ? handleDeleteNode : undefined}
              running={running}
              currentRun={currentRun}
              editMode={editMode}
              setNodes={setNodes}
              showModal={showModal}
            />
          )}

          {/* Run Panel */}
          {showRunPanel && (
            <RunPanel
              onClose={() => setShowRunPanel(false)}
              running={running}
              currentRun={currentRun}
            />
          )}

          {/* Empty State */}
          {nodes.length === 0 && !editMode && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <Card className="p-8 text-center pointer-events-auto">
                <p className="text-lg font-medium mb-2">This flow has no nodes</p>
                <p className="text-sm text-muted-foreground mb-4">
                  Click "Edit Flow" to add nodes and build your pipeline
                </p>
                <Button onClick={() => setEditMode(true)}>
                  <Edit className="mr-2 h-4 w-4" />
                  Edit Flow
                </Button>
              </Card>
            </div>
          )}
          
          {/* Edit Mode Empty State */}
          {nodes.length === 0 && editMode && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <Card className="p-8 text-center pointer-events-auto">
                <p className="text-lg font-medium mb-2">Drag nodes from the palette</p>
                <p className="text-sm text-muted-foreground">
                  Build your flow by connecting nodes together
                </p>
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

      {/* Delete Flow Confirmation Dialog */}
      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Delete Flow"
        description={`Are you sure you want to delete "${graph?.name}"? This action cannot be undone and will also delete all associated runs.`}
        type="warning"
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={confirmDeleteFlow}
        onCancel={() => setDeleteDialogOpen(false)}
      />
    </div>
  )
}

