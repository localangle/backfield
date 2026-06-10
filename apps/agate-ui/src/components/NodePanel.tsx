import { X, Trash2, AlertTriangle } from 'lucide-react'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Button } from '@/components/ui/button'
import type { Run } from '@/lib/api'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import { Suspense, useEffect, useMemo, useState, type ReactNode } from 'react'
import { nodeMetadata, panelComponents } from '@/nodes/registry'
import { NodePanelTabProvider } from '@/components/node-panel/NodePanelTabContext'
import { getNodePanelTabs, NODE_PANEL_TAB_LABELS, type NodePanelTabId } from '@/lib/nodePanelTabs'
import { getNodeBgColor, getNodeIcon, getNodeLabel } from '@/lib/nodeUtils'
import { cn } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

export type ProjectAiModelOption = {
  label: string
  providerModelId: string
  configId?: string
}

export type GraphPanelContext = {
  /** Organization that owns the resolved flow project (for Stylebook catalog in node panels). */
  organizationId: number | null
  /** Resolved Backfield project id for AI catalog lookups (when known). */
  projectId: number | null
  workspaceDefaultStylebookId: number | null
  workspaceStylebookName: string | null
  /** True when a project is selected but the API did not resolve a workspace Stylebook. */
  missingWorkspaceStylebook?: boolean
  /** Flow editor is still fetching the project (for workspace Stylebook). */
  flowProjectLoading?: boolean
  /** Loads project-effective AI models filtered by capability (e.g. text+json for JSON-using nodes). */
  fetchProjectAiModels?: (capabilities: string[]) => Promise<ProjectAiModelOption[]>
}

interface NodePanelProps {
  selectedNode: any
  onClose: () => void
  onTextChange?: (text: string) => void
  onRun?: () => void
  onDelete?: (nodeId: string) => void
  running?: boolean
  currentRun?: Run | null
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext | null
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
  allowClose?: boolean
  footer?: ReactNode
  invalidConnectionMessage?: string | null
  /** When true, onDelete runs immediately (caller handles confirmation). */
  skipDeleteConfirmation?: boolean
  showModal?: (config: {
    title: string
    description: string
    type: 'info' | 'warning' | 'error' | 'success'
    confirmText?: string
    cancelText?: string
    onConfirm: () => void
    onCancel?: () => void
  }) => void
}

export default function NodePanel({
  selectedNode,
  onClose,
  onTextChange,
  onDelete,
  currentRun,
  editMode,
  setNodes,
  showModal,
  graphContext,
  nodeOutputLookupSpec,
  allowClose = true,
  footer,
  invalidConnectionMessage = null,
  skipDeleteConfirmation = false,
}: NodePanelProps) {
  const { showConfirm } = useAppMessage()
  if (!selectedNode) return null

  const nodeMeta = nodeMetadata.find((m) => m.type === selectedNode.type)
  const nodePanelTitle = nodeMeta?.label ?? getNodeLabel(String(selectedNode.type))
  const nodeType = String(selectedNode.type ?? '')

  const rawNodeOutputs = currentRun?.node_outputs as Record<string, unknown> | undefined
  const selectedNodeOutput = rawNodeOutputs
    ? getNodeOutputById(rawNodeOutputs, selectedNode.id, nodeOutputLookupSpec ?? undefined)
    : undefined

  const hasRunOutput = selectedNodeOutput !== undefined && selectedNodeOutput !== null
  const panelTabs = useMemo(
    () => getNodePanelTabs(nodeType, { hasRunOutput }),
    [hasRunOutput, nodeType],
  )
  const [activeTab, setActiveTab] = useState<NodePanelTabId>(panelTabs[0] ?? 'settings')

  useEffect(() => {
    if (panelTabs.length === 0) return
    setActiveTab(panelTabs[0]!)
  }, [panelTabs, selectedNode.id])

  const handleDelete = () => {
    if (skipDeleteConfirmation) {
      onDelete?.(selectedNode.id)
      return
    }
    if (showModal) {
      showModal({
        title: 'Delete Node',
        description: `Are you sure you want to delete the ${selectedNode.type} node? This action cannot be undone.`,
        type: 'warning',
        confirmText: 'Delete',
        cancelText: 'Cancel',
        onConfirm: () => onDelete?.(selectedNode.id),
      })
    } else {
      void (async () => {
        const ok = await showConfirm(
          `Are you sure you want to delete the ${selectedNode.type} node? This action cannot be undone.`,
          {
            title: 'Delete node',
            confirmLabel: 'Delete',
            destructive: true,
          },
        )
        if (ok) onDelete?.(selectedNode.id)
      })()
    }
  }

  return (
    <div className="absolute top-0 right-0 z-20 flex h-full w-96 flex-col border-l bg-background/95 shadow-lg backdrop-blur-sm slide-in-from-right">
      <div className="flex items-center justify-between gap-3 p-4 border-b">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
              getNodeBgColor(nodeType),
            )}
          >
            {getNodeIcon(nodeType, 'h-4 w-4')}
          </div>
          <h3 className="truncate font-semibold text-lg">{nodePanelTitle}</h3>
        </div>
        <div className="flex gap-1">
          {editMode && onDelete && (
            <Button variant="ghost" size="icon" onClick={handleDelete} title="Delete node">
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          )}
          {allowClose && (
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {invalidConnectionMessage ? (
          <div className="flex gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
            <div>
              <p className="font-medium">Invalid connection</p>
              <p className="mt-0.5 text-amber-800">{invalidConnectionMessage}</p>
            </div>
          </div>
        ) : null}

        {nodeMeta?.description ? (
          <p className="text-sm text-muted-foreground leading-relaxed">{nodeMeta.description}</p>
        ) : null}
        {nodeType !== 'GeocodeAgent' &&
        !panelTabs.includes('info') &&
        'dependencyHelperText' in (nodeMeta ?? {}) &&
        typeof (nodeMeta as { dependencyHelperText?: string }).dependencyHelperText === 'string' ? (
          <p className="text-sm text-muted-foreground border-l-2 border-muted pl-3 leading-relaxed">
            {(nodeMeta as { dependencyHelperText: string }).dependencyHelperText}
          </p>
        ) : null}

        {panelTabs.length > 1 ? (
          <Tabs
            value={activeTab}
            onValueChange={(value) => setActiveTab(value as NodePanelTabId)}
            className="space-y-4"
          >
            <TabsList
              className="grid h-auto w-full gap-1 p-1"
              style={{ gridTemplateColumns: `repeat(${panelTabs.length}, minmax(0, 1fr))` }}
            >
              {panelTabs.map((tab) => (
                <TabsTrigger key={tab} value={tab} className="text-xs sm:text-sm">
                  {NODE_PANEL_TAB_LABELS[tab]}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        ) : null}

        <NodePanelTabProvider activeTab={panelTabs.length > 0 ? activeTab : 'settings'}>
          <Suspense fallback={<div>Loading...</div>}>
            {(() => {
              const PanelComponent =
                panelComponents[selectedNode.type as keyof typeof panelComponents]
              if (PanelComponent) {
                return (
                  <PanelComponent
                    node={selectedNode}
                    onChange={onTextChange}
                    currentRun={currentRun}
                    editMode={editMode}
                    setNodes={setNodes}
                    graphContext={graphContext ?? undefined}
                    nodeOutputLookupSpec={nodeOutputLookupSpec}
                  />
                )
              }
              return <div>Unknown node type: {selectedNode.type}</div>
            })()}
          </Suspense>
        </NodePanelTabProvider>
      </div>
      {footer}
    </div>
  )
}
