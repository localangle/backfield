// Auto-injected metadata for DBOutput
const nodeMetadata = {
  "type": "DBOutput",
  "label": "Backfield Output",
  "icon": "Database",
  "color": "bg-slate-500",
  "description": "Persist the data to Backfield database, for access in Stylebook and Proof.",
  "category": "output",
  "requiredUpstreamNodes": [],
  "inputs": [
    {
      "id": "data",
      "label": "Any Data",
      "type": "any",
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
    "stylebook_matching_enabled": true,
    "stylebook_id": null,
    "canonicalization_mode": "ai_assisted",
    "reconciliation_policy": "smart_merge",
    "auto_apply_canonicalization": true,
    "adjudication_model": "",
    "adjudication_ai_model_config_id": null
  }
};

import { useEffect, useMemo, useState } from 'react'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { listOrgStylebooks, type OrgStylebook } from '@/lib/core-api'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
  resolvedStylebookId,
} from '@/lib/nodePanelAiModel'

interface DBOutputPanelProps {
  node: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
}

const DEFAULTS = {
  stylebook_matching_enabled: true,
  stylebook_id: null as number | null,
  canonicalization_mode: 'ai_assisted' as 'rules' | 'ai_assisted',
  reconciliation_policy: 'smart_merge' as 'add_only' | 'smart_merge' | 'replace',
  auto_apply_canonicalization: true,
  adjudication_model: '',
  adjudication_ai_model_config_id: null as string | null,
}

const ORG_DEFAULT_STYLEBOOK_SELECT = '__org_default_stylebook__'

const ADJUDICATION_MODEL_KEYS = {
  configIdKey: 'adjudication_ai_model_config_id',
  modelKey: 'adjudication_model',
} as const

function resolvedAdjudicationSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, ADJUDICATION_MODEL_KEYS)
}

function hasExplicitAdjudicationChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, ADJUDICATION_MODEL_KEYS)
}

function yesNoSelectValue(flag: boolean): 'yes' | 'no' {
  return flag ? 'yes' : 'no'
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

  const orgDefaultStylebook = stylebooks.find((sb) => sb.is_default)
  const usesOrgDefault =
    paramStylebookId == null ||
    (orgDefaultStylebook != null && paramStylebookId === orgDefaultStylebook.id)

  const stylebookSelectValue = usesOrgDefault
    ? ORG_DEFAULT_STYLEBOOK_SELECT
    : String(paramStylebookId)

  const handleStylebookSelect = (value: string) => {
    if (!setNodes) return
    const nextId = value === ORG_DEFAULT_STYLEBOOK_SELECT ? null : Number(value)
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id ? { ...n, data: mergeData({ ...(n.data || {}), stylebook_id: nextId }) } : n,
      ),
    )
  }

  const defaultOptionLabel = orgDefaultStylebook?.name
    ? `${orgDefaultStylebook.name} (Default)`
    : 'Default'

  const selectableStylebooks = orgDefaultStylebook
    ? stylebooks.filter((sb) => sb.id !== orgDefaultStylebook.id)
    : stylebooks

  const data = merged
  const stylebookMatchingEnabled = Boolean(data.stylebook_matching_enabled)
  const aiAssisted = data.canonicalization_mode === 'ai_assisted'

  const catalogHint =
    (projectId == null || graphContext?.fetchProjectAiModels == null) && editMode ? (
      <p className="text-xs text-muted-foreground">
        Save this flow under a project to choose decision models enabled for this project.
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
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="dbout-reconciliation">Update strategy</Label>
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
            <Label htmlFor="dbout-stylebook-matching">Stylebook matching</Label>
            <Select
              value={yesNoSelectValue(stylebookMatchingEnabled)}
              onValueChange={(value) => patch({ stylebook_matching_enabled: value === 'yes' })}
              disabled={disabled}
            >
              <SelectTrigger id="dbout-stylebook-matching" className="text-xs">
                <SelectValue placeholder="Choose whether to match with Stylebook" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="yes">Yes</SelectItem>
                <SelectItem value="no">No</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              When on, extracted entities are linked to your Stylebook. When off, results are saved but
              not linked to Stylebook.
            </p>
          </div>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="stylebook">
        {!stylebookMatchingEnabled ? (
          <p className="text-sm text-muted-foreground leading-relaxed">
            Turn on Stylebook matching in Settings to configure catalog matching.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="dbout-stylebook">Stylebook</Label>
              <Select
                value={stylebookSelectValue}
                onValueChange={handleStylebookSelect}
                disabled={disabled || orgId == null}
              >
                <SelectTrigger id="dbout-stylebook" className="text-xs">
                  <SelectValue placeholder="Choose a Stylebook" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ORG_DEFAULT_STYLEBOOK_SELECT}>{defaultOptionLabel}</SelectItem>
                  {missingFromList && paramStylebookId != null ? (
                    <SelectItem value={String(paramStylebookId)}>
                      {stylebooks.length === 0 && !stylebooksError
                        ? `Saved selection (ID ${paramStylebookId})`
                        : `Saved Stylebook unavailable (ID ${paramStylebookId})`}
                    </SelectItem>
                  ) : null}
                  {selectableStylebooks.map((sb) => (
                    <SelectItem key={sb.id} value={String(sb.id)}>
                      {sb.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {orgId == null && (
                <p className="text-xs text-muted-foreground">
                  Save the flow to a project (or open an existing project flow) to choose a Stylebook
                  for your organization.
                </p>
              )}
              {orgId != null && stylebooks.length === 0 && !stylebooksError && (
                <p className="text-xs text-muted-foreground">Loading Stylebooks…</p>
              )}
              {stylebooksError && <p className="text-xs text-destructive">{stylebooksError}</p>}
              <p className="text-xs text-muted-foreground">
                Default uses your organization&apos;s default Stylebook. Choose another to match and
                write against a different catalog.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dbout-mode">Matching strategy</Label>
              <Select
                value={data.canonicalization_mode}
                onValueChange={(value) =>
                  patch({ canonicalization_mode: value as 'rules' | 'ai_assisted' })
                }
                disabled={disabled}
              >
                <SelectTrigger id="dbout-mode" className="text-xs">
                  <SelectValue placeholder="Choose how to match" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="rules">Rules-based</SelectItem>
                  <SelectItem value="ai_assisted">AI Assisted</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {data.canonicalization_mode === 'rules'
                  ? 'Reconcile entities with Stylebook without using LLMs. Less accurate but faster and cheaper.'
                  : 'Use LLM to match entities with Stylebook entries. More accurate, especially in complex cases.'}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dbout-model">Decision model</Label>
              {aiAssisted ? (
                <>
                  {catalogHint}
                  {projectId != null && catalogLoading && (
                    <p className="text-xs text-muted-foreground">Loading models…</p>
                  )}
                  {catalogError ? <p className="text-xs text-destructive">{catalogError}</p> : null}
                  {catalogEmptyHint}
                  {showInvalidAdjPersisted ? (
                    <p className="text-xs text-muted-foreground">
                      The saved decision model is no longer available. Choose another model below.
                    </p>
                  ) : null}
                  <Select
                    value={adjRadixValue}
                    onValueChange={handleAdjudicationModel}
                    disabled={disabled || modelSelectOptions.length === 0}
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
                    Used to judge ambiguous catalog matches. Options come from this
                    project&apos;s enabled models.
                  </p>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Available when matching strategy is AI Assisted.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="dbout-auto">Auto-apply matching</Label>
              <Select
                value={yesNoSelectValue(Boolean(data.auto_apply_canonicalization))}
                onValueChange={(value) =>
                  patch({ auto_apply_canonicalization: value === 'yes' })
                }
                disabled={disabled}
              >
                <SelectTrigger id="dbout-auto" className="text-xs">
                  <SelectValue placeholder="Choose whether to apply matches automatically" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="yes">Yes</SelectItem>
                  <SelectItem value="no">No</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                When set to No, items go to the Stylebook queue for human review.
              </p>
            </div>
          </div>
        )}
      </NodePanelTabGate>
    </>
  )
}
