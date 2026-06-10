// Auto-injected metadata for EmbedImages
const nodeMetadata = {
  "type": "EmbedImages",
  "label": "Embed Images",
  "description": "Write a text description for each image from caption and article context, then embed those descriptions for search and analysis.",
  "category": "embedding",
  "icon": "Image",
  "color": "bg-orange-500",
  "requiredUpstreamNodes": [],
  "requiredProjectModelCapabilities": [
    "generative",
    "embedding"
  ],
  "dependencyHelperText": "Requires upstream images, such as from JSON Input with an images field.",
  "inputs": [
    {
      "id": "images",
      "label": "Images",
      "type": "object",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "image_embeddings",
      "label": "Image embeddings",
      "type": "array"
    }
  ],
  "defaultParams": {
    "prompt": "Write a clear, detailed description of the image using only the caption and article context provided. Do not invent visual details that are not supported by the context.",
    "descriptionModel": "",
    "descriptionAiModelConfigId": null,
    "embeddingModel": "",
    "embeddingAiModelConfigId": null
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface EmbedImagesData {
  descriptionModel?: string
  /** @deprecated Legacy vision model param */
  visionModel?: string
  embeddingModel?: string
}

function EmbedImagesNode({ data, selected }: NodeProps<EmbedImagesData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('EmbedImages', 'h-4 w-4')
  const bgColor = getNodeBgColor('EmbedImages')
  const descriptionLabel =
    data.descriptionModel?.trim() || data.visionModel?.trim() || 'Description model not set'
  const embeddingLabel = data.embeddingModel?.trim()
    ? data.embeddingModel.trim()
    : 'Embedding model not set'

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Embed Images
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="images"
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
          <p className="truncate" title={descriptionLabel}>
            {descriptionLabel}
          </p>
          <p className="truncate" title={embeddingLabel}>
            {embeddingLabel}
          </p>
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="image_embeddings"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(EmbedImagesNode)
