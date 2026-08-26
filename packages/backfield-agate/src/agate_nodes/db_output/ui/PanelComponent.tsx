import { useCallback, useEffect, useMemo, useState } from 'react'
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
import {
  autoConnectionsEligibility,
  autoConnectionsIneligibleCopy,
  autoConnectionsSelectDisabled,
  autoConnectionsUiShowsYes,
  resolvedAutoConnectionsEnabled,
} from '@/lib/autoConnectionsAvailability'
import {
  isProjectSemanticIndexingConfigured,
  semanticIndexingSelectDisabled,
  semanticIndexingUiShowsYes,
  shouldAutoClearSemanticIndexingEnabled,
} from '@/lib/semanticIndexingAvailability'
import {
  PROJECT_AI_MODELS_CHANGED_EVENT,
  type ProjectAiModelsChangedDetail,
} from '@/lib/projectAiModelsEvents'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
} from '@/lib/nodePanelAiModel'

interface DBOutputPanelProps {
  node: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
}

const DEFAULTS = {
  stylebook_matching_enabled: true,
  canonicalization_mode: 'ai_assisted' as 'rules' | 'ai_assisted',
  reconciliation_policy: 'smart_merge' as 'add_only' | 'smart_merge' | 'replace',
  auto_apply_canonicalization: true,
  adjudication_model: '',
  adjudication_ai_model_config_id: null as string | null,
  semantic_indexing_enabled: false,
  auto_connections_enabled: false,
  connections_model: '',
  connections_ai_model_config_id: null as string | null,
}

const ADJUDICATION_MODEL_KEYS = {
  configIdKey: 'adjudication_ai_model_config_id',
  modelKey: 'adjudication_model',
} as const

const CONNECTIONS_MODEL_KEYS = {
  configIdKey: 'connections_ai_model_config_id',
  modelKey: 'connections_model',
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

function resolvedConnectionsSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, CONNECTIONS_MODEL_KEYS)
}

function hasExplicitConnectionsChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, CONNECTIONS_MODEL_KEYS)
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

  const disabled = !(editMode && setNodes)
  const projectId = graphContext?.projectId ?? null

  const [catalogRows, setCatalogRows] = useState<ProjectAiModelOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [semanticIndexingConfigured, setSemanticIndexingConfigured] = useState<boolean | null>(
    null,
  )

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

  const refreshSemanticIndexingConfigured = useCallback(() => {
    if (projectId == null) {
      setSemanticIndexingConfigured(null)
      return
    }
    void isProjectSemanticIndexingConfigured(projectId)
      .then((configured) => {
        setSemanticIndexingConfigured(configured)
      })
      .catch(() => {
        setSemanticIndexingConfigured(false)
      })
  }, [projectId])

  useEffect(() => {
    refreshSemanticIndexingConfigured()
  }, [refreshSemanticIndexingConfigured])

  useEffect(() => {
    if (projectId == null) return

    const onModelsChanged = (event: Event) => {
      const detail = (event as CustomEvent<ProjectAiModelsChangedDetail>).detail
      if (detail?.projectId === projectId) {
        refreshSemanticIndexingConfigured()
      }
    }

    const onWindowFocus = () => {
      refreshSemanticIndexingConfigured()
    }

    window.addEventListener(PROJECT_AI_MODELS_CHANGED_EVENT, onModelsChanged)
    window.addEventListener('focus', onWindowFocus)
    return () => {
      window.removeEventListener(PROJECT_AI_MODELS_CHANGED_EVENT, onModelsChanged)
      window.removeEventListener('focus', onWindowFocus)
    }
  }, [projectId, refreshSemanticIndexingConfigured])

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

  const resolvedConn = resolvedConnectionsSelectValue(paramsRecord, catalogRows)
  const connSelectionValid =
    resolvedConn !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedConn)

  const nodeDataFlat = (node.data || {}) as Record<string, unknown>

  const showInvalidAdjPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitAdjudicationChoice(nodeDataFlat) &&
    !adjSelectionValid

  const showInvalidConnPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitConnectionsChoice(nodeDataFlat) &&
    !connSelectionValid

  const adjRadixValue = adjSelectionValid
    ? resolvedAdj
    : showInvalidAdjPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  const connRadixValue = connSelectionValid
    ? resolvedConn
    : showInvalidConnPersisted
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

  useEffect(() => {
    if (!editMode || !setNodes || catalogLoading || catalogRows.length === 0) return
    const data = nodeDataFlat
    if (hasExplicitConnectionsChoice(data)) return
    const first = modelSelectOptions[0]
    if (!first) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({
                ...(n.data || {}),
                connections_model: first.providerModelId,
                connections_ai_model_config_id: first.configId ?? null,
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

  const handleConnectionsModel = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    patch({
      connections_model: providerModelId,
      connections_ai_model_config_id: configId ?? null,
    })
  }

  const data = merged
  const stylebookMatchingEnabled = Boolean(data.stylebook_matching_enabled)
  const semanticIndexingEnabled = Boolean(data.semantic_indexing_enabled)
  const semanticIndexingAvailable = semanticIndexingConfigured === true
  const aiAssisted = data.canonicalization_mode === 'ai_assisted'
  const autoApplyEnabled = Boolean(data.auto_apply_canonicalization)
  const autoConnectionsEnabled = resolvedAutoConnectionsEnabled(
    data.auto_connections_enabled as boolean | undefined | null,
  )
  const autoConnectionsGate = autoConnectionsEligibility({
    stylebook_matching_enabled: stylebookMatchingEnabled,
    canonicalization_mode: data.canonicalization_mode,
    auto_apply_canonicalization: autoApplyEnabled,
  })

  useEffect(() => {
    if (shouldAutoClearSemanticIndexingEnabled(semanticIndexingConfigured, semanticIndexingEnabled)) {
      patch({ semantic_indexing_enabled: false })
    }
  }, [semanticIndexingConfigured, semanticIndexingEnabled])

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
                  ? 'Uses this run as the complete result for each included category, while preserving editor changes.'
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

          <div className="space-y-2">
            <Label htmlFor="dbout-semantic-indexing">Semantic indexing</Label>
            <Select
              value={yesNoSelectValue(
                semanticIndexingUiShowsYes(semanticIndexingConfigured, semanticIndexingEnabled),
              )}
              onValueChange={(value) =>
                patch({ semantic_indexing_enabled: value === 'yes' })
              }
              disabled={semanticIndexingSelectDisabled(semanticIndexingConfigured, disabled)}
            >
              <SelectTrigger id="dbout-semantic-indexing" className="text-xs">
                <SelectValue placeholder="Choose whether to prepare saved mentions for search" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="yes">Yes</SelectItem>
                <SelectItem value="no">No</SelectItem>
              </SelectContent>
            </Select>
            {semanticIndexingAvailable ? (
              <p className="text-xs text-muted-foreground">
                When on, saved mentions are indexed for semantic search across stories.
              </p>
            ) : projectId == null ? (
              <p className="text-xs text-muted-foreground">
                Save this flow under a project to use semantic indexing.
              </p>
            ) : semanticIndexingConfigured === false ? (
              <p className="text-xs text-muted-foreground">
                Enable an embedding model for this project in Models and set a default for semantic
                indexing before turning this on.
              </p>
            ) : null}
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

      <NodePanelTabGate tab="connections">
        {!stylebookMatchingEnabled ? (
          <p className="text-sm text-muted-foreground leading-relaxed">
            Turn on Stylebook matching in Settings to configure connections.
          </p>
        ) : !autoConnectionsGate.eligible ? (
          <p className="text-sm text-muted-foreground leading-relaxed">
            {autoConnectionsIneligibleCopy(autoConnectionsGate.reason)}
          </p>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="dbout-auto-connections">Automatic connections</Label>
              <Select
                value={yesNoSelectValue(
                  autoConnectionsUiShowsYes(
                    autoConnectionsGate.eligible,
                    autoConnectionsEnabled,
                  ),
                )}
                onValueChange={(value) =>
                  patch({ auto_connections_enabled: value === 'yes' })
                }
                disabled={autoConnectionsSelectDisabled(autoConnectionsGate.eligible, disabled)}
              >
                <SelectTrigger id="dbout-auto-connections" className="text-xs">
                  <SelectValue placeholder="Choose whether to add clear relationships automatically" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="yes">Yes</SelectItem>
                  <SelectItem value="no">No</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                When on, Backfield adds high-confidence connections between people,
                organizations, and locations found in each story.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dbout-connections-model">Connections model</Label>
              {catalogHint}
              {projectId != null && catalogLoading && (
                <p className="text-xs text-muted-foreground">Loading models…</p>
              )}
              {catalogError ? <p className="text-xs text-destructive">{catalogError}</p> : null}
              {catalogEmptyHint}
              {showInvalidConnPersisted ? (
                <p className="text-xs text-muted-foreground">
                  The saved connections model is no longer available. Choose another model below.
                </p>
              ) : null}
              <Select
                value={connRadixValue}
                onValueChange={handleConnectionsModel}
                disabled={disabled || modelSelectOptions.length === 0}
              >
                <SelectTrigger id="dbout-connections-model" className="text-xs">
                  <SelectValue placeholder="Choose a model" />
                </SelectTrigger>
                <SelectContent>
                  {showInvalidConnPersisted ? (
                    <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                      Saved model unavailable
                    </SelectItem>
                  ) : null}
                  {modelSelectOptions.map((m) => (
                    <SelectItem key={`conn-${m.selectValue}`} value={m.selectValue}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Used to infer relationships between entities. Options come from this
                project&apos;s enabled models.
              </p>
            </div>
          </div>
        )}
      </NodePanelTabGate>
    </>
  )
}
