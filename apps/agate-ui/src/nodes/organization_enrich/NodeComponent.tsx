// Auto-injected metadata for OrganizationEnrich
const nodeMetadata = {
  "type": "OrganizationEnrich",
  "label": "Organization Enrich",
  "description": "Enrich organizations with external connections and data sources.",
  "category": "enrichment",
  "icon": "Sparkles",
  "color": "bg-indigo-500",
  "requiredUpstreamNodes": [
    "OrganizationExtract"
  ],
  "requiredProjectModelCapabilities": [
    "decision"
  ],
  "dependencyHelperText": "Connect this after Organization Extract. It looks up organizations and saves Wikidata and Wikipedia links.",
  "inputs": [
    {
      "id": "organizations",
      "label": "Organizations",
      "type": "array",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "organizations",
      "label": "Organizations",
      "type": "array"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "sources": [
      "wikidata",
      "wikipedia"
    ],
    "confidence_cutoff": 0.8
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getNodeIcon, getNodeBgColor } from '@/lib/nodeUtils'

interface OrganizationEnrichData {
  model?: string
  sources?: string[]
}

const SOURCE_LABELS: Record<string, string> = {
  wikidata: 'Wikidata',
  wikipedia: 'Wikipedia',
}

function OrganizationEnrichNode({ data, selected }: NodeProps<OrganizationEnrichData>) {
  const icon = getNodeIcon('OrganizationEnrich', 'h-4 w-4')
  const bgColor = getNodeBgColor('OrganizationEnrich')
  const modelLabel = data.model?.trim() ? data.model.trim() : 'Decision model not set'
  const sources = Array.isArray(data.sources) ? data.sources : ['wikidata', 'wikipedia']
  const sourceLabel = sources
    .map((source) => SOURCE_LABELS[source])
    .filter((label): label is string => Boolean(label))
    .join(', ')

  return (
    <Card className={`w-[280px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          Organization Enrich
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle type="target" position={Position.Left} id="organizations" className="w-3 h-3 bg-gray-700" />
        <div className="text-xs space-y-1 text-muted-foreground">
          <p>{modelLabel}</p>
          <p>{sourceLabel || 'No sources selected'}</p>
        </div>
        <Handle type="source" position={Position.Right} id="organizations" className="w-3 h-3 bg-gray-700" />
      </CardContent>
    </Card>
  )
}

export default memo(OrganizationEnrichNode)
