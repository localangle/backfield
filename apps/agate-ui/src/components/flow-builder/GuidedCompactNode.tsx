import { Handle, Position, type NodeProps } from 'reactflow'

import { useGuidedFlowCanvasUi } from '@/components/flow-builder/guidedFlowCanvasUi'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { getNodeBgColor, getNodeIcon, getNodeLabel } from '@/lib/nodeUtils'
import { nodeMetadata } from '@/nodes/registry'

/** Canvas layout width for guided compact nodes (keep in sync with flowGraphModel). */
export const GUIDED_COMPACT_NODE_WIDTH = 200
/** Fixed height so serial edges connect at vertical center. */
export const GUIDED_COMPACT_NODE_HEIGHT = 64

type PortDef = { id: string }

type GuidedCompactNodeProps = NodeProps & {
  exitAnimation?: boolean
}

export default function GuidedCompactNode({
  id,
  type,
  data,
  selected,
  exitAnimation = false,
}: GuidedCompactNodeProps) {
  const { selectedNodeId, enteringNodeIds } = useGuidedFlowCanvasUi()
  const isSelected = selected || id === selectedNodeId
  const enterAnimation = enteringNodeIds.has(id)
  const nodeType = String(type ?? '')
  const meta = nodeMetadata.find((entry) => entry.type === nodeType)
  const inputs = (meta?.inputs ?? []) as PortDef[]
  const outputs = (meta?.outputs ?? []) as PortDef[]
  const primaryTarget = inputs[0]
  const isOutputBookend = Boolean(
    (data as { guidedIsOutputBookend?: boolean } | undefined)?.guidedIsOutputBookend,
  )
  const primarySource = isOutputBookend
    ? null
    : (outputs.find((output) => output.id === 'locations') ??
      outputs.find((output) => output.id === 'text') ??
      outputs[outputs.length - 1])
  const label = getNodeLabel(nodeType)
  const icon = getNodeIcon(nodeType, 'h-4 w-4')
  const bgColor = getNodeBgColor(nodeType)

  return (
    <div
      className="relative"
      style={{ width: GUIDED_COMPACT_NODE_WIDTH, height: GUIDED_COMPACT_NODE_HEIGHT }}
    >
      {primaryTarget ? (
        <Handle
          type="target"
          position={Position.Left}
          id={primaryTarget.id}
          className="!h-2 !w-2 !border-none !bg-muted-foreground"
        />
      ) : null}
      {primarySource ? (
        <Handle
          type="source"
          position={Position.Right}
          id={primarySource.id}
          className="!h-2 !w-2 !border-none !bg-muted-foreground"
        />
      ) : null}
      <Card
        className={cn(
          'flex h-full w-full items-center',
          isSelected && 'ring-2 ring-primary',
          exitAnimation && 'guided-node-exit',
          enterAnimation && !exitAnimation && 'guided-node-enter',
        )}
      >
        <CardHeader className="flex w-full flex-row items-center gap-2 space-y-0 p-3">
          <div
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
              bgColor,
            )}
          >
            {icon}
          </div>
          <CardTitle className="truncate text-sm font-medium leading-none">{label}</CardTitle>
        </CardHeader>
      </Card>
    </div>
  )
}
