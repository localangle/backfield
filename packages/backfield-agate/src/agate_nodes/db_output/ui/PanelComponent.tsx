import React, { useEffect, useMemo, useState } from 'react'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
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

const INVALID_SELECTION_VALUE = '__bf_model_invalid__'

const DEFAULTS = {
  stylebook_id: null as number | null,
  canonicalization_mode: 'rules' as 'rules' | 'ai_assisted',
  reconciliation_policy: 'smart_merge' as 'add_only' | 'smart_merge' | 'replace',
  auto_apply_canonicalization: true,
  adjudication_model: '',
  adjudication_ai_model_config_id: null as string | null,
}

const WORKSPACE_DEFAULT_SELECT = '__workspace_default__'

type UnifiedAiModelOption = {
  selectValue: string
  label: string
  providerModelId: string
  configId?: string
}

function catalogToSelectOptions(catalog: ProjectAiModelOption[]): UnifiedAiModelOption[] {
  const out: UnifiedAiModelOption[] = []
  const seen = new Set<string>()
  for (const row of catalog) {
    const sv = row.configId ?? row.providerModelId
    if (sv === '' || seen.has(sv)) continue
    seen.add(sv)
    out.push({
      selectValue: sv,
      label: row.label,
      providerModelId: row.providerModelId,
      configId: row.configId,
    })
  }
  return out
}

function resolvedAdjudicationSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  const cfg = params.adjudication_ai_model_config_id
  if (typeof cfg === 'string' && cfg.trim() !== '') return cfg.trim()
  const model = String(params.adjudication_model ?? '')
  const hit = catalog.find((r) => r.providerModelId === model && r.configId)
  if (hit?.configId) return hit.configId
  return model.trim()
}

function hasExplicitAdjudicationChoice(data: Record<string, unknown>): boolean {
  const cfg = data.adjudication_ai_model_config_id
  if (typeof cfg === 'string' && cfg.trim() !== '') return true
  const m = data.adjudication_model
  return typeof m === 'string' && m.trim() !== ''
}

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
  const projectId = graphContext?.projectId ?? null

  const [stylebooks, setStylebooks] = useState<OrgStylebook[]>([])
  const [stylebooksError, setStylebooksError] = useState<string | null>(null)
  const [catalogRows, setCatalogRows] = useState<ProjectAiModelOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)

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

  useEffect(() => {
    const fetcher = graphContext?.fetchProjectAiModels
    if (projectId == null || fetcher == null) {
      setCatalogRows([])
      setCatalogError(null)
      setCatalogLoading(false)
      return
    }
    let cancelled = false
    setCatalogLoading(true)
    setCatalogError(null)
    void fetcher(['text', 'json'])
      .then((rows) => {
        if (!cancelled) {
          setCatalogRows(rows)
          setCatalogLoading(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setCatalogRows([])
          setCatalogError(e instanceof Error ? e.message : 'Could not load models.')
          setCatalogLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, graphContext?.fetchProjectAiModels])

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
        n.id === node.id ? { ...n, data: mergeData({ ...(n.data || {}), ...partial }) } : n,
      ),
    )
  }

  const paramsRecord = merged as Record<string, unknown>
  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])

  const resolvedAdj = resolvedAdjudicationSelectValue(paramsRecord, catalogRows)
  const adjSelectionValid =
    resolvedAdj !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedAdj)

  const nodeDataFlat = (node.data || {}) as Record<string, unknown>

  const showInvalidAdjPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitAdjudicationChoice(nodeDataFlat) &&
    !adjSelectionValid

  const adjRadixValue = adjSelectionValid
    ? resolvedAdj
    : showInvalidAdjPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  useEffect(() => {
    if (!editMode || !setNodes || catalogLoading || catalogRows.length === 0) return
    const data = nodeDataFlat
    if (hasExplicitAdjudicationChoice(data)) return
    const first = modelSelectOptions[0]
    if (!first) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({
                ...(n.data || {}),
                adjudication_model: first.providerModelId,
                adjudication_ai_model_config_id: first.configId ?? null,
              }),
            }
          : n,
      ),
    )
  }, [editMode, setNodes, catalogLoading, catalogRows, modelSelectOptions, node.id, node.data])

  const handleAdjudicationModel = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    patch({
      adjudication_model: providerModelId,
      adjudication_ai_model_config_id: configId ?? null,
    })
  }

  const missingFromList = paramStylebookId != null && !stylebooks.some((s) => s.id === paramStylebookId)

  const stylebookSelectValue =
    paramStylebookId != null ? String(paramStylebookId) : WORKSPACE_DEFAULT_SELECT

  const handleStylebookSelect = (value: string) => {
    if (!setNodes) return
    const nextId = value === WORKSPACE_DEFAULT_SELECT ? null : Number(value)
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id ? { ...n, data: mergeData({ ...(n.data || {}), stylebook_id: nextId }) } : n,
      ),
    )
  }

  const defaultOptionLabel = graphContext?.workspaceStylebookName
    ? `Workspace default (${graphContext.workspaceStylebookName})`
    : 'Workspace default'

  const data = merged
  const aiAssisted = data.canonicalization_mode === 'ai_assisted'

  const catalogHint =
    (projectId == null || graphContext?.fetchProjectAiModels == null) && editMode ? (
      <p className="text-xs text-muted-foreground">
        Save this flow under a project to choose adjudication models enabled for this project.
      </p>
    ) : null

  const catalogEmptyHint =
    !catalogLoading &&
    !catalogError &&
    projectId != null &&
    graphContext?.fetchProjectAiModels != null &&
    modelSelectOptions.length === 0 ? (
      <p className="text-xs text-muted-foreground">
        No models available for this project yet. Ask an administrator to enable models for your
        organization, then turn them on for this project in project settings if needed.
      </p>
    ) : null

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
            Save the flow to a project (or open an existing project flow) to choose a catalog for
            your organization.
          </p>
        )}
        {orgId != null && stylebooks.length === 0 && !stylebooksError && (
          <p className="text-xs text-muted-foreground">Loading catalogs…</p>
        )}
        {stylebooksError && <p className="text-xs text-destructive">{stylebooksError}</p>}
        <p className="text-xs text-muted-foreground">
          When set, canonicalization targets this Stylebook (must belong to the project
          organization). Workspace default uses the catalog configured for this flow&apos;s
          workspace.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="dbout-reconciliation">Saved data</Label>
        <Select
          value={data.reconciliation_policy}
          onValueChange={(value) =>
            patch({
              reconciliation_policy: value as 'add_only' | 'smart_merge' | 'replace',
            })
          }
          disabled={disabled}
        >
          <SelectTrigger id="dbout-reconciliation" className="text-xs">
            <SelectValue placeholder="Choose how saved data is updated" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="add_only">Add Only</SelectItem>
            <SelectItem value="smart_merge">Smart Merge</SelectItem>
            <SelectItem value="replace">Replace</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          {data.reconciliation_policy === 'add_only'
            ? 'Adds new data from this flow without changing existing saved data.'
            : data.reconciliation_policy === 'replace'
              ? 'Replaces existing saved data from this flow’s categories with this run’s results.'
              : 'Updates data from this flow while preserving changes made by editors.'}
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
        <Label htmlFor="dbout-model" className="text-xs">
          Adjudication model (AI-assisted)
        </Label>
        {catalogHint}
        {projectId != null && catalogLoading && (
          <p className="text-xs text-muted-foreground">Loading models…</p>
        )}
        {catalogError ? <p className="text-xs text-destructive">{catalogError}</p> : null}
        {catalogEmptyHint}
        {showInvalidAdjPersisted ? (
          <p className="text-xs text-muted-foreground">
            The saved adjudication model is no longer available. Choose another model below.
          </p>
        ) : null}
        <Select
          value={adjRadixValue}
          onValueChange={handleAdjudicationModel}
          disabled={disabled || !aiAssisted || modelSelectOptions.length === 0}
        >
          <SelectTrigger id="dbout-model" className="text-xs">
            <SelectValue placeholder="Choose a model" />
          </SelectTrigger>
          <SelectContent>
            {showInvalidAdjPersisted ? (
              <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                Saved model unavailable
              </SelectItem>
            ) : null}
            {modelSelectOptions.map((m) => (
              <SelectItem key={`adj-${m.selectValue}`} value={m.selectValue}>
                {m.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Used when AI-assisted canonicalization needs to judge ambiguous catalog matches. Options
          come from this project&apos;s enabled models.
        </p>
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
