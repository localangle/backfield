import React, { useEffect, useState } from 'react'
import type { GraphPanelContext } from '@/components/NodePanel'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { listOrgStylebooks, type OrgStylebook } from '@/lib/core-api'

interface DBOutputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
}

const DEFAULTS = {
  stylebook_id: null as number | null,
  canonicalization_mode: 'rules' as 'rules' | 'ai_assisted',
  auto_apply_canonicalization: true,
  adjudication_model: 'gpt-5-nano' as 'gpt-5-nano' | 'gpt-5-mini',
}

/** Sentinel value for Radix Select (workspace default Stylebook). */
const WORKSPACE_DEFAULT_SELECT = '__workspace_default__'

/** Prefer canonical ``stylebook_id``; legacy persisted ``stylebookId`` is still read once. */
function resolvedStylebookId(data: Record<string, unknown> | undefined): number | null {
  const d = data || {}
  const snake = d.stylebook_id
  const camel = d.stylebookId
  const raw = snake !== undefined && snake !== null ? snake : camel
  if (raw === null || raw === undefined || raw === '') return null
  const n = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(n) ? n : null
}

export default function DBOutputPanel({
  node,
  editMode,
  setNodes,
  graphContext,
}: DBOutputPanelProps) {
  const merged = { ...DEFAULTS, ...(node.data || {}) }
  const legacyCamel = (node.data as Record<string, unknown> | undefined)?.stylebookId
  if (merged.stylebook_id == null && legacyCamel != null && legacyCamel !== '') {
    ;(merged as Record<string, unknown>).stylebook_id = legacyCamel
  }

  const paramStylebookId = resolvedStylebookId(merged as Record<string, unknown>)

  const disabled = !(editMode && setNodes)
  const orgId = graphContext?.organizationId ?? null

  const [stylebooks, setStylebooks] = useState<OrgStylebook[]>([])
  const [stylebooksError, setStylebooksError] = useState<string | null>(null)

  useEffect(() => {
    if (!orgId) {
      setStylebooks([])
      setStylebooksError(null)
      return
    }
    let cancelled = false
    setStylebooksError(null)
    listOrgStylebooks(orgId)
      .then((rows) => {
        if (!cancelled) setStylebooks(rows)
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setStylebooks([])
          setStylebooksError(e instanceof Error ? e.message : 'Could not load catalogs.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [orgId])

  const mergeData = (base: Record<string, unknown>) => {
    const out = {
      ...DEFAULTS,
      ...base,
    }
    delete (out as { stylebookId?: unknown }).stylebookId
    return out
  }

  const patch = (partial: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? { ...n, data: mergeData({ ...(n.data || {}), ...partial }) }
          : n,
      ),
    )
  }

  /** Saved id not yet present in the fetched list (loading or removed from org). */
  const missingFromList =
    paramStylebookId != null && !stylebooks.some((s) => s.id === paramStylebookId)

  const stylebookSelectValue =
    paramStylebookId != null ? String(paramStylebookId) : WORKSPACE_DEFAULT_SELECT

  const handleStylebookSelect = (value: string) => {
    if (!setNodes) return
    const nextId = value === WORKSPACE_DEFAULT_SELECT ? null : Number(value)
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? { ...n, data: mergeData({ ...(n.data || {}), stylebook_id: nextId }) }
          : n,
      ),
    )
  }

  const defaultOptionLabel = graphContext?.workspaceStylebookName
    ? `Workspace default (${graphContext.workspaceStylebookName})`
    : 'Workspace default'

  const data = merged

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
        <Label htmlFor="dbout-stylebook" className="text-xs">
          Catalog
        </Label>
        <Select
          value={stylebookSelectValue}
          onValueChange={handleStylebookSelect}
          disabled={disabled || orgId == null}
        >
          <SelectTrigger id="dbout-stylebook" className="text-xs">
            <SelectValue placeholder="Choose a catalog" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={WORKSPACE_DEFAULT_SELECT}>{defaultOptionLabel}</SelectItem>
            {missingFromList && paramStylebookId != null ? (
              <SelectItem value={String(paramStylebookId)}>
                {stylebooks.length === 0 && !stylebooksError
                  ? `Saved selection (ID ${paramStylebookId})`
                  : `Saved catalog unavailable (ID ${paramStylebookId})`}
              </SelectItem>
            ) : null}
            {stylebooks.map((sb) => (
              <SelectItem key={sb.id} value={String(sb.id)}>
                {sb.name}
                {sb.is_default ? ' (organization default)' : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {orgId == null && (
          <p className="text-xs text-muted-foreground">
            Save the flow to a project (or open an existing project flow) to choose a catalog for your
            organization.
          </p>
        )}
        {orgId != null && stylebooks.length === 0 && !stylebooksError && (
          <p className="text-xs text-muted-foreground">Loading catalogs…</p>
        )}
        {stylebooksError && <p className="text-xs text-destructive">{stylebooksError}</p>}
        <p className="text-xs text-muted-foreground">
          When set, canonicalization targets this Stylebook (must belong to the project organization).
          Workspace default uses the catalog configured for this flow&apos;s workspace.
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
