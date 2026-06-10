// Auto-injected metadata for EmbedImages
const nodeMetadata = {
  "type": "EmbedImages",
  "label": "Embed Images",
  "description": "Describe each image with a vision model, then embed those descriptions for search and analysis.",
  "category": "embedding",
  "icon": "Image",
  "color": "bg-orange-500",
  "requiredUpstreamNodes": [],
  "requiredProjectModelCapabilities": [
    "generative",
    "embedding"
  ],
  "dependencyHelperText": "Requires upstream images, such as from JSON Input with an images field.",
  "inputs": [
    {
      "id": "images",
      "label": "Images",
      "type": "object",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "image_embeddings",
      "label": "Image embeddings",
      "type": "array"
    }
  ],
  "defaultParams": {
    "prompt": "Describe this image in detail. Use the provided context (caption and article text) to inform your description, but focus primarily on what you see in the image itself.",
    "visionModel": "",
    "visionAiModelConfigId": null,
    "embeddingModel": "",
    "embeddingAiModelConfigId": null
  }
};

import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { FieldLabel } from '@/components/node-panel/FieldLabel'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
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
  prompt: '',
  visionModel: '',
  visionAiModelConfigId: null as string | null,
  embeddingModel: '',
  embeddingAiModelConfigId: null as string | null,
}

const VISION_MODEL_KEYS: AiModelFieldKeys = {
  configIdKey: 'visionAiModelConfigId',
  modelKey: 'visionModel',
}

const EMBEDDING_MODEL_KEYS: AiModelFieldKeys = {
  configIdKey: 'embeddingAiModelConfigId',
  modelKey: 'embeddingModel',
}

interface EmbedImagesPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: (updater: (nodes: unknown[]) => unknown[]) => void
  graphContext?: GraphPanelContext
}

function useCatalogRows(
  graphContext: GraphPanelContext | undefined,
  capabilities: string[],
): {
  rows: ProjectAiModelOption[]
  loading: boolean
  error: string | null
} {
  const projectId = graphContext?.projectId ?? null
  const [rows, setRows] = useState<ProjectAiModelOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetcher = graphContext?.fetchProjectAiModels
    if (projectId == null || fetcher == null) {
      setRows([])
      setError(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    void fetcher(capabilities)
      .then((nextRows) => {
        if (!cancelled) {
          setRows(nextRows)
          setLoading(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setRows([])
          setError(e instanceof Error ? e.message : 'Could not load models.')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, graphContext?.fetchProjectAiModels, capabilities.join(',')])

  return { rows, loading, error }
}

function ModelSelect({
  id,
  label,
  required,
  disabled,
  modelKeys,
  paramsRecord,
  catalogRows,
  catalogLoading,
  catalogError,
  nodeData,
  onChange,
}: {
  id: string
  label: string
  required?: boolean
  disabled: boolean
  modelKeys: AiModelFieldKeys
  paramsRecord: Record<string, unknown>
  catalogRows: ProjectAiModelOption[]
  catalogLoading: boolean
  catalogError: string | null
  nodeData: Record<string, unknown>
  onChange: (updates: Record<string, unknown>) => void
}) {
  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])
  const resolvedUnderlying = resolvedAiModelSelectValue(paramsRecord, catalogRows, modelKeys)
  const selectionValid =
    resolvedUnderlying !== '' &&
    modelSelectOptions.some((option) => option.selectValue === resolvedUnderlying)

  const showInvalidPersisted =
    Boolean(!disabled && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitAiModelChoice(nodeData, modelKeys) &&
    !selectionValid

  const radixSelectValue = selectionValid
    ? resolvedUnderlying
    : showInvalidPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  return (
    <div className="space-y-2">
      <FieldLabel required={required} htmlFor={id}>
        {label}
      </FieldLabel>
      {catalogLoading ? (
        <p className="text-sm text-muted-foreground">Loading models…</p>
      ) : catalogError ? (
        <p className="text-sm text-destructive">{catalogError}</p>
      ) : modelSelectOptions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No models available for this project.</p>
      ) : (
        <Select
          value={radixSelectValue}
          onValueChange={(selectValue) => {
            if (selectValue === INVALID_SELECTION_VALUE) return
            const hit = catalogRows.find(
              (row) => (row.configId ?? row.providerModelId) === selectValue,
            )
            onChange({
              [modelKeys.configIdKey]: hit?.configId ?? null,
              [modelKeys.modelKey]: hit?.providerModelId ?? selectValue,
            })
          }}
          disabled={disabled}
        >
          <SelectTrigger id={id} className="text-sm">
            <SelectValue placeholder={`Choose a ${label.toLowerCase()}`} />
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
  )
}

export default function EmbedImagesPanel({
  node,
  editMode,
  setNodes,
  graphContext,
}: EmbedImagesPanelProps) {
  const merged = {
    ...DEFAULTS,
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  }
  const paramsRecord = merged as Record<string, unknown>
  const disabled = !(editMode && setNodes)

  const visionCatalog = useCatalogRows(graphContext, ['generative'])
  const embeddingCatalog = useCatalogRows(graphContext, ['embedding'])

  const patch = (updates: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nds) =>
      (nds as { id: string; data?: Record<string, unknown> }[]).map((n) =>
        n.id === node.id ? { ...n, data: { ...(n.data || {}), ...updates } } : n,
      ),
    )
  }

  const currentPrompt =
    typeof paramsRecord.prompt === 'string' && paramsRecord.prompt.trim()
      ? paramsRecord.prompt
      : String(nodeMetadata.defaultParams?.prompt || '')

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-4">
          <ModelSelect
            id="embed-images-vision-model"
            label="Vision model"
            required
            disabled={disabled}
            modelKeys={VISION_MODEL_KEYS}
            paramsRecord={paramsRecord}
            catalogRows={visionCatalog.rows}
            catalogLoading={visionCatalog.loading}
            catalogError={visionCatalog.error}
            nodeData={(node.data || {}) as Record<string, unknown>}
            onChange={patch}
          />
          <ModelSelect
            id="embed-images-embedding-model"
            label="Embedding model"
            required
            disabled={disabled}
            modelKeys={EMBEDDING_MODEL_KEYS}
            paramsRecord={paramsRecord}
            catalogRows={embeddingCatalog.rows}
            catalogLoading={embeddingCatalog.loading}
            catalogError={embeddingCatalog.error}
            nodeData={(node.data || {}) as Record<string, unknown>}
            onChange={patch}
          />
          <div className="space-y-2">
            <Label htmlFor="embed-images-prompt" className="text-sm font-medium">
              Description prompt
            </Label>
            {disabled ? (
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{currentPrompt}</p>
            ) : (
              <Textarea
                id="embed-images-prompt"
                value={currentPrompt}
                onChange={(e) => patch({ prompt: e.target.value })}
                className="min-h-[120px] text-xs font-mono"
              />
            )}
            <p className="text-xs text-muted-foreground">
              Caption and article text from upstream inputs are added automatically as context.
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
