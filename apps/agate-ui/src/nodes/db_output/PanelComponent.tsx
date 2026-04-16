// Auto-injected metadata for DBOutput
const nodeMetadata = {
  "type": "DBOutput",
  "label": "DB Output",
  "icon": "Database",
  "color": "bg-slate-500",
  "description": "Persist consolidated upstream JSON into Backfield Postgres (worker-local)",
  "category": "output",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Same consolidation rules as JSON Output: wire any upstream nodes you want merged (unwraps node-* namespaces, apply include/exclude), then persists when `places` is present. JSON Output is optional — not required upstream.",
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
    "exclude": null,
    "include": null
  }
};

import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

interface DBOutputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function DBOutputPanel({
  node,
  editMode,
  setNodes,
}: DBOutputPanelProps) {
  const arrayToString = (arr: string[] | undefined): string => {
    if (!arr || arr.length === 0) return ''
    return arr.join(', ')
  }

  const stringToArray = (str: string): string[] => {
    if (!str || str.trim() === '') return []
    return str.split(',').map((s) => s.trim()).filter((s) => s.length > 0)
  }

  const handleExcludeChange = (value: string) => {
    if (!setNodes) return
    const excludeArray = stringToArray(value)
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...n.data,
                exclude_raw: value,
                exclude: excludeArray.length > 0 ? excludeArray : undefined,
              },
            }
          : n
      )
    )
  }

  const handleIncludeChange = (value: string) => {
    if (!setNodes) return
    const includeArray = stringToArray(value)
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...n.data,
                include_raw: value,
                include: includeArray.length > 0 ? includeArray : undefined,
              },
            }
          : n
      )
    )
  }

  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Same consolidation rules as JSON Output (include/exclude keys), then persists the consolidated payload
            into shared Backfield tables when the worker runs this graph. Wire upstream nodes directly; JSON Output
            is optional.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>

        <div className="space-y-3 mt-2">
          <div>
            <Label htmlFor="dboutput-exclude" className="text-xs text-muted-foreground">
              Exclude Keys (comma-separated)
            </Label>
            {editMode && setNodes ? (
              <Textarea
                id="dboutput-exclude"
                value={node.data?.exclude_raw ?? arrayToString(node.data?.exclude) ?? ''}
                onChange={(e) => handleExcludeChange(e.target.value)}
                placeholder="locations, node-6, etc."
                className="mt-1 min-h-[60px] text-xs"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs">{arrayToString(node.data?.exclude) || 'None'}</span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Keys to drop before persistence. Same semantics as JSON Output.
            </p>
          </div>

          <div>
            <Label htmlFor="dboutput-include" className="text-xs text-muted-foreground">
              Include Keys (whitelist, comma-separated)
            </Label>
            {editMode && setNodes ? (
              <Textarea
                id="dboutput-include"
                value={node.data?.include_raw ?? arrayToString(node.data?.include) ?? ''}
                onChange={(e) => handleIncludeChange(e.target.value)}
                placeholder="places, images, text, etc."
                className="mt-1 min-h-[60px] text-xs"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs">{arrayToString(node.data?.include) || 'All keys'}</span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              If set, only these keys are kept before persistence (whitelist).
            </p>
          </div>
        </div>
      </div>
    </>
  )
}
