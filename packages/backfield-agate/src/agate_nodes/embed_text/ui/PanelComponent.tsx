import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { FieldLabel } from '@/components/node-panel/FieldLabel'
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
}

const MODEL_KEYS: AiModelFieldKeys = {
  configIdKey: 'aiModelConfigId',
  modelKey: 'model',
}

interface EmbedTextPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: (updater: (nodes: unknown[]) => unknown[]) => void
  graphContext?: GraphPanelContext
}

export default function EmbedTextPanel({
  node,
  editMode,
  setNodes,
  graphContext,
}: EmbedTextPanelProps) {
  const merged = {
    ...DEFAULTS,
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  }
  const paramsRecord = merged as Record<string, unknown>
  const disabled = !(editMode && setNodes)
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
    void fetcher(['embedding'])
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
  const enabledOptions = modelSelectOptions

  const resolvedUnderlying = resolvedAiModelSelectValue(paramsRecord, catalogRows)
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
    const hit = catalogRows.find(
      (row) => (row.configId ?? row.providerModelId) === selectValue,
    )
    patch({
      aiModelConfigId: hit?.configId ?? null,
      model: hit?.providerModelId ?? selectValue,
    })
  }

  return (
    <NodePanelTabGate tab="settings">
      <div className="space-y-4">
        <div className="space-y-2">
          <FieldLabel required htmlFor="embed-text-model">
            Embedding model
          </FieldLabel>
          {catalogLoading ? (
            <p className="text-sm text-muted-foreground">Loading models…</p>
          ) : catalogError ? (
            <p className="text-sm text-destructive">{catalogError}</p>
          ) : enabledOptions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Enable at least one embedding model for this project in Models.
            </p>
          ) : (
            <Select
              value={radixSelectValue}
              onValueChange={onModelChange}
              disabled={disabled}
            >
              <SelectTrigger id="embed-text-model" className="text-sm">
                <SelectValue placeholder="Choose an embedding model" />
              </SelectTrigger>
              <SelectContent>
                {showInvalidPersisted ? (
                  <SelectItem value={INVALID_SELECTION_VALUE} disabled>
                    Saved model is no longer available
                  </SelectItem>
                ) : null}
                {enabledOptions.map((option) => (
                  <SelectItem key={option.selectValue} value={option.selectValue}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <div className="space-y-2 border-t pt-4">
          <Label className="text-sm font-medium">About this step</Label>
          <p className="text-sm text-muted-foreground leading-relaxed">
            This step turns the full story text (including the headline when present) into a
            searchable vector. When the flow saves through Backfield Output, the embedding is stored
            with the story.
          </p>
        </div>
      </div>
    </NodePanelTabGate>
  )
}
