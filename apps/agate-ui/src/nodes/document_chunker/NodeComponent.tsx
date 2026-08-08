// Auto-injected metadata for DocumentChunker
const nodeMetadata = {
  "type": "DocumentChunker",
  "name": "DocumentChunker",
  "label": "Document Chunker",
  "description": "Optionally split a long document into overlapping pieces so extraction can handle larger content while keeping one story for review.",
  "category": "other",
  "icon": "Split",
  "color": "bg-cyan-500",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Place this directly after Text Input, JSON Input, or S3 Input. Extraction nodes after it process each piece and combine the results.",
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
      "id": "chunking_summary",
      "label": "Chunking summary",
      "type": "object"
    }
  ],
  "defaultParams": {
    "target_tokens": 4000,
    "overlap_tokens": 250
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

function DocumentChunkerNode({ data, selected }: NodeProps) {
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('DocumentChunker', 'h-4 w-4')
  const bgColor = getNodeBgColor('DocumentChunker')
  const targetTokens =
    typeof data?.target_tokens === 'number'
      ? data.target_tokens
      : typeof data?.target_tokens === 'string' && data.target_tokens.trim()
        ? data.target_tokens
        : 4000

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Document Chunker
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="text"
          className="w-3 h-3 bg-gray-700"
        />
        <p className="text-xs text-muted-foreground">
          Splits long documents into pieces of about {targetTokens} tokens.
        </p>
        {dependencyHelperText ? (
          <p className="text-xs text-muted-foreground">{dependencyHelperText}</p>
        ) : null}
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

export default memo(DocumentChunkerNode)
