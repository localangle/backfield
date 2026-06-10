// Auto-injected metadata for Gather
const nodeMetadata = {
  "type": "Gather",
  "label": "Gather",
  "icon": "Package",
  "description": "Wait for parallel branches to finish, then pass their outputs downstream as one collection.",
  "category": "control",
  "color": "bg-cyan-500",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Waits for other nodes in the flow to finish, then combines their outputs for the next step.",
  "inputs": [],
  "outputs": [],
  "defaultParams": {}
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

function GatherNode({ selected }: NodeProps) {
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('Gather', 'h-4 w-4')
  const bgColor = getNodeBgColor('Gather')

  return (
    <Card className={`w-[220px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Gather
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle type="target" position={Position.Left} className="w-3 h-3 bg-gray-700" />
        {dependencyHelperText ? (
          <p className="text-xs text-muted-foreground">{dependencyHelperText}</p>
        ) : null}
        <Handle type="source" position={Position.Right} className="w-3 h-3 bg-gray-700" />
      </CardContent>
    </Card>
  )
}

export default memo(GatherNode)
