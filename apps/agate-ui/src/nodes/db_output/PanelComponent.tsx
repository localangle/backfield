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
  "defaultParams": {}
};

import { Label } from '@/components/ui/label'

interface DBOutputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function DBOutputPanel(_props: DBOutputPanelProps) {
  return (
    <div className="space-y-3">
      <div>
        <Label className="text-sm font-medium">Description</Label>
        <p className="text-sm text-muted-foreground mt-1">Persists results to Stylebook</p>
      </div>
    </div>
  )
}
