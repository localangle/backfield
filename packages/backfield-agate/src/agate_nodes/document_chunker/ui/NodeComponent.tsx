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
