import NodePanel, { type GraphPanelContext } from '@/components/NodePanel'
import { Button } from '@/components/ui/button'
import {
  bookendContinueHint,
  canContinueBookendNode,
  canContinueMiddleNode,
  type BookendNodeLike,
} from '@/lib/flowBuilderSteps'
import type { Run } from '@/lib/api'
import type { NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import type { Node } from 'reactflow'

type ConfigureGatePanelProps = {
  selectedNode: Node
  gateActive: boolean
  onContinue: () => void
  /** Clears the current bookend selection and returns to the chooser on input/output steps. */
  onCancel?: () => void
  onClose: () => void
  onSave?: () => void
  onTextChange?: (text: string) => void
  setNodes: (nodes: Node[] | ((nodes: Node[]) => Node[])) => void
  graphContext?: GraphPanelContext | null
  isMiddleNode?: boolean
  viewOnly?: boolean
  onDelete?: (nodeId: string) => void
  running?: boolean
  saving?: boolean
  canSave?: boolean
  currentRun?: Run | null
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
  invalidConnectionMessage?: string | null
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

export default function ConfigureGatePanel({
  selectedNode,
  gateActive,
  onContinue,
  onCancel,
  onClose,
  onSave,
  onTextChange,
  setNodes,
  graphContext,
  isMiddleNode = false,
  viewOnly = false,
  onDelete,
  running,
  saving = false,
  canSave = true,
  currentRun,
  nodeOutputLookupSpec,
  invalidConnectionMessage,
  showModal,
}: ConfigureGatePanelProps) {
  const nodeLike: BookendNodeLike = {
    type: selectedNode.type,
    data: selectedNode.data as Record<string, unknown>,
  }
  const canContinue = isMiddleNode
    ? canContinueMiddleNode(nodeLike)
    : canContinueBookendNode(nodeLike)
  const hint = isMiddleNode || viewOnly ? null : bookendContinueHint(nodeLike)

  const saveButton =
    !viewOnly && !gateActive && onSave ? (
      <Button
        type="button"
        className="w-full"
        disabled={saving || !canSave}
        onClick={onSave}
      >
        {saving ? 'Saving...' : 'Save changes'}
      </Button>
    ) : null

  const footer =
    !viewOnly && (gateActive || saveButton) ? (
    <div className="border-t bg-background p-4">
      {gateActive ? (
        <>
          {hint && <p className="mb-3 text-sm text-destructive">{hint}</p>}
          <div className={onCancel && !isMiddleNode ? 'flex gap-2' : 'space-y-2'}>
            <Button
              className={onCancel && !isMiddleNode ? 'flex-1' : 'w-full'}
              disabled={!canContinue}
              onClick={onContinue}
            >
              {isMiddleNode ? 'Add node' : 'Continue'}
            </Button>
            {onCancel ? (
              <Button
                type="button"
                variant="outline"
                className={isMiddleNode ? 'w-full' : 'flex-1'}
                onClick={onCancel}
              >
                Cancel
              </Button>
            ) : null}
          </div>
        </>
      ) : (
        saveButton
      )}
    </div>
  ) : undefined

  return (
    <NodePanel
      selectedNode={selectedNode}
      onClose={onClose}
      onTextChange={onTextChange}
      editMode={!viewOnly}
      setNodes={setNodes}
      graphContext={graphContext}
      showModal={showModal}
      running={running}
      currentRun={currentRun}
      nodeOutputLookupSpec={nodeOutputLookupSpec}
      invalidConnectionMessage={invalidConnectionMessage}
      onDelete={!viewOnly && isMiddleNode ? onDelete : undefined}
      skipDeleteConfirmation={isMiddleNode}
      allowClose={viewOnly || !gateActive}
      footer={footer}
    />
  )
}
