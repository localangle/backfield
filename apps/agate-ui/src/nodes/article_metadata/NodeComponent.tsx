// Auto-injected metadata for ArticleMetadata
const nodeMetadata = {
  "type": "ArticleMetadata",
  "name": "ArticleMetadata",
  "label": "Article Metadata",
  "description": "Classify the article with an LLM using a category, rationale, and confidence score.",
  "category": "enrichment",
  "icon": "Tag",
  "color": "bg-green-500",
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
      "id": "article_metadata",
      "label": "Article metadata",
      "type": "object"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "prompt_preset": "topic",
    "prompt": "Classify the article topic using the story text below.\n\n## Categories\n- Local news\n- Politics\n- Business\n- Sports\n- Culture\n- Other\n\n{text}\n",
    "prompt_file": "prompts/presets/topic.md",
    "output_format_file": "prompts/_output_format.json",
    "llmTimeout": 600,
    "preset_prompts": {
      "geographic_scope": "Classify the geographic scope of the article using the story text below.\n\n## Categories\n- Neighborhood\n- City\n- Regional\n- National\n- International\n- Other\n\n{text}\n",
      "information_needs": "Classify the primary information need this article serves using the story text below.\n\n## Categories\n- Explain an event\n- Provide practical guidance\n- Offer analysis\n- Hold power to account\n- Human interest\n- Other\n\n{text}\n",
      "jobs_to_be_done": "Classify the jobs-to-be-done this article fulfills for readers using the story text below.\n\n## Categories\n- Stay informed\n- Make a decision\n- Be entertained\n- Learn how-to\n- Compare options\n- Other\n\n{text}\n",
      "temporal_orientation": "Classify the temporal orientation of the article using the story text below.\n\n## Categories\n- Breaking news\n- Developing story\n- Historical recap\n- Evergreen\n- Other\n\n{text}\n",
      "topic": "Classify the article topic using the story text below.\n\n## Categories\n- Local news\n- Politics\n- Business\n- Sports\n- Culture\n- Other\n\n{text}\n"
    },
    "output_format": "{\n  \"category\": \"Local news\",\n  \"rationale\": \"The story focuses on a city council decision affecting residents.\",\n  \"confidence\": 0.86\n}\n"
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeLabel, getNodeBgColor } from '@/lib/nodeUtils'

interface ArticleMetadataData {
  model?: string
  prompt_preset?: string
}

function ArticleMetadataNode({ data, selected }: NodeProps<ArticleMetadataData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('ArticleMetadata', 'h-4 w-4')
  const bgColor = getNodeBgColor('ArticleMetadata')
  const presetLabel =
    typeof data.prompt_preset === 'string' && data.prompt_preset.trim()
      ? data.prompt_preset.replace(/_/g, ' ')
      : 'topic'

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
