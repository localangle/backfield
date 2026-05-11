// Auto-injected metadata for DBOutput
const nodeMetadata = {
  "type": "DBOutput",
  "label": "Stylebook Output",
  "icon": "Database",
  "color": "bg-slate-500",
  "description": "Persists results to Stylebook",
  "category": "output",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Persists results to Stylebook",
  "inputs": [
    {
      "id": "data",
      "label": "Any Data",
      "type": "object",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "success",
      "label": "Success",
      "type": "boolean"
    },
    {
      "id": "article_id",
      "label": "Article ID",
      "type": "number"
    },
    {
      "id": "message",
      "label": "Message",
      "type": "string"
    }
  ],
  "defaultParams": {
    "stylebook_id": null,
    "canonicalization_mode": "rules",
    "auto_apply_canonicalization": true,
    "adjudication_model": "",
    "adjudication_ai_model_config_id": null
  }
};

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { getNodeIcon, getNodeLabel, getNodeBgColor } from '@/lib/nodeUtils'

function DBOutputNode({ selected }: NodeProps) {
  const requiredUpstreamNodes = nodeMetadata?.requiredUpstreamNodes || []
  const dependencyHelperText = nodeMetadata?.dependencyHelperText || ''
  const type = 'DBOutput'
  const icon = getNodeIcon(type, 'h-4 w-4')
  const bgColor = getNodeBgColor(type)
  const title = getNodeLabel(type)

  return (
    <Card className={`w-[200px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColor}`}>
            {icon}
          </div>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Handle
          type="target"
          position={Position.Left}
          id="data"
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
          {dependencyHelperText && <p className="text-xs text-muted-foreground mt-1">{dependencyHelperText}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

export default memo(DBOutputNode)
