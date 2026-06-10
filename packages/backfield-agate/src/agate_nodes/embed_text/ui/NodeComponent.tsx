import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface EmbedTextData {
  model?: string
}

function EmbedTextNode({ data, selected }: NodeProps<EmbedTextData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('EmbedText', 'h-4 w-4')
  const bgColor = getNodeBgColor('EmbedText')
  const modelLabel = data.model?.trim() ? data.model.trim() : 'Embedding model not set'

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Embed Text
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="text"
          className="w-3 h-3 bg-gray-700"
        />
        <div className="text-xs space-y-2 bg-muted rounded-md p-3 text-muted-foreground">
          {requiredUpstreamNodes.length > 0 && (
            <div className="space-y-1">
              <Label className="text-muted-foreground">Depends on:</Label>
              <div className="flex flex-wrap gap-2">
                {requiredUpstreamNodes.map((nodeType: string) => {
                  const depIcon = getNodeIcon(nodeType, 'h-3 w-3')
                  return (
                    <div key={nodeType} className="flex items-center gap-1">
                      {depIcon}
                      <span className="text-xs">{nodeType}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          {dependencyHelperText ? <p>{dependencyHelperText}</p> : null}
          <p className="truncate" title={modelLabel}>
            {modelLabel}
          </p>
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="article_embedding"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(EmbedTextNode)
