import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeLabel, getNodeBgColor } from '@/lib/nodeUtils'

import { ARTICLE_METADATA_DEFAULT_PRESET } from './presetOptions'

interface ArticleMetadataData {
  model?: string
  prompt_preset?: string
  meta_type?: string
}

function ArticleMetadataNode({ data, selected }: NodeProps<ArticleMetadataData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('ArticleMetadata', 'h-4 w-4')
  const bgColor = getNodeBgColor('ArticleMetadata')
  const presetId =
    typeof data.prompt_preset === 'string' && data.prompt_preset.trim()
      ? data.prompt_preset.trim().toLowerCase().replace(/-/g, '_')
      : ARTICLE_METADATA_DEFAULT_PRESET
  const presetLabel =
    presetId === 'custom' && typeof data.meta_type === 'string' && data.meta_type.trim()
      ? data.meta_type.trim().replace(/_/g, ' ')
      : presetId.replace(/_/g, ' ')

  return (
    <Card className={`w-[220px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          {getNodeLabel('ArticleMetadata')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="text"
          className="w-3 h-3 bg-gray-700"
        />
        <div className="text-xs space-y-2">
          {requiredUpstreamNodes.length > 0 && (
            <div className="space-y-1">
              <Label className="text-muted-foreground">Depends on:</Label>
              <div className="flex flex-wrap gap-2">
                {requiredUpstreamNodes.map((nodeType: string) => {
                  const depIcon = getNodeIcon(nodeType, 'h-3 w-3')
                  const label = getNodeLabel(nodeType)
                  return (
                    <div key={nodeType} className="flex items-center gap-1">
                      {depIcon}
                      <span className="text-xs">{label}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          {dependencyHelperText ? (
            <p className="text-xs text-muted-foreground mt-1">{dependencyHelperText}</p>
          ) : null}
          <p className="text-xs text-muted-foreground capitalize">{presetLabel}</p>
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="article_metadata"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(ArticleMetadataNode)
