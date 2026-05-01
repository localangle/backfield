// Auto-injected metadata for AdvancedGeocodeAgent
const nodeMetadata = {
  "type": "AdvancedGeocodeAgent",
  "label": "Advanced Geocode Agent",
  "icon": "MapPin",
  "color": "bg-teal-600",
  "description": "LangGraph geocoding with per-node OpenAI models: area evaluation plus post-cache route_strategy (after Stylebook/cache lookup).",
  "category": "enrichment",
  "requiredUpstreamNodes": [
    "PlaceExtract"
  ],
  "dependencyHelperText": "Requires extracted places as input.",
  "inputs": [
    {
      "id": "locations",
      "label": "Locations",
      "type": "array",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "places",
      "label": "Places",
      "type": "object"
    },
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    }
  ],
  "defaultParams": {
    "maxLocations": 100,
    "perLocationTimeout": 300,
    "useCache": false,
    "stylebookId": null,
    "stylebookApiUrl": "",
    "projectSlug": "",
    "evaluationModel": "gpt-5-nano",
    "routerModel": "gpt-5-nano"
  },
  "availableModels": [
    {
      "value": "gpt-5.4",
      "label": "GPT 5.4"
    },
    {
      "value": "gpt-5.2",
      "label": "GPT 5.2"
    },
    {
      "value": "gpt-5-mini",
      "label": "GPT-5 Mini"
    },
    {
      "value": "gpt-5-nano",
      "label": "GPT-5 Nano"
    },
    {
      "value": "gpt-4o-mini",
      "label": "GPT-4o Mini"
    }
  ]
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeLabel, getNodeBgColor } from '@/lib/nodeUtils'

interface GeocodeAgentData {
  locations?: any[]
}

function GeocodeAgentNode({ data, selected }: NodeProps<GeocodeAgentData>) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const icon = getNodeIcon('AdvancedGeocodeAgent', 'h-4 w-4')
  const bgColor = getNodeBgColor('AdvancedGeocodeAgent')

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Advanced Geocode Agent
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="locations"
          className="w-3 h-3 bg-gray-700"
        />
        <div className="text-xs space-y-2">
          {requiredUpstreamNodes.length > 0 && (
            <div className="space-y-1">
              <Label className="text-muted-foreground">Depends on:</Label>
              <div className="flex flex-wrap gap-2">
                {requiredUpstreamNodes.map((nodeType: string) => {
                  const icon = getNodeIcon(nodeType, 'h-3 w-3')
                  const label = getNodeLabel(nodeType)
                  return (
                    <div key={nodeType} className="flex items-center gap-1">
                      {icon}
                      <span className="text-xs">{label}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          {dependencyHelperText && (
            <p className="text-xs text-muted-foreground mt-1">{dependencyHelperText}</p>
          )}
        </div>
        <Handle
          type="source"
          position={Position.Right}
          id="locations"
          className="w-3 h-3 bg-gray-700"
        />
      </CardContent>
    </Card>
  )
}

export default memo(GeocodeAgentNode)

