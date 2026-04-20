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

  const readOnlyText = (() => {
    const ctx = graphContext
    if (!ctx) {
      return 'Loading workspace Stylebook…'
    }
    if (ctx.flowProjectLoading) {
      return 'Loading workspace Stylebook…'
    }
    const name = ctx.workspaceStylebookName?.trim()
    if (name) return name
    if (ctx.workspaceDefaultStylebookId != null) {
      return `Stylebook ${ctx.workspaceDefaultStylebookId}`
    }
    if (ctx.missingWorkspaceStylebook) {
      return 'No workspace Stylebook resolved for this project.'
    }
    return 'Could not load the workspace Stylebook for this flow.'
  })()

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
        <Label htmlFor="dbout-workspace-stylebook">Workspace Stylebook</Label>
        <div
          id="dbout-workspace-stylebook"
          className="flex min-h-10 w-full items-center rounded-md border border-input bg-muted px-3 py-2 text-sm text-foreground"
          aria-readonly="true"
        >
          {readOnlyText}
        </div>
        <p className="text-xs text-muted-foreground">
          Taken from the workspace that owns this flow&apos;s project. Change it in workspace
          settings.
        </p>
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
