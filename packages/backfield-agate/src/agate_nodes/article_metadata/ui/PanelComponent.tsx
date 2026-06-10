import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
} from '@/lib/nodePanelAiModel'
import {
  ARTICLE_METADATA_DEFAULT_PRESET,
  ARTICLE_METADATA_PRESET_OPTIONS,
  type ArticleMetadataPresetId,
} from './presetOptions'

const DEFAULTS = {
  model: '',
  aiModelConfigId: null as string | null,
  prompt_preset: ARTICLE_METADATA_DEFAULT_PRESET,
  meta_type: '',
  prompt: '',
}

const MODEL_KEYS = {
  configIdKey: 'aiModelConfigId',
  modelKey: 'model',
} as const

type PresetPromptMap = Record<string, string>

function presetPromptsFromMetadata(): PresetPromptMap {
  const raw = nodeMetadata.defaultParams?.preset_prompts
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as PresetPromptMap
  }
  return {}
}

function normalizePreset(raw: unknown): ArticleMetadataPresetId {
  const value =
    typeof raw === 'string'
      ? raw.trim().toLowerCase().replace(/-/g, '_')
      : ARTICLE_METADATA_DEFAULT_PRESET
  const match = ARTICLE_METADATA_PRESET_OPTIONS.find((option) => option.id === value)
  return match?.id ?? ARTICLE_METADATA_DEFAULT_PRESET
}

/** Keep metadata type slugs lowercase with underscores; strip disallowed characters. */
function sanitizeMetaTypeInput(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .replace(/_+/g, '_')
    .replace(/^[_0-9]+/, '')
}

function resolvedModelSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, MODEL_KEYS)
}

function hasExplicitModelChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, MODEL_KEYS)
}

function promptMatchesPresetDefault(
  prompt: string,
  presetId: string,
  presetPrompts: PresetPromptMap,
): boolean {
  const trimmed = prompt.trim()
  if (!trimmed) return true
  const presetDefault = presetPrompts[presetId]
  if (typeof presetDefault === 'string' && trimmed === presetDefault.trim()) {
    return true
  }
  const bundledDefault =
    typeof nodeMetadata.defaultParams?.prompt === 'string'
      ? nodeMetadata.defaultParams.prompt.trim()
      : ''
  return presetId === ARTICLE_METADATA_DEFAULT_PRESET && bundledDefault !== '' && trimmed === bundledDefault
}

interface ArticleMetadataPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  currentRun?: { node_outputs?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: (nodes: unknown) => void
  graphContext?: GraphPanelContext
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

export default function ArticleMetadataPanel({
  node,
  editMode,
  setNodes,
  currentRun,
  graphContext,
  nodeOutputLookupSpec,
}: ArticleMetadataPanelProps) {
  const merged = {
    ...DEFAULTS,
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  }
  const paramsRecord = merged as Record<string, unknown>
  const presetPrompts = useMemo(() => presetPromptsFromMetadata(), [])

  const projectId = graphContext?.projectId ?? null
  const [catalogRows, setCatalogRows] = useState<ProjectAiModelOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)

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

  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])

  const resolvedUnderlying = resolvedModelSelectValue(paramsRecord, catalogRows)
  const selectionValid =
    resolvedUnderlying !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedUnderlying)

  const showInvalidPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitModelChoice((node.data || {}) as Record<string, unknown>) &&
    !selectionValid

  const radixSelectValue = selectionValid
    ? resolvedUnderlying
    : showInvalidPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  useEffect(() => {
    if (!editMode || !setNodes || catalogLoading || catalogRows.length === 0) return
    const data = (node.data || {}) as Record<string, unknown>
    if (hasExplicitModelChoice(data)) return
    const first = modelSelectOptions[0]
    if (!first) return
    setNodes((nds: { id: string; data?: Record<string, unknown> }[]) =>
      nds.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...(n.data || {}),
                model: first.providerModelId,
                aiModelConfigId: first.configId ?? null,
              },
            }
          : n,
      ),
    )
  }, [
    editMode,
    setNodes,
    catalogLoading,
    catalogRows,
    modelSelectOptions,
    node.id,
    node.data,
  ])

  const isDisabled = !(editMode && setNodes)
  const currentPreset = normalizePreset(paramsRecord.prompt_preset)
  const currentPrompt =
    typeof paramsRecord.prompt === 'string'
      ? paramsRecord.prompt
      : typeof nodeMetadata.defaultParams?.prompt === 'string'
        ? nodeMetadata.defaultParams.prompt
        : ''
  const currentMetaType =
    typeof paramsRecord.meta_type === 'string' ? paramsRecord.meta_type : ''

  const patchNodeData = (updates: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nds: { id: string; data?: Record<string, unknown> }[]) =>
      nds.map((n) =>
        n.id === node.id ? { ...n, data: { ...(n.data || {}), ...updates } } : n,
      ),
    )
  }

  const handleModelChange = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    patchNodeData({
      model: row?.providerModelId ?? selectValue,
      aiModelConfigId: row?.configId ?? null,
    })
  }

  const handlePresetChange = (nextPreset: string) => {
    if (!setNodes) return
    const presetId = normalizePreset(nextPreset)
    const updates: Record<string, unknown> = { prompt_preset: presetId }
    if (presetId !== 'custom') {
      updates.meta_type = ''
    }
    if (
      presetId !== 'custom' &&
      promptMatchesPresetDefault(currentPrompt, currentPreset, presetPrompts)
    ) {
      updates.prompt = presetPrompts[presetId] ?? ''
    }
    patchNodeData(updates)
  }

  const displayModelLabel =
    modelSelectOptions.find((o) => o.selectValue === resolvedUnderlying)?.label ??
    (showInvalidPersisted
      ? 'Previous model unavailable'
      : resolvedUnderlying !== ''
        ? String(paramsRecord.model ?? resolvedUnderlying)
        : '—')

  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
    nodeOutputLookupSpec ?? undefined,
  )
  const latestMetadata =
    nodeOutput &&
    typeof nodeOutput === 'object' &&
    nodeOutput !== null &&
    'article_metadata' in nodeOutput
      ? (nodeOutput as { article_metadata?: Record<string, unknown> }).article_metadata
      : null

  return (
    <>
      <NodePanelTabGate tab="info">
        <div className="space-y-2">
          <Label className="text-sm font-medium">Input placeholders</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Pull fields from upstream JSON into the prompt using these tokens:
          </p>
          <ul className="list-disc list-inside text-xs mt-2 space-y-1 text-muted-foreground">
            <li>
              <code className="bg-muted px-1 rounded">{'{text}'}</code> — plain text or the{' '}
              <code className="bg-muted px-1 rounded">text</code> field from JSON input
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{headline}'}</code> —{' '}
              <code className="bg-muted px-1 rounded">headline</code> field when present
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{raw}'}</code> — entire input object as JSON
            </li>
          </ul>
          {nodeMetadata.dependencyHelperText ? (
            <p className="text-sm text-muted-foreground mt-3">{nodeMetadata.dependencyHelperText}</p>
          ) : null}
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="settings">
        <div>
          <Label className="text-sm font-medium">Classification model</Label>
          {editMode && setNodes ? (
            <>
              {(projectId == null || graphContext?.fetchProjectAiModels == null) && (
                <p className="text-xs text-muted-foreground mt-2">
                  Save this flow under a project to choose models your organization enabled for
                  this project.
                </p>
              )}
              {projectId != null && catalogLoading && (
                <p className="text-xs text-muted-foreground mt-2">Loading models…</p>
              )}
              {catalogError != null && catalogError !== '' ? (
                <p className="text-xs text-destructive mt-2">{catalogError}</p>
              ) : null}
              {!catalogLoading &&
                !catalogError &&
                projectId != null &&
                graphContext?.fetchProjectAiModels != null &&
                modelSelectOptions.length === 0 && (
                  <p className="text-xs text-muted-foreground mt-2">
                    No models available for this project yet. Ask an administrator to enable
                    models for your organization, then turn them on for this project in project
                    settings if needed.
                  </p>
                )}
              {showInvalidPersisted && (
                <p className="text-xs text-muted-foreground mt-2">
                  The saved model is no longer available. Choose another model below.
                </p>
              )}
              <Select
                value={radixSelectValue}
                onValueChange={handleModelChange}
                disabled={isDisabled || modelSelectOptions.length === 0}
              >
                <SelectTrigger className="h-8 text-xs mt-2">
                  <SelectValue placeholder="Choose a model" />
                </SelectTrigger>
                <SelectContent>
                  {showInvalidPersisted ? (
                    <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                      Saved model unavailable
                    </SelectItem>
                  ) : null}
                  {modelSelectOptions.map((m) => (
                    <SelectItem key={`am-${m.selectValue}`} value={m.selectValue}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Set available models in your organization settings.
              </p>
            </>
          ) : (
            <>
              <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                <span className="text-muted-foreground">Classification model</span>
                <span className="font-medium text-xs">{displayModelLabel}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Set available models in your organization settings.
              </p>
            </>
          )}
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="prompts">
        <div className="space-y-3">
          <div>
            <Label className="text-sm font-medium">Preset</Label>
            {editMode && setNodes ? (
              <Select value={currentPreset} onValueChange={handlePresetChange} disabled={isDisabled}>
                <SelectTrigger className="h-8 text-xs mt-2">
                  <SelectValue placeholder="Choose a preset" />
                </SelectTrigger>
                <SelectContent>
                  {ARTICLE_METADATA_PRESET_OPTIONS.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                <span className="text-muted-foreground">Preset</span>
                <span className="font-medium text-xs capitalize">
                  {ARTICLE_METADATA_PRESET_OPTIONS.find((option) => option.id === currentPreset)
                    ?.label ?? currentPreset.replace(/_/g, ' ')}
                </span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Each preset classifies one metadata dimension for this run.
            </p>
          </div>

          {currentPreset === 'custom' ? (
            <div>
              <Label className="text-sm font-medium">Metadata type</Label>
              {editMode && setNodes ? (
                <Input
                  value={currentMetaType}
                  onChange={(e) => {
                    patchNodeData({ meta_type: sanitizeMetaTypeInput(e.target.value) })
                  }}
                  placeholder="brand_safety"
                  className="mt-2 h-8 text-xs font-mono"
                  spellCheck={false}
                  autoCapitalize="off"
                  autoCorrect="off"
                />
              ) : (
                <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                  <span className="text-muted-foreground">Metadata type</span>
                  <span className="font-medium text-xs font-mono">
                    {currentMetaType.trim() || '—'}
                  </span>
                </div>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                Stored as the dimension key for this classifier (for example{' '}
                <code className="bg-muted px-1 rounded">brand_safety</code>). Letters, numbers, and
                underscores only — spaces become underscores as you type.
              </p>
            </div>
          ) : null}

          <div>
            <Label className="text-sm font-medium">Prompt</Label>
            {editMode && setNodes ? (
              <Textarea
                value={currentPrompt}
                onChange={(e) => {
                  patchNodeData({ prompt: e.target.value })
                }}
                placeholder="Enter custom prompt"
                className="mt-2 min-h-[200px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
              />
            ) : (
              <div className="mt-2 p-2 bg-muted rounded max-h-48 overflow-y-auto">
                <pre className="text-xs whitespace-pre-wrap font-mono">
                  {currentPrompt || 'Using default prompt'}
                </pre>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Include a <code className="bg-muted px-1 rounded">## Categories</code> section with
              bullet labels the model must choose from.
            </p>
          </div>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        <div className="space-y-4">
          <div>
            <Label className="text-sm font-medium">Output format</Label>
            <Textarea
              readOnly
              value={nodeMetadata.defaultParams?.output_format?.trim() || ''}
              placeholder="Run node sync (apps/agate-ui) after changing prompts/_output_format.json"
              className="mt-2 min-h-[120px] px-3 py-2 text-xs border border-input bg-muted/50 rounded-md font-mono cursor-default"
              spellCheck={false}
            />
            <p className="text-xs text-muted-foreground mt-1">For reference only.</p>
          </div>

          {latestMetadata && (
            <div className="border-t pt-4">
              <Label className="text-sm font-medium">Latest run</Label>
              <div className="mt-2 space-y-2 text-xs">
                {typeof latestMetadata.category === 'string' && latestMetadata.category ? (
                  <div className="p-2 bg-muted rounded">
                    <div className="font-medium">{latestMetadata.category}</div>
                    {typeof latestMetadata.rationale === 'string' && latestMetadata.rationale ? (
                      <div className="text-muted-foreground mt-1">{latestMetadata.rationale}</div>
                    ) : null}
                    {typeof latestMetadata.confidence === 'number' ? (
                      <div className="text-muted-foreground mt-1">
                        Confidence: {latestMetadata.confidence.toFixed(2)}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </NodePanelTabGate>
    </>
  )
}
