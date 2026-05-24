import NodePanel, { type GraphPanelContext } from '@/components/NodePanel'
import { Button } from '@/components/ui/button'
import {
  bookendContinueHint,
  canContinueBookendNode,
  canContinueMiddleNode,
  type BookendNodeLike,
} from '@/lib/flowBuilderSteps'
import type { Node } from 'reactflow'

type ConfigureGatePanelProps = {
  selectedNode: Node
  gateActive: boolean
  onContinue: () => void
  onClose: () => void
  onTextChange?: (text: string) => void
  setNodes: (nodes: Node[] | ((nodes: Node[]) => Node[])) => void
  graphContext?: GraphPanelContext | null
  isMiddleNode?: boolean
  onDelete?: (nodeId: string) => void
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
  onClose,
  onTextChange,
  setNodes,
  graphContext,
  isMiddleNode = false,
  onDelete,
  showModal,
}: ConfigureGatePanelProps) {
  const nodeLike: BookendNodeLike = {
    type: selectedNode.type,
    data: selectedNode.data as Record<string, unknown>,
  }
  const canContinue = isMiddleNode
    ? canContinueMiddleNode(nodeLike)
    : canContinueBookendNode(nodeLike)
  const hint = isMiddleNode ? null : bookendContinueHint(nodeLike)

  const footer = gateActive ? (
    <div className="border-t bg-background p-4">
      {hint && <p className="mb-3 text-sm text-destructive">{hint}</p>}
      <Button className="w-full" disabled={!canContinue} onClick={onContinue}>
        Continue
      </Button>
    </div>
  ) : undefined

  return (
    <NodePanel
      selectedNode={selectedNode}
      onClose={onClose}
      onTextChange={onTextChange}
      editMode
      setNodes={setNodes}
      graphContext={graphContext}
      showModal={showModal}
      onDelete={isMiddleNode ? onDelete : undefined}
      skipDeleteConfirmation={isMiddleNode}
      allowClose={!gateActive}
      footer={footer}
    />
  )
}
