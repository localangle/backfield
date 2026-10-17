// Auto-injected metadata for ProcessingGuard
const nodeMetadata = {
  "type": "ProcessingGuard",
  "name": "ProcessingGuard",
  "label": "Processing Guard",
  "description": "Pause a story before later steps when it is outside the length or name limits you set.",
  "category": "filter",
  "icon": "Shield",
  "color": "bg-orange-500",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Place this directly after Text Input, JSON Input, or S3 Input. When a limit is exceeded, later steps do not run and the story is marked Needs attention.",
  "inputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    },
    {
      "id": "processing_guard",
      "label": "Guard findings",
      "type": "object"
    }
  ],
  "defaultParams": {
    "criteria": []
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

function ProcessingGuardNode({ data, selected }: NodeProps) {
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('ProcessingGuard', 'h-4 w-4')
  const bgColor = getNodeBgColor('ProcessingGuard')
  const criteria = Array.isArray(data?.criteria) ? data.criteria : []
  const ruleLabel = criteria.length === 1 ? '1 limit' : `${criteria.length} limits`

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Processing Guard
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle type="target" position={Position.Left} id="text" className="w-3 h-3 bg-gray-700" />
        <p className="text-xs text-muted-foreground">
          {criteria.length === 0 ? 'No limits set. Stories continue as usual.' : `Checks ${ruleLabel} before later steps.`}
        </p>
        {dependencyHelperText ? (
          <p className="text-xs text-muted-foreground">{dependencyHelperText}</p>
        ) : null}
        <Handle type="source" position={Position.Right} id="text" className="w-3 h-3 bg-gray-700" />
      </CardContent>
    </Card>
  )
}

export default memo(ProcessingGuardNode)
