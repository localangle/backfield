// Auto-injected metadata for PersonEnrich
const nodeMetadata = {
  "type": "PersonEnrich",
  "label": "Person Enrich",
  "description": "Enrich public figures with external connections and data sources.",
  "category": "enrichment",
  "icon": "Sparkles",
  "color": "bg-indigo-500",
  "requiredUpstreamNodes": [
    "PersonExtract"
  ],
  "requiredProjectModelCapabilities": [
    "decision"
  ],
  "dependencyHelperText": "Connect this after Person Extract. It looks up public figures and saves reference links.",
  "inputs": [
    {
      "id": "people",
      "label": "People",
      "type": "array",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "people",
      "label": "People",
      "type": "array"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "sources": [
      "wikidata",
      "wikipedia"
    ],
    "confidence_cutoff": 0.8
  }
};

import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { FieldLabel } from '@/components/node-panel/FieldLabel'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
  type AiModelFieldKeys,
} from '@/lib/nodePanelAiModel'

const DEFAULTS = {
  model: '',
  aiModelConfigId: null as string | null,
  sources: ['wikidata', 'wikipedia'] as string[],
  confidence_cutoff: 0.8,
}

const MODEL_KEYS: AiModelFieldKeys = {
  configIdKey: 'aiModelConfigId',
  modelKey: 'model',
}

const SOURCE_OPTIONS = [
  { id: 'wikidata', label: 'Wikidata' },
  { id: 'wikipedia', label: 'Wikipedia' },
] as const

interface PersonEnrichPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: (updater: (nodes: unknown[]) => unknown[]) => void
  graphContext?: GraphPanelContext
}

function selectedSources(value: unknown): string[] {
  if (!Array.isArray(value)) return [...DEFAULTS.sources]
  return value.filter((item): item is string => item === 'wikidata' || item === 'wikipedia')
}

export default function PersonEnrichPanel({
  node,
  editMode,
  setNodes,
  graphContext,
}: PersonEnrichPanelProps) {
  const merged = {
    ...DEFAULTS,
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  }
  const paramsRecord = merged as Record<string, unknown>
  const disabled = !(editMode && setNodes)
  const projectId = graphContext?.projectId ?? null
  const sources = selectedSources(paramsRecord.sources)
  const cutoff =
    typeof paramsRecord.confidence_cutoff === 'number' ? paramsRecord.confidence_cutoff : 0.8

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
    void fetcher(['decision'])
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

  const resolvedUnderlying = resolvedAiModelSelectValue(paramsRecord, catalogRows, MODEL_KEYS)
  const selectionValid =
    resolvedUnderlying !== '' &&
    modelSelectOptions.some((option) => option.selectValue === resolvedUnderlying)

  const showInvalidPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitAiModelChoice((node.data || {}) as Record<string, unknown>, MODEL_KEYS) &&
    !selectionValid

  const radixSelectValue = selectionValid
    ? resolvedUnderlying
    : showInvalidPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  const patch = (updates: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nds) =>
      (nds as { id: string; data?: Record<string, unknown> }[]).map((n) =>
        n.id === node.id ? { ...n, data: { ...(n.data || {}), ...updates } } : n,
      ),
    )
  }

  const onModelChange = (selectValue: string) => {
    if (selectValue === INVALID_SELECTION_VALUE) return
    const hit = catalogRows.find((row) => (row.configId ?? row.providerModelId) === selectValue)
    patch({
      aiModelConfigId: hit?.configId ?? null,
      model: hit?.providerModelId ?? selectValue,
    })
  }

  const onSourceChange = (sourceId: string, checked: boolean) => {
    const next = checked
      ? [...sources, sourceId]
      : sources.filter((source) => source !== sourceId)
    patch({ sources: SOURCE_OPTIONS.map((option) => option.id).filter((id) => next.includes(id)) })
  }

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-4">
          <div className="space-y-2">
            <FieldLabel required htmlFor="person-enrich-model">
              Decision model
            </FieldLabel>
            {catalogLoading ? (
              <p className="text-sm text-muted-foreground">Loading models…</p>
            ) : catalogError ? (
              <p className="text-sm text-destructive">{catalogError}</p>
            ) : modelSelectOptions.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Enable at least one decision model for this project in Models.
              </p>
            ) : (
              <Select value={radixSelectValue} onValueChange={onModelChange} disabled={disabled}>
                <SelectTrigger id="person-enrich-model" className="text-sm">
                  <SelectValue placeholder="Choose a decision model" />
                </SelectTrigger>
                <SelectContent>
                  {showInvalidPersisted ? (
                    <SelectItem value={INVALID_SELECTION_VALUE} disabled>
                      Saved model is no longer available
                    </SelectItem>
                  ) : null}
                  {modelSelectOptions.map((option) => (
                    <SelectItem key={option.selectValue} value={option.selectValue}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="space-y-2">
            <Label>Sources</Label>
            {SOURCE_OPTIONS.map((option) => (
              <div key={option.id} className="flex items-center gap-2">
                <Checkbox
                  id={`person-enrich-source-${option.id}`}
                  checked={sources.includes(option.id)}
                  disabled={disabled}
                  onCheckedChange={(checked) => onSourceChange(option.id, checked === true)}
                />
                <Label htmlFor={`person-enrich-source-${option.id}`} className="text-sm font-normal">
                  {option.label}
                </Label>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <FieldLabel htmlFor="person-enrich-cutoff">Match confidence</FieldLabel>
            <Input
              id="person-enrich-cutoff"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={cutoff}
              disabled={disabled}
              onChange={(event) => {
                const next = Number(event.target.value)
                patch({ confidence_cutoff: Number.isFinite(next) ? next : 0.8 })
              }}
            />
            <p className="text-xs text-muted-foreground">
              Only save a link when the match is at least this sure. Use a number from 0 to 1.
            </p>
          </div>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="info">
        {nodeMetadata.dependencyHelperText ? (
          <p className="text-sm text-muted-foreground leading-relaxed">
            {nodeMetadata.dependencyHelperText}
          </p>
        ) : null}
      </NodePanelTabGate>
    </>
  )
}
