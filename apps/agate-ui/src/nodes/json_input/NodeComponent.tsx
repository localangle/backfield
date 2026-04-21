// Auto-injected metadata for JSONInput
const nodeMetadata = {
  "type": "JSONInput",
  "label": "JSON Input",
  "icon": "Braces",
  "color": "bg-blue-500",
  "description": "Provide structured JSON data with required text field",
  "category": "input",
  "inputs": [],
  "outputs": [
    {
      "id": "text",
      "label": "Text + Data",
      "type": "object"
    }
  ],
  "defaultParams": {
    "text": ""
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface JSONInputData {
  text?: string
  [key: string]: unknown
}

function JSONInputNode({ data, selected }: NodeProps<JSONInputData>) {
  const text = typeof data.text === 'string' ? data.text : ''
  const textPreview = text ? text.substring(0, 50) : 'No text provided'
  const additionalFields = Object.keys(data).filter(
    (k) => k !== 'text' && k !== 'onChange',
  ).length
  const icon = getNodeIcon('JSONInput', 'h-4 w-4')
  const bgColor = getNodeBgColor('JSONInput')

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          JSON Input
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="text-xs text-gray-600">
          {additionalFields > 0
            ? `+ ${additionalFields} field${additionalFields > 1 ? 's' : ''}`
            : 'Text only'}
        </div>
        {textPreview && (
          <div className="text-xs text-gray-600 italic">
            {textPreview}
            {text.length > 50 ? '...' : ''}
          </div>
        )}
        <Handle
          type="source"
          position={Position.Right}
          id="text"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(JSONInputNode)
