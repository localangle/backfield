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
    "adjudication_model": "gpt-5-nano"
  }
};

import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import type { GraphPanelContext } from '@/components/NodePanel'

interface DBOutputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext | null
}

const DEFAULTS = {
  stylebook_id: null as number | null,
  canonicalization_mode: 'rules' as 'rules' | 'ai_assisted',
  auto_apply_canonicalization: true,
  adjudication_model: 'gpt-5-nano' as 'gpt-5-nano' | 'gpt-5-mini',
}

export default function DBOutputPanel({
  node,
  editMode,
  setNodes,
  graphContext,
}: DBOutputPanelProps) {
  const data = { ...DEFAULTS, ...(node.data || {}) }
  const disabled = !(editMode && setNodes)

  const patch = (partial: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id ? { ...n, data: { ...DEFAULTS, ...(n.data || {}), ...partial } } : n,
      ),
    )
  }

  const stylebookStr =
    data.stylebook_id === null || data.stylebook_id === undefined || data.stylebook_id === ''
      ? ''
      : String(data.stylebook_id)

  return (
    <div className="space-y-4">
      <div>
        <Label className="text-sm font-medium">Description</Label>
        <p className="text-sm text-muted-foreground mt-1">
          Persists geocoded places to substrate tables and applies Stylebook canonicalization
          according to the options below.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="dbout-stylebook-id">Stylebook ID</Label>
        <Input
          id="dbout-stylebook-id"
          type="number"
          min={1}
          placeholder="Leave empty to use project workspace default"
          value={stylebookStr}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value.trim()
            patch({ stylebook_id: v === '' ? null : Number(v) })
          }}
        />
        <p className="text-xs text-muted-foreground">
          When set, canonicalization targets this Stylebook (must belong to the project
          organization). When empty, the workspace default Stylebook is used.
        </p>
        {stylebookStr === '' && graphContext?.workspaceDefaultStylebookId != null && (
          <p className="text-xs text-muted-foreground">
            Workspace default: Stylebook {graphContext.workspaceDefaultStylebookId}
          </p>
        )}
        {stylebookStr === '' && graphContext?.missingWorkspaceStylebook === true && (
          <p className="text-xs text-muted-foreground">
            This project has no workspace Stylebook from the API. Assign the project to a
            workspace (org admin) or set a Stylebook ID above.
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="dbout-mode">Canonicalization</Label>
        <select
          id="dbout-mode"
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          disabled={disabled}
          value={data.canonicalization_mode}
          onChange={(e) =>
            patch({ canonicalization_mode: e.target.value as 'rules' | 'ai_assisted' })
          }
        >
          <option value="rules">Rules-based</option>
          <option value="ai_assisted">AI-assisted</option>
        </select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="dbout-model">Adjudication model (AI-assisted)</Label>
        <select
          id="dbout-model"
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          disabled={disabled || data.canonicalization_mode === 'rules'}
          value={data.adjudication_model}
          onChange={(e) =>
            patch({ adjudication_model: e.target.value as 'gpt-5-nano' | 'gpt-5-mini' })
          }
        >
          <option value="gpt-5-nano">gpt-5-nano (default)</option>
          <option value="gpt-5-mini">gpt-5-mini</option>
        </select>
      </div>

      <div className="flex items-center gap-2">
        <input
          id="dbout-auto"
          type="checkbox"
          className="h-4 w-4 rounded border-input"
          disabled={disabled}
          checked={Boolean(data.auto_apply_canonicalization)}
          onChange={(e) => patch({ auto_apply_canonicalization: e.target.checked })}
        />
        <Label htmlFor="dbout-auto" className="text-sm font-normal cursor-pointer">
          Auto-apply canonicalization (off = review queue with recommendations)
        </Label>
      </div>
    </div>
  )
}
