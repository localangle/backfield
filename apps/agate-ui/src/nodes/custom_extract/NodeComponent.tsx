// Auto-injected metadata for CustomExtract
const nodeMetadata = {
  "type": "CustomExtract",
  "name": "CustomExtract",
  "label": "Custom Extract",
  "description": "Extract records you define — like ingredients, artists, or event details — with supporting passages from the text.",
  "category": "extraction",
  "icon": "Table",
  "color": "bg-amber-500",
  "requiredProjectModelCapabilities": [
    "generative"
  ],
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Requires upstream text, such as from Text Input or JSON Input.",
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
      "id": "custom_records",
      "label": "Custom records",
      "type": "object"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "record_type": "",
    "label": "",
    "fields": [],
    "instructions": "",
    "llmTimeout": 600
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface CustomExtractData {
  record_type?: string
  label?: string
  fields?: Array<{ label?: string; name?: string }>
}

function CustomExtractNode({ data, selected }: NodeProps<CustomExtractData>) {
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('CustomExtract', 'h-4 w-4')
  const bgColor = getNodeBgColor('CustomExtract')

  const recordSetLabel =
    data.label?.trim() || data.record_type?.trim() || 'Records not set up yet'
  const fieldCount = Array.isArray(data.fields) ? data.fields.length : 0
  const fieldSummary =
    fieldCount > 0 ? `${fieldCount} field${fieldCount === 1 ? '' : 's'}` : 'No fields yet'

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Custom Extract
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle type="target" position={Position.Left} id="text" className="w-3 h-3 bg-gray-700" />
        <div className="text-xs space-y-2 bg-muted rounded-md p-3 text-muted-foreground">
          {dependencyHelperText ? <p>{dependencyHelperText}</p> : null}
          <p className="truncate font-medium text-foreground" title={recordSetLabel}>
            {recordSetLabel}
          </p>
          <p>{fieldSummary}</p>
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="custom_records"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(CustomExtractNode)
